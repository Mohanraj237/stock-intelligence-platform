"""Earnings schemas."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel
from backend.schemas.news import Sentiment


class UpcomingResult(BaseModel):
    symbol: str
    company: Optional[str] = None
    meeting_date: str
    purpose: Optional[str] = None
    agenda: Optional[str] = None


class EarningsItem(BaseModel):
    symbol: str
    period: str
    sales: Optional[float] = None
    net_profit: Optional[float] = None
    opm_pct: Optional[float] = None
    sales_yoy_pct: Optional[float] = None
    profit_yoy_pct: Optional[float] = None
    sentiment: Sentiment = Sentiment.NEUTRAL
