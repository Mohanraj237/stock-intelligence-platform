"""
Procedurally generates synthetic OHLCV time-series that visually demonstrate
each chart pattern, for the Learn page. Returns a pandas DataFrame ready
to be plotted as a candlestick chart.

Each generator returns ~100 candles with realistic noise + the target pattern
visible in the last ~30 candles.
"""
from __future__ import annotations
import math
from typing import Callable, Dict
import numpy as np
import pandas as pd

_RNG = np.random.default_rng(42)


def _make_df(closes: np.ndarray, vol_base: float = 1.0) -> pd.DataFrame:
    """Convert a close series into OHLCV with realistic intraday wicks."""
    n = len(closes)
    rng = np.random.default_rng(7)
    daily_range = np.abs(rng.normal(0, 0.012, n)) * closes  # ~1.2% range
    opens  = np.empty(n)
    highs  = np.empty(n)
    lows   = np.empty(n)
    opens[0] = closes[0]
    for i in range(1, n):
        opens[i] = closes[i-1] + rng.normal(0, 0.003) * closes[i-1]
    for i in range(n):
        body_hi = max(opens[i], closes[i])
        body_lo = min(opens[i], closes[i])
        highs[i] = body_hi + abs(rng.normal(0, 0.4)) * daily_range[i]
        lows[i]  = body_lo - abs(rng.normal(0, 0.4)) * daily_range[i]
    volume = vol_base * (1 + rng.normal(0, 0.4, n))
    volume = np.clip(volume, 0.3, None) * 1e6
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                         "Close": closes, "Volume": volume}, index=dates)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern generators — each returns OHLCV
# ─────────────────────────────────────────────────────────────────────────────
def _bull_flag() -> pd.DataFrame:
    n = 100
    base = 100
    rally = np.linspace(base, base * 1.25, 40)
    pull  = np.linspace(base * 1.25, base * 1.18, 25)
    pull += np.linspace(0, 0, 25) + _RNG.normal(0, 0.5, 25)
    breakout = np.linspace(base * 1.18, base * 1.40, 35)
    closes = np.concatenate([rally, pull, breakout])
    return _make_df(closes)


def _bear_flag() -> pd.DataFrame:
    base = 100
    drop = np.linspace(base, base * 0.78, 40)
    pull = np.linspace(base * 0.78, base * 0.84, 25) + _RNG.normal(0, 0.4, 25)
    breakdown = np.linspace(base * 0.84, base * 0.62, 35)
    return _make_df(np.concatenate([drop, pull, breakdown]))


def _ascending_triangle() -> pd.DataFrame:
    n = 100
    base = 100
    res = base * 1.15
    closes = np.empty(n)
    for i in range(n):
        progress = i / n
        bottom = base * (1 + 0.10 * progress)
        amp = max(0.06 * (1 - progress), 0.02)
        cycle = (math.sin(i * 0.55) + 1) / 2
        closes[i] = bottom + amp * cycle * base
        if closes[i] > res:
            closes[i] = res - _RNG.uniform(0, 0.5)
    # Breakout
    closes[-15:] = np.linspace(res, res * 1.12, 15)
    return _make_df(closes)


def _descending_triangle() -> pd.DataFrame:
    n = 100
    base = 100
    sup = base * 0.88
    closes = np.empty(n)
    for i in range(n):
        progress = i / n
        top = base * (1 - 0.10 * progress)
        amp = max(0.06 * (1 - progress), 0.02)
        cycle = (math.sin(i * 0.55) + 1) / 2
        closes[i] = top - amp * cycle * base
        if closes[i] < sup:
            closes[i] = sup + _RNG.uniform(0, 0.5)
    closes[-15:] = np.linspace(sup, sup * 0.88, 15)
    return _make_df(closes)


def _symmetrical_triangle() -> pd.DataFrame:
    n = 100
    base = 100
    closes = np.empty(n)
    for i in range(n):
        progress = i / n
        amp = max(0.10 * (1 - progress), 0.015)
        cycle = math.sin(i * 0.55)
        closes[i] = base + amp * cycle * base
    closes[-12:] = np.linspace(base, base * 1.10, 12)
    return _make_df(closes)


def _double_bottom() -> pd.DataFrame:
    n = 100
    base = 100
    drop1 = np.linspace(base * 1.05, base * 0.85, 18)
    bounce1 = np.linspace(base * 0.85, base * 0.97, 12)
    drop2 = np.linspace(base * 0.97, base * 0.85, 14)
    bounce2 = np.linspace(base * 0.85, base * 1.18, 30)
    head = np.full(26, base * 1.05) + _RNG.normal(0, 0.6, 26)
    closes = np.concatenate([head, drop1, bounce1, drop2, bounce2])
    return _make_df(closes)


def _double_top() -> pd.DataFrame:
    n = 100
    base = 100
    rally1 = np.linspace(base * 0.92, base * 1.12, 18)
    drop1  = np.linspace(base * 1.12, base * 1.02, 12)
    rally2 = np.linspace(base * 1.02, base * 1.12, 14)
    drop2  = np.linspace(base * 1.12, base * 0.85, 30)
    base_p = np.full(26, base * 0.92) + _RNG.normal(0, 0.5, 26)
    return _make_df(np.concatenate([base_p, rally1, drop1, rally2, drop2]))


def _head_and_shoulders() -> pd.DataFrame:
    base = 100
    rise = np.linspace(base * 0.88, base * 1.06, 14)   # left shoulder up
    drop1 = np.linspace(base * 1.06, base * 0.96, 8)   # neckline
    head = np.linspace(base * 0.96, base * 1.16, 12)   # head up
    drop2 = np.linspace(base * 1.16, base * 0.96, 12)  # neckline
    rs = np.linspace(base * 0.96, base * 1.06, 10)     # right shoulder
    breakdown = np.linspace(base * 1.06, base * 0.78, 30)
    intro = np.full(14, base * 0.88) + _RNG.normal(0, 0.4, 14)
    return _make_df(np.concatenate([intro, rise, drop1, head, drop2, rs, breakdown]))


def _inverse_head_and_shoulders() -> pd.DataFrame:
    base = 100
    drop = np.linspace(base * 1.12, base * 0.94, 14)   # left shoulder down
    rise1 = np.linspace(base * 0.94, base * 1.04, 8)
    head = np.linspace(base * 1.04, base * 0.84, 12)   # head down
    rise2 = np.linspace(base * 0.84, base * 1.04, 12)
    rs = np.linspace(base * 1.04, base * 0.94, 10)     # right shoulder
    breakout = np.linspace(base * 0.94, base * 1.22, 30)
    intro = np.full(14, base * 1.12) + _RNG.normal(0, 0.4, 14)
    return _make_df(np.concatenate([intro, drop, rise1, head, rise2, rs, breakout]))


