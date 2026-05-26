"""Position-sizing schemas."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class PositionSize(BaseModel):
    qty: int
    deployed: float
    at_risk: float
    rr: Optional[float] = None
    risk_pct: float
    capital: float
    entry: float
    stop: float
    target: Optional[float] = None
    notes: List[str] = []


class KellyResult(BaseModel):
    full_kelly_pct: float
    used_kelly_pct: float
    deploy_amount: float
    edge: float
    note: str = ""


class AIAllocationRow(BaseModel):
    symbol: str
    score: float
    weight_pct: float
    deploy: float
    qty: int
    entry: float
    stop: float
    target: Optional[float] = None
    at_risk: float


class AIAllocation(BaseModel):
    rows: List[AIAllocationRow]
    total_deployed: float
    total_at_risk: float
    cash_buffer: float
    rejected: List[str] = []
