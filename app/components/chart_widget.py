"""
Chart widget shims.

The TradingView embed widgets that previously lived here have been removed.
These functions remain as no-ops so that any pages still calling them do not
crash; they render nothing. New chart rendering happens via
`utils.advanced_chart.render_ohlcv_chart` (Plotly, fully local).

Parameters are prefixed with `_` to indicate they are intentionally unused —
they exist only to preserve the previous call signatures.
"""
from __future__ import annotations


def render_advanced_chart(_symbol: str = "", _exchange: str = "NSE", _height: int = 620):
    return None


def render_mini_chart(_symbol: str = "", _exchange: str = "NSE"):
    return None


def render_technical_analysis_widget(_symbol: str = "", _exchange: str = "NSE"):
    return None


def render_symbol_info(_symbol: str = "", _exchange: str = "NSE"):
    return None


def render_market_ticker():
    return None


def render_market_overview():
    return None