def _cup_and_handle() -> pd.DataFrame:
    base = 100
    intro = np.linspace(base * 0.95, base * 1.08, 10)
    cup = base * 1.08 - 0.20 * base * np.sin(np.linspace(0, math.pi, 50))
    handle = np.linspace(cup[-1], cup[-1] - 0.04 * base, 15) + _RNG.normal(0, 0.4, 15)
    breakout = np.linspace(handle[-1], handle[-1] + 0.18 * base, 25)
    return _make_df(np.concatenate([intro, cup, handle, breakout]))


def _rounding_bottom() -> pd.DataFrame:
    base = 100
    n = 100
    x = np.linspace(-1, 1, n)
    bowl = base * (1 - 0.18 * (1 - x ** 2))
    bowl[-15:] = np.linspace(bowl[-15], bowl[-15] * 1.18, 15)
    return _make_df(bowl)


def _rising_wedge() -> pd.DataFrame:
    n = 100
    closes = np.empty(n)
    for i in range(n):
        progress = i / n
        mid = 100 + progress * 20
        amp = max(8 - progress * 7, 1.5)
        cycle = math.sin(i * 0.55)
        closes[i] = mid + amp * cycle * 0.5
    closes[-12:] = np.linspace(closes[-12], closes[-12] * 0.85, 12)
    return _make_df(closes)


def _falling_wedge() -> pd.DataFrame:
    n = 100
    closes = np.empty(n)
    for i in range(n):
        progress = i / n
        mid = 120 - progress * 18
        amp = max(8 - progress * 7, 1.5)
        cycle = math.sin(i * 0.55)
        closes[i] = mid + amp * cycle * 0.5
    closes[-12:] = np.linspace(closes[-12], closes[-12] * 1.20, 12)
    return _make_df(closes)


def _rectangle_breakout() -> pd.DataFrame:
    n = 100
    closes = np.empty(n)
    box_lo, box_hi = 95, 105
    for i in range(n - 15):
        cycle = math.sin(i * 0.5)
        closes[i] = (box_lo + box_hi) / 2 + 4 * cycle + _RNG.normal(0, 0.4)
    closes[n - 15:] = np.linspace(box_hi, box_hi * 1.18, 15)
    return _make_df(closes)


def _channel_breakout() -> pd.DataFrame:
    n = 100
    closes = np.empty(n)
    for i in range(n - 12):
        progress = i / n
        mid = 95 + 12 * progress
        cycle = math.sin(i * 0.45)
        closes[i] = mid + 4 * cycle
    closes[-12:] = np.linspace(closes[-13] + 6, closes[-13] + 22, 12)
    return _make_df(closes)


def _hammer() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 0.85, n - 5)
    closes = np.concatenate([closes, np.linspace(closes[-1], closes[-1] * 1.06, 5)])
    df = _make_df(closes)
    # Force last candle to look like hammer
    last = df.index[-1]
    body_open = df.loc[last, "Open"]
    body_close = df.loc[last, "Close"]
    df.loc[last, "Low"] = min(body_open, body_close) * 0.96
    df.loc[last, "High"] = max(body_open, body_close) * 1.005
    return df


def _shooting_star() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 1.18, n - 5)
    closes = np.concatenate([closes, np.linspace(closes[-1], closes[-1] * 0.95, 5)])
    df = _make_df(closes)
    last = df.index[-1]
    body_open = df.loc[last, "Open"]
    body_close = df.loc[last, "Close"]
    df.loc[last, "High"] = max(body_open, body_close) * 1.04
    df.loc[last, "Low"] = min(body_open, body_close) * 0.998
    return df


def _bullish_engulfing() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 0.88, n - 1)
    closes = np.append(closes, closes[-1] * 1.06)
    df = _make_df(closes)
    return df


def _bearish_engulfing() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 1.12, n - 1)
    closes = np.append(closes, closes[-1] * 0.94)
    return _make_df(closes)


def _morning_star() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 0.86, n - 3)
    star = closes[-1] * 0.99
    rev1 = closes[-1] * 1.02
    rev2 = closes[-1] * 1.10
    closes = np.concatenate([closes, [star, rev1, rev2]])
    return _make_df(closes)


def _evening_star() -> pd.DataFrame:
    base = 100
    n = 80
    closes = np.linspace(base, base * 1.14, n - 3)
    star = closes[-1] * 1.01
    rev1 = closes[-1] * 0.98
    rev2 = closes[-1] * 0.90
    return _make_df(np.concatenate([closes, [star, rev1, rev2]]))


