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
        "name": "Symmetrical Triangle",
        "category": "Continuation",
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
        "name": "Falling Wedge",
        "category": "Reversal",
        "direction": "Bullish",
        "generator": _falling_wedge,
        "description": "Both trendlines slope down but converge. Selling pressure exhausting — usually breaks up.",
        "when_to_trade": "Buy on close above the upper wedge line.",
        "target_rule": "Project the wedge's widest height upward.",
        "stop": "Below the most recent low.",
        "confidence_factors": ["Multiple touches on both lines", "Volume declining inside, rising on breakout", "Bullish RSI divergence"],
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
        "category": "Continuation",
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
]


def get_pattern_by_name(name: str) -> dict | None:
    for p in PATTERN_LIBRARY:
        if p["name"].lower() == name.lower():
            return p
    return None


def all_pattern_names() -> list:
    return [p["name"] for p in PATTERN_LIBRARY]
