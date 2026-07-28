"""
Pattern Registry — unified detection engine for the live F&O scanner.

Coverage:
  Tier 1: Candlesticks (21 patterns), Price Action (5), Volume (6)
  Tier 2: Classic chart patterns (19)
  Tier 3: Wyckoff experimental (2, gated)

Architecture:
  Each detector is a pure function: (pd.DataFrame) -> PatternResult | None
  run_detectors() is the single entry point per symbol/timeframe.
  best_for_confluence() selects the Category-4 trigger for the confluence scorer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Return type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatternResult:
    name: str
    family: str        # candlestick | price_action | volume | chart | harmonic
    tier: int          # 1 | 2 | 3
    direction: str     # bullish | bearish | neutral
    strength: int      # 1 weak | 2 medium | 3 strong
    confidence: float  # 0.0–1.0
    key_levels: dict   # e.g. {"neckline": 100, "target": 110, "stop": 95}
    span_bars: int
    state: str         # "forming" | "confirmed"
    timeframe: str = ""

    @property
    def points(self) -> int:
        return {1: 8, 2: 16, 3: 25}.get(self.strength, 0)

    def as_dict(self) -> dict:
        return {
            "name":       self.name,
            "family":     self.family,
            "tier":       self.tier,
            "direction":  self.direction,
            "strength":   self.strength,
            "confidence": round(self.confidence, 3),
            "key_levels": self.key_levels,
            "span_bars":  self.span_bars,
            "state":      self.state,
            "timeframe":  self.timeframe,
        }


@dataclass
class RegistryEntry:
    name: str
    family: str
    tier: int
    direction_bias: str
    valid_timeframes: list[str]
    min_bars: int
    detector_fn: Callable[[pd.DataFrame], PatternResult | None]
    needs_confirmation: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Shared micro-helpers (inline — no module import needed)
# ─────────────────────────────────────────────────────────────────────────────

def _sf(v) -> float:
    try:
        f = float(v)
        return 0.0 if (f != f or abs(f) == float("inf")) else f
    except Exception:
        return 0.0

def _body(o: float, c: float) -> float:
    return abs(c - o)

def _uw(o: float, c: float, h: float) -> float:
    return h - max(o, c)

def _lw(o: float, c: float, l: float) -> float:
    return min(o, c) - l

def _rng(h: float, l: float) -> float:
    return max(h - l, 1e-10)

def _bull(o: float, c: float) -> bool:
    return c > o

def _bear(o: float, c: float) -> bool:
    return c < o

def _swing_pts(df: pd.DataFrame, col: str, mode: str, w: int = 3) -> list[tuple]:
    vals = df[col].to_numpy(dtype=float)
    pts: list[tuple] = []
    for i in range(w, len(df) - w):
        slc = vals[i - w: i + w + 1]
        v = vals[i]
        if mode == "high" and v == np.nanmax(slc):
            pts.append((df.index[i], v))
        elif mode == "low" and v == np.nanmin(slc):
            pts.append((df.index[i], v))
    return pts

def _slope(xs, ys) -> float:
    if len(xs) < 2:
        return 0.0
    return float(np.polyfit(xs, ys, 1)[0])

def _has_vol(df: pd.DataFrame) -> bool:
    return "volume" in df.columns and float(df["volume"].tail(20).sum()) > 0

def _break_status(cls: "pd.Series", level: float, above: bool) -> str:
    """
    Classify price vs. `level` (above it if above=True, else below) as one of:
      "forming" — hasn't crossed yet (still a valid setup to watch)
      "fresh"   — crossed, and did so within the last few bars (a real signal)
      "stale"   — crossed a while ago; price has just stayed beyond the level
                  since — not a new event, shouldn't keep re-firing every bar.
    """
    n = len(cls)
    lookback = min(_BREAKOUT_RECENCY_BARS, n - 1)
    now_val    = float(cls.iloc[-1])
    recent_val = float(cls.iloc[-1 - lookback])
    crossed_now    = now_val > level    if above else now_val < level
    crossed_recent = recent_val > level if above else recent_val < level
    if not crossed_now:
        return "forming"
    return "fresh" if not crossed_recent else "stale"


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Candlesticks: single bar
# ─────────────────────────────────────────────────────────────────────────────

def _det_hammer(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    b = _body(o, cl); lw = _lw(o, cl, l); uw = _uw(o, cl, h)
    if b == 0 or lw < 2.0 * b or uw >= b:
        return None
    ratio = lw / b
    str_ = 3 if ratio >= 3 else 2
    conf = min(0.90, 0.55 + (ratio - 2) * 0.10)
    if len(df) >= 6:
        prev = df.iloc[-6:-1]["close"].astype(float)
        if float(prev.iloc[0]) > float(prev.iloc[-1]):
            conf = min(0.95, conf + 0.05)
    return PatternResult("Hammer", "candlestick", 1, "bullish", str_, conf,
                         {"stop": round(l, 2)}, 1, "confirmed")


def _det_inverted_hammer(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    b = _body(o, cl); uw = _uw(o, cl, h); lw = _lw(o, cl, l)
    if b == 0 or uw < 2.0 * b or lw >= b:
        return None
    ratio = uw / b
    str_ = 3 if ratio >= 3 else 2
    return PatternResult("Inverted Hammer", "candlestick", 1, "bullish", str_,
                         min(0.80, 0.50 + (ratio - 2) * 0.08),
                         {"stop": round(l, 2)}, 1, "confirmed")


def _det_dragonfly_doji(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.08 or _lw(o, cl, l) < r * 0.5 or _uw(o, cl, h) > r * 0.1:
        return None
    return PatternResult("Dragonfly Doji", "candlestick", 1, "bullish", 2, 0.65,
                         {"stop": round(l, 2)}, 1, "confirmed")


def _det_hanging_man(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 6:
        return None
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    b = _body(o, cl); lw = _lw(o, cl, l); uw = _uw(o, cl, h)
    if b == 0 or lw < 2.0 * b or uw >= b:
        return None
    prev = df.iloc[-6:-1]["close"].astype(float)
    if float(prev.iloc[0]) >= float(prev.iloc[-1]):  # must be in uptrend
        return None
    return PatternResult("Hanging Man", "candlestick", 1, "bearish", 2, 0.62,
                         {"stop": round(h, 2)}, 1, "confirmed")


def _det_shooting_star(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    b = _body(o, cl); uw = _uw(o, cl, h); lw = _lw(o, cl, l)
    if b == 0 or uw < 2.0 * b or lw >= b:
        return None
    ratio = uw / b
    str_ = 3 if ratio >= 3 else 2
    return PatternResult("Shooting Star", "candlestick", 1, "bearish", str_,
                         min(0.88, 0.55 + (ratio - 2) * 0.10),
                         {"stop": round(h, 2)}, 1, "confirmed")


def _det_gravestone_doji(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.08 or _uw(o, cl, h) < r * 0.5 or _lw(o, cl, l) > r * 0.1:
        return None
    return PatternResult("Gravestone Doji", "candlestick", 1, "bearish", 2, 0.65,
                         {"stop": round(h, 2)}, 1, "confirmed")


def _det_doji(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.08 or r == 0:
        return None
    # skip if already matched by dragonfly/gravestone/long-legged
    lw = _lw(o, cl, l); uw = _uw(o, cl, h)
    if lw > r * 0.5 or uw > r * 0.5:
        return None  # specialised doji — handled separately
    return PatternResult("Doji", "candlestick", 1, "neutral", 1, 0.55, {}, 1, "confirmed")


def _det_long_legged_doji(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.08 or r == 0:
        return None
    if _uw(o, cl, h) < r * 0.3 or _lw(o, cl, l) < r * 0.3:
        return None
    return PatternResult("Long-Legged Doji", "candlestick", 1, "neutral", 2, 0.62,
                         {}, 1, "confirmed")


def _det_spinning_top(df: pd.DataFrame) -> PatternResult | None:
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if r == 0:
        return None
    b = _body(o, cl)
    bp = b / r
    if not (0.08 < bp < 0.25):
        return None
    if _uw(o, cl, h) < b * 0.5 or _lw(o, cl, l) < b * 0.5:
        return None
    return PatternResult("Spinning Top", "candlestick", 1, "neutral", 1, 0.55, {}, 1, "confirmed")


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Candlesticks: two bar
# ─────────────────────────────────────────────────────────────────────────────

def _det_bullish_engulfing(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    if not (_bear(po, pc) and _bull(co, cc)):
        return None
    if co > pc or cc < po or _body(co, cc) < _body(po, pc):
        return None
    conf = 0.78
    if _has_vol(df):
        vp, vc = _sf(p.get("volume", 0)), _sf(c.get("volume", 0))
        if vp > 0 and vc > vp * 1.3:
            conf = min(0.92, conf + 0.08)
    return PatternResult("Bullish Engulfing", "candlestick", 1, "bullish", 3, conf,
                         {"stop": round(_sf(c["low"]), 2)}, 2, "confirmed")


def _det_bearish_engulfing(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    if not (_bull(po, pc) and _bear(co, cc)):
        return None
    if co < pc or cc > po or _body(co, cc) < _body(po, pc):
        return None
    conf = 0.76
    if _has_vol(df):
        vp, vc = _sf(p.get("volume", 0)), _sf(c.get("volume", 0))
        if vp > 0 and vc > vp * 1.3:
            conf = min(0.90, conf + 0.08)
    return PatternResult("Bearish Engulfing", "candlestick", 1, "bearish", 3, conf,
                         {"stop": round(_sf(c["high"]), 2)}, 2, "confirmed")


def _det_piercing(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    if not (_bear(po, pc) and _bull(co, cc)):
        return None
    mid = (po + pc) / 2
    if co >= pc or cc <= mid or cc >= po:
        return None
    return PatternResult("Piercing", "candlestick", 1, "bullish", 2, 0.70,
                         {"stop": round(_sf(c["low"]), 2)}, 2, "confirmed")


def _det_dark_cloud_cover(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    if not (_bull(po, pc) and _bear(co, cc)):
        return None
    mid = (po + pc) / 2
    if co <= pc or cc >= mid or cc <= po:
        return None
    return PatternResult("Dark Cloud Cover", "candlestick", 1, "bearish", 2, 0.70,
                         {"stop": round(_sf(c["high"]), 2)}, 2, "confirmed")


def _det_tweezer_bottom(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    pl, cl_ = _sf(p["low"]), _sf(c["low"])
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    avg = (pl + cl_) / 2
    if avg == 0 or abs(pl - cl_) / avg > 0.003:
        return None
    if not (_bear(po, pc) and _bull(co, cc)):
        return None
    return PatternResult("Tweezer Bottom", "candlestick", 1, "bullish", 2, 0.68,
                         {"stop": round(min(pl, cl_), 2)}, 2, "confirmed")


def _det_tweezer_top(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    ph, ch = _sf(p["high"]), _sf(c["high"])
    po, pc = _sf(p["open"]), _sf(p["close"])
    co, cc = _sf(c["open"]), _sf(c["close"])
    avg = (ph + ch) / 2
    if avg == 0 or abs(ph - ch) / avg > 0.003:
        return None
    if not (_bull(po, pc) and _bear(co, cc)):
        return None
    return PatternResult("Tweezer Top", "candlestick", 1, "bearish", 2, 0.68,
                         {"stop": round(max(ph, ch), 2)}, 2, "confirmed")


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Candlesticks: three bar
# ─────────────────────────────────────────────────────────────────────────────

def _det_morning_star(df: pd.DataFrame) -> PatternResult | None:
    c0, c1, c2 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    o0, cl0 = _sf(c0["open"]), _sf(c0["close"])
    o1, cl1 = _sf(c1["open"]), _sf(c1["close"])
    o2, cl2 = _sf(c2["open"]), _sf(c2["close"])
    b0 = _body(o0, cl0)
    if not _bear(o0, cl0) or b0 == 0 or _body(o1, cl1) >= 0.3 * b0:
        return None
    if cl1 >= cl0 or not _bull(o2, cl2) or cl2 <= (o0 + cl0) / 2:
        return None
    return PatternResult("Morning Star", "candlestick", 1, "bullish", 3, 0.80,
                         {"stop": round(_sf(c1["low"]), 2)}, 3, "confirmed")


def _det_evening_star(df: pd.DataFrame) -> PatternResult | None:
    c0, c1, c2 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    o0, cl0 = _sf(c0["open"]), _sf(c0["close"])
    o1, cl1 = _sf(c1["open"]), _sf(c1["close"])
    o2, cl2 = _sf(c2["open"]), _sf(c2["close"])
    b0 = _body(o0, cl0)
    if not _bull(o0, cl0) or b0 == 0 or _body(o1, cl1) >= 0.3 * b0:
        return None
    if cl1 <= cl0 or not _bear(o2, cl2) or cl2 >= (o0 + cl0) / 2:
        return None
    return PatternResult("Evening Star", "candlestick", 1, "bearish", 3, 0.78,
                         {"stop": round(_sf(c1["high"]), 2)}, 3, "confirmed")


def _det_three_white_soldiers(df: pd.DataFrame) -> PatternResult | None:
    rows = [(df.iloc[-3 + i], _sf(df.iloc[-3 + i]["open"]), _sf(df.iloc[-3 + i]["close"]),
             _sf(df.iloc[-3 + i]["high"]), _sf(df.iloc[-3 + i]["low"])) for i in range(3)]
    closes = []
    for _, o, cl, h, l in rows:
        if not _bull(o, cl):
            return None
        b = _body(o, cl)
        if b == 0 or _uw(o, cl, h) > b * 0.3:
            return None
        closes.append(cl)
    if not (closes[2] > closes[1] > closes[0]):
        return None
    return PatternResult("Three White Soldiers", "candlestick", 1, "bullish", 3, 0.82,
                         {"stop": round(rows[0][4], 2)}, 3, "confirmed")


def _det_three_black_crows(df: pd.DataFrame) -> PatternResult | None:
    rows = [(df.iloc[-3 + i], _sf(df.iloc[-3 + i]["open"]), _sf(df.iloc[-3 + i]["close"]),
             _sf(df.iloc[-3 + i]["high"]), _sf(df.iloc[-3 + i]["low"])) for i in range(3)]
    closes = []
    for _, o, cl, h, l in rows:
        if not _bear(o, cl):
            return None
        b = _body(o, cl)
        if b == 0 or _lw(o, cl, l) > b * 0.3:
            return None
        closes.append(cl)
    if not (closes[2] < closes[1] < closes[0]):
        return None
    return PatternResult("Three Black Crows", "candlestick", 1, "bearish", 3, 0.80,
                         {"stop": round(rows[0][3], 2)}, 3, "confirmed")


def _det_abandoned_baby_bull(df: pd.DataFrame) -> PatternResult | None:
    c0, c1, c2 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    o0, cl0 = _sf(c0["open"]), _sf(c0["close"])
    o1, cl1, h1, l1 = _sf(c1["open"]), _sf(c1["close"]), _sf(c1["high"]), _sf(c1["low"])
    o2, cl2 = _sf(c2["open"]), _sf(c2["close"])
    if not _bear(o0, cl0) or _body(o1, cl1) > _rng(h1, l1) * 0.1:
        return None
    if h1 >= cl0 or o2 <= h1 or not _bull(o2, cl2):
        return None
    return PatternResult("Abandoned Baby Bottom", "candlestick", 1, "bullish", 3, 0.85,
                         {"stop": round(l1, 2)}, 3, "confirmed")


def _det_abandoned_baby_bear(df: pd.DataFrame) -> PatternResult | None:
    c0, c1, c2 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    o0, cl0 = _sf(c0["open"]), _sf(c0["close"])
    o1, cl1, h1, l1 = _sf(c1["open"]), _sf(c1["close"]), _sf(c1["high"]), _sf(c1["low"])
    o2, cl2 = _sf(c2["open"]), _sf(c2["close"])
    if not _bull(o0, cl0) or _body(o1, cl1) > _rng(h1, l1) * 0.1:
        return None
    if l1 <= cl0 or o2 >= l1 or not _bear(o2, cl2):
        return None
    return PatternResult("Abandoned Baby Top", "candlestick", 1, "bearish", 3, 0.85,
                         {"stop": round(h1, 2)}, 3, "confirmed")


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Price Action
# ─────────────────────────────────────────────────────────────────────────────

def _det_inside_bar(df: pd.DataFrame) -> PatternResult | None:
    m, ib, br = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    mh, ml = _sf(m["high"]), _sf(m["low"])
    if _sf(ib["high"]) > mh or _sf(ib["low"]) < ml:
        return None
    bc = _sf(br["close"])
    if bc > mh:
        return PatternResult("Inside Bar Breakout", "price_action", 1, "bullish", 2, 0.72,
                             {"breakout": round(mh, 2), "stop": round(ml, 2)}, 3, "confirmed")
    if bc < ml:
        return PatternResult("Inside Bar Breakdown", "price_action", 1, "bearish", 2, 0.72,
                             {"breakout": round(ml, 2), "stop": round(mh, 2)}, 3, "confirmed")
    return PatternResult("Inside Bar", "price_action", 1, "neutral", 1, 0.50,
                         {"resistance": round(mh, 2), "support": round(ml, 2)}, 2, "forming")


def _det_outside_bar(df: pd.DataFrame) -> PatternResult | None:
    p, c = df.iloc[-2], df.iloc[-1]
    ph, pl = _sf(p["high"]), _sf(p["low"])
    ch, cl, co, cc = _sf(c["high"]), _sf(c["low"]), _sf(c["open"]), _sf(c["close"])
    if ch <= ph or cl >= pl:
        return None
    direction = "bullish" if _bull(co, cc) else "bearish"
    return PatternResult("Outside Bar", "price_action", 1, direction, 2, 0.65,
                         {"resistance": round(ch, 2), "support": round(cl, 2)}, 2, "confirmed")


def _det_nr7(df: pd.DataFrame) -> PatternResult | None:
    ranges = [float(df.iloc[-i]["high"]) - float(df.iloc[-i]["low"]) for i in range(1, 8)]
    if ranges[0] != min(ranges):
        return None
    return PatternResult("NR7", "price_action", 1, "neutral", 1, 0.60,
                         {"resistance": round(_sf(df.iloc[-1]["high"]), 2),
                          "support":    round(_sf(df.iloc[-1]["low"]),  2)},
                         7, "confirmed")


def _det_fakey(df: pd.DataFrame) -> PatternResult | None:
    m, ib, bo, rev = df.iloc[-4], df.iloc[-3], df.iloc[-2], df.iloc[-1]
    mh, ml = _sf(m["high"]), _sf(m["low"])
    if _sf(ib["high"]) > mh or _sf(ib["low"]) < ml:
        return None
    boh, bol, boc = _sf(bo["high"]), _sf(bo["low"]), _sf(bo["close"])
    ro, rc = _sf(rev["open"]), _sf(rev["close"])
    if boh > mh and boc < mh and _bear(ro, rc):
        return PatternResult("Fakey", "price_action", 1, "bearish", 2, 0.73,
                             {"stop": round(boh, 2), "support": round(ml, 2)}, 4, "confirmed")
    if bol < ml and boc > ml and _bull(ro, rc):
        return PatternResult("Fakey", "price_action", 1, "bullish", 2, 0.73,
                             {"stop": round(bol, 2), "resistance": round(mh, 2)}, 4, "confirmed")
    return None


def _det_breakout_retest(df: pd.DataFrame) -> PatternResult | None:
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    curr  = float(close.iloc[-1])
    prior_res = float(high.iloc[-15:-5].max())
    prior_sup = float(low.iloc[-15:-5].min())
    # Bullish: broke above prior resistance, pulled back near it, now bouncing
    if curr > prior_res:
        rt_low = float(low.iloc[-5:].min())
        if prior_res * 0.97 <= rt_low <= prior_res * 1.02 and float(close.iloc[-1]) > float(close.iloc[-2]):
            return PatternResult("Breakout Retest", "price_action", 1, "bullish", 2, 0.75,
                                 {"breakout": round(prior_res, 2),
                                  "stop":     round(rt_low * 0.99, 2)}, 15, "confirmed")
    # Bearish: broke below prior support, pulled back near it, now falling
    if curr < prior_sup:
        rt_high = float(high.iloc[-5:].max())
        if prior_sup * 0.98 <= rt_high <= prior_sup * 1.03 and float(close.iloc[-1]) < float(close.iloc[-2]):
            return PatternResult("Breakdown Retest", "price_action", 1, "bearish", 2, 0.75,
                                 {"breakout": round(prior_sup, 2),
                                  "stop":     round(rt_high * 1.01, 2)}, 15, "confirmed")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Volume
# ─────────────────────────────────────────────────────────────────────────────

def _det_vol_expansion_breakout(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol   = df["volume"].astype(float)
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    avg_v = float(vol.iloc[-21:-1].mean())
    if avg_v <= 0:
        return None
    rel_v = float(vol.iloc[-1]) / avg_v
    if rel_v < 1.8:
        return None
    prev_h = float(high.iloc[-21:-1].max())
    if float(close.iloc[-1]) <= prev_h * 0.99:
        return None
    conf = min(0.90, 0.65 + (rel_v - 1.8) * 0.05)
    return PatternResult("Volume Surge on Breakout", "volume", 1, "bullish",
                         3 if rel_v >= 2.5 else 2, conf,
                         {"resistance": round(prev_h, 2)}, 1, "confirmed")


def _det_vol_dry_up(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol   = df["volume"].astype(float)
    close = df["close"].astype(float)
    avg_v = float(vol.iloc[-21:-1].mean())
    if avg_v <= 0 or float(vol.tail(3).mean()) > avg_v * 0.5:
        return None
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    if float(close.iloc[-1]) < ema20 * 0.99:
        return None
    return PatternResult("Volume Dry Up", "volume", 1, "bullish", 1, 0.62,
                         {"support": round(float(df["low"].iloc[-3:].min()), 2)}, 3, "forming")


def _det_accumulation(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol    = df["volume"].astype(float)
    close  = df["close"].astype(float)
    chg    = close.diff().tail(10)
    vols   = vol.tail(10)
    up_v   = float(vols[chg > 0].mean()) if (chg > 0).any() else 0.0
    dn_v   = float(vols[chg < 0].mean()) if (chg < 0).any() else 0.0
    if up_v <= dn_v * 1.4:
        return None
    return PatternResult("Accumulation Phase", "volume", 1, "bullish", 2, 0.68, {}, 10, "forming")


def _det_distribution(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol   = df["volume"].astype(float)
    close = df["close"].astype(float)
    chg   = close.diff().tail(10)
    vols  = vol.tail(10)
    up_v  = float(vols[chg > 0].mean()) if (chg > 0).any() else 0.0
    dn_v  = float(vols[chg < 0].mean()) if (chg < 0).any() else 0.0
    if dn_v <= up_v * 1.4:
        return None
    return PatternResult("Distribution Phase", "volume", 1, "bearish", 2, 0.68, {}, 10, "forming")


def _det_selling_climax(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol  = df["volume"].astype(float)
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    cls  = df["close"].astype(float)
    avg_v = float(vol.iloc[-21:-1].mean())
    if avg_v <= 0:
        return None
    rel_v = float(vol.iloc[-1]) / avg_v
    if rel_v < 2.5:
        return None
    prev_l = float(low.iloc[-21:-1].min())
    curr_l = float(low.iloc[-1])
    if curr_l >= prev_l:
        return None
    r = float(high.iloc[-1]) - curr_l
    if r > 0 and (float(cls.iloc[-1]) - curr_l) / r > 0.5:
        return PatternResult("Selling Climax", "volume", 1, "bullish", 2,
                             min(0.85, 0.70 + rel_v * 0.02),
                             {"stop": round(curr_l, 2)}, 1, "confirmed")
    return None


def _det_volume_breakdown(df: pd.DataFrame) -> PatternResult | None:
    if not _has_vol(df):
        return None
    vol  = df["volume"].astype(float)
    low  = df["low"].astype(float)
    cls  = df["close"].astype(float)
    avg_v = float(vol.iloc[-21:-1].mean())
    if avg_v <= 0:
        return None
    rel_v = float(vol.iloc[-1]) / avg_v
    if rel_v < 1.8:
        return None
    prev_l = float(low.iloc[-21:-1].min())
    if float(cls.iloc[-1]) >= prev_l:
        return None
    conf = min(0.88, 0.65 + (rel_v - 1.8) * 0.05)
    return PatternResult("Volume Breakdown", "volume", 1, "bearish",
                         3 if rel_v >= 2.5 else 2, conf,
                         {"breakdown": round(prev_l, 2)}, 1, "confirmed")


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — Classic chart patterns
# ─────────────────────────────────────────────────────────────────────────────

def _det_head_and_shoulders(df: pd.DataFrame) -> PatternResult | None:
    sh = _swing_pts(df, "high", "high")[-5:]
    cls = df["close"].astype(float)
    if len(sh) < 3:
        return None
    ls, head, rs = sh[-3], sh[-2], sh[-1]
    if head[1] <= ls[1] * 1.02 or head[1] <= rs[1] * 1.02:
        return None
    if abs(ls[1] - rs[1]) / max(ls[1], 1) * 100 > 8:
        return None
    neckline = float(cls.tail(30).min())
    confirmed = float(cls.iloc[-1]) < neckline
    target    = neckline - (head[1] - neckline)
    return PatternResult("Head & Shoulders", "chart", 2, "bearish",
                         3 if confirmed else 2, 0.78 if confirmed else 0.65,
                         {"neckline": round(neckline, 2), "target": round(target, 2),
                          "stop":     round(rs[1], 2)},
                         len(df), "confirmed" if confirmed else "forming")


def _det_inverse_hs(df: pd.DataFrame) -> PatternResult | None:
    sl  = _swing_pts(df, "low", "low")[-5:]
    cls = df["close"].astype(float)
    if len(sl) < 3:
        return None
    ls, head, rs = sl[-3], sl[-2], sl[-1]
    if head[1] >= ls[1] * 0.98 or head[1] >= rs[1] * 0.98:
        return None
    if abs(ls[1] - rs[1]) / max(ls[1], 1) * 100 > 8:
        return None
    neckline  = float(cls.tail(30).max())
    confirmed = float(cls.iloc[-1]) > neckline
    target    = neckline + (neckline - head[1])
    return PatternResult("Inverse Head & Shoulders", "chart", 2, "bullish",
                         3 if confirmed else 2, 0.78 if confirmed else 0.65,
                         {"neckline": round(neckline, 2), "target": round(target, 2),
                          "stop":     round(rs[1], 2)},
                         len(df), "confirmed" if confirmed else "forming")


def _det_double_bottom(df: pd.DataFrame) -> PatternResult | None:
    sl  = _swing_pts(df, "low", "low")[-4:]
    cls = df["close"].astype(float)
    if len(sl) < 2:
        return None
    la, lb = sl[-2], sl[-1]
    if abs(la[1] - lb[1]) / max((la[1] + lb[1]) / 2, 1) * 100 > 4:
        return None
    idx = list(df.index)
    ia = idx.index(la[0]) if la[0] in idx else None
    ib = idx.index(lb[0]) if lb[0] in idx else None
    if ia is None or ib is None or ib - ia < 5:
        return None
    neckline = float(df.iloc[ia:ib]["high"].max())
    status   = _break_status(cls, neckline, above=True)
    if status == "stale":
        return None
    confirmed = status == "fresh"
    target    = neckline + (neckline - min(la[1], lb[1]))
    return PatternResult("Double Bottom", "chart", 2, "bullish",
                         3 if confirmed else 2, 0.80 if confirmed else 0.68,
                         {"support":  round(min(la[1], lb[1]), 2),
                          "neckline": round(neckline, 2), "target": round(target, 2)},
                         ib - ia + 5, "confirmed" if confirmed else "forming")


def _det_double_top(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 2:
        return None
    ha, hb = sh[-2], sh[-1]
    if abs(ha[1] - hb[1]) / max((ha[1] + hb[1]) / 2, 1) * 100 > 4:
        return None
    idx = list(df.index)
    ia = idx.index(ha[0]) if ha[0] in idx else None
    ib = idx.index(hb[0]) if hb[0] in idx else None
    if ia is None or ib is None or ib - ia < 5:
        return None
    neckline = float(df.iloc[ia:ib]["low"].min())
    status   = _break_status(cls, neckline, above=False)
    if status == "stale":
        return None
    confirmed = status == "fresh"
    target    = neckline - (max(ha[1], hb[1]) - neckline)
    return PatternResult("Double Top", "chart", 2, "bearish",
                         3 if confirmed else 2, 0.78 if confirmed else 0.65,
                         {"resistance": round(max(ha[1], hb[1]), 2),
                          "neckline":   round(neckline, 2), "target": round(target, 2)},
                         ib - ia + 5, "confirmed" if confirmed else "forming")


def _det_triple_bottom(df: pd.DataFrame) -> PatternResult | None:
    sl  = _swing_pts(df, "low", "low")[-6:]
    cls = df["close"].astype(float)
    if len(sl) < 3:
        return None
    la, lb, lc = sl[-3], sl[-2], sl[-1]
    lows = [la[1], lb[1], lc[1]]
    if max(lows) / max(min(lows), 1e-10) > 1.04:
        return None
    avg_low  = float(np.mean(lows))
    idx      = list(df.index)
    ia       = idx.index(la[0]) if la[0] in idx else 0
    neckline = float(df.iloc[ia:]["high"].max())
    status   = _break_status(cls, neckline, above=True)
    if status == "stale":
        return None
    confirmed = status == "fresh"
    target    = neckline + (neckline - avg_low)
    return PatternResult("Triple Bottom", "chart", 2, "bullish",
                         3 if confirmed else 2, 0.82 if confirmed else 0.70,
                         {"support": round(avg_low, 2), "neckline": round(neckline, 2),
                          "target":  round(target, 2)},
                         len(df), "confirmed" if confirmed else "forming")


def _det_triple_top(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-6:]
    cls = df["close"].astype(float)
    if len(sh) < 3:
        return None
    ha, hb, hc = sh[-3], sh[-2], sh[-1]
    highs = [ha[1], hb[1], hc[1]]
    if max(highs) / max(min(highs), 1e-10) > 1.04:
        return None
    avg_high = float(np.mean(highs))
    idx      = list(df.index)
    ia       = idx.index(ha[0]) if ha[0] in idx else 0
    neckline = float(df.iloc[ia:]["low"].min())
    status   = _break_status(cls, neckline, above=False)
    if status == "stale":
        return None
    confirmed = status == "fresh"
    target    = neckline - (avg_high - neckline)
    return PatternResult("Triple Top", "chart", 2, "bearish",
                         3 if confirmed else 2, 0.80 if confirmed else 0.68,
                         {"resistance": round(avg_high, 2), "neckline": round(neckline, 2),
                          "target":     round(target, 2)},
                         len(df), "confirmed" if confirmed else "forming")


def _det_rounding_bottom(df: pd.DataFrame) -> PatternResult | None:
    seg = df["close"].tail(60).astype(float).values
    t = [float(np.mean(x)) for x in np.array_split(seg, 3)]
    if not (t[0] > t[1] and t[2] > t[1] and (t[0] - t[1]) / max(t[1], 1) > 0.03):
        return None
    return PatternResult("Rounding Bottom", "chart", 2, "bullish", 2, 0.68,
                         {"support": round(t[1], 2), "target": round(t[0], 2)}, 60, "forming")


def _det_rounding_top(df: pd.DataFrame) -> PatternResult | None:
    seg = df["close"].tail(60).astype(float).values
    t = [float(np.mean(x)) for x in np.array_split(seg, 3)]
    if not (t[0] < t[1] and t[2] < t[1] and (t[1] - t[0]) / max(t[0], 1) > 0.03):
        return None
    return PatternResult("Rounding Top", "chart", 2, "bearish", 2, 0.65,
                         {"resistance": round(t[1], 2), "target": round(t[0], 2)}, 60, "forming")


def _det_ascending_triangle(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-4:]
    sl  = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp = float(cls.mean())
    h_range = (max(x[1] for x in sh) - min(x[1] for x in sh)) / max(mp, 1) * 100
    l_sp    = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if h_range >= 4 or l_sp <= 0.1:
        return None
    res = float(np.mean([x[1] for x in sh]))
    confirmed = float(cls.iloc[-1]) > res * 1.01
    target    = res + (res - sl[-1][1])
    return PatternResult("Ascending Triangle", "chart", 2, "bullish",
                         3 if confirmed else 2, 0.78 if confirmed else 0.68,
                         {"resistance": round(res, 2), "support": round(sl[-1][1], 2),
                          "target": round(target, 2)},
                         len(df) // 2, "confirmed" if confirmed else "forming")


def _det_descending_triangle(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-4:]
    sl  = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp = float(cls.mean())
    l_range = (max(x[1] for x in sl) - min(x[1] for x in sl)) / max(mp, 1) * 100
    h_sp    = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    if l_range >= 4 or h_sp >= -0.1:
        return None
    sup = float(np.mean([x[1] for x in sl]))
    confirmed = float(cls.iloc[-1]) < sup * 0.99
    target    = sup - (sh[-1][1] - sup)
    return PatternResult("Descending Triangle", "chart", 2, "bearish",
                         3 if confirmed else 2, 0.76 if confirmed else 0.66,
                         {"support": round(sup, 2), "resistance": round(sh[-1][1], 2),
                          "target": round(target, 2)},
                         len(df) // 2, "confirmed" if confirmed else "forming")


def _det_symmetrical_triangle(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-4:]
    sl  = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp   = float(cls.mean())
    h_sp = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if not (h_sp < -0.08 and l_sp > 0.08):
        return None
    latest = float(cls.iloc[-1])
    b_up = latest > sh[-1][1]; b_dn = latest < sl[-1][1]
    dir_ = "bullish" if b_up else ("bearish" if b_dn else "neutral")
    state = "confirmed" if (b_up or b_dn) else "forming"
    return PatternResult("Symmetrical Triangle Breakout", "chart", 2, dir_,
                         2 if (b_up or b_dn) else 1, 0.74 if (b_up or b_dn) else 0.60,
                         {"resistance": round(sh[-1][1], 2), "support": round(sl[-1][1], 2)},
                         len(df) // 2, state)


def _det_bull_flag(df: pd.DataFrame) -> PatternResult | None:
    cls = df["close"].astype(float)
    low = df["low"].astype(float)
    for pb in (10, 15, 20):
        if len(df) < pb + 10:
            continue
        pole = df.iloc[-(pb + 10):-10]
        flag = df.tail(10)
        pm   = (float(pole["close"].iloc[-1]) - float(pole["close"].iloc[0])) / max(float(pole["close"].iloc[0]), 1) * 100
        if pm < 8:
            continue
        fr = float(flag["high"].max() - flag["low"].min()) / max(float(flag["close"].mean()), 1) * 100
        if fr >= 8:
            continue
        fs = np.polyfit(range(len(flag)), flag["close"].astype(float).values, 1)[0]
        if fs > 0:
            continue
        target = float(cls.iloc[-1]) * (1 + pm / 100)
        return PatternResult("Bull Flag", "chart", 2, "bullish",
                             3 if pm > 15 else 2, min(0.88, 0.70 + min(0.18, abs(pm) * 0.01)),
                             {"support": round(float(low.tail(10).min()), 2),
                              "target":  round(target, 2)},
                             pb + 10, "forming")
    return None


def _det_bear_flag(df: pd.DataFrame) -> PatternResult | None:
    cls  = df["close"].astype(float)
    high = df["high"].astype(float)
    for pb in (10, 15, 20):
        if len(df) < pb + 10:
            continue
        pole = df.iloc[-(pb + 10):-10]
        flag = df.tail(10)
        pm   = (float(pole["close"].iloc[-1]) - float(pole["close"].iloc[0])) / max(float(pole["close"].iloc[0]), 1) * 100
        if pm > -8:
            continue
        fr = float(flag["high"].max() - flag["low"].min()) / max(float(flag["close"].mean()), 1) * 100
        if fr >= 8:
            continue
        fs = np.polyfit(range(len(flag)), flag["close"].astype(float).values, 1)[0]
        if fs < 0:
            continue
        target = float(cls.iloc[-1]) * (1 + pm / 100)
        return PatternResult("Bear Flag", "chart", 2, "bearish",
                             3 if abs(pm) > 15 else 2, min(0.85, 0.68 + min(0.17, abs(pm) * 0.01)),
                             {"resistance": round(float(high.tail(10).max()), 2),
                              "target":     round(target, 2)},
                             pb + 10, "forming")
    return None


def _det_bull_pennant(df: pd.DataFrame) -> PatternResult | None:
    cls = df["close"].astype(float)
    for pb in (8, 12):
        if len(df) < pb + 10:
            continue
        pole = df.iloc[-(pb + 10):-10]
        pm = (float(pole["close"].iloc[-1]) - float(pole["close"].iloc[0])) / max(float(pole["close"].iloc[0]), 1) * 100
        if pm < 8:
            continue
        pen = df.tail(10)
        # Converging highs and lows = pennant
        pen_h = [float(pen.iloc[j]["high"]) for j in range(len(pen))]
        pen_l = [float(pen.iloc[j]["low"])  for j in range(len(pen))]
        hs = _slope(range(len(pen_h)), pen_h)
        ls = _slope(range(len(pen_l)), pen_l)
        if not (hs < 0 and ls > 0):  # converging
            continue
        target = float(cls.iloc[-1]) * (1 + pm / 100)
        return PatternResult("Bull Pennant", "chart", 2, "bullish", 2, 0.72,
                             {"target": round(target, 2)}, pb + 10, "forming")
    return None


def _det_bear_pennant(df: pd.DataFrame) -> PatternResult | None:
    cls = df["close"].astype(float)
    for pb in (8, 12):
        if len(df) < pb + 10:
            continue
        pole = df.iloc[-(pb + 10):-10]
        pm = (float(pole["close"].iloc[-1]) - float(pole["close"].iloc[0])) / max(float(pole["close"].iloc[0]), 1) * 100
        if pm > -8:
            continue
        pen = df.tail(10)
        pen_h = [float(pen.iloc[j]["high"]) for j in range(len(pen))]
        pen_l = [float(pen.iloc[j]["low"])  for j in range(len(pen))]
        hs = _slope(range(len(pen_h)), pen_h)
        ls = _slope(range(len(pen_l)), pen_l)
        if not (hs < 0 and ls > 0):
            continue
        target = float(cls.iloc[-1]) * (1 + pm / 100)
        return PatternResult("Bear Pennant", "chart", 2, "bearish", 2, 0.70,
                             {"target": round(target, 2)}, pb + 10, "forming")
    return None


def _det_falling_wedge(df: pd.DataFrame) -> PatternResult | None:
    sh = _swing_pts(df, "high", "high")[-4:]
    sl = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp = float(cls.mean())
    h_sp = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if not (h_sp < -0.1 and l_sp < 0 and h_sp < l_sp - 0.1):
        return None
    confirmed = float(cls.iloc[-1]) > sh[-1][1]
    return PatternResult("Descending Wedge Breakout", "chart", 2, "bullish",
                         3 if confirmed else 2, 0.74 if confirmed else 0.63,
                         {"resistance": round(sh[-1][1], 2), "stop": round(sl[-1][1], 2)},
                         len(df) // 2, "confirmed" if confirmed else "forming")


def _det_rising_wedge(df: pd.DataFrame) -> PatternResult | None:
    sh = _swing_pts(df, "high", "high")[-4:]
    sl = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp = float(cls.mean())
    h_sp = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if not (l_sp > 0.1 and h_sp > 0 and l_sp > h_sp + 0.1):
        return None
    confirmed = float(cls.iloc[-1]) < sl[-1][1]
    return PatternResult("Rising Wedge", "chart", 2, "bearish",
                         3 if confirmed else 2, 0.72 if confirmed else 0.62,
                         {"support": round(sl[-1][1], 2), "stop": round(sh[-1][1], 2)},
                         len(df) // 2, "confirmed" if confirmed else "forming")


def _det_rectangle(df: pd.DataFrame) -> PatternResult | None:
    sh = _swing_pts(df, "high", "high")[-4:]
    sl = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 2 or len(sl) < 2:
        return None
    rsh = [x[1] for x in sh[-4:]]; rsl = [x[1] for x in sl[-4:]]
    res = float(np.mean(rsh)); sup = float(np.mean(rsl))
    rr  = (max(rsh) - min(rsh)) / max(res, 1) * 100
    sr  = (max(rsl) - min(rsl)) / max(sup, 1) * 100
    bh  = (res - sup) / max(sup, 1) * 100
    if rr >= 4 or sr >= 4 or not (3 < bh < 30):
        return None
    latest = float(cls.iloc[-1])
    if latest > res * 1.01:
        target = res + (res - sup)
        return PatternResult("Rectangle Breakout", "chart", 2, "bullish", 2, 0.78,
                             {"support": round(sup, 2), "resistance": round(res, 2),
                              "target":  round(target, 2)}, 20, "confirmed")
    if latest < sup * 0.99:
        target = sup - (res - sup)
        return PatternResult("Rectangle Breakdown", "chart", 2, "bearish", 2, 0.76,
                             {"support": round(sup, 2), "resistance": round(res, 2),
                              "target":  round(target, 2)}, 20, "confirmed")
    return None


def _det_cup_and_handle(df: pd.DataFrame) -> PatternResult | None:
    cup = df.tail(90)
    cc  = cup["close"].astype(float)
    hl  = float(cc.iloc[:15].mean())
    hr  = float(cc.iloc[-15:].mean())
    fl  = float(cc.iloc[30:60].min())
    dep = (hl - fl) / max(hl, 1) * 100
    rdiff = abs(hl - hr) / max(hl, 1) * 100
    if not (10 < dep < 50 and rdiff < 8 and fl < hl * 0.92):
        return None
    hdl = cc.iloc[-15:]
    hp  = (float(hdl.max()) - float(hdl.min())) / max(float(hdl.max()), 1) * 100
    has_handle = hp < 10 and float(hdl.iloc[-1]) > float(hdl.mean())
    target = float(cc.iloc[-1]) + (hl - fl)
    return PatternResult("Cup & Handle", "chart", 2, "bullish",
                         3 if has_handle else 2, 0.80 if has_handle else 0.68,
                         {"support": round(fl, 2), "resistance": round(hr, 2),
                          "target":  round(target, 2)}, 90, "forming")


def _det_high_tight_flag(df: pd.DataFrame) -> PatternResult | None:
    cls  = df["close"].astype(float)
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    for start in range(8, 16):
        if len(df) < start + 5:
            continue
        move = (float(cls.iloc[-5]) - float(cls.iloc[-(start + 5)])) / max(float(cls.iloc[-(start + 5)]), 1) * 100
        if move < 25:
            continue
        flag_h = float(high.tail(5).max())
        flag_l = float(low.tail(5).min())
        if (flag_h - flag_l) / max(flag_l, 1) * 100 > 15:
            continue
        target = float(cls.iloc[-1]) * (1 + move / 100)
        return PatternResult("High Tight Flag", "chart", 2, "bullish", 3, 0.82,
                             {"support": round(flag_l, 2), "target": round(target, 2)},
                             start + 5, "forming")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — Price-action / momentum / context patterns (equity-focused)
# ─────────────────────────────────────────────────────────────────────────────

def _rsi(close: "pd.Series", period: int = 14) -> "pd.Series":
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _det_52w_high_breakout(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 52:
        return None
    close  = df["close"].astype(float)
    high52 = float(close.iloc[-52:-1].max())
    curr   = float(close.iloc[-1])
    if curr <= high52:
        return None
    conf = 0.78
    if _has_vol(df):
        vol   = df["volume"].astype(float)
        avg_v = float(vol.iloc[-21:-1].mean())
        if avg_v > 0 and float(vol.iloc[-1]) > avg_v * 1.5:
            conf = min(0.90, conf + 0.10)
    return PatternResult("52W High Breakout", "price_action", 2, "bullish", 3, conf,
                         {"breakout": round(high52, 2), "stop": round(high52 * 0.97, 2)},
                         52, "confirmed")


def _det_near_52w_high(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 52:
        return None
    close  = df["close"].astype(float)
    high   = df["high"].astype(float)
    high52 = float(high.iloc[-52:].max())
    curr   = float(close.iloc[-1])
    if high52 <= 0:
        return None
    dist = (high52 - curr) / high52
    if not (0 < dist <= 0.05):
        return None
    return PatternResult("Near 52W High", "price_action", 1, "bullish", 2, 0.65,
                         {"resistance": round(high52, 2)}, 52, "forming")


def _det_near_52w_low(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 52:
        return None
    close = df["close"].astype(float)
    low   = df["low"].astype(float)
    low52 = float(low.iloc[-52:].min())
    curr  = float(close.iloc[-1])
    if low52 <= 0:
        return None
    dist = (curr - low52) / low52
    if not (0 < dist <= 0.05):
        return None
    return PatternResult("Near 52W Low", "price_action", 1, "bearish", 2, 0.63,
                         {"support": round(low52, 2)}, 52, "forming")


def _det_pullback_20ema(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 30:
        return None
    close    = df["close"].astype(float)
    ema20    = close.ewm(span=20, adjust=False).mean()
    curr     = float(close.iloc[-1])
    e_curr   = float(ema20.iloc[-1])
    e_prev   = float(ema20.iloc[-5])
    if e_curr <= e_prev or e_curr <= 0:
        return None
    if abs(curr - e_curr) / e_curr > 0.015:
        return None
    if curr <= float(close.iloc[-2]):
        return None
    return PatternResult("Pullback to 20 EMA", "price_action", 1, "bullish", 2, 0.70,
                         {"support": round(e_curr, 2), "stop": round(e_curr * 0.98, 2)},
                         20, "confirmed")


def _det_pullback_50dma(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 60:
        return None
    close  = df["close"].astype(float)
    sma50  = close.rolling(50).mean()
    curr   = float(close.iloc[-1])
    s_curr = float(sma50.iloc[-1])
    s_prev = float(sma50.iloc[-10])
    if np.isnan(s_curr) or s_curr <= 0 or s_curr <= s_prev:
        return None
    if abs(curr - s_curr) / s_curr > 0.02:
        return None
    if curr <= float(close.iloc[-2]):
        return None
    return PatternResult("Pullback to 50 DMA", "price_action", 1, "bullish", 2, 0.68,
                         {"support": round(s_curr, 2), "stop": round(s_curr * 0.97, 2)},
                         50, "confirmed")


def _det_overbought_reversal(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 20:
        return None
    close    = df["close"].astype(float)
    rsi      = _rsi(close)
    r_curr   = float(rsi.iloc[-1])
    r_prev   = float(rsi.iloc[-3])
    if np.isnan(r_curr) or r_curr >= 70 or r_prev <= 70:
        return None
    if float(close.iloc[-1]) >= float(close.iloc[-2]):
        return None
    return PatternResult("Overbought Reversal", "price_action", 1, "bearish", 2, 0.68,
                         {"stop": round(float(df["high"].astype(float).iloc[-3:].max()), 2)},
                         14, "confirmed")


def _det_oversold_bounce(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 20:
        return None
    close  = df["close"].astype(float)
    rsi    = _rsi(close)
    r_curr = float(rsi.iloc[-1])
    r_prev = float(rsi.iloc[-3])
    if np.isnan(r_curr) or r_curr <= 30 or r_prev >= 30:
        return None
    if float(close.iloc[-1]) <= float(close.iloc[-2]):
        return None
    return PatternResult("Oversold Bounce", "price_action", 1, "bullish", 2, 0.68,
                         {"stop": round(float(df["low"].astype(float).iloc[-3:].min()), 2)},
                         14, "confirmed")


def _det_doji_at_support(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 20:
        return None
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.10 or r == 0:
        return None
    sup = float(df["low"].astype(float).iloc[-20:].min())
    if cl > sup * 1.02:
        return None
    return PatternResult("Doji at Support", "candlestick", 1, "bullish", 2, 0.68,
                         {"support": round(sup, 2), "stop": round(l * 0.99, 2)},
                         20, "confirmed")


def _det_doji_at_resistance(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 20:
        return None
    c = df.iloc[-1]
    o, h, l, cl = _sf(c["open"]), _sf(c["high"]), _sf(c["low"]), _sf(c["close"])
    r = _rng(h, l)
    if _body(o, cl) > r * 0.10 or r == 0:
        return None
    res = float(df["high"].astype(float).iloc[-20:].max())
    if cl < res * 0.98:
        return None
    return PatternResult("Doji at Resistance", "candlestick", 1, "bearish", 2, 0.67,
                         {"resistance": round(res, 2), "stop": round(h * 1.01, 2)},
                         20, "confirmed")


def _det_gap_up_volume(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 10 or not _has_vol(df):
        return None
    curr_o = _sf(df.iloc[-1]["open"])
    prev_h = _sf(df.iloc[-2]["high"])
    if curr_o <= prev_h * 1.005:
        return None
    vol   = df["volume"].astype(float)
    avg_v = float(vol.iloc[-21:-1].mean())
    if avg_v <= 0 or float(vol.iloc[-1]) < avg_v * 1.5:
        return None
    gap_pct = (curr_o - prev_h) / max(prev_h, 1) * 100
    return PatternResult("Gap Up with Volume", "volume", 1, "bullish",
                         3 if gap_pct >= 2 else 2,
                         min(0.85, 0.65 + gap_pct * 0.02),
                         {"gap_open": round(curr_o, 2), "prev_high": round(prev_h, 2)},
                         5, "confirmed")


def _det_v_bottom(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 20:
        return None
    close   = df["close"].astype(float)
    seg     = close.iloc[-20:].reset_index(drop=True)
    bot_idx = int(seg.argmin())
    if bot_idx < 3 or bot_idx > len(seg) - 4:
        return None
    pre_fall  = (float(seg.iloc[0]) - float(seg.iloc[bot_idx])) / max(float(seg.iloc[0]), 1) * 100
    post_rise = (float(seg.iloc[-1]) - float(seg.iloc[bot_idx])) / max(float(seg.iloc[bot_idx]), 1) * 100
    if pre_fall < 8 or post_rise < 8:
        return None
    recovery = post_rise / max(pre_fall, 1)
    if recovery < 0.70:
        return None
    conf = min(0.82, 0.65 + recovery * 0.10)
    return PatternResult("V Bottom", "chart", 2, "bullish", 2, conf,
                         {"bottom":  round(float(seg.iloc[bot_idx]), 2),
                          "target":  round(float(seg.iloc[0]), 2)},
                         20, "confirmed")


def _det_channel_breakout(df: pd.DataFrame) -> PatternResult | None:
    sh  = _swing_pts(df, "high", "high")[-4:]
    sl  = _swing_pts(df, "low",  "low")[-4:]
    cls = df["close"].astype(float)
    if len(sh) < 2 or len(sl) < 2:
        return None
    mp      = float(cls.mean())
    h_sp    = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp    = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if abs(h_sp - l_sp) > 0.25 or abs(h_sp) < 0.05:
        return None
    curr     = float(cls.iloc[-1])
    chan_top = sh[-1][1]
    chan_bot = sl[-1][1]
    if curr > chan_top * 1.01:
        target = curr + (chan_top - chan_bot)
        return PatternResult("Channel Breakout", "chart", 2, "bullish", 2, 0.72,
                             {"resistance": round(chan_top, 2), "support": round(chan_bot, 2),
                              "target": round(target, 2)},
                             len(df) // 2, "confirmed")
    if curr < chan_bot * 0.99:
        target = curr - (chan_top - chan_bot)
        return PatternResult("Channel Breakdown", "chart", 2, "bearish", 2, 0.72,
                             {"resistance": round(chan_top, 2), "support": round(chan_bot, 2),
                              "target": round(target, 2)},
                             len(df) // 2, "confirmed")
    return None


_BREAKOUT_RECENCY_BARS = 5  # a breakout/neckline-break must have happened within this many
                             # bars — otherwise "price is still above the level it broke
                             # weeks ago" just describes an ongoing trend, not a fresh event.


def _det_trendline_breakout(df: pd.DataFrame) -> PatternResult | None:
    if len(df) < 30 + _BREAKOUT_RECENCY_BARS:
        return None
    cls = df["close"].astype(float)
    idx = list(df.index)
    n   = len(df)

    sl = _swing_pts(df, "low", "low")[-5:]
    if len(sl) >= 3:
        xs = [idx.index(pt[0]) for pt in sl]
        ys = [pt[1] for pt in sl]
        coeffs = np.polyfit(xs, ys, 1)
        if coeffs[0] > 0:
            proj_now    = float(np.polyval(coeffs, n - 1))
            proj_recent = float(np.polyval(coeffs, n - 1 - _BREAKOUT_RECENCY_BARS))
            broke_now    = float(cls.iloc[-1]) > proj_now * 1.005
            broke_recent = float(cls.iloc[-1 - _BREAKOUT_RECENCY_BARS]) > proj_recent * 1.005
            if broke_now and not broke_recent:
                return PatternResult("Trendline Breakout", "chart", 2, "bullish", 2, 0.72,
                                     {"trendline": round(proj_now, 2), "stop": round(sl[-1][1], 2)},
                                     30, "confirmed")
    sh = _swing_pts(df, "high", "high")[-5:]
    if len(sh) >= 3:
        xs = [idx.index(pt[0]) for pt in sh]
        ys = [pt[1] for pt in sh]
        coeffs = np.polyfit(xs, ys, 1)
        if coeffs[0] < 0:
            proj_now    = float(np.polyval(coeffs, n - 1))
            proj_recent = float(np.polyval(coeffs, n - 1 - _BREAKOUT_RECENCY_BARS))
            broke_now    = float(cls.iloc[-1]) < proj_now * 0.995
            broke_recent = float(cls.iloc[-1 - _BREAKOUT_RECENCY_BARS]) < proj_recent * 0.995
            if broke_now and not broke_recent:
                return PatternResult("Trendline Breakdown", "chart", 2, "bearish", 2, 0.70,
                                     {"trendline": round(proj_now, 2), "stop": round(sh[-1][1], 2)},
                                     30, "confirmed")
    return None


def _det_ascending_channel(df: pd.DataFrame) -> PatternResult | None:
    """Price rises inside two parallel upward-sloping trendlines — bullish trend continuation."""
    if len(df) < 30:
        return None
    sh = _swing_pts(df, "high", "high")[-5:]
    sl = _swing_pts(df, "low",  "low")[-5:]
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp   = float(df["close"].astype(float).mean())
    h_sp = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if h_sp <= 0 or l_sp <= 0:          # both trendlines must rise
        return None
    if abs(h_sp - l_sp) > 0.30:        # must be roughly parallel
        return None
    cls = float(df["close"].astype(float).iloc[-1])
    top = sh[-1][1]
    bot = sl[-1][1]
    if not (bot * 0.97 <= cls <= top * 1.03):
        return None
    return PatternResult("Ascending Channel", "chart", 2, "bullish", 2, 0.68,
                         {"upper": round(top, 2), "lower": round(bot, 2)},
                         len(df) // 2, "forming")


def _det_descending_channel(df: pd.DataFrame) -> PatternResult | None:
    """Price falls inside two parallel downward-sloping trendlines — bearish trend continuation."""
    if len(df) < 30:
        return None
    sh = _swing_pts(df, "high", "high")[-5:]
    sl = _swing_pts(df, "low",  "low")[-5:]
    if len(sh) < 3 or len(sl) < 3:
        return None
    mp   = float(df["close"].astype(float).mean())
    h_sp = _slope(range(len(sh)), [x[1] for x in sh]) / max(mp, 1) * 100
    l_sp = _slope(range(len(sl)), [x[1] for x in sl]) / max(mp, 1) * 100
    if h_sp >= 0 or l_sp >= 0:          # both trendlines must fall
        return None
    if abs(h_sp - l_sp) > 0.30:        # must be roughly parallel
        return None
    cls = float(df["close"].astype(float).iloc[-1])
    top = sh[-1][1]
    bot = sl[-1][1]
    if not (bot * 0.97 <= cls <= top * 1.03):
        return None
    return PatternResult("Descending Channel", "chart", 2, "bearish", 2, 0.68,
                         {"upper": round(top, 2), "lower": round(bot, 2)},
                         len(df) // 2, "forming")


# ─────────────────────────────────────────────────────────────────────────────
# Wyckoff patterns (harmonic family, Tier 2)
# ─────────────────────────────────────────────────────────────────────────────

def _det_wyckoff_accum(df: pd.DataFrame) -> PatternResult | None:
    cls = df["close"].tail(40).astype(float)
    rng = (float(cls.max()) - float(cls.min())) / max(float(cls.mean()), 1) * 100
    if rng > 15 or rng < 3:
        return None
    if _has_vol(df):
        vol  = df["volume"].astype(float)
        ev   = float(vol.iloc[-40:-20].mean())
        lv   = float(vol.tail(20).mean())
        if lv >= ev:
            return None
    return PatternResult("Wyckoff Accumulation", "harmonic", 2,
                         "bullish", 1, 0.35, {}, 40, "forming")


def _det_wyckoff_dist(df: pd.DataFrame) -> PatternResult | None:
    cls = df["close"].tail(40).astype(float)
    rng = (float(cls.max()) - float(cls.min())) / max(float(cls.mean()), 1) * 100
    if rng > 15 or rng < 3:
        return None
    if _has_vol(df):
        vol = df["volume"].astype(float)
        ev  = float(vol.iloc[-40:-20].mean())
        lv  = float(vol.tail(20).mean())
        if lv >= ev:
            return None
    if float(cls.iloc[-1]) < float(cls.mean()):
        return None
    return PatternResult("Wyckoff Distribution", "harmonic", 2,
                         "bearish", 1, 0.32, {}, 40, "forming")


# ─────────────────────────────────────────────────────────────────────────────
# Registry definition
# ─────────────────────────────────────────────────────────────────────────────

_A  = ["5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]   # all timeframes (incl. equity)
_C  = ["15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]         # chart-appropriate timeframes
_EQ = ["1d", "1wk", "1mo"]                       # equity only (52W / EMA / RSI)
_S  = ["1h", "4h", "1d"]                         # slow (Tier 3)

REGISTRY: list[RegistryEntry] = [
    # Tier 1 — single candle
    RegistryEntry("Hammer",                   "candlestick", 1, "bullish", _A,   3,  _det_hammer),
    RegistryEntry("Inverted Hammer",          "candlestick", 1, "bullish", _A,   3,  _det_inverted_hammer,    True),
    RegistryEntry("Dragonfly Doji",           "candlestick", 1, "bullish", _A,   3,  _det_dragonfly_doji,     True),
    RegistryEntry("Hanging Man",              "candlestick", 1, "bearish", _A,   6,  _det_hanging_man,        True),
    RegistryEntry("Shooting Star",            "candlestick", 1, "bearish", _A,   3,  _det_shooting_star),
    RegistryEntry("Gravestone Doji",          "candlestick", 1, "bearish", _A,   3,  _det_gravestone_doji,    True),
    RegistryEntry("Doji",                     "candlestick", 1, "neutral", _A,   3,  _det_doji),
    RegistryEntry("Long-Legged Doji",         "candlestick", 1, "neutral", _A,   3,  _det_long_legged_doji),
    RegistryEntry("Spinning Top",             "candlestick", 1, "neutral", _A,   3,  _det_spinning_top),
    RegistryEntry("Doji at Support",          "candlestick", 1, "bullish", _A,  20,  _det_doji_at_support),
    RegistryEntry("Doji at Resistance",       "candlestick", 1, "bearish", _A,  20,  _det_doji_at_resistance),
    # Tier 1 — two candle
    RegistryEntry("Bullish Engulfing",        "candlestick", 1, "bullish", _A,   4,  _det_bullish_engulfing),
    RegistryEntry("Piercing",                 "candlestick", 1, "bullish", _A,   4,  _det_piercing),
    RegistryEntry("Tweezer Bottom",           "candlestick", 1, "bullish", _A,   4,  _det_tweezer_bottom),
    RegistryEntry("Bearish Engulfing",        "candlestick", 1, "bearish", _A,   4,  _det_bearish_engulfing),
    RegistryEntry("Dark Cloud Cover",         "candlestick", 1, "bearish", _A,   4,  _det_dark_cloud_cover),
    RegistryEntry("Tweezer Top",              "candlestick", 1, "bearish", _A,   4,  _det_tweezer_top),
    # Tier 1 — three candle
    RegistryEntry("Morning Star",             "candlestick", 1, "bullish", _A,   5,  _det_morning_star),
    RegistryEntry("Three White Soldiers",     "candlestick", 1, "bullish", _A,   5,  _det_three_white_soldiers),
    RegistryEntry("Abandoned Baby Bottom",    "candlestick", 1, "bullish", _A,   5,  _det_abandoned_baby_bull),
    RegistryEntry("Evening Star",             "candlestick", 1, "bearish", _A,   5,  _det_evening_star),
    RegistryEntry("Three Black Crows",        "candlestick", 1, "bearish", _A,   5,  _det_three_black_crows),
    RegistryEntry("Abandoned Baby Top",       "candlestick", 1, "bearish", _A,   5,  _det_abandoned_baby_bear),
    # Tier 1 — price action
    RegistryEntry("Inside Bar",               "price_action", 1, "neutral", _A,  5,  _det_inside_bar),
    RegistryEntry("Outside Bar",              "price_action", 1, "neutral", _A,  4,  _det_outside_bar),
    RegistryEntry("NR7",                      "price_action", 1, "neutral", _A,  9,  _det_nr7),
    RegistryEntry("Fakey",                    "price_action", 1, "neutral", _A,  6,  _det_fakey),
    RegistryEntry("Breakout Retest",          "price_action", 1, "neutral", _A, 20,  _det_breakout_retest),
    RegistryEntry("Near 52W High",            "price_action", 1, "bullish", _EQ, 52, _det_near_52w_high),
    RegistryEntry("Near 52W Low",             "price_action", 1, "bearish", _EQ, 52, _det_near_52w_low),
    RegistryEntry("Pullback to 20 EMA",       "price_action", 1, "bullish", _EQ, 30, _det_pullback_20ema),
    RegistryEntry("Pullback to 50 DMA",       "price_action", 1, "bullish", _EQ, 60, _det_pullback_50dma),
    RegistryEntry("Overbought Reversal",      "price_action", 1, "bearish", _A,  20, _det_overbought_reversal),
    RegistryEntry("Oversold Bounce",          "price_action", 1, "bullish", _A,  20, _det_oversold_bounce),
    # Tier 1 — volume
    RegistryEntry("Volume Surge on Breakout", "volume",    1, "bullish", _A,  22,  _det_vol_expansion_breakout),
    RegistryEntry("Volume Dry Up",            "volume",    1, "bullish", _A,  22,  _det_vol_dry_up),
    RegistryEntry("Accumulation Phase",       "volume",    1, "bullish", _A,  12,  _det_accumulation),
    RegistryEntry("Distribution Phase",       "volume",    1, "bearish", _A,  12,  _det_distribution),
    RegistryEntry("Selling Climax",           "volume",    1, "bullish", _A,  22,  _det_selling_climax),
    RegistryEntry("Volume Breakdown",         "volume",    1, "bearish", _A,  22,  _det_volume_breakdown),
    RegistryEntry("Gap Up with Volume",       "volume",    1, "bullish", _A,  10,  _det_gap_up_volume),
    # Tier 2 — price action (equity-focused)
    RegistryEntry("52W High Breakout",        "price_action", 2, "bullish", _EQ, 52, _det_52w_high_breakout),
    # Tier 2 — chart
    RegistryEntry("Head & Shoulders",         "chart", 2, "bearish", _C, 40,  _det_head_and_shoulders, True),
    RegistryEntry("Inverse Head & Shoulders", "chart", 2, "bullish", _C, 40,  _det_inverse_hs,         True),
    RegistryEntry("Double Bottom",            "chart", 2, "bullish", _C, 25,  _det_double_bottom,      True),
    RegistryEntry("Double Top",               "chart", 2, "bearish", _C, 25,  _det_double_top,         True),
    RegistryEntry("Triple Bottom",            "chart", 2, "bullish", _C, 40,  _det_triple_bottom,      True),
    RegistryEntry("Triple Top",               "chart", 2, "bearish", _C, 40,  _det_triple_top,         True),
    RegistryEntry("Rounding Bottom",          "chart", 2, "bullish", _C, 60,  _det_rounding_bottom),
    RegistryEntry("Rounding Top",             "chart", 2, "bearish", _C, 60,  _det_rounding_top),
    RegistryEntry("Ascending Triangle",       "chart", 2, "bullish", _C, 25,  _det_ascending_triangle, True),
    RegistryEntry("Descending Triangle",      "chart", 2, "bearish", _C, 25,  _det_descending_triangle,True),
    RegistryEntry("Symmetrical Triangle Breakout", "chart", 2, "neutral", _C, 25,  _det_symmetrical_triangle,True),
    RegistryEntry("Bull Flag",                "chart", 2, "bullish", _C, 30,  _det_bull_flag),
    RegistryEntry("Bull Pennant",             "chart", 2, "bullish", _C, 30,  _det_bull_pennant),
    RegistryEntry("Bear Flag",                "chart", 2, "bearish", _C, 30,  _det_bear_flag),
    RegistryEntry("Bear Pennant",             "chart", 2, "bearish", _C, 30,  _det_bear_pennant),
    RegistryEntry("Descending Wedge Breakout", "chart", 2, "bullish", _C, 30,  _det_falling_wedge,      True),
    RegistryEntry("Rising Wedge",             "chart", 2, "bearish", _C, 30,  _det_rising_wedge,       True),
    RegistryEntry("Rectangle Breakout",       "chart", 2, "neutral", _C, 20,  _det_rectangle,          True),
    RegistryEntry("Cup & Handle",             "chart", 2, "bullish", _C, 90,  _det_cup_and_handle),
    RegistryEntry("High Tight Flag",          "chart", 2, "bullish", _C, 20,  _det_high_tight_flag),
    RegistryEntry("V Bottom",                 "chart", 2, "bullish", _C, 20,  _det_v_bottom),
    RegistryEntry("Channel Breakout",         "chart", 2, "bullish", _C, 25,  _det_channel_breakout),
    RegistryEntry("Trendline Breakout",       "chart", 2, "bullish", _C, 30,  _det_trendline_breakout),
    RegistryEntry("Ascending Channel",        "chart", 2, "bullish", _C, 30,  _det_ascending_channel),
    RegistryEntry("Descending Channel",       "chart", 2, "bearish", _C, 30,  _det_descending_channel),
    # Tier 2 — Wyckoff structural patterns
    RegistryEntry("Wyckoff Accumulation",     "harmonic", 2, "bullish", _C, 40, _det_wyckoff_accum),
    RegistryEntry("Wyckoff Distribution",     "harmonic", 2, "bearish", _C, 40, _det_wyckoff_dist),
]

DEFAULT_ENABLED_FAMILIES: set[str] = {"candlestick", "price_action", "volume", "chart", "harmonic"}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_detectors(
    df: pd.DataFrame,
    timeframe: str,
    enabled_families: set[str] | None = None,
    max_tier: int = 2,
) -> list[PatternResult]:
    """
    Run all applicable registry detectors for the given OHLCV DataFrame.
    Returns list sorted by confidence descending.
    Deduplicates per (family, direction, name) to prevent double-counting.
    """
    if enabled_families is None:
        enabled_families = DEFAULT_ENABLED_FAMILIES

    n = len(df)
    results: list[PatternResult] = []

    for entry in REGISTRY:
        if entry.family not in enabled_families:
            continue
        if entry.tier > max_tier:
            continue
        if timeframe not in entry.valid_timeframes:
            continue
        if n < entry.min_bars:
            continue
        try:
            r = entry.detector_fn(df)
        except Exception as exc:
            log.debug("Detector %s failed: %s", entry.name, exc)
            continue
        if r is None:
            continue
        # Confidence penalty for chart/harmonic on noisy short TFs
        if entry.family in ("chart", "harmonic") and timeframe in ("5m", "15m", "30m"):
            r = PatternResult(
                r.name, r.family, r.tier, r.direction, r.strength,
                max(0.0, r.confidence - 0.10), r.key_levels, r.span_bars, r.state,
            )
        r.timeframe = timeframe
        results.append(r)

    results.sort(key=lambda r: r.confidence, reverse=True)

    # Deduplicate: keep highest-confidence per (family, direction, name)
    seen: set[tuple] = set()
    final: list[PatternResult] = []
    for r in results:
        k = (r.family, r.direction, r.name)
        if k not in seen:
            seen.add(k)
            final.append(r)
    return final


def best_for_confluence(
    patterns: list[PatternResult],
    trend_direction: str,
) -> PatternResult | None:
    """
    Return the single best pattern to feed into Category-4 of the confluence scorer.

    Priority order:
      1. Confirmed Tier-2 structural patterns (chart / price_action) aligned with trend
         — channels, flags, triangles, trendlines represent real structural moves
      2. Confirmed Tier-1 non-volume patterns aligned with trend (candlesticks)
      3. Any confirmed aligned pattern (volume allowed as last resort)
      4. Forming / cross-direction fallback
    """
    if not patterns:
        return None

    def aligned(p: PatternResult) -> bool:
        return p.direction == trend_direction or trend_direction == "range"

    def confirmed(p: PatternResult) -> bool:
        return p.state == "confirmed"

    structural_fams = {"chart", "price_action"}

    # Stage 1: confirmed structural (Tier-2) aligned with trend
    s1 = [p for p in patterns
          if p.tier == 2 and p.family in structural_fams
          and confirmed(p) and aligned(p) and p.strength > 0]
    if s1:
        return max(s1, key=lambda p: (p.strength, p.confidence))

    # Stage 2: confirmed Tier-1 non-volume aligned
    s2 = [p for p in patterns
          if p.tier == 1 and p.family != "volume"
          and confirmed(p) and aligned(p) and p.strength > 0]
    if s2:
        return max(s2, key=lambda p: (p.strength, p.confidence))

    # Stage 3: any confirmed aligned (volume allowed as last resort)
    s3 = [p for p in patterns if confirmed(p) and aligned(p) and p.strength > 0]
    if s3:
        return max(s3, key=lambda p: (p.tier == 2, p.strength, p.confidence))

    # Stage 4: forming or cross-direction fallback
    aligned_any = [p for p in patterns if aligned(p) and p.strength > 0]
    if aligned_any:
        return max(aligned_any, key=lambda p: (p.tier == 2, p.state == "confirmed", p.strength, p.confidence))
    return None
