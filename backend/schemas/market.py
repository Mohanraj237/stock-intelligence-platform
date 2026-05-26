"""Market-data schemas: quotes, indices, OHLCV, FII/DII, sectors."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from backend.schemas.common import Timeframe


class Quote(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: float
    change: float = 0
    change_pct: float = 0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


class IndexPerf(BaseModel):
    symbol: str
    name: str
    last_price: float
    change: float = 0
    change_pct: float = 0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None


class MarketStatus(BaseModel):
    status: str  # "OPEN" | "CLOSED" | "PRE_OPEN" | etc.
    is_open: bool
    trade_date: Optional[str] = None
    nifty: Optional[float] = None
    nifty_change_pct: Optional[float] = None
    market_cap_lakh_cr: Optional[float] = None
    gift_nifty: Optional[float] = None
    gift_nifty_change_pct: Optional[float] = None


class SectorPerf(BaseModel):
    name: str
    symbol: str
    last_price: Optional[float] = None
    change_pct: float = 0
    advances: int = 0
    declines: int = 0
    unchanged: int = 0


class FIIDIIRow(BaseModel):
    date: str
    fii_buy: float = 0
    fii_sell: float = 0
    fii_net: float = 0
    dii_buy: float = 0
    dii_sell: float = 0
    dii_net: float = 0


class OHLCVBar(BaseModel):
    time: int  # unix epoch seconds (UTC) — what lightweight-charts wants
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class OHLCVResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    bars: List[OHLCVBar]
    source: str = "yahoo"


class UniverseRow(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    volume: Optional[float] = None
    return_30d: Optional[float] = None
    return_1y: Optional[float] = None
    rsi: Optional[float] = None
    adx: Optional[float] = None
    signal: Optional[str] = None
    score: Optional[float] = None
