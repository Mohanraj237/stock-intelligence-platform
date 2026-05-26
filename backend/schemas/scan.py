"""Scanner schemas."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class FilterCriteria(BaseModel):
    pe_max: Optional[float] = None
    pb_max: Optional[float] = None
    de_max: Optional[float] = None
    roe_min: Optional[float] = None
    roce_min: Optional[float] = None
    sales_growth_min: Optional[float] = None
    profit_growth_min: Optional[float] = None
    promoter_min: Optional[float] = None
    rsi_min: Optional[float] = None
    rsi_max: Optional[float] = None
    adx_min: Optional[float] = None
    price_above_sma50: Optional[bool] = None
    price_above_sma200: Optional[bool] = None
    macd_bullish: Optional[bool] = None
    change_pct_min: Optional[float] = None
    change_pct_max: Optional[float] = None


class ScanRequest(BaseModel):
    universe: str = "NIFTY 50"
    scan_type: str = "all"
    filters: FilterCriteria = FilterCriteria()
    enable_ai: bool = False
    max_symbols: Optional[int] = None


class ScanRow(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    rsi: Optional[float] = None
    adx: Optional[float] = None
    macd_bullish: Optional[bool] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    volume: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    signal: Optional[str] = None
    ai_score: Optional[float] = None
    ai_verdict: Optional[str] = None
    rules_passed: List[str] = []


class ScanResult(BaseModel):
    request: ScanRequest
    rows: List[ScanRow]
    audit_log: List[Dict[str, Any]] = []
    total_scanned: int
    total_matched: int
    duration_ms: float


SCAN_TYPES = [
    "all", "breakout_ready", "oversold_bounce", "strong_momentum",
    "macd_crossover", "quality_growth", "undervalued", "techno_funda",
    "high_promoter", "dividend_compounders", "high52w_breakout", "reversal_watch",
]
