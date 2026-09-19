"""Pydantic schemas — single source of truth shared with frontend via OpenAPI."""
from backend.schemas.common import Timeframe, Direction, Verdict, BreakoutState
from backend.schemas.market import (
    Quote, IndexPerf, MarketStatus, SectorPerf, FIIDIIRow, OHLCVBar, OHLCVResponse,
    UniverseRow,
)
from backend.schemas.stock import (
    AIVerdict, Indicators, Fundamentals, QuarterlyRow, BalanceSheetRow,
    StockSnapshot, ChartAnalysis,
)
from backend.schemas.pattern import (
    PatternHit, BreakoutClassification, MultiTFBreakout, PatternScanRequest, PatternScanResult,
)
from backend.schemas.scan import ScanRequest, ScanRow, ScanResult, FilterCriteria
from backend.schemas.news import NewsItem, AnnouncementItem, Sentiment
from backend.schemas.earnings import EarningsItem, UpcomingResult
from backend.schemas.position import PositionSize, KellyResult, AIAllocation
from backend.schemas.backtest import BacktestRequest, BacktestResult, TradeRow
from backend.schemas.portfolio import Holding, PortfolioRow, PortfolioSummary
from backend.schemas.watchlist import WatchlistItem, WatchlistRow
from backend.schemas.rule import Rule, RuleCondition, RuleSet, RuleMatchRow
from backend.schemas.settings import AppSettings
from backend.schemas.scoring import ScoringConfig

__all__ = [
    "Timeframe", "Direction", "Verdict", "BreakoutState",
    "Quote", "IndexPerf", "MarketStatus", "SectorPerf", "FIIDIIRow",
    "OHLCVBar", "OHLCVResponse", "UniverseRow",
    "AIVerdict", "Indicators", "Fundamentals", "QuarterlyRow", "BalanceSheetRow",
    "StockSnapshot", "ChartAnalysis",
    "PatternHit", "BreakoutClassification", "MultiTFBreakout", "PatternScanRequest", "PatternScanResult",
    "ScanRequest", "ScanRow", "ScanResult", "FilterCriteria",
    "NewsItem", "AnnouncementItem", "Sentiment",
    "EarningsItem", "UpcomingResult",
    "PositionSize", "KellyResult", "AIAllocation",
    "BacktestRequest", "BacktestResult", "TradeRow",
    "Holding", "PortfolioRow", "PortfolioSummary",
    "WatchlistItem", "WatchlistRow",
    "Rule", "RuleCondition", "RuleSet", "RuleMatchRow",
    "AppSettings",
    "ScoringConfig",
]
