"""
Multi-Timeframe Analysis Engine.
Fetches 4 timeframes (monthly/weekly/daily/hourly) via yfinance and returns
structured trend, pattern, S/R, CPR and volume analysis.
Trend detection uses EMA 20 / 50 / 200 alignment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance not installed — MTF analysis unavailable. Run: pip install yfinance")

try:
    from scipy.signal import argrelextrema
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

# ── Index symbol map: internal name → yfinance ticker ─────────────────────────
_INDEX_MAP: dict[str, str] = {
    "NIFTY":       "^NSEI",
    "BANKNIFTY":   "^NSEBANK",
    "FINNIFTY":    "NIFTY_FIN_SERVICE.NS",
    "MIDCPNIFTY":  "^NSEMDCP50",
    "SENSEX":      "^BSESN",
    "BANKEX":      "^BSEBANKEX",
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CPRLevel:
    pivot:     float
    bc:        float
    tc:        float
    width_pct: float
    is_narrow: bool   # < 0.25 % — trending day expected
    is_wide:   bool   # > 0.50 % — sideways expected


@dataclass
class KeyLevel:
    price:       float
    level_type:  str   # PDH | PDL | PWH | PWL | ROUND | SUPPORT | RESISTANCE
    significance: int  # 1–10
    description: str


@dataclass
class PricePattern:
    name:        str
    direction:   str   # BULLISH | BEARISH | NEUTRAL
    strength:    int   # 1–10
    candle_index: int
    description: str


@dataclass
class TimeframeAnalysis:
    trend:         str              # UPTREND | DOWNTREND | SIDEWAYS
    ema20:         float
    ema50:         float
    ema200:        float            # 0.0 if insufficient data
    last_close:    float
    adx:           float
    ema_aligned:   bool             # EMA20 > EMA50 (bull) or EMA20 < EMA50 (bear)
    ema_full_bull: bool             # price > EMA20 > EMA50 > EMA200
    ema_full_bear: bool             # price < EMA20 < EMA50 < EMA200
    structure:     str              # HHHL | LHLL | MIXED
    patterns:      list[PricePattern]
    key_levels:    list[KeyLevel]
    volume_signal: str              # BULLISH | BEARISH | DRY_UP | NEUTRAL
    cpr:           Optional[CPRLevel]
    rsi:           float
    obv_trend:     str              # UP | DOWN | FLAT


@dataclass
class MTFAnalysis:
    symbol:          str
    timestamp:       str
    monthly:         Optional[TimeframeAnalysis]
    weekly:          Optional[TimeframeAnalysis]
    daily:           Optional[TimeframeAnalysis]
    hourly:          Optional[TimeframeAnalysis]
    overall_trend:   str   # UPTREND | DOWNTREND | SIDEWAYS
    alignment_count: int   # 0–4 timeframes agreeing
    error:           str = ""


# ── Technical helpers ──────────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> float:
    try:
        h, l, c = df["High"], df["Low"], df["Close"]
        plus_dm  = h.diff().clip(lower=0)
        minus_dm = (-l.diff()).clip(lower=0)
        plus_dm[plus_dm < minus_dm]   = 0
        minus_dm[minus_dm < plus_dm]  = 0
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr      = tr.ewm(span=period, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / (atr + 1e-10)
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / (atr + 1e-10)
        dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        return float(dx.ewm(span=period, adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def _rsi(close: pd.Series, period: int = 14) -> float:
    try:
        d  = close.diff()
        g  = d.where(d > 0, 0.0).ewm(span=period, adjust=False).mean()
        ls = (-d.where(d < 0, 0.0)).ewm(span=period, adjust=False).mean()
        return float(100 - 100 / (1 + g / (ls + 1e-10))).real
    except Exception:
        return 50.0


# ── Core analysis sub-functions ───────────────────────────────────────────────

def detect_trend(df: pd.DataFrame) -> tuple[str, float, float, float]:
    """Returns (UPTREND|DOWNTREND|SIDEWAYS, ema20, ema50, ema200).
    ema200 is 0.0 when there is insufficient data (< 200 candles)."""
    close = df["Close"]
    n     = len(df)

    if n < 22:
        return "SIDEWAYS", 0.0, 0.0, 0.0

    e20  = _ema(close, 20)
    e50  = _ema(close, 50) if n >= 52 else e20
    e200 = _ema(close, 200) if n >= 200 else None

    last = float(close.iloc[-1])
    v20  = float(e20.iloc[-1])
    v50  = float(e50.iloc[-1])
    v200 = float(e200.iloc[-1]) if e200 is not None else 0.0

    # Full bull: price > EMA20 > EMA50 (> EMA200 if available)
    full_bull = last > v20 > v50 and (v200 == 0.0 or v50 > v200)
    full_bear = last < v20 < v50 and (v200 == 0.0 or v50 < v200)

    if full_bull or (last > v20 > v50):
        return "UPTREND", v20, v50, v200
    if full_bear or (last < v20 < v50):
        return "DOWNTREND", v20, v50, v200
    return "SIDEWAYS", v20, v50, v200


def calculate_cpr(df: pd.DataFrame) -> Optional[CPRLevel]:
    """CPR from previous session H/L/C."""
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    h, l, c = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
    pivot = (h + l + c) / 3
    bc    = (h + l) / 2
    tc    = 2 * pivot - bc
    if tc < bc:
        tc, bc = bc, tc
    w = abs(tc - bc) / pivot * 100 if pivot > 0 else 0
    return CPRLevel(
        pivot=round(pivot, 2), bc=round(bc, 2), tc=round(tc, 2),
        width_pct=round(w, 3), is_narrow=(w < 0.25), is_wide=(w > 0.5),
    )


def detect_market_structure(df: pd.DataFrame) -> str:
    """HHHL / LHLL using swing highs/lows."""
    if len(df) < 12:
        return "MIXED"
    try:
        highs = df["High"].values
        lows  = df["Low"].values
        n = len(df)
        order = max(2, n // 10)

        if _SCIPY_AVAILABLE:
            sh_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
            sl_idx = argrelextrema(lows,  np.less_equal,   order=order)[0]
        else:
            win = max(3, n // 8)
            sh_idx, sl_idx = [], []
            for i in range(win, n - win):
                if highs[i] == highs[max(0, i-win):i+win+1].max():
                    sh_idx.append(i)
                if lows[i] == lows[max(0, i-win):i+win+1].min():
                    sl_idx.append(i)

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            return "MIXED"

        sh = [highs[i] for i in sh_idx[-3:]]
        sl = [lows[i]  for i in sl_idx[-3:]]

        hh = all(sh[i] > sh[i-1] for i in range(1, len(sh)))
        hl = all(sl[i] > sl[i-1] for i in range(1, len(sl)))
        lh = all(sh[i] < sh[i-1] for i in range(1, len(sh)))
        ll = all(sl[i] < sl[i-1] for i in range(1, len(sl)))

        if hh and hl:
            return "HHHL"
        if lh and ll:
            return "LHLL"
    except Exception:
        pass
    return "MIXED"


def detect_price_action_patterns(df: pd.DataFrame) -> list[PricePattern]:
    """Detect all 12 Madras Trader price-action patterns."""
    out: list[PricePattern] = []
    if len(df) < 5:
        return out

    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    n = len(df)
    vol = df["Volume"].values if "Volume" in df.columns else np.ones(n)

    def body(i): return abs(c[i] - o[i])
    def wick_lo(i): return min(o[i], c[i]) - l[i]
    def wick_hi(i): return h[i] - max(o[i], c[i])
    def rng(i): return h[i] - l[i]

    # 1 — Bullish Engulfing
    for i in range(n - 2, max(n - 6, 0), -1):
        if c[i] < o[i] and c[i+1] > o[i+1]:
            if o[i+1] <= c[i] and c[i+1] >= o[i] and body(i+1) > body(i):
                out.append(PricePattern("Bullish Engulfing", "BULLISH", min(10, int(body(i+1)/max(body(i), 1)*4)), i+1,
                    "Prior bearish candle fully engulfed — buyers dominant"))
                break

    # 2 — Bearish Engulfing
    for i in range(n - 2, max(n - 6, 0), -1):
        if c[i] > o[i] and c[i+1] < o[i+1]:
            if o[i+1] >= c[i] and c[i+1] <= o[i] and body(i+1) > body(i):
                out.append(PricePattern("Bearish Engulfing", "BEARISH", min(10, int(body(i+1)/max(body(i), 1)*4)), i+1,
                    "Prior bullish candle fully engulfed — sellers dominant"))
                break

    # 3 — Hammer
    i = n - 1
    if rng(i) > 0 and wick_lo(i) >= 2 * body(i) and wick_hi(i) <= 0.1 * rng(i) and body(i) > 0:
        out.append(PricePattern("Hammer", "BULLISH", 7, i,
            "Long lower wick — rejection of lower prices, bullish reversal signal"))

    # 4 — Hanging Man (hammer after uptrend)
    if n >= 6:
        i = n - 1
        prev_up = c[n-3] > c[n-6]
        if prev_up and rng(i) > 0 and wick_lo(i) >= 2 * body(i) and wick_hi(i) <= 0.1 * rng(i) and body(i) > 0:
            out.append(PricePattern("Hanging Man", "BEARISH", 6, i,
                "Hammer-like after uptrend — potential reversal warning"))

    # 5 — Pin Bar (long wick rejection)
    i = n - 1
    if rng(i) > 0:
        if wick_hi(i) / rng(i) > 0.6 and body(i) / rng(i) < 0.25:
            out.append(PricePattern("Pin Bar (Bearish)", "BEARISH", 8, i,
                "Long upper wick — strong rejection of higher prices at resistance"))
        elif wick_lo(i) / rng(i) > 0.6 and body(i) / rng(i) < 0.25:
            out.append(PricePattern("Pin Bar (Bullish)", "BULLISH", 8, i,
                "Long lower wick — strong rejection of lower prices at support"))

    # 6 — Inside Bar
    if n >= 2:
        i = n - 1
        if h[i] <= h[i-1] and l[i] >= l[i-1]:
            direction = "BULLISH" if c[i-1] > o[i-1] else "BEARISH"
            out.append(PricePattern("Inside Bar", direction, 6, i,
                "Current candle inside prior range — coiling before directional breakout"))

    # 7 — Outside Bar
    if n >= 2:
        i = n - 1
        if h[i] > h[i-1] and l[i] < l[i-1]:
            direction = "BULLISH" if c[i] > o[i] else "BEARISH"
            out.append(PricePattern("Outside Bar", direction, 7, i,
                "Current candle engulfs prior range — high momentum indecision / continuation"))

    # 8 — Morning Star
    if n >= 3:
        i = n - 1
        if (c[i-2] < o[i-2] and body(i-2) > rng(i-2) * 0.5
                and body(i-1) < rng(i-1) * 0.3
                and c[i] > o[i] and c[i] > (o[i-2] + c[i-2]) / 2):
            out.append(PricePattern("Morning Star", "BULLISH", 9, i,
                "3-candle bullish reversal — seller exhaustion, buyers reclaiming"))

    # 9 — Evening Star
    if n >= 3:
        i = n - 1
        if (c[i-2] > o[i-2] and body(i-2) > rng(i-2) * 0.5
                and body(i-1) < rng(i-1) * 0.3
                and c[i] < o[i] and c[i] < (o[i-2] + c[i-2]) / 2):
            out.append(PricePattern("Evening Star", "BEARISH", 9, i,
                "3-candle bearish reversal — buyer exhaustion, sellers reclaiming"))

    # 10 — Consolidation Breakout
    if n >= 12:
        lb = 5
        lo_range = np.mean([rng(j) for j in range(n - 1 - lb, n - 1)])
        avg_range = np.mean([rng(j) for j in range(max(0, n - 20), n)])
        if lo_range < avg_range * 0.5 and rng(n-1) > avg_range * 1.5:
            rec_hi = h[n-1-lb:n-1].max()
            rec_lo = l[n-1-lb:n-1].min()
            direction = ("BULLISH" if c[n-1] > rec_hi
                         else "BEARISH" if c[n-1] < rec_lo
                         else "NEUTRAL")
            if direction != "NEUTRAL":
                out.append(PricePattern("Consolidation Breakout", direction, 9, n-1,
                    "Tight range followed by strong expansion — coil released"))

    # 11 — Break and Retest
    if n >= 10:
        lb = 8
        prev_hi = h[n-1-lb:n-3].max()
        if h[n-3] > prev_hi and l[n-1] > prev_hi * 0.995 and c[n-1] > c[n-2]:
            out.append(PricePattern("Break and Retest (Bullish)", "BULLISH", 10, n-1,
                "Resistance broken, retested from above, now bouncing — BnR confirmed"))
        prev_lo = l[n-1-lb:n-3].min()
        if l[n-3] < prev_lo and h[n-1] < prev_lo * 1.005 and c[n-1] < c[n-2]:
            out.append(PricePattern("Break and Retest (Bearish)", "BEARISH", 10, n-1,
                "Support broken, retested from below, now falling — BnR confirmed"))

    # 12 — Flag / Pennant (continuation)
    if n >= 12:
        pole_move = (c[n-6] - c[n-11]) / max(abs(c[n-11]), 1e-10) * 100 if n >= 11 else 0
        retrace   = (c[n-1] - c[n-6]) / max(abs(c[n-6] - c[n-11]), 1e-10) if n >= 11 else 0
        if pole_move > 3 and -0.6 < retrace < 0:
            out.append(PricePattern("Bull Flag", "BULLISH", 8, n-1,
                "Strong upward pole then orderly pullback — continuation setup"))
        elif pole_move < -3 and 0 < retrace < 0.6:
            out.append(PricePattern("Bear Flag", "BEARISH", 8, n-1,
                "Strong downward pole then orderly pullback — continuation setup"))

    return out


def find_key_levels(df: pd.DataFrame, spot: float) -> list[KeyLevel]:
    """PDH/PDL, PWH/PWL, round number levels near spot."""
    levels: list[KeyLevel] = []
    if len(df) < 2:
        return levels

    # PDH / PDL
    prev = df.iloc[-2]
    levels += [
        KeyLevel(float(prev["High"]), "PDH", 8, f"Previous Day High: {prev['High']:.2f}"),
        KeyLevel(float(prev["Low"]),  "PDL", 8, f"Previous Day Low:  {prev['Low']:.2f}"),
    ]

    # PWH / PWL (use last 5 sessions before yesterday)
    if len(df) >= 7:
        wk = df.iloc[-7:-1]
        levels += [
            KeyLevel(float(wk["High"].max()), "PWH", 7, f"Previous Week High: {wk['High'].max():.2f}"),
            KeyLevel(float(wk["Low"].min()),  "PWL", 7, f"Previous Week Low:  {wk['Low'].min():.2f}"),
        ]

    # Round number levels
    if spot > 0:
        interval = (100 if spot > 20_000 else
                    50  if spot > 5_000  else
                    50  if spot > 1_000  else
                    20  if spot > 500    else 10)
        lo = (spot // interval) * interval
        for rnd in [lo - interval, lo, lo + interval, lo + 2 * interval]:
            if rnd > 0 and abs(rnd - spot) / spot * 100 < 5:
                levels.append(KeyLevel(rnd, "ROUND", 5, f"Psychological level: {rnd:.0f}"))

    # Sort: first by significance desc, then proximity to spot
    levels.sort(key=lambda x: (-x.significance, abs(x.price - spot) if spot > 0 else 0))
    return levels


def _obv_trend(df: pd.DataFrame) -> str:
    if "Volume" not in df.columns or len(df) < 10:
        return "FLAT"
    try:
        c = df["Close"].values
        v = df["Volume"].values
        obv = np.zeros(len(c))
        for i in range(1, len(c)):
            obv[i] = obv[i-1] + (v[i] if c[i] > c[i-1] else -v[i] if c[i] < c[i-1] else 0)
        recent = obv[-10:]
        if recent[-1] > recent[0] * 1.01:
            return "UP"
        if recent[-1] < recent[0] * 0.99:
            return "DOWN"
    except Exception:
        pass
    return "FLAT"


def _volume_signal(df: pd.DataFrame) -> str:
    if "Volume" not in df.columns or len(df) < 5:
        return "NEUTRAL"
    try:
        avg = df["Volume"].iloc[:-1].mean()
        last = df["Volume"].iloc[-1]
        if last > avg * 1.5:
            return "BULLISH" if df["Close"].iloc[-1] > df["Close"].iloc[-2] else "BEARISH"
        if last < avg * 0.5:
            return "DRY_UP"
    except Exception:
        pass
    return "NEUTRAL"


# ── Per-timeframe analyser ─────────────────────────────────────────────────────

def _analyse_tf(df: pd.DataFrame, include_cpr: bool = False) -> Optional[TimeframeAnalysis]:
    if df is None or df.empty:
        return None

    # Flatten MultiIndex columns (yfinance quirk)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)

    df = df.ffill().dropna(subset=["Close", "High", "Low", "Open"])
    if len(df) < 5:
        return None

    trend, ema20, ema50, ema200 = detect_trend(df)
    spot = float(df["Close"].iloc[-1])

    # EMA alignment flags
    ema_aligned   = (ema20 > ema50) if (ema20 > 0 and ema50 > 0) else False
    ema_full_bull = (spot > ema20 > ema50) and (ema200 == 0.0 or ema50 > ema200)
    ema_full_bear = (spot < ema20 < ema50) and (ema200 == 0.0 or ema50 < ema200)

    return TimeframeAnalysis(
        trend=trend,
        ema20=round(ema20, 2),
        ema50=round(ema50, 2),
        ema200=round(ema200, 2),
        last_close=round(spot, 2),
        adx=round(_adx(df), 2),
        ema_aligned=ema_aligned,
        ema_full_bull=ema_full_bull,
        ema_full_bear=ema_full_bear,
        structure=detect_market_structure(df),
        patterns=detect_price_action_patterns(df),
        key_levels=find_key_levels(df, spot),
        volume_signal=_volume_signal(df),
        cpr=calculate_cpr(df) if include_cpr else None,
        rsi=round(_rsi(df["Close"]), 2),
        obv_trend=_obv_trend(df),
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_symbol_mtf(symbol: str) -> MTFAnalysis:
    """
    Download 4 timeframes (monthly/weekly/daily/hourly) via yfinance and run
    structured MTF analysis. NSE stocks get .NS suffix; indices use ^ tickers.
    """
    if not _YF_AVAILABLE:
        return MTFAnalysis(
            symbol=symbol, timestamp=datetime.now().isoformat(),
            monthly=None, weekly=None, daily=None, hourly=None,
            overall_trend="SIDEWAYS", alignment_count=0,
            error="yfinance not installed — pip install yfinance",
        )

    ticker = _INDEX_MAP.get(symbol.upper(), f"{symbol.upper()}.NS")

    _tf_cfg = [
        ("monthly", dict(period="5y",  interval="1mo"), False),
        ("weekly",  dict(period="2y",  interval="1wk"), False),
        ("daily",   dict(period="1y",  interval="1d"),  True),
        ("hourly",  dict(period="60d", interval="1h"),  False),
    ]

    import time

    def _download_with_retry(tkr: str, retries: int = 2, **kwargs):
        for attempt in range(retries + 1):
            try:
                df = yf.download(tkr, progress=False, auto_adjust=True, **kwargs)
                if df is not None and not df.empty:
                    return df
                return None
            except Exception as exc:
                if attempt < retries and "rate" in str(exc).lower():
                    time.sleep(3 * (attempt + 1))
                else:
                    raise
        return None

    results: dict[str, Optional[TimeframeAnalysis]] = {}
    for name, kwargs, cpr in _tf_cfg:
        try:
            df = _download_with_retry(ticker, **kwargs)
            results[name] = _analyse_tf(df, include_cpr=cpr) if df is not None else None
        except Exception as exc:
            logger.debug("MTF %s %s failed: %s", name, symbol, exc)
            results[name] = None

    # Overall trend + alignment count
    target_trends = {tf: (results[tf].trend if results[tf] else "SIDEWAYS")
                     for tf in ["monthly", "weekly", "daily", "hourly"]}
    up   = sum(1 for t in target_trends.values() if t == "UPTREND")
    down = sum(1 for t in target_trends.values() if t == "DOWNTREND")

    if up >= 3:
        overall, align = "UPTREND", up
    elif down >= 3:
        overall, align = "DOWNTREND", down
    else:
        overall, align = "SIDEWAYS", max(up, down)

    return MTFAnalysis(
        symbol=symbol,
        timestamp=datetime.now().isoformat(),
        monthly=results["monthly"],
        weekly=results["weekly"],
        daily=results["daily"],
        hourly=results["hourly"],
        overall_trend=overall,
        alignment_count=align,
    )
