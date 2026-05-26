"""
DEPRECATED — kept only as a backwards-compatibility shim.

All market data now comes from `services.market_data_service`
(NSE + Yahoo Finance + locally computed indicators). No TradingView
account, session cookie, or `tradingview-ta` dependency is required.

Existing imports continue to work:
    from services.tradingview_service import scan_symbols_bulk, get_tv_analysis,
                                              get_tv_ohlcv_history, tv_score, normalize_symbol
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List

from services.market_data_service import (
    normalize_symbol,
    get_ohlcv_history,
    get_market_analysis,
    scan_market_bulk,
    score_signal,
)

# ── Re-exports under the old TradingView names ───────────────────────────────

def get_tv_ohlcv_history(symbol: str, period: str = "1y", interval: str = "1d",
                         session_cookie: Optional[str] = None) -> Optional[Any]:
    return get_ohlcv_history(symbol, period=period, interval=interval)


def get_tv_analysis(symbol: str, interval: str = "1d") -> Optional[Dict[str, Any]]:
    return get_market_analysis(symbol, interval=interval)


def get_tv_analysis_batch(symbols: List[str], interval: str = "1d",
                          max_workers: int = 8) -> Dict[str, Dict]:
    return scan_market_bulk(symbols, max_workers=max_workers)


def scan_symbols_bulk(symbols: List[str], exchange: str = "NSE",
                      session_cookie: Optional[str] = None) -> Dict[str, Dict]:
    return scan_market_bulk(symbols, exchange=exchange)


def tv_score(recommendation: str) -> int:
    return score_signal(recommendation)


def configure_session_cookie(session_id: str):
    """No-op — TradingView session is no longer used."""
    return None


# ── Widget HTML generators — removed ─────────────────────────────────────────
# All TradingView embed widgets have been removed from the app.
# These stubs return empty strings so any lingering callers do not crash.

def get_tv_advanced_chart_html(symbol: str, exchange: str = "NSE", height: int = 610) -> str:
    return ""


def get_tv_mini_chart_html(symbol: str, exchange: str = "NSE") -> str:
    return ""


def get_market_ticker_html() -> str:
    return ""


def get_market_overview_html() -> str:
    return ""


def get_tv_symbol_info_html(symbol: str, exchange: str = "NSE") -> str:
    return ""


def get_tv_technical_analysis_html(symbol: str, exchange: str = "NSE") -> str:
    return ""
