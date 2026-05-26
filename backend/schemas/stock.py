"""Stock analysis schemas: AI verdict, indicators, fundamentals, chart analysis."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from backend.schemas.common import Verdict, Timeframe


class Indicators(BaseModel):
    """28+ technical indicators computed from OHLCV via the `ta` library."""
    close: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    rsi: Optional[float] = None
    ao: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma100: Optional[float] = None
    sma200: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_middle: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    adx: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    cci20: Optional[float] = None
    atr: Optional[float] = None
    change_pct: Optional[float] = None


class Fundamentals(BaseModel):
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    book_value: Optional[float] = None
    dividend_yield: Optional[float] = None
    eps: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    opm: Optional[float] = None
    npm: Optional[float] = None
    sales_growth: Optional[float] = None
    profit_growth: Optional[float] = None
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    promoter_holding: Optional[float] = None
    fii_holding: Optional[float] = None
    dii_holding: Optional[float] = None
    public_holding: Optional[float] = None
    pledge_pct: Optional[float] = None
    about: Optional[str] = None
    pros: List[str] = []
    cons: List[str] = []
    insights: List[str] = []
    peers: List[Dict[str, Any]] = []
    error: Optional[str] = None


class QuarterlyRow(BaseModel):
    period: str
    sales: Optional[float] = None
    net_profit: Optional[float] = None
    opm_pct: Optional[float] = None
    sales_yoy_pct: Optional[float] = None
    profit_yoy_pct: Optional[float] = None


class BalanceSheetRow(BaseModel):
    period: str
    metric: str
    value: Optional[float] = None


class AIVerdict(BaseModel):
    symbol: str
    verdict: Verdict
    composite_score: float = 50
    tech_score: float = 50
    fund_score: float = 50
    pattern_score: float = 50
    momentum_score: float = 50
    confidence: str = "Medium"  # Low / Medium / High
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    bull_case: List[str] = []
    bear_case: List[str] = []
    risk_flags: List[str] = []
    signal_chain: List[str] = []


class StockSnapshot(BaseModel):
    symbol: str
    quote: Optional[Dict[str, Any]] = None
    indicators: Optional[Indicators] = None
    fundamentals: Optional[Fundamentals] = None
    ai: Optional[AIVerdict] = None
    quarterly: List[QuarterlyRow] = []
    error: Optional[str] = None


class ChartAnalysis(BaseModel):
    """Rule-based 14-section institutional chart analysis."""
    symbol: str
    timeframe: Timeframe
    sections: Dict[str, Any]  # keyed by section name
    probability_scores: Dict[str, float] = {}  # breakout / trend / rr / overall (out of 10)
    final_verdict: str = ""
    confidence: str = "Medium"
    pro_explanation: str = ""
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    targets: List[float] = []
    red_flags: List[str] = []
