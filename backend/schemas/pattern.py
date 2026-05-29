"""Chart-pattern + breakout schemas."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from backend.schemas.common import Direction, BreakoutState, Timeframe


class PatternHit(BaseModel):
    name: str
    category: str
    direction: Direction
    confidence: float = 0
    status: Optional[str] = None
    description: Optional[str] = None
    target: Optional[float] = None
    stop: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    points: List[Dict[str, Any]] = []   # for chart overlay
    lines: List[Dict[str, Any]] = []
    zones: List[Dict[str, Any]] = []
    timeframe: Optional[Timeframe] = None


class BreakoutClassification(BaseModel):
    state: BreakoutState
    label: str
    color: str
    level: Optional[float] = None
    current_price: Optional[float] = None
    distance_pct: Optional[float] = None
    bars_since_breakout: int = 0
    volume_confirmed: bool = False
    is_bullish: bool = False
    is_bearish: bool = False
    timeframe: Optional[Timeframe] = None


class MultiTFBreakout(BaseModel):
    symbol: str
    by_timeframe: Dict[str, BreakoutClassification] = {}
    overall: str = ""


class PatternScanRequest(BaseModel):
    universe: str = "NIFTY 50"
    pattern_names: List[str] = []           # empty = all
    direction: Optional[Direction] = None    # None = all
    timeframes: List[Timeframe] = [Timeframe.DAILY, Timeframe.WEEKLY, Timeframe.MONTHLY]
    min_confidence: float = 60
    breakout_states: List[BreakoutState] = []  # empty = all
    max_symbols: Optional[int] = None
    region: str = "IN"


class PatternStockResult(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: Optional[float] = None
    confluence_score: float = 0
    patterns: List[PatternHit] = []
    breakouts: Dict[str, BreakoutClassification] = {}
    timeframes_present: List[Timeframe] = []


class PatternScanResult(BaseModel):
    request: PatternScanRequest
    rows: List[PatternStockResult]
    total_scanned: int
    total_matched: int
    duration_ms: float
