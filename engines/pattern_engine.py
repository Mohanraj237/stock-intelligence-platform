from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Pattern categories ─────────────────────────────────────────────────────────
PATTERN_CATEGORIES = {
    "Trend Continuation": [
        "Bull Flag", "Bear Flag", "Ascending Channel", "Descending Channel",
        "Rectangle Breakout", "Descending Wedge Breakout", "Rising Wedge",
    ],
    "Reversal": [
        "Double Bottom", "Double Top", "Head & Shoulders",
        "Inverse Head & Shoulders", "Rounding Bottom", "V Bottom",
    ],
    "Candlestick": [
        "Hammer", "Shooting Star", "Bullish Engulfing", "Bearish Engulfing",
        "Morning Star", "Evening Star", "Doji at Support", "Doji at Resistance",
    ],
    "Breakout / Momentum": [
        "52W High Breakout", "Volume Breakout", "Gap Up with Volume",
        "Cup & Handle", "Trendline Breakout", "Symmetrical Triangle Breakout",
    ],
    "Mean Reversion": [
        "Pullback to 20 EMA", "Pullback to 50 DMA",
        "Oversold Bounce", "Overbought Reversal",
    ],
    "Support & Resistance": [
        "Ascending Triangle", "Descending Triangle",
        "Near 52W High", "Near 52W Low",
    ],
    "Volume": [
        "Accumulation Phase", "Distribution Phase",
        "Volume Dry Up", "Volume Surge on Breakout",
    ],
}

ALL_PATTERN_NAMES = [p for pats in PATTERN_CATEGORIES.values() for p in pats]

CATEGORY_OF = {p: cat for cat, pats in PATTERN_CATEGORIES.items() for p in pats}


@dataclass
class ChartPattern:
    name: str
    category: str
    direction: str           # Bullish / Bearish / Neutral
    confidence: int          # 0-100
    status: str              # Forming / Confirmed / Breakout / Failed
    description: str
    key_levels: dict = field(default_factory=dict)   # support, resistance, target, stop
    points: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)  # trendlines for chart overlay
    zones: list[dict] = field(default_factory=list)  # shaded zones
    detected_at: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["is_bullish"] = self.direction == "Bullish"
        d["is_bearish"] = self.direction == "Bearish"
        return d


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pt(idx_val, price: float) -> dict:
    return {"date": str(pd.to_datetime(idx_val).date()), "price": round(float(price), 2)}


def _line(x0, y0, x1, y1, color: str = "#94a3b8", dash: str = "dot") -> dict:
    return {"x0": str(pd.to_datetime(x0).date()), "y0": round(float(y0), 2),
            "x1": str(pd.to_datetime(x1).date()), "y1": round(float(y1), 2),
            "color": color, "dash": dash}


def _hline(x0, x1, price: float, color: str, dash: str = "dash") -> dict:
    return _line(x0, price, x1, price, color, dash)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _swing_points(df: pd.DataFrame, col: str, mode: str, window: int = 3) -> list[tuple]:
    vals = df[col].to_numpy(dtype=float)
    pts = []
    for i in range(window, len(df) - window):
        slc = vals[i - window: i + window + 1]
        v = vals[i]
        if mode == "high" and v == np.nanmax(slc):
            pts.append((df.index[i], v))
        elif mode == "low" and v == np.nanmin(slc):
            pts.append((df.index[i], v))
    return pts


def _trendline(xs: list, ys: list) -> tuple[float, float]:
    """Return (slope, intercept) of linear fit. xs = integer positions."""
    if len(xs) < 2:
        return 0.0, float(ys[0]) if ys else 0.0
    coeffs = np.polyfit(xs, ys, 1)
    return float(coeffs[0]), float(coeffs[1])


def _slope_pct(slope: float, mean_price: float) -> float:
    """Slope as % of mean price per bar."""
    return (slope / mean_price * 100) if mean_price else 0.0


def _candle_body(o, c): return abs(c - o)
def _candle_range(h, l): return max(h - l, 0.0001)
def _upper_wick(o, c, h): return h - max(o, c)
def _lower_wick(o, c, l): return min(o, c) - l


# ── Trend Continuation ─────────────────────────────────────────────────────────

