"""Shared enums + base types — Timeframe is the single source of truth."""
from __future__ import annotations
from enum import Enum
from typing import Literal


class Timeframe(str, Enum):
    """The ONLY supported analysis timeframes. 1H is intentionally absent."""
    DAILY   = "1D"
    WEEKLY  = "1W"
    MONTHLY = "1M"


TIMEFRAME_TO_YF_INTERVAL = {
    Timeframe.DAILY:   "1d",
    Timeframe.WEEKLY:  "1wk",
    Timeframe.MONTHLY: "1mo",
}

TIMEFRAME_TO_YF_PERIOD = {
    Timeframe.DAILY:   "1y",
    Timeframe.WEEKLY:  "5y",
    Timeframe.MONTHLY: "max",
}

TIMEFRAME_LABEL = {
    Timeframe.DAILY:   "Daily",
    Timeframe.WEEKLY:  "Weekly",
    Timeframe.MONTHLY: "Monthly",
}


class Direction(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class Verdict(str, Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    NEUTRAL     = "NEUTRAL"
    HOLD        = "HOLD"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"


class BreakoutState(str, Enum):
    VERGE_BREAKOUT       = "VERGE_BREAKOUT"
    FRESH_BREAKOUT       = "FRESH_BREAKOUT"
    CONFIRMED_BREAKOUT   = "CONFIRMED_BREAKOUT"
    EXTENDED             = "EXTENDED"
    NO_BREAKOUT          = "NO_BREAKOUT"
    VERGE_BREAKDOWN      = "VERGE_BREAKDOWN"
    FRESH_BREAKDOWN      = "FRESH_BREAKDOWN"
    CONFIRMED_BREAKDOWN  = "CONFIRMED_BREAKDOWN"


SignalLiteral = Literal["STRONG_BUY", "BUY", "NEUTRAL", "HOLD", "SELL", "STRONG_SELL"]
SentimentLiteral = Literal["POSITIVE", "MILDLY_POSITIVE", "NEUTRAL", "MILDLY_NEGATIVE", "NEGATIVE"]
