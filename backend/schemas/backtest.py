"""Backtest schemas."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class BacktestRequest(BaseModel):
    universe: str = "NIFTY 50"
    pattern_name: str
    period: str = "2y"           # 1y / 2y / 5y / max
    max_symbols: int = 50
    min_confidence: float = 60
    max_holding_bars: int = 30
    step_size: int = 1
    rolling_window: int = 120


class TradeRow(BaseModel):
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    bars_held: int
    exit_reason: str   # target_hit | stop_hit | time_stop | end_of_data


class BacktestResult(BaseModel):
    request: BacktestRequest
    win_rate: float = 0
    avg_return: float = 0
    expectancy: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    avg_holding_days: float = 0
    avg_winner: float = 0
    avg_loser: float = 0
    best_winner: float = 0
    worst_loser: float = 0
    total_trades: int = 0
    equity_curve: List[float] = []
    return_distribution: List[float] = []
    trades: List[TradeRow] = []
    verdict: str = ""
    audit_log: List[str] = []
    duration_ms: float = 0