def _detect_channel(df, swing_highs, swing_lows, close, high, low) -> list[ChartPattern]:
    patterns = []
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return patterns

    # Use last 4 swing points each
    sh = swing_highs[-4:]
    sl = swing_lows[-4:]

    sh_xs = list(range(len(sh)))
    sl_xs = list(range(len(sl)))
    sh_ys = [x[1] for x in sh]
    sl_ys = [x[1] for x in sl]

    h_slope, h_int = _trendline(sh_xs, sh_ys)
    l_slope, l_int = _trendline(sl_xs, sl_ys)

    mean_price = float(close.mean())
    h_slope_pct = _slope_pct(h_slope, mean_price)
    l_slope_pct = _slope_pct(l_slope, mean_price)

    latest = float(close.iloc[-1])
    x0_date = sh[0][0]; x1_date = df.index[-1]
    lx0_date = sl[0][0]

    # Extrapolate trendlines to latest bar
    n_h = len(df) - 1 - list(df.index).index(sh[-1][0]) if sh[-1][0] in df.index else 0
    n_l = len(df) - 1 - list(df.index).index(sl[-1][0]) if sl[-1][0] in df.index else 0
    upper_now = sh_ys[-1] + h_slope * n_h * (len(sh_xs) / max(len(df), 1))
    lower_now = sl_ys[-1] + l_slope * n_l * (len(sl_xs) / max(len(df), 1))

    slope_diff = abs(h_slope_pct - l_slope_pct)
    both_rise = h_slope_pct > 0.05 and l_slope_pct > 0.05
    both_fall = h_slope_pct < -0.05 and l_slope_pct < -0.05
    both_flat = abs(h_slope_pct) < 0.08 and abs(l_slope_pct) < 0.08
    converging = h_slope_pct < 0 and l_slope_pct > 0
    asc_wedge = h_slope_pct > 0 and l_slope_pct > 0 and l_slope_pct > h_slope_pct + 0.1
    desc_wedge = h_slope_pct < 0 and l_slope_pct < 0 and h_slope_pct > l_slope_pct + 0.1

    tl_high = _line(sh[0][0], sh_ys[0], df.index[-1], upper_now, "#f59e0b", "solid")
    tl_low  = _line(sl[0][0], sl_ys[0], df.index[-1], lower_now, "#f59e0b", "solid")

    if both_rise and slope_diff < 0.25:
        breakout = latest > upper_now * 1.01
        conf = 78 if breakout else 68
        status = "Breakout" if breakout else "Forming"
        desc = f"Parallel rising channel: upper ≈ ₹{upper_now:.2f}, lower ≈ ₹{lower_now:.2f}."
        if breakout:
            desc += f" Price broke above upper channel at ₹{latest:.2f}!"
        patterns.append(ChartPattern("Ascending Channel", "Trend Continuation", "Bullish", conf, status, desc,
            {"resistance": round(upper_now, 2), "support": round(lower_now, 2),
             "target": round(upper_now + (upper_now - lower_now), 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_high, tl_low]))

    elif both_fall and slope_diff < 0.25:
        breakdown = latest < lower_now * 0.99
        bounce = latest > upper_now * 0.98
        conf = 74 if breakdown else (72 if bounce else 66)
        status = "Breakdown" if breakdown else ("Breakout" if bounce else "Forming")
        direction = "Bearish" if not bounce else "Bullish"
        desc = f"Parallel falling channel: upper ≈ ₹{upper_now:.2f}, lower ≈ ₹{lower_now:.2f}."
        if bounce:
            desc += f" Price breaking above channel — potential reversal breakout!"
        patterns.append(ChartPattern("Descending Channel", "Trend Continuation",
            direction, conf, status, desc,
            {"resistance": round(upper_now, 2), "support": round(lower_now, 2),
             "target": round(lower_now - (upper_now - lower_now), 2) if breakdown else round(sh_ys[0], 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_high, tl_low]))

    if desc_wedge:
        # Descending wedge (converging downward lines) — bullish reversal
        breakout = latest > upper_now
        conf = 76 if breakout else 64
        desc = f"Descending wedge: falling trendlines converging. Breakout above ₹{upper_now:.2f} is bullish."
        patterns.append(ChartPattern("Descending Wedge Breakout", "Trend Continuation",
            "Bullish", conf, "Breakout" if breakout else "Forming",
            desc, {"resistance": round(upper_now, 2), "support": round(lower_now, 2),
                   "target": round(sh_ys[0], 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_high, tl_low]))

    if asc_wedge:
        # Rising wedge (converging upward lines) — bearish reversal
        breakdown = latest < lower_now
        conf = 72 if breakdown else 62
        desc = f"Rising wedge: price narrowing upward. Breakdown below ₹{lower_now:.2f} is bearish."
        patterns.append(ChartPattern("Rising Wedge", "Trend Continuation",
            "Bearish", conf, "Breakdown" if breakdown else "Forming",
            desc, {"resistance": round(upper_now, 2), "support": round(lower_now, 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_high, tl_low]))

    return patterns


def _detect_flag(df, close, high, low, vol) -> list[ChartPattern]:
    patterns = []
    if len(df) < 30:
        return patterns

    avg_vol = float(vol.mean()) if float(vol.sum()) > 0 else 0

    # Check for prior sharp move (flagpole) in last 5-15 bars
    for pole_bars in (10, 15, 20):
        if len(df) < pole_bars + 10:
            continue
        pole = df.iloc[-(pole_bars + 10): -10]
        flag = df.tail(10)
        pole_move = (float(pole["Close"].iloc[-1]) - float(pole["Close"].iloc[0])) / max(float(pole["Close"].iloc[0]), 1) * 100

        if abs(pole_move) < 8:
            continue  # Not a sharp enough flagpole

        flag_range = float(flag["High"].max() - flag["Low"].min()) / max(float(flag["Close"].mean()), 1) * 100
        flag_slope = np.polyfit(range(len(flag)), flag["Close"].astype(float).values, 1)[0]
        flag_slope_pct = _slope_pct(flag_slope, float(flag["Close"].mean()))

        if flag_range < 5 and abs(flag_slope_pct) < 0.3:  # Tight consolidation
            if pole_move > 8:  # Bull flag
                conf = min(88, int(72 + min(16, abs(pole_move) * 0.5)))
                target = float(close.iloc[-1]) * (1 + pole_move / 100)
                desc = f"Flagpole rise: {pole_move:.1f}%. Flag consolidation: {flag_range:.1f}% range. Target: ₹{target:.2f}."
                patterns.append(ChartPattern("Bull Flag", "Trend Continuation", "Bullish", conf, "Forming",
                    desc, {"support": round(float(flag["Low"].min()), 2),
                           "resistance": round(float(flag["High"].max()), 2), "target": round(target, 2)},
                    [_pt(pole.index[-1], float(pole["Close"].iloc[-1])),
                     _pt(flag.index[-1], float(close.iloc[-1]))]))
            elif pole_move < -8:  # Bear flag
                conf = min(85, int(70 + min(15, abs(pole_move) * 0.5)))
                target = float(close.iloc[-1]) * (1 + pole_move / 100)
                desc = f"Flagpole fall: {pole_move:.1f}%. Flag bounce: {flag_range:.1f}% range. Target: ₹{target:.2f}."
                patterns.append(ChartPattern("Bear Flag", "Trend Continuation", "Bearish", conf, "Forming",
                    desc, {"support": round(float(flag["Low"].min()), 2),
                           "resistance": round(float(flag["High"].max()), 2), "target": round(target, 2)},
                    [_pt(pole.index[-1], float(pole["Close"].iloc[-1])),
                     _pt(flag.index[-1], float(close.iloc[-1]))]))
        break

    return patterns


def _detect_rectangle(df, swing_highs, swing_lows, close) -> list[ChartPattern]:
    patterns = []
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return patterns

    recent_sh = [x[1] for x in swing_highs[-4:]]
    recent_sl = [x[1] for x in swing_lows[-4:]]

    res_level = np.mean(recent_sh)
    sup_level = np.mean(recent_sl)
    res_range = (max(recent_sh) - min(recent_sh)) / max(res_level, 1) * 100
    sup_range = (max(recent_sl) - min(recent_sl)) / max(sup_level, 1) * 100
    box_height = (res_level - sup_level) / max(sup_level, 1) * 100

    latest = float(close.iloc[-1])

    if res_range < 4 and sup_range < 4 and 3 < box_height < 30:
        breakout = latest > res_level * 1.01
        breakdown = latest < sup_level * 0.99
        direction = "Bullish" if breakout else ("Bearish" if breakdown else "Neutral")
        status = "Breakout" if breakout else ("Breakdown" if breakdown else "Forming")
        conf = 80 if (breakout or breakdown) else 64
        target = res_level + (res_level - sup_level) if breakout else sup_level - (res_level - sup_level)
        desc = f"Rectangle: resistance ≈ ₹{res_level:.2f}, support ≈ ₹{sup_level:.2f} ({box_height:.1f}% box)."
        if breakout:
            desc += f" Breakout confirmed! Target: ₹{target:.2f}."
        elif breakdown:
            desc += f" Breakdown confirmed! Target: ₹{target:.2f}."

        x0 = swing_lows[-4][0] if len(swing_lows) >= 4 else df.index[0]
        x1 = df.index[-1]
        patterns.append(ChartPattern("Rectangle Breakout", "Trend Continuation", direction, conf, status,
            desc, {"support": round(sup_level, 2), "resistance": round(res_level, 2), "target": round(target, 2)},
            [_pt(swing_highs[-1][0], swing_highs[-1][1]), _pt(swing_lows[-1][0], swing_lows[-1][1])],
            [_hline(x0, x1, res_level, "#ef4444"), _hline(x0, x1, sup_level, "#22c55e")]))

    return patterns


# ── Reversal ───────────────────────────────────────────────────────────────────

def _detect_double_tops_bottoms(df, swing_highs, swing_lows, close) -> list[ChartPattern]:
    patterns = []
    latest = float(close.iloc[-1])

    # Double Bottom
    if len(swing_lows) >= 2:
        la, lb = swing_lows[-2], swing_lows[-1]
        diff = abs(la[1] - lb[1]) / max((la[1] + lb[1]) / 2, 1) * 100
        # Get the peak between the two lows
        idx_a = list(df.index).index(la[0]) if la[0] in df.index else 0
        idx_b = list(df.index).index(lb[0]) if lb[0] in df.index else 0
        if idx_a < idx_b and idx_b - idx_a > 5:
            between = df.iloc[idx_a:idx_b]
            neckline = float(between["High"].max()) if len(between) else (la[1] + lb[1]) / 2
            if diff < 4:  # Within 4%
                confirmed = latest > neckline
                conf = 82 if confirmed else 70
                target = neckline + (neckline - min(la[1], lb[1]))
                desc = f"Two lows at ₹{min(la[1], lb[1]):.2f} ({diff:.1f}% apart). Neckline: ₹{neckline:.2f}."
                if confirmed:
                    desc += f" Confirmed breakout! Target: ₹{target:.2f}."
                x0 = la[0]; x1 = df.index[-1]
                patterns.append(ChartPattern("Double Bottom", "Reversal", "Bullish", conf,
                    "Confirmed" if confirmed else "Forming", desc,
                    {"support": round(min(la[1], lb[1]), 2), "resistance": round(neckline, 2), "target": round(target, 2)},
                    [_pt(la[0], la[1]), _pt(lb[0], lb[1])],
                    [_hline(x0, x1, neckline, "#22c55e")]))

    # Double Top
    if len(swing_highs) >= 2:
        ha, hb = swing_highs[-2], swing_highs[-1]
        diff = abs(ha[1] - hb[1]) / max((ha[1] + hb[1]) / 2, 1) * 100
        idx_a = list(df.index).index(ha[0]) if ha[0] in df.index else 0
        idx_b = list(df.index).index(hb[0]) if hb[0] in df.index else 0
        if idx_a < idx_b and idx_b - idx_a > 5:
            between = df.iloc[idx_a:idx_b]
            neckline = float(between["Low"].min()) if len(between) else (ha[1] + hb[1]) / 2
            if diff < 4:
                confirmed = latest < neckline
                conf = 80 if confirmed else 68
                target = neckline - (max(ha[1], hb[1]) - neckline)
                desc = f"Two peaks at ₹{max(ha[1], hb[1]):.2f} ({diff:.1f}% apart). Neckline: ₹{neckline:.2f}."
                if confirmed:
                    desc += f" Confirmed breakdown! Target: ₹{target:.2f}."
                x0 = ha[0]; x1 = df.index[-1]
                patterns.append(ChartPattern("Double Top", "Reversal", "Bearish", conf,
                    "Confirmed" if confirmed else "Forming", desc,
                    {"resistance": round(max(ha[1], hb[1]), 2), "support": round(neckline, 2), "target": round(target, 2)},
                    [_pt(ha[0], ha[1]), _pt(hb[0], hb[1])],
                    [_hline(x0, x1, neckline, "#ef4444")]))

    return patterns


def _detect_hs(df, swing_highs, swing_lows, close) -> list[ChartPattern]:
    patterns = []
    if len(swing_highs) < 3:
        return patterns

    ls, head, rs = swing_highs[-3], swing_highs[-2], swing_highs[-1]
    latest = float(close.iloc[-1])

    # Standard H&S (bearish)
    if head[1] > ls[1] * 1.02 and head[1] > rs[1] * 1.02:
        shoulder_diff = abs(ls[1] - rs[1]) / max(ls[1], 1) * 100
        if shoulder_diff < 8:
            neckline = float(close.tail(30).min())
            confirmed = latest < neckline
            conf = 78 if confirmed else 68
            target = neckline - (head[1] - neckline)
            desc = f"Left shoulder ₹{ls[1]:.2f}, head ₹{head[1]:.2f}, right shoulder ₹{rs[1]:.2f}. Neckline ≈ ₹{neckline:.2f}."
            if confirmed:
                desc += f" Bearish breakdown confirmed! Target: ₹{target:.2f}."
            x0 = ls[0]; x1 = df.index[-1]
            patterns.append(ChartPattern("Head & Shoulders", "Reversal", "Bearish", conf,
                "Confirmed" if confirmed else "Forming", desc,
                {"resistance": round(head[1], 2), "support": round(neckline, 2), "target": round(target, 2)},
                [_pt(ls[0], ls[1]), _pt(head[0], head[1]), _pt(rs[0], rs[1])],
                [_hline(x0, x1, neckline, "#ef4444")]))

    # Inverse H&S (bullish) — using swing lows
    if len(swing_lows) >= 3:
        lls, lhead, lrs = swing_lows[-3], swing_lows[-2], swing_lows[-1]
        if lhead[1] < lls[1] * 0.98 and lhead[1] < lrs[1] * 0.98:
            shoulder_diff = abs(lls[1] - lrs[1]) / max(lls[1], 1) * 100
            if shoulder_diff < 8:
                neckline = float(close.tail(30).max())
                confirmed = latest > neckline
                conf = 78 if confirmed else 68
                target = neckline + (neckline - lhead[1])
                desc = f"Inv H&S: shoulders ≈ ₹{max(lls[1], lrs[1]):.2f}, head ₹{lhead[1]:.2f}. Neckline ≈ ₹{neckline:.2f}."
                if confirmed:
                    desc += f" Bullish breakout! Target: ₹{target:.2f}."
                x0 = lls[0]; x1 = df.index[-1]
                patterns.append(ChartPattern("Inverse Head & Shoulders", "Reversal", "Bullish", conf,
                    "Confirmed" if confirmed else "Forming", desc,
                    {"support": round(lhead[1], 2), "resistance": round(neckline, 2), "target": round(target, 2)},
                    [_pt(lls[0], lls[1]), _pt(lhead[0], lhead[1]), _pt(lrs[0], lrs[1])],
                    [_hline(x0, x1, neckline, "#22c55e")]))

    return patterns


def _detect_rounding_v(df, close, low) -> list[ChartPattern]:
    patterns = []
    if len(df) < 60:
        return patterns

    seg = close.tail(60).astype(float)
    thirds = np.array_split(seg, 3)
    m0, m1, m2 = float(thirds[0].mean()), float(thirds[1].mean()), float(thirds[2].mean())

    # Rounding Bottom: first third > middle, middle < last third
    if m0 > m1 and m2 > m1 and (m0 - m1) / max(m1, 1) > 0.03:
        conf = 68
        desc = f"Gradual U-shape: early avg ₹{m0:.2f} → trough ₹{m1:.2f} → recovery ₹{m2:.2f}."
        patterns.append(ChartPattern("Rounding Bottom", "Reversal", "Bullish", conf, "Forming", desc,
            {"support": round(m1, 2), "target": round(m0, 2)},
            [_pt(seg.index[0], m0), _pt(seg.index[len(seg)//2], m1), _pt(seg.index[-1], m2)]))

    # V Bottom: sharp drop then sharp recovery
    if len(df) >= 30:
        recent = close.tail(30).astype(float)
        bottom_idx = int(recent.values.argmin())
        if 5 < bottom_idx < 25:
            drop = (float(recent.iloc[0]) - float(recent.iloc[bottom_idx])) / max(float(recent.iloc[0]), 1) * 100
            recovery = (float(recent.iloc[-1]) - float(recent.iloc[bottom_idx])) / max(float(recent.iloc[bottom_idx]), 1) * 100
            if drop > 10 and recovery > 8:
                conf = 72
                desc = f"Sharp drop of {drop:.1f}% then recovery of {recovery:.1f}% — V-shaped reversal."
                patterns.append(ChartPattern("V Bottom", "Reversal", "Bullish", conf, "Confirmed", desc,
                    {"support": round(float(recent.iloc[bottom_idx]), 2), "target": round(float(recent.iloc[0]), 2)},
                    [_pt(recent.index[0], float(recent.iloc[0])),
                     _pt(recent.index[bottom_idx], float(recent.iloc[bottom_idx])),
                     _pt(recent.index[-1], float(recent.iloc[-1]))]))

    return patterns


# ── Candlestick ────────────────────────────────────────────────────────────────

def _detect_candlestick(df, close, high, low, vol) -> list[ChartPattern]:
    patterns = []
    if len(df) < 3:
        return patterns

    o = df["Open"].astype(float)
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)

    latest_support = float(low.tail(30).min())
    latest_resist  = float(high.tail(30).max())
    at_support = float(c.iloc[-1]) < latest_support * 1.03
    at_resist  = float(c.iloc[-1]) > latest_resist * 0.97
    avg_vol = float(vol.tail(20).mean()) if float(vol.sum()) > 0 else 0

    def _add(name, direction, conf, desc, extra_conf=0):
        final_conf = min(92, conf + extra_conf)
        cat = "Candlestick"
        patterns.append(ChartPattern(name, cat, direction, final_conf, "Confirmed", desc,
            {}, [_pt(df.index[-1], float(c.iloc[-1]))]))

    # Last bar
    o1, c1, h1, l1 = float(o.iloc[-1]), float(c.iloc[-1]), float(h.iloc[-1]), float(l.iloc[-1])
    body1 = _candle_body(o1, c1)
    rng1  = _candle_range(h1, l1)
    uw1   = _upper_wick(o1, c1, h1)
    lw1   = _lower_wick(o1, c1, l1)
    vol_surge = avg_vol > 0 and float(vol.iloc[-1]) > avg_vol * 1.5

    # Hammer
    if lw1 > body1 * 2 and uw1 < body1 * 0.5 and c1 > o1 - rng1 * 0.3:
        _add("Hammer", "Bullish", 72, f"Long lower wick at ₹{l1:.2f} — buying pressure at lows.", 8 if at_support else 0)

    # Shooting Star
    if uw1 > body1 * 2 and lw1 < body1 * 0.5 and c1 < o1 + rng1 * 0.3:
        _add("Shooting Star", "Bearish", 70, f"Long upper wick at ₹{h1:.2f} — selling pressure at highs.", 8 if at_resist else 0)

    # Doji
    if body1 < rng1 * 0.08 and rng1 > 0:
        if at_support:
            _add("Doji at Support", "Bullish", 62, f"Indecision at support ₹{l1:.2f} — potential reversal up.")
        elif at_resist:
            _add("Doji at Resistance", "Bearish", 62, f"Indecision at resistance ₹{h1:.2f} — potential reversal down.")

    # Engulfing
    if len(df) >= 2:
        o2, c2, h2, l2 = float(o.iloc[-2]), float(c.iloc[-2]), float(h.iloc[-2]), float(l.iloc[-2])
        # Bullish Engulfing
        if c2 < o2 and c1 > o1 and c1 > o2 and o1 < c2 and body1 > _candle_body(o2, c2):
            _add("Bullish Engulfing", "Bullish", 78, f"Bullish bar fully engulfs prior bearish bar — reversal signal.", 6 if vol_surge else 0)
        # Bearish Engulfing
        if c2 > o2 and c1 < o1 and c1 < o2 and o1 > c2 and body1 > _candle_body(o2, c2):
            _add("Bearish Engulfing", "Bearish", 76, f"Bearish bar fully engulfs prior bullish bar — reversal signal.", 6 if vol_surge else 0)

    # Morning Star (3-bar)
    if len(df) >= 3:
        o3, c3 = float(o.iloc[-3]), float(c.iloc[-3])
        o2, c2 = float(o.iloc[-2]), float(c.iloc[-2])
        mid_body = _candle_body(o2, c2)
        if c3 < o3 and mid_body < _candle_body(o3, c3) * 0.5 and c1 > o1 and c1 > (o3 + c3) / 2:
            _add("Morning Star", "Bullish", 80, "Three-candle bullish reversal: down → small → up. Strong buy signal.")

    if len(df) >= 3:
        o3, c3 = float(o.iloc[-3]), float(c.iloc[-3])
        o2, c2 = float(o.iloc[-2]), float(c.iloc[-2])
        mid_body = _candle_body(o2, c2)
        if c3 > o3 and mid_body < _candle_body(o3, c3) * 0.5 and c1 < o1 and c1 < (o3 + c3) / 2:
            _add("Evening Star", "Bearish", 78, "Three-candle bearish reversal: up → small → down. Sell signal.")

    return patterns


# ── Breakout / Momentum ────────────────────────────────────────────────────────

def _detect_breakout_momentum(df, close, high, low, vol) -> list[ChartPattern]:
    patterns = []
    latest = float(close.iloc[-1])
    avg_vol = float(vol.tail(20).mean()) if float(vol.sum()) > 0 else 0
    latest_vol = float(vol.iloc[-1]) if len(vol) else 0
    vol_surge = avg_vol > 0 and latest_vol > avg_vol * 1.5

    # 52W High Breakout
    high_52w = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
    if latest >= high_52w * 0.998:
        conf = min(90, 78 + (8 if vol_surge else 0))
        desc = f"Price at/above 52-week high ₹{high_52w:.2f}! Strong momentum breakout."
        patterns.append(ChartPattern("52W High Breakout", "Breakout / Momentum", "Bullish", conf, "Confirmed",
            desc, {"resistance": round(high_52w, 2)},
            [_pt(df.index[-1], latest)]))

    # Near 52W Low
    low_52w = float(low.tail(252).min()) if len(low) >= 252 else float(low.min())
    near_low = latest <= low_52w * 1.05
    if near_low:
        desc = f"Price within 5% of 52-week low ₹{low_52w:.2f}. Watch for bounce or capitulation."
        patterns.append(ChartPattern("Near 52W Low", "Support & Resistance", "Neutral", 60, "Watch",
            desc, {"support": round(low_52w, 2)},
            [_pt(df.index[-1], latest)]))

    # Volume Surge on Breakout
    if vol_surge:
        prev_high = float(high.tail(20).iloc[:-1].max())
        if latest > prev_high:
            conf = 82
            desc = f"Volume {latest_vol/avg_vol:.1f}x average on price breakout above ₹{prev_high:.2f}. High conviction."
            patterns.append(ChartPattern("Volume Surge on Breakout", "Volume", "Bullish", conf, "Confirmed",
                desc, {"resistance": round(prev_high, 2)},
                [_pt(df.index[-1], latest)]))
        else:
            desc = f"Volume spike {latest_vol/avg_vol:.1f}x average but price not breaking out — watch closely."
            patterns.append(ChartPattern("Volume Breakout", "Breakout / Momentum", "Neutral", 64, "Watch",
                desc, {}, [_pt(df.index[-1], latest)]))

    # Gap Up with Volume
    if len(df) >= 2:
        prev_close = float(close.iloc[-2])
        today_open = float(df["Open"].iloc[-1])
        gap_pct = (today_open - prev_close) / max(prev_close, 1) * 100
        if gap_pct > 2:
            conf = min(85, 68 + int(gap_pct * 2) + (10 if vol_surge else 0))
            desc = f"Gap up of {gap_pct:.1f}% at open. {'Strong volume confirms gap.' if vol_surge else 'Watch for gap fill vs continuation.'}"
            patterns.append(ChartPattern("Gap Up with Volume", "Breakout / Momentum", "Bullish", conf, "Confirmed",
                desc, {"support": round(prev_close, 2)},
                [_pt(df.index[-2], prev_close), _pt(df.index[-1], latest)]))
        elif gap_pct < -2:
            conf = min(82, 66 + int(abs(gap_pct) * 2) + (8 if vol_surge else 0))
            desc = f"Gap down of {abs(gap_pct):.1f}% at open — bearish pressure."
            patterns.append(ChartPattern("Gap Up with Volume", "Breakout / Momentum", "Bearish", conf, "Confirmed",
                desc, {"resistance": round(prev_close, 2)},
                [_pt(df.index[-2], prev_close), _pt(df.index[-1], latest)]))

    # Cup & Handle
    if len(df) >= 90:
        cup = df.tail(90)
        cup_close = cup["Close"].astype(float)
        cup_high_l = float(cup_close.iloc[:15].mean())
        cup_high_r = float(cup_close.iloc[-15:].mean())
        cup_floor  = float(cup_close.iloc[30:60].min())
        depth = (cup_high_l - cup_floor) / max(cup_high_l, 1) * 100
        rim_diff = abs(cup_high_l - cup_high_r) / max(cup_high_l, 1) * 100
        if 10 < depth < 50 and rim_diff < 8 and cup_floor < cup_high_l * 0.92:
            handle = cup_close.iloc[-15:]
            handle_pullback = (float(handle.max()) - float(handle.min())) / max(float(handle.max()), 1) * 100
            is_handle = handle_pullback < 10 and float(handle.iloc[-1]) > float(handle.mean())
            conf = 80 if is_handle else 68
            target = float(cup_close.iloc[-1]) + (cup_high_l - cup_floor)
            desc = f"U-shaped cup: depth {depth:.1f}%, rim diff {rim_diff:.1f}%. {'Handle forming.' if is_handle else 'Awaiting handle.'} Target: ₹{target:.2f}."
            patterns.append(ChartPattern("Cup & Handle", "Breakout / Momentum", "Bullish", conf,
                "Forming" if not is_handle else "Breakout",
                desc, {"support": round(cup_floor, 2), "resistance": round(cup_high_r, 2), "target": round(target, 2)},
                [_pt(cup.index[0], cup_high_l), _pt(cup.index[44], cup_floor), _pt(cup.index[-1], cup_high_r)]))

    return patterns


# ── Triangles (S&R / Breakout) ─────────────────────────────────────────────────

def _detect_triangles(df, swing_highs, swing_lows, close) -> list[ChartPattern]:
    patterns = []
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return patterns

    sh = swing_highs[-4:]
    sl = swing_lows[-4:]
    mean_price = float(close.mean())

    sh_xs = list(range(len(sh)))
    sl_xs = list(range(len(sl)))
    h_slope, _ = _trendline(sh_xs, [x[1] for x in sh])
    l_slope, _ = _trendline(sl_xs, [x[1] for x in sl])
    h_sp = _slope_pct(h_slope, mean_price)
    l_sp = _slope_pct(l_slope, mean_price)
    latest = float(close.iloc[-1])

    tl_h = _line(sh[0][0], sh[0][1], df.index[-1], sh[-1][1] + h_slope * (len(sh) - 1), "#f59e0b")
    tl_l = _line(sl[0][0], sl[0][1], df.index[-1], sl[-1][1] + l_slope * (len(sl) - 1), "#f59e0b")

    # Ascending Triangle: flat highs + rising lows
    h_range_pct = (max(x[1] for x in sh) - min(x[1] for x in sh)) / max(mean_price, 1) * 100
    l_range_pct = (max(x[1] for x in sl) - min(x[1] for x in sl)) / max(mean_price, 1) * 100
    if h_range_pct < 4 and l_sp > 0.1:
        res = np.mean([x[1] for x in sh])
        breakout = latest > res * 1.01
        conf = 80 if breakout else 70
        target = res + (res - sl[-1][1])
        desc = f"Ascending triangle: resistance ₹{res:.2f} tested multiple times, rising support. Target: ₹{target:.2f}."
        patterns.append(ChartPattern("Ascending Triangle", "Support & Resistance", "Bullish", conf,
            "Breakout" if breakout else "Forming", desc,
            {"resistance": round(res, 2), "support": round(sl[-1][1], 2), "target": round(target, 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [_hline(sh[0][0], df.index[-1], res, "#f59e0b"), tl_l]))

    # Descending Triangle: flat lows + falling highs
    if l_range_pct < 4 and h_sp < -0.1:
        sup = np.mean([x[1] for x in sl])
        breakdown = latest < sup * 0.99
        conf = 78 if breakdown else 68
        target = sup - (sh[-1][1] - sup)
        desc = f"Descending triangle: support ₹{sup:.2f} tested multiple times, falling resistance. Target: ₹{target:.2f}."
        patterns.append(ChartPattern("Descending Triangle", "Support & Resistance", "Bearish", conf,
            "Breakdown" if breakdown else "Forming", desc,
            {"support": round(sup, 2), "resistance": round(sh[-1][1], 2), "target": round(target, 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_h, _hline(sl[0][0], df.index[-1], sup, "#f59e0b")]))

    # Symmetrical Triangle: converging
    if h_sp < -0.08 and l_sp > 0.08:
        apex_y = (sh[-1][1] + sl[-1][1]) / 2
        breakout_up = latest > sh[-1][1]
        breakout_dn = latest < sl[-1][1]
        direction = "Bullish" if breakout_up else ("Bearish" if breakout_dn else "Neutral")
        status = "Breakout" if breakout_up or breakout_dn else "Forming"
        conf = 76 if (breakout_up or breakout_dn) else 62
        desc = f"Symmetrical triangle: highs declining, lows rising, converging toward ₹{apex_y:.2f}."
        if breakout_up:
            desc += " Breakout above triangle!"
        elif breakout_dn:
            desc += " Breakdown below triangle!"
        patterns.append(ChartPattern("Symmetrical Triangle Breakout", "Breakout / Momentum", direction, conf, status, desc,
            {"resistance": round(sh[-1][1], 2), "support": round(sl[-1][1], 2)},
            [_pt(sh[-1][0], sh[-1][1]), _pt(sl[-1][0], sl[-1][1])],
            [tl_h, tl_l]))

    return patterns


# ── Mean Reversion ─────────────────────────────────────────────────────────────

def _detect_mean_reversion(df, close, high, low, vol) -> list[ChartPattern]:
    patterns = []
    if len(df) < 50:
        return patterns

    ema20  = _ema(close, 20)
    sma50  = close.rolling(50).mean()
    rsi14  = _rsi(close)

    latest = float(close.iloc[-1])
    e20    = float(ema20.iloc[-1])
    s50    = float(sma50.iloc[-1])
    rsi    = float(rsi14.iloc[-1]) if not np.isnan(float(rsi14.iloc[-1])) else 50

    # Trend is up if price is above both MAs
    uptrend = latest > e20 and latest > s50
    downtrend = latest < e20 and latest < s50

    # Pullback to 20 EMA in uptrend
    prev_above_ema = float(close.iloc[-5]) > float(ema20.iloc[-5])
    touching_ema   = abs(latest - e20) / max(e20, 1) < 0.015
    if uptrend and touching_ema and prev_above_ema:
        conf = 74
        target = latest * 1.05
        desc = f"Pullback to 20 EMA (₹{e20:.2f}) in uptrend — potential bounce entry. Target: ₹{target:.2f}."
        patterns.append(ChartPattern("Pullback to 20 EMA", "Mean Reversion", "Bullish", conf, "Forming",
            desc, {"support": round(e20, 2), "target": round(target, 2)},
            [_pt(df.index[-1], latest)]))

    # Pullback to 50 DMA
    touching_sma50 = abs(latest - s50) / max(s50, 1) < 0.02
    if uptrend and touching_sma50:
        conf = 72
        target = latest * 1.07
        desc = f"Pullback to 50-day SMA (₹{s50:.2f}) in uptrend — stronger support. Target: ₹{target:.2f}."
        patterns.append(ChartPattern("Pullback to 50 DMA", "Mean Reversion", "Bullish", conf, "Forming",
            desc, {"support": round(s50, 2), "target": round(target, 2)},
            [_pt(df.index[-1], latest)]))

    # Oversold Bounce
    if rsi < 35 and latest > float(close.iloc[-3]):  # RSI oversold + starting to bounce
        conf = 70 + (8 if rsi < 25 else 0)
        target = float(sma50.iloc[-1])
        desc = f"RSI = {rsi:.1f} (oversold) with price starting to recover. Mean-reversion bounce to ₹{target:.2f}."
        patterns.append(ChartPattern("Oversold Bounce", "Mean Reversion", "Bullish", conf, "Forming",
            desc, {"support": round(latest, 2), "target": round(target, 2)},
            [_pt(df.index[-1], latest)]))

    # Overbought Reversal
    if rsi > 75 and latest < float(close.iloc[-3]):
        conf = 68
        target = float(sma50.iloc[-1])
        desc = f"RSI = {rsi:.1f} (overbought) with price starting to pull back. Target mean: ₹{target:.2f}."
        patterns.append(ChartPattern("Overbought Reversal", "Mean Reversion", "Bearish", conf, "Forming",
            desc, {"resistance": round(latest, 2), "target": round(target, 2)},
            [_pt(df.index[-1], latest)]))

    return patterns


# ── Volume ─────────────────────────────────────────────────────────────────────

def _detect_volume_patterns(df, close, vol) -> list[ChartPattern]:
    patterns = []
    if len(df) < 20 or float(vol.sum()) == 0:
        return patterns

    avg_vol = float(vol.tail(20).mean())
    latest = float(close.iloc[-1])

    # Compute up/down day volume for last 10 bars
    changes = close.diff().tail(10)
    vols    = vol.tail(10)
    up_vol   = float(vols[changes > 0].mean()) if len(vols[changes > 0]) else 0
    down_vol = float(vols[changes < 0].mean()) if len(vols[changes < 0]) else 0

    if up_vol > down_vol * 1.4:
        desc = f"Up days averaging {up_vol/avg_vol:.1f}x vs down days {down_vol/avg_vol:.1f}x — accumulation pattern."
        patterns.append(ChartPattern("Accumulation Phase", "Volume", "Bullish", 72, "Active",
            desc, {}, [_pt(df.index[-1], latest)]))

    elif down_vol > up_vol * 1.4:
        desc = f"Down days averaging {down_vol/avg_vol:.1f}x vs up days {up_vol/avg_vol:.1f}x — distribution pattern."
        patterns.append(ChartPattern("Distribution Phase", "Volume", "Bearish", 70, "Active",
            desc, {}, [_pt(df.index[-1], latest)]))

    # Volume Dry Up (low volume pullback = bullish in uptrend)
    latest_vol = float(vol.tail(3).mean())
    if latest_vol < avg_vol * 0.5:
        desc = f"Volume dried up to {latest_vol/avg_vol:.0%} of average — low conviction pullback, trend likely to continue."
        patterns.append(ChartPattern("Volume Dry Up", "Volume", "Neutral", 62, "Forming",
            desc, {}, [_pt(df.index[-1], latest)]))

    return patterns


# ── Near S&R ───────────────────────────────────────────────────────────────────

def _detect_sr_levels(df, close, high, low) -> list[ChartPattern]:
    patterns = []
    latest = float(close.iloc[-1])

    # Near 52W High
    high_252 = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
    if high_252 * 0.97 < latest < high_252 * 0.999:
        desc = f"Price within 3% of 52-week high ₹{high_252:.2f} — key resistance watch."
        patterns.append(ChartPattern("Near 52W High", "Support & Resistance", "Bullish", 66, "Watch",
            desc, {"resistance": round(high_252, 2)}, [_pt(df.index[-1], latest)]))

    return patterns


# ── Main detect function ───────────────────────────────────────────────────────

def detect_patterns(history: pd.DataFrame) -> list[dict]:
    """Detect all patterns. Returns sorted list of pattern dicts."""
    df = history.dropna(subset=["Open", "High", "Low", "Close"]).tail(300).copy()
    if len(df) < 30:
        return []

    close = df["Close"].astype(float)
    high  = df["High"].astype(float)
    low   = df["Low"].astype(float)
    vol   = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(0.0, index=df.index)

    swing_highs = _swing_points(df, "High", "high", window=3)[-8:]
    swing_lows  = _swing_points(df, "Low",  "low",  window=3)[-8:]

    all_patterns: list[ChartPattern] = []

    # Run all detectors
    all_patterns += _detect_channel(df, swing_highs, swing_lows, close, high, low)
    all_patterns += _detect_flag(df, close, high, low, vol)
    all_patterns += _detect_rectangle(df, swing_highs, swing_lows, close)
    all_patterns += _detect_double_tops_bottoms(df, swing_highs, swing_lows, close)
    all_patterns += _detect_hs(df, swing_highs, swing_lows, close)
    all_patterns += _detect_rounding_v(df, close, low)
    all_patterns += _detect_candlestick(df, close, high, low, vol)
    all_patterns += _detect_breakout_momentum(df, close, high, low, vol)
    all_patterns += _detect_triangles(df, swing_highs, swing_lows, close)
    all_patterns += _detect_mean_reversion(df, close, high, low, vol)
    all_patterns += _detect_volume_patterns(df, close, vol)
    all_patterns += _detect_sr_levels(df, close, high, low)

    result = sorted([p.as_dict() for p in all_patterns], key=lambda x: x["confidence"], reverse=True)
    ts = time.strftime("%Y-%m-%d %H:%M")
    for r in result:
        r["detected_at"] = ts
    return result
