"""
Candle pattern detector for the live scanner.
Checks the most recent 1-3 bars for actionable trigger patterns.
Returns a PatternSignal with name, direction, and strength (1-3).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PatternSignal:
    name: str         # e.g. "Bullish Engulfing"
    direction: str    # "bullish" | "bearish" | "neutral"
    strength: int     # 1=weak 2=medium 3=strong

    @property
    def points(self) -> int:
        """Candle trigger score contribution (max 25)."""
        return {1: 8, 2: 16, 3: 25}.get(self.strength, 0)


NO_PATTERN = PatternSignal("None", "neutral", 0)


# ─────────────────────────────────────────────────────────────────────────────
# Individual pattern checks
# ─────────────────────────────────────────────────────────────────────────────

def _body(c: pd.Series) -> float:
    return abs(float(c["close"]) - float(c["open"]))

def _upper_wick(c: pd.Series) -> float:
    return float(c["high"]) - max(float(c["open"]), float(c["close"]))

def _lower_wick(c: pd.Series) -> float:
    return min(float(c["open"]), float(c["close"])) - float(c["low"])

def _is_bullish(c: pd.Series) -> bool:
    return float(c["close"]) > float(c["open"])

def _is_bearish(c: pd.Series) -> bool:
    return float(c["close"]) < float(c["open"])


def _bullish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    return (
        _is_bearish(prev)
        and _is_bullish(curr)
        and float(curr["open"]) <= float(prev["close"])
        and float(curr["close"]) >= float(prev["open"])
        and _body(curr) >= _body(prev)
    )

def _bearish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    return (
        _is_bullish(prev)
        and _is_bearish(curr)
        and float(curr["open"]) >= float(prev["close"])
        and float(curr["close"]) <= float(prev["open"])
        and _body(curr) >= _body(prev)
    )

def _hammer(c: pd.Series) -> bool:
    b = _body(c)
    if b == 0:
        return False
    return _lower_wick(c) >= 2.0 * b and _upper_wick(c) < b

def _shooting_star(c: pd.Series) -> bool:
    b = _body(c)
    if b == 0:
        return False
    return _upper_wick(c) >= 2.0 * b and _lower_wick(c) < b

def _marubozu_bull(c: pd.Series) -> bool:
    b = _body(c)
    if b == 0:
        return False
    return (
        _is_bullish(c)
        and _lower_wick(c) < 0.1 * b
        and _upper_wick(c) < 0.1 * b
    )

def _marubozu_bear(c: pd.Series) -> bool:
    b = _body(c)
    if b == 0:
        return False
    return (
        _is_bearish(c)
        and _upper_wick(c) < 0.1 * b
        and _lower_wick(c) < 0.1 * b
    )

def _inside_bar_bull(mother: pd.Series, inside: pd.Series, breakout: pd.Series) -> bool:
    """Inside bar + breakout above mother high."""
    is_inside = (
        float(inside["high"]) <= float(mother["high"])
        and float(inside["low"]) >= float(mother["low"])
    )
    return is_inside and float(breakout["close"]) > float(mother["high"])

def _inside_bar_bear(mother: pd.Series, inside: pd.Series, breakdown: pd.Series) -> bool:
    is_inside = (
        float(inside["high"]) <= float(mother["high"])
        and float(inside["low"]) >= float(mother["low"])
    )
    return is_inside and float(breakdown["close"]) < float(mother["low"])

def _morning_star(c1: pd.Series, c2: pd.Series, c3: pd.Series) -> bool:
    """Classic 3-bar reversal: big bearish → small doji/body → big bullish."""
    gap_down = float(c2["open"]) < float(c1["close"])
    return (
        _is_bearish(c1) and _body(c1) > 0
        and _body(c2) < 0.3 * _body(c1)
        and gap_down
        and _is_bullish(c3)
        and float(c3["close"]) > (float(c1["open"]) + float(c1["close"])) / 2
    )

def _evening_star(c1: pd.Series, c2: pd.Series, c3: pd.Series) -> bool:
    gap_up = float(c2["open"]) > float(c1["close"])
    return (
        _is_bullish(c1) and _body(c1) > 0
        and _body(c2) < 0.3 * _body(c1)
        and gap_up
        and _is_bearish(c3)
        and float(c3["close"]) < (float(c1["open"]) + float(c1["close"])) / 2
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main detector: check the last bar and up to 2 bars before it
# ─────────────────────────────────────────────────────────────────────────────

def detect(df: pd.DataFrame, i: int | None = None) -> PatternSignal:
    """
    Detect the most significant pattern ending at bar index i
    (defaults to last bar).
    Priority: 3-bar patterns > 2-bar patterns > 1-bar patterns.
    """
    if i is None:
        i = len(df) - 1
    if i < 2 or i >= len(df):
        return NO_PATTERN

    c0 = df.iloc[i - 2]  # two bars ago
    c1 = df.iloc[i - 1]  # previous bar
    c2 = df.iloc[i]      # current / trigger bar

    # ── 3-bar patterns (strongest) ──────────────────────────────────────────
    if _morning_star(c0, c1, c2):
        return PatternSignal("Morning Star", "bullish", 3)
    if _evening_star(c0, c1, c2):
        return PatternSignal("Evening Star", "bearish", 3)

    # ── Inside-bar breakout / breakdown ─────────────────────────────────────
    if _inside_bar_bull(c0, c1, c2):
        return PatternSignal("Inside Bar Breakout", "bullish", 2)
    if _inside_bar_bear(c0, c1, c2):
        return PatternSignal("Inside Bar Breakdown", "bearish", 2)

    # ── 2-bar engulfing ──────────────────────────────────────────────────────
    if _bullish_engulfing(c1, c2):
        return PatternSignal("Bullish Engulfing", "bullish", 3)
    if _bearish_engulfing(c1, c2):
        return PatternSignal("Bearish Engulfing", "bearish", 3)

    # ── 1-bar single candles ─────────────────────────────────────────────────
    if _hammer(c2):
        return PatternSignal("Hammer / Pin Bar", "bullish", 2)
    if _shooting_star(c2):
        return PatternSignal("Shooting Star", "bearish", 2)
    if _marubozu_bull(c2):
        return PatternSignal("Bullish Marubozu", "bullish", 2)
    if _marubozu_bear(c2):
        return PatternSignal("Bearish Marubozu", "bearish", 2)

    return NO_PATTERN
