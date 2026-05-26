"""Watchlist schemas."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class WatchlistItem(BaseModel):
    symbol: str
    added_at: Optional[str] = None
    note: Optional[str] = None


class WatchlistRow(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    volume: Optional[float] = None
    signal: Optional[str] = None
    score: Optional[float] = None
    added_at: Optional[str] = None
