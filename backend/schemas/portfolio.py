"""Portfolio schemas."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class Holding(BaseModel):
    symbol: str
    qty: float
    buy_price: float
    buy_date: Optional[str] = None
    notes: Optional[str] = None


class PortfolioRow(BaseModel):
    symbol: str
    company: Optional[str] = None
    qty: float
    buy_price: float
    buy_date: Optional[str] = None
    cmp: Optional[float] = None
    today_change_pct: Optional[float] = None
    invested: float
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    signal: Optional[str] = None


class PortfolioSummary(BaseModel):
    rows: List[PortfolioRow]
    total_invested: float = 0
    current_value: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    holdings_count: int = 0