def _flat_top_breakout() -> pd.DataFrame:
    """Generic accumulation breakout."""
    n = 100
    closes = np.empty(n)
    res = 105
    for i in range(n - 15):
        cycle = math.sin(i * 0.7)
        closes[i] = 100 + 4 * cycle
        if closes[i] > res:
            closes[i] = res - _RNG.uniform(0, 0.5)
    closes[-15:] = np.linspace(res, res * 1.20, 15)
    return _make_df(closes, vol_base=1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern catalogue
# ─────────────────────────────────────────────────────────────────────────────
PATTERN_LIBRARY: list = [
    {
        "name": "Bull Flag",
        "category": "Trend Continuation",
        "direction": "Bullish",
        "generator": _bull_flag,
        "description": (
            "A short-term consolidation against the trend after a sharp rally. "
            "Forms a small downward-sloping channel (the 'flag') after the strong "
            "advance (the 'flagpole'). Resolves with a continuation breakout."
        ),
        "when_to_trade": "Enter on breakout above the flag's upper trendline, ideally with above-average volume.",
        "target_rule": "Project the height of the flagpole upward from the breakout level.",
        "stop": "Below the lowest point of the flag.",
        "confidence_factors": [
            "Sharper, steeper flagpole = higher conviction",
            "Tighter flag (small price range) = stronger setup",
            "Volume should dry up during the flag, expand on breakout",
        ],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Bear Flag",
        "category": "Trend Continuation",
        "direction": "Bearish",
        "generator": _bear_flag,
        "description": "Opposite of bull flag — short rally inside a downtrend, then continuation lower.",
        "when_to_trade": "Short on breakdown of the flag's lower trendline with rising volume.",
        "target_rule": "Project the prior down move's height downward from the breakdown point.",
        "stop": "Above the highest point of the flag.",
        "confidence_factors": ["Steep prior decline", "Tight flag with low volume", "Breakdown on heavy volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Ascending Triangle",
        "category": "Continuation / Breakout",
        "direction": "Bullish",
        "generator": _ascending_triangle,
        "description": (
            "Flat horizontal resistance + rising support line. Buyers keep stepping "
            "in at higher lows while sellers defend the same price ceiling. Eventually buyers win."
        ),
        "when_to_trade": "Enter on close above the horizontal resistance with volume confirmation.",
        "target_rule": "Project the triangle's widest height above the breakout level.",
        "stop": "Below the most recent swing low inside the triangle.",
        "confidence_factors": [
            "At least 3 touches on the flat top",
            "Higher lows clearly visible",
            "Volume contracts inside, expands on breakout",
        ],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Descending Triangle",
        "category": "Continuation / Breakdown",
        "direction": "Bearish",
        "generator": _descending_triangle,
        "description": "Flat support + falling highs. Sellers chip away while buyers defend a fixed floor — usually breaks down.",
        "when_to_trade": "Short on close below the horizontal support.",
        "target_rule": "Project triangle height downward from breakdown.",
        "stop": "Above the most recent lower high.",
        "confidence_factors": ["Multiple touches on the flat bottom", "Clear lower highs", "Volume rises on breakdown"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Symmetrical Triangle Breakout",
        "category": "Continuation / Breakout",
        "direction": "Either",
        "generator": _symmetrical_triangle,
        "description": "Lower highs + higher lows converging. Volatility compresses; resolves in the direction of the prior trend (usually).",
        "when_to_trade": "Enter on close beyond either trendline; trade in the breakout direction.",
        "target_rule": "Project the triangle's widest height in the breakout direction.",
        "stop": "Other side of the triangle.",
        "confidence_factors": ["Clean trendlines with multiple touches", "Volume contraction inside", "Breakout volume confirmation"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Double Bottom",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": _double_bottom,
        "description": "'W' shape — price tests a low twice, fails to break it, then rallies. Classic reversal signal.",
        "when_to_trade": "Enter on close above the central peak (the 'neckline').",
        "target_rule": "Project the depth of the W upward from the neckline.",
        "stop": "Below the second bottom.",
        "confidence_factors": ["Two distinct lows at similar price", "Higher volume on the second bounce", "Rising RSI / bullish divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Double Top",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": _double_top,
        "description": "'M' shape — price hits a high twice, fails, drops. Sentiment reversal.",
        "when_to_trade": "Short on close below the trough between the two tops.",
        "target_rule": "Project the height of the M downward from the neckline.",
        "stop": "Above the second top.",
        "confidence_factors": ["Two highs at similar price", "Lower volume on the 2nd top", "Bearish RSI divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Head & Shoulders",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": _head_and_shoulders,
        "description": "Three peaks with the middle (head) higher than the outer two (shoulders). Major top-reversal pattern.",
        "when_to_trade": "Short on close below the neckline (line connecting the two troughs).",
        "target_rule": "Project the head-to-neckline distance downward from the breakdown.",
        "stop": "Above the right shoulder.",
        "confidence_factors": ["Clear symmetry between shoulders", "Volume highest on left shoulder, lowest on right", "Decisive neckline break"],
        "best_timeframes": "1d, 1w, 1mo",
    },
    {
        "name": "Inverse Head & Shoulders",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": _inverse_head_and_shoulders,
        "description": "H&S flipped — three troughs with the middle the lowest. Major bottom-reversal pattern.",
        "when_to_trade": "Enter on close above the neckline.",
        "target_rule": "Project head-to-neckline distance upward.",
        "stop": "Below the right shoulder.",
        "confidence_factors": ["Symmetric shoulders", "Volume rises on the right shoulder", "Strong neckline breakout"],
        "best_timeframes": "1d, 1w, 1mo",
    },
    {
        "name": "Cup & Handle",
        "category": "Continuation / Breakout",
        "direction": "Bullish",
        "generator": _cup_and_handle,
        "description": "Rounded 'U'-shaped base followed by a small drift-down 'handle'. Resolves with continuation breakout.",
        "when_to_trade": "Enter on breakout above the cup's rim (handle's top).",
        "target_rule": "Project the cup's depth above the breakout level.",
        "stop": "Below the handle's low.",
        "confidence_factors": ["Smooth, rounded cup (not V-shape)", "Handle in upper third of the cup", "Cup duration weeks-to-months"],
        "best_timeframes": "1w, 1mo",
    },
    {
        "name": "Rounding Bottom",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": _rounding_bottom,
        "description": "Long, slow, smooth basing pattern — accumulation by patient capital.",
        "when_to_trade": "Enter on breakout above the prior resistance area.",
        "target_rule": "Project the bowl's depth upward from breakout.",
        "stop": "Below the bowl's low.",
        "confidence_factors": ["Symmetric, smooth curve (no sharp Vs)", "Volume highest at the start and end of the bowl", "Long duration (months)"],
        "best_timeframes": "1w, 1mo",
    },
    {
        "name": "Rising Wedge",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": _rising_wedge,
        "description": "Both trendlines slope up but converge. Despite higher highs, momentum weakens — usually breaks down.",
        "when_to_trade": "Short on close below the lower wedge line.",
        "target_rule": "Project the wedge's widest height downward.",
        "stop": "Above the most recent peak.",
        "confidence_factors": ["Multiple touches on both lines", "Volume declining inside the wedge", "Bearish RSI divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Descending Wedge Breakout",
        "category": "Continuation / Breakout",
        "direction": "Bullish",
        "generator": _falling_wedge,
        "description": "Both trendlines slope down but converge. Selling pressure exhausts as range narrows — resolves with a bullish breakout above the upper line.",
        "when_to_trade": "Buy on close above the upper wedge line with expanding volume.",
        "target_rule": "Project the wedge's widest height upward from the breakout level.",
        "stop": "Below the most recent low inside the wedge.",
        "confidence_factors": ["Multiple touches on both lines", "Volume declining inside, expanding on breakout", "Bullish RSI divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Rectangle Breakout",
        "category": "Continuation / Breakout",
        "direction": "Either",
        "generator": _rectangle_breakout,
        "description": "Price oscillates between two parallel horizontal lines — accumulation or distribution range. Breakout = trend resumption.",
        "when_to_trade": "Enter on close beyond either bound, trade in breakout direction.",
        "target_rule": "Project the rectangle's height in the breakout direction.",
        "stop": "Other side of the rectangle.",
        "confidence_factors": ["At least 2 touches each side", "Volume contracts inside, surges on breakout", "Confirmed close beyond the bound"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Channel Breakout",
        "category": "Continuation / Breakout",
        "direction": "Either",
        "generator": _channel_breakout,
        "description": "Price moves inside a parallel sloping channel; breakout from the channel signals trend acceleration.",
        "when_to_trade": "Enter when price closes beyond the upper or lower channel line.",
        "target_rule": "Project channel width in the breakout direction.",
        "stop": "Inside the channel, beyond the most recent swing.",
        "confidence_factors": ["Clean parallel lines", "At least 3 touches each side", "Breakout on volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Hammer",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": _hammer,
        "description": "Single candle: small body at the top, long lower wick, little/no upper wick. Appears after a downtrend — buyers rejected lower prices.",
        "when_to_trade": "Buy after confirmation candle closes above the hammer's high.",
        "target_rule": "Use prior resistance or risk:reward 1:2.",
        "stop": "Below the hammer's low.",
        "confidence_factors": ["Lower wick at least 2× the body", "Forms at obvious support / oversold RSI", "Confirmation candle next day"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Shooting Star",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": _shooting_star,
        "description": "Inverse hammer at the top of an uptrend — long upper wick, small body. Sellers rejected higher prices.",
        "when_to_trade": "Short on confirmation candle closing below the shooting star's low.",
        "target_rule": "Prior support or 1:2 R:R.",
        "stop": "Above the shooting star's high.",
        "confidence_factors": ["Upper wick at least 2× body", "After extended uptrend / overbought RSI", "Bearish confirmation"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Bullish Engulfing",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": _bullish_engulfing,
        "description": "Large green candle whose body completely engulfs the prior red candle's body. Sentiment shift.",
        "when_to_trade": "Buy at engulfing candle close or on the next candle.",
        "target_rule": "Prior swing high.",
        "stop": "Below the engulfing candle's low.",
        "confidence_factors": ["Larger green body = stronger signal", "Higher volume on the engulfing candle", "At a known support area"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Bearish Engulfing",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": _bearish_engulfing,
        "description": "Large red candle whose body engulfs prior green candle's body. Sentiment shift down.",
        "when_to_trade": "Short at engulfing close or next candle.",
        "target_rule": "Prior swing low.",
        "stop": "Above the engulfing candle's high.",
        "confidence_factors": ["Big red body", "Volume spike", "At resistance / overbought"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Morning Star",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": _morning_star,
        "description": "Three-candle bottom-reversal: large red, small indecision (the 'star'), large green.",
        "when_to_trade": "Buy after the third (green) candle closes.",
        "target_rule": "Prior swing high or 1:2 R:R.",
        "stop": "Below the star's low.",
        "confidence_factors": ["Star has small body (any color)", "3rd candle closes above midpoint of 1st", "Volume rises on 3rd candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Evening Star",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": _evening_star,
        "description": "Three-candle top-reversal: large green, small star, large red.",
        "when_to_trade": "Short after 3rd (red) candle closes.",
        "target_rule": "Prior swing low.",
        "stop": "Above the star's high.",
        "confidence_factors": ["Small star body", "3rd candle closes below midpoint of 1st", "Volume on 3rd candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "52W High Breakout",
        "category": "Momentum / Breakout",
        "direction": "Bullish",
        "generator": _flat_top_breakout,
        "description": "Price breaks above the prior 52-week high — institutional momentum signal, often the start of a multi-month trend.",
        "when_to_trade": "Buy on close above the 52W high; ideally with volume > 1.5× average.",
        "target_rule": "Initial 8–10% above breakout; trail with rising 50 EMA.",
        "stop": "Below the breakout level (now-support).",
        "confidence_factors": ["Volume surge on breakout day", "Tight base before breakout", "Sector also strong"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Near 52W High",
        "category": "Momentum",
        "direction": "Bullish",
        "generator": None,
        "description": "Price is within 5% of its 52-week high, indicating strong momentum and potential for a fresh breakout.",
        "when_to_trade": "Enter on a close above the 52W high with above-average volume.",
        "target_rule": "Project prior consolidation height above the breakout.",
        "stop": "Below the most recent swing low.",
        "confidence_factors": ["Tight consolidation near the high", "Rising volume", "Sector strength"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Near 52W Low",
        "category": "Caution / Contrarian",
        "direction": "Bearish",
        "generator": None,
        "description": "Price is within 5% of its 52-week low — potential support but also a warning of continued weakness.",
        "when_to_trade": "Avoid fresh longs; only consider on strong reversal signals with volume.",
        "target_rule": "N/A (caution signal).",
        "stop": "Below the 52W low.",
        "confidence_factors": ["Declining volume near the low", "No bullish reversal candle", "Sector also weak"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Pullback to 20 EMA",
        "category": "Trend Continuation",
        "direction": "Bullish",
        "generator": None,
        "description": "In an uptrend, price pulls back to the 20-period EMA (dynamic support) and shows signs of a bounce. High-probability entry in trending stocks.",
        "when_to_trade": "Enter on the first bullish candle close after touching the 20 EMA.",
        "target_rule": "Prior swing high; risk:reward ≥ 2:1.",
        "stop": "Below the 20 EMA or the recent pullback low.",
        "confidence_factors": ["Rising EMA slope", "Low-volume pullback", "Bullish reversal candle at the EMA"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Pullback to 50 DMA",
        "category": "Trend Continuation",
        "direction": "Bullish",
        "generator": None,
        "description": "Price retraces to the 50-day moving average and finds support. A classic institutional re-entry level in medium-term uptrends.",
        "when_to_trade": "Buy on close above the bounce candle after touching the 50 DMA.",
        "target_rule": "Prior high or 10% target; trail with rising 50 DMA.",
        "stop": "A daily close below the 50 DMA.",
        "confidence_factors": ["Price bounced from 50 DMA before", "Rising 50 DMA slope", "Volume dries up on pullback"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Overbought Reversal",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "RSI drops from above 70 (overbought), signaling exhaustion of the prior uptrend and potential reversal lower.",
        "when_to_trade": "Short on bearish candle after RSI crosses below 70.",
        "target_rule": "Prior support or RSI 50 level.",
        "stop": "Above the recent swing high.",
        "confidence_factors": ["RSI divergence (price higher, RSI lower)", "Volume declining on rally", "Bearish candle on crossing"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Oversold Bounce",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "RSI rises from below 30 (oversold), signaling exhaustion of selling and potential mean-reversion bounce.",
        "when_to_trade": "Buy on bullish candle after RSI crosses above 30.",
        "target_rule": "Prior resistance or RSI 50 level.",
        "stop": "Below the recent swing low.",
        "confidence_factors": ["RSI divergence (price lower, RSI higher)", "Volume spike on down-days drying", "Bullish reversal candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Doji at Support",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "A Doji candle (open ≈ close) forms exactly at a key support level — buyers and sellers balanced, but support is holding. Needs bullish follow-through.",
        "when_to_trade": "Buy on the next candle closing above the Doji's high.",
        "target_rule": "Prior resistance or 1:2 R:R.",
        "stop": "Below the support zone.",
        "confidence_factors": ["Strong historical support level", "Low-volume Doji (indecision)", "High-volume bullish follow-through"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Doji at Resistance",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "A Doji forms at a resistance level — indecision after a rally, often preceding a reversal lower.",
        "when_to_trade": "Short on next candle closing below the Doji's low.",
        "target_rule": "Prior support or 1:2 R:R.",
        "stop": "Above the resistance zone.",
        "confidence_factors": ["Multiple prior touches of resistance", "High-volume Doji shows battle", "Bearish gap-down follow-through"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Gap Up with Volume",
        "category": "Momentum / Breakout",
        "direction": "Bullish",
        "generator": None,
        "description": "Price opens above the prior session's high with volume ≥ 1.5× average — a momentum surge driven by institutional participation.",
        "when_to_trade": "Buy on open confirmation (15-min rule) if price holds above gap level.",
        "target_rule": "Gap-fill risk defined by prior high; target = prior resistance.",
        "stop": "Below the gap's low (gap fills = trade invalid).",
        "confidence_factors": ["Volume ≥ 2× average", "Catalyst (earnings / news)", "Sector or market also up"],
        "best_timeframes": "1d",
    },
    {
        "name": "V Bottom",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "A sharp, steep decline followed by an equally sharp recovery — a 'V' shape on the chart. Indicates panic selling quickly absorbed by buyers.",
        "when_to_trade": "Enter after price recovers ≥ 70% of the decline and prints a bullish candle.",
        "target_rule": "Return to the pre-decline high.",
        "stop": "Below the 'V' bottom low.",
        "confidence_factors": ["Decline on volume, recovery on even higher volume", "No consolidation in recovery (sharp reversal)", "Catalyst resolved"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Trendline Breakout",
        "category": "Reversal / Continuation",
        "direction": "Either",
        "generator": None,
        "description": "Price breaks through a significant trendline connecting swing highs (for bearish break) or swing lows (for bullish break).",
        "when_to_trade": "Enter on the close that breaches the trendline; watch for a retest.",
        "target_rule": "Measure the prior swing amplitude and project in the breakout direction.",
        "stop": "Back on the other side of the trendline.",
        "confidence_factors": ["Trendline has ≥ 3 clean touches", "Volume surges on break", "RSI confirms with break of own trendline"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Ascending Channel",
        "category": "Continuation / Breakout",
        "direction": "Bullish",
        "generator": None,
        "description": "Price rises steadily inside two upward-sloping parallel trendlines. The lower line is dynamic support; the upper line is resistance. A bullish continuation pattern.",
        "when_to_trade": "Buy near the lower trendline on a bullish reversal candle; enter breakout above the upper line for acceleration trade.",
        "target_rule": "Target the upper trendline projection on a channel bounce; target channel width above the upper line on a breakout.",
        "stop": "Below the lower trendline (channel support break invalidates the pattern).",
        "confidence_factors": ["At least 3 clean touches on each trendline", "Volume dries up at upper line, expands at lower", "Overall market in uptrend"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Descending Channel",
        "category": "Continuation / Breakdown",
        "direction": "Bearish",
        "generator": None,
        "description": "Price falls steadily inside two downward-sloping parallel trendlines. The upper line is dynamic resistance; the lower line is support. A bearish continuation pattern.",
        "when_to_trade": "Short near the upper trendline on a bearish candle; use a breakdown below the lower line for acceleration entry.",
        "target_rule": "Target the lower trendline projection on a channel rally; target channel width below the lower line on a breakdown.",
        "stop": "Above the upper trendline (resistance break invalidates the bearish case).",
        "confidence_factors": ["At least 3 clean touches on each trendline", "Volume rises on down-days, dries on rallies", "Sector or market trend aligns"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Accumulation Phase",
        "category": "Support & Resistance",
        "direction": "Bullish",
        "generator": None,
        "description": "Price consolidates in a tight range at or near a support zone with shrinking volume — smart money is quietly buying. Precedes a bullish breakout.",
        "when_to_trade": "Enter on a breakout above the upper boundary of the range with expanding volume.",
        "target_rule": "Project the range height above the breakout; minimum 2:1 R:R.",
        "stop": "Below the lower boundary of the accumulation range.",
        "confidence_factors": ["Volume declining inside the range", "Multiple tests of support without breaking", "Price closes near the high of the range"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Distribution Phase",
        "category": "Support & Resistance",
        "direction": "Bearish",
        "generator": None,
        "description": "Price consolidates near a resistance zone with high but declining volume — smart money is distributing (selling) to retail buyers. Precedes a bearish breakdown.",
        "when_to_trade": "Short on a breakdown below the lower boundary of the range with high volume.",
        "target_rule": "Project the range height downward from the breakdown level.",
        "stop": "Above the upper boundary of the distribution range.",
        "confidence_factors": ["High volume during the range (distribution)", "Multiple failures to break above resistance", "Price closes near the low of the range"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Volume Surge on Breakout",
        "category": "Volume / Momentum",
        "direction": "Bullish",
        "generator": None,
        "description": "Volume spikes significantly (≥ 1.5× average) as price breaks through a key resistance level. Institutional conviction behind the move validates the breakout.",
        "when_to_trade": "Enter on the breakout candle close if volume is ≥ 1.5× the 20-day average.",
        "target_rule": "Project the prior range height above the breakout; first target at 1.5× ATR.",
        "stop": "Below the breakout level (failed breakout if volume doesn't confirm next session).",
        "confidence_factors": ["Volume ≥ 2× average is ideal", "Price closes in the upper half of the breakout candle", "Sector also breaking out"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Volume Dry Up",
        "category": "Volume / Momentum",
        "direction": "Neutral",
        "generator": None,
        "description": "Volume contracts sharply over several sessions — often signals the end of a selling wave (for bullish setup) or a pause before continuation. A low-volume pause inside a trend is constructive.",
        "when_to_trade": "Use as a filter: enter when price breaks out of the low-volume consolidation on a volume expansion candle.",
        "target_rule": "N/A alone — use with price pattern for target; expect a breakout of similar magnitude to the prior trend leg.",
        "stop": "Below the lowest close of the dry-up consolidation zone.",
        "confidence_factors": ["Volume well below 20-day average for 3+ sessions", "Price range contracting (NR7 or similar)", "Occurs inside an existing trend, not at a top/bottom"],
        "best_timeframes": "1d, 1w",
    },

    # ── Candlestick additions ────────────────────────────────────────────────
    {
        "name": "Inverted Hammer",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Forms after a downtrend: small body near the bottom, long upper wick (≥ 2× body), little/no lower wick. Buyers attempted a recovery — needs bullish follow-through to confirm.",
        "when_to_trade": "Buy on the next candle closing above the inverted hammer's high.",
        "target_rule": "Prior resistance or 1:2 R:R.",
        "stop": "Below the inverted hammer's low.",
        "confidence_factors": ["Long upper wick ≥ 2× the body", "At a clear support zone or oversold RSI", "Strong bullish confirmation next candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Dragonfly Doji",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Open = Close near the session high, with a long lower wick. Sellers pushed price down but buyers reclaimed all losses. Bullish signal at support.",
        "when_to_trade": "Buy on the next bullish candle closing above the Doji's high.",
        "target_rule": "Prior resistance level or 1:2 R:R from the Doji's high.",
        "stop": "Below the Doji's low (the day's rejection point).",
        "confidence_factors": ["Long lower wick ≥ 3× the body", "At a known support or demand zone", "Bullish confirmation with volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Hanging Man",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Visually identical to a Hammer but appears at the TOP of an uptrend. Small body near the high, long lower wick. The intraday weakness is a warning — bulls are losing control.",
        "when_to_trade": "Short on the next bearish candle closing below the Hanging Man's low.",
        "target_rule": "Prior swing low or 1:2 R:R.",
        "stop": "Above the Hanging Man's high.",
        "confidence_factors": ["At resistance or extended uptrend (overbought RSI)", "Lower wick ≥ 2× the body", "Bearish confirmation candle with volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Gravestone Doji",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Open = Close near the session low, with a long upper wick. Bulls pushed price up but bears wiped out all gains. Bearish signal at resistance.",
        "when_to_trade": "Short on the next bearish candle closing below the Gravestone's low.",
        "target_rule": "Prior support level or 1:2 R:R.",
        "stop": "Above the Gravestone's high.",
        "confidence_factors": ["Long upper wick ≥ 3× the body", "At a known resistance or supply zone", "Bearish confirmation with volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Doji",
        "category": "Candlestick — Reversal",
        "direction": "Neutral",
        "generator": None,
        "description": "Open and Close are equal (or nearly equal) — perfect indecision. A single Doji has no directional bias on its own; context (trend, key level, volume) determines significance.",
        "when_to_trade": "Use as a context signal only. Confirm direction with the next candle's close.",
        "target_rule": "N/A alone — depends on the confirming candle.",
        "stop": "Beyond the Doji's high or low depending on direction taken.",
        "confidence_factors": ["At a key support or resistance level", "After a prolonged trend (exhaustion)", "Follow-through candle is decisive"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Long-Legged Doji",
        "category": "Candlestick — Reversal",
        "direction": "Neutral",
        "generator": None,
        "description": "Extreme Doji with long upper AND lower wicks of roughly equal length. Maximum indecision — a fierce battle between bulls and bears with neither side winning.",
        "when_to_trade": "Treat as a reversal warning only at extreme levels. Confirm with the next candle.",
        "target_rule": "N/A alone.",
        "stop": "Beyond the full wick range of the Long-Legged Doji.",
        "confidence_factors": ["At a major support or resistance level", "After an extended trend", "High volume on the Doji session"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Spinning Top",
        "category": "Candlestick — Reversal",
        "direction": "Neutral",
        "generator": None,
        "description": "Small body with wicks on both sides. Less extreme than a Doji but signals indecision between buyers and sellers. Most useful as part of a multi-candle pattern.",
        "when_to_trade": "Not a standalone signal. Use in conjunction with support/resistance or inside a multi-candle pattern.",
        "target_rule": "N/A alone.",
        "stop": "Beyond the candle's range.",
        "confidence_factors": ["At a significant level (support/resistance)", "After a prolonged move", "Confirmed by the next candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Piercing",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Two-candle bottom reversal: large red candle followed by a green candle that opens below the prior red's close but closes above its midpoint. Buyers take control mid-session.",
        "when_to_trade": "Buy on the close of the piercing candle or the open of the next session.",
        "target_rule": "Top of the prior red candle or prior resistance level.",
        "stop": "Below the piercing candle's low.",
        "confidence_factors": ["Green candle closes above 50% of the red candle's body", "Occurs at support or after oversold RSI", "Volume rises on the piercing candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Tweezer Bottom",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Two consecutive candles (one red, one green) with matching lows at a support level. Price twice tested the same low and rejected it — buyers defended strongly.",
        "when_to_trade": "Buy on the close of the second (green) candle or on a break above its high.",
        "target_rule": "Prior resistance or 1:2 R:R from the entry.",
        "stop": "Below the matching lows (if broken, support is lost).",
        "confidence_factors": ["Matching lows at a clean support level", "Higher volume on the second candle", "Bullish RSI divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Dark Cloud Cover",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Two-candle top reversal: large green candle followed by a red candle that opens above the prior green's close but closes below its midpoint. Bears take control mid-session.",
        "when_to_trade": "Short on the close of the dark cloud candle or the open of the next session.",
        "target_rule": "Bottom of the prior green candle or prior support level.",
        "stop": "Above the dark cloud candle's high.",
        "confidence_factors": ["Red candle closes below 50% of the green candle's body", "At resistance or overbought RSI", "Volume rises on the dark cloud candle"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Tweezer Top",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Two consecutive candles with matching highs at a resistance level. Price twice tested the same high and was rejected — sellers defended strongly.",
        "when_to_trade": "Short on the close of the second (red) candle or on a break below its low.",
        "target_rule": "Prior support or 1:2 R:R from the entry.",
        "stop": "Above the matching highs.",
        "confidence_factors": ["Matching highs at a clean resistance zone", "Lower volume on the second candle", "Bearish RSI divergence"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Three White Soldiers",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Three consecutive large green candles, each opening within the prior body and closing near its high. Strong bullish momentum reversal from a low or base.",
        "when_to_trade": "Buy on the close of the third candle, or on the first pullback to the first soldier's body.",
        "target_rule": "Project the total height of the three-candle pattern upward from the close of the third candle.",
        "stop": "Below the low of the first soldier.",
        "confidence_factors": ["Each candle progressively larger or similar in size", "Volume rises across all three candles", "Occurs after a downtrend or at a key support"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Abandoned Baby Bottom",
        "category": "Candlestick — Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Three-candle extreme reversal: large red candle, then a gap-down Doji (completely isolated by gaps), then a gap-up large green candle. The Doji 'island' signals complete seller exhaustion.",
        "when_to_trade": "Buy on the close of the third (large green) candle.",
        "target_rule": "Return to the prior swing high before the decline.",
        "stop": "Below the Doji's low.",
        "confidence_factors": ["True gaps on both sides of the Doji", "High volume on the final green candle", "Prior steep decline before the pattern"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Three Black Crows",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Three consecutive large red candles, each opening within the prior body and closing near its low. Strong bearish momentum reversal from a high or distribution zone.",
        "when_to_trade": "Short on the close of the third candle, or on the first rally to the first crow's body.",
        "target_rule": "Project the total height of the pattern downward from the third candle's close.",
        "stop": "Above the high of the first crow.",
        "confidence_factors": ["Each candle closing near its low", "Volume rises across all three candles", "Occurs after an uptrend or at a key resistance"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Abandoned Baby Top",
        "category": "Candlestick — Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Three-candle extreme reversal: large green candle, then a gap-up Doji (isolated by gaps), then a gap-down large red candle. The Doji 'island' signals complete buyer exhaustion.",
        "when_to_trade": "Short on the close of the third (large red) candle.",
        "target_rule": "Return to the prior swing low before the rally.",
        "stop": "Above the Doji's high.",
        "confidence_factors": ["True gaps on both sides of the Doji", "High volume on the final red candle", "Prior steep rally before the pattern"],
        "best_timeframes": "1d, 1w",
    },

    # ── Price Action additions ────────────────────────────────────────────────
    {
        "name": "Inside Bar",
        "category": "Price Action",
        "direction": "Neutral",
        "generator": None,
        "description": "The current bar's entire high-low range falls within the prior bar's range. Volatility compression — the market is coiling before a directional move. Trade the breakout.",
        "when_to_trade": "Buy above the inside bar's high, or short below its low, on the next candle.",
        "target_rule": "2× the inside bar's range in the breakout direction.",
        "stop": "The opposite side of the inside bar (if long: below the low; if short: above the high).",
        "confidence_factors": ["Inside bar follows a strong trend candle (mother bar)", "Tight inside bar (small range vs mother bar)", "Volume contracts on the inside bar"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Outside Bar",
        "category": "Price Action",
        "direction": "Neutral",
        "generator": None,
        "description": "The current bar's high is higher AND low is lower than the prior bar. Volatility expansion showing a battle between both sides. Often a turning point or acceleration signal.",
        "when_to_trade": "Trade the breakout of the outside bar's range on the next candle, in the direction of the prior trend.",
        "target_rule": "2× the outside bar's range in the breakout direction.",
        "stop": "Mid-point of the outside bar.",
        "confidence_factors": ["Occurs at a key support or resistance level", "Strong close near the high (bullish) or low (bearish) of the outside bar", "Higher than average volume"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "NR7",
        "category": "Price Action",
        "direction": "Neutral",
        "generator": None,
        "description": "Narrow Range 7 — the current bar has the smallest high-low range of the last 7 bars. Extreme range compression typically precedes an explosive directional move.",
        "when_to_trade": "Buy above the NR7 bar's high or short below its low on the next candle's break.",
        "target_rule": "2–3× the NR7 range in the breakout direction.",
        "stop": "Opposite side of the NR7 bar.",
        "confidence_factors": ["NR7 follows a series of contracting ranges", "Volume also at a multi-bar low", "Occurs in the direction of the broader trend"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Fakey",
        "category": "Price Action",
        "direction": "Neutral",
        "generator": None,
        "description": "A false breakout of an inside bar's range — price briefly exceeds the boundary then reverses back inside. Traps breakout traders; sets up a high-probability move in the opposite direction.",
        "when_to_trade": "Enter in the opposite direction of the false break as price re-enters the inside bar's range.",
        "target_rule": "Prior swing in the reversal direction; minimum 2:1 R:R.",
        "stop": "Beyond the false breakout extreme (the pin-bar high or low).",
        "confidence_factors": ["Clear false breakout pin wick beyond the inside bar boundary", "Quick reversal back inside the range", "Occurs at a significant level (support / resistance)"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Breakout Retest",
        "category": "Price Action",
        "direction": "Neutral",
        "generator": None,
        "description": "After a confirmed breakout above resistance (or below support), price pulls back to the broken level which now acts as the opposite role (resistance becomes support, and vice versa). One of the highest-probability entries.",
        "when_to_trade": "Enter on a bullish confirming candle as price bounces from the retested level (or bearish candle on a re-test of broken support).",
        "target_rule": "2× the height of the prior breakout candle projected from the breakout level.",
        "stop": "Below the retested level (failed retest means the breakout was false).",
        "confidence_factors": ["Prior breakout was clean and on volume", "Retest is on lower volume (healthy)", "Price holds above (or below) the level on the retest candle"],
        "best_timeframes": "1d, 1w",
    },

    # ── Chart Pattern additions ──────────────────────────────────────────────
    {
        "name": "Bull Pennant",
        "category": "Trend Continuation",
        "direction": "Bullish",
        "generator": None,
        "description": "Like a Bull Flag but the consolidation forms a small symmetrical triangle (converging trendlines) instead of a parallel channel. Requires a strong prior 'flagpole' rally. High-momentum continuation.",
        "when_to_trade": "Enter on breakout above the upper converging trendline of the pennant, ideally with volume.",
        "target_rule": "Project the flagpole's height from the breakout point.",
        "stop": "Below the pennant's lowest point.",
        "confidence_factors": ["Steep flagpole rally (>15% in days)", "Tight, small pennant (volume contraction)", "Volume expands sharply on breakout"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Bear Pennant",
        "category": "Trend Continuation",
        "direction": "Bearish",
        "generator": None,
        "description": "A short consolidation forming a small converging triangle after a sharp decline. Bears pause before continuing lower. Continuation of a downtrend.",
        "when_to_trade": "Short on breakdown below the lower converging trendline with volume confirmation.",
        "target_rule": "Project the prior decline's height downward from the breakdown point.",
        "stop": "Above the pennant's highest point.",
        "confidence_factors": ["Steep prior decline (flagpole)", "Tight consolidation on low volume", "Breakdown candle with volume surge"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "High Tight Flag",
        "category": "Momentum / Breakout",
        "direction": "Bullish",
        "generator": None,
        "description": "A stock surges 100%+ in ≤8 weeks (the 'pole'), then consolidates 10–25% in a tight, brief flag. One of the rarest and most powerful continuation patterns — signals exceptional momentum.",
        "when_to_trade": "Buy on breakout above the flag's upper trendline; this pattern should be traded aggressively.",
        "target_rule": "100%+ target from the flag base — same distance as the flagpole.",
        "stop": "Below the lowest point of the tight consolidation.",
        "confidence_factors": ["Pole gain ≥ 100% in ≤8 weeks", "Flag correction ≤ 25% of the pole", "Volume surges on the breakout"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Rounding Top",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Long, slow, dome-shaped topping pattern — the mirror image of the Rounding Bottom. Distribution by patient sellers over months. Once the neckline breaks, the decline can be large.",
        "when_to_trade": "Short on breakdown below the prior support/neckline of the dome.",
        "target_rule": "Project the dome's height (peak to neckline) downward from the breakdown level.",
        "stop": "Above the dome's peak.",
        "confidence_factors": ["Smooth, symmetric dome shape (no sharp peaks)", "Volume highest at the start and declining at the top", "Long formation duration (months to a year)"],
        "best_timeframes": "1w, 1mo",
    },
    {
        "name": "Triple Bottom",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": None,
        "description": "Three distinct lows at a similar price level, each followed by a rally. Stronger institutional confirmation than a Double Bottom — buyers have defended the level three times.",
        "when_to_trade": "Enter on close above the highest peak between the three lows (neckline breakout).",
        "target_rule": "Project the depth of the pattern (neckline to bottom) upward from the neckline.",
        "stop": "Below the third bottom.",
        "confidence_factors": ["Three lows at similar price (within 3%)", "Volume highest on the third bounce", "RSI forms higher lows (divergence)"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Triple Top",
        "category": "Reversal",
        "direction": "Bearish",
        "generator": None,
        "description": "Three distinct highs at a similar price level, each followed by a decline. Stronger than Double Top — sellers have defended the level three times. Major resistance.",
        "when_to_trade": "Short on close below the lowest trough between the three highs (neckline breakdown).",
        "target_rule": "Project the pattern's height (top to neckline) downward from the breakdown.",
        "stop": "Above the third top.",
        "confidence_factors": ["Three highs within 3% of each other", "Volume declining on each successive high", "RSI forms lower highs (bearish divergence)"],
        "best_timeframes": "1d, 1w",
    },

    # ── Volume additions ─────────────────────────────────────────────────────
    {
        "name": "Selling Climax",
        "category": "Volume / Momentum",
        "direction": "Bullish",
        "generator": None,
        "description": "Extreme volume spike on a large red candle followed by a quick recovery (close near the open or a reversal candle). Panic selling exhausted — all weak hands shaken out. High-probability reversal zone.",
        "when_to_trade": "Buy on the next bullish candle closing above the climax bar's high. Wait for confirmation.",
        "target_rule": "Prior support / resistance zone before the panic decline.",
        "stop": "Below the selling climax candle's low (the panic low).",
        "confidence_factors": ["Volume 2–3× above the 20-day average", "Large wick on the bottom of the climax candle", "Next candle is decisively bullish"],
        "best_timeframes": "1d, 1w",
    },
    {
        "name": "Volume Breakdown",
        "category": "Volume / Momentum",
        "direction": "Bearish",
        "generator": None,
        "description": "Price breaks below a key support level with significantly above-average volume. Institutional selling is driving the move — this is not a shakeout but a genuine shift in supply/demand.",
        "when_to_trade": "Short on close below the support level if volume ≥ 1.5× the 20-day average.",
        "target_rule": "Next major support level or prior swing low; measured move = size of the base above the break.",
        "stop": "Above the broken support level (failed breakdown = re-enter above).",
        "confidence_factors": ["Volume ≥ 1.5× average on the breakdown candle", "Close well below the support (not just a wick)", "Sector or market also weak"],
        "best_timeframes": "1d, 1w",
    },

    # ── Harmonic / Experimental additions ───────────────────────────────────
    {
        "name": "Wyckoff Accumulation",
        "category": "Harmonic",
        "direction": "Bullish",
        "generator": None,
        "description": "Multi-phase institutional buying identified by Richard Wyckoff: Preliminary Support → Selling Climax → Automatic Rally → Secondary Test → Spring (shakeout) → Last Point of Support → Sign of Strength → breakout. Occurs over weeks to months.",
        "when_to_trade": "Enter at the Spring (final shakeout below support) with tight stop, or at the Last Point of Support on the markup phase.",
        "target_rule": "Measured move = height of the entire accumulation range projected upward from the breakout.",
        "stop": "Below the Spring low (shakeout point).",
        "confidence_factors": ["Clear Selling Climax with high volume", "Volume dries up in the trading range", "Spring/shakeout on low volume followed by strong recovery"],
        "best_timeframes": "1d, 1w, 1mo",
    },
    {
        "name": "Wyckoff Distribution",
        "category": "Harmonic",
        "direction": "Bearish",
        "generator": None,
        "description": "Multi-phase institutional selling: Preliminary Supply → Buying Climax → Automatic Reaction → Secondary Test → Upthrust After Distribution (UTAD) → Last Point of Supply → Sign of Weakness → breakdown. Occurs over weeks to months.",
        "when_to_trade": "Short at the Upthrust After Distribution (false breakout above resistance) or at the Last Point of Supply.",
        "target_rule": "Height of the distribution range projected downward from the breakdown level.",
        "stop": "Above the Upthrust high (UTAD level).",
        "confidence_factors": ["Buying Climax on extreme volume", "Volume dries up on rallies within the range", "Upthrust / UTAD reversal is sharp and decisive"],
        "best_timeframes": "1d, 1w, 1mo",
    },
]


def get_pattern_by_name(name: str) -> dict | None:
    for p in PATTERN_LIBRARY:
        if p["name"].lower() == name.lower():
            return p
    return None


def all_pattern_names() -> list:
    return [p["name"] for p in PATTERN_LIBRARY]
