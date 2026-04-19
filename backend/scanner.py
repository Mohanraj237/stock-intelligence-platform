from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from backend.analysis_engine import analyze_universe
from backend.stock_universe import DEFAULT_NSE_UNIVERSE


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank(rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool], scorer: Callable[[dict[str, Any]], float], limit: int = 10) -> list[dict[str, Any]]:
    filtered = [row.copy() for row in rows if predicate(row)]
    for row in filtered:
        row["Score"] = round(scorer(row), 1)
    return sorted(filtered, key=lambda item: item["Score"], reverse=True)[:limit]


def scan_all_in_one(universe: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
    symbols = universe or DEFAULT_NSE_UNIVERSE
    return analyze_universe(symbols)[:limit]


def scan_breakout_stocks(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: _num(r["Price"]) > _num(r["50 DMA"]) and r["RSI"] > 60 and _num(r["Volume"]) > _num(r["Avg Volume"]) and (
            r["Breakout Probability"] >= 55 or "Breakout" in str(r.get("Top Pattern"))
        ),
        lambda r: r["Breakout Probability"] + r["Pattern Confidence"] * 0.35 + min(20, max(0, r["RSI"] - 60) * 2),
        limit,
    )


def scan_pattern_stocks(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: bool(r.get("Top Pattern")) and _num(r.get("Pattern Confidence")) >= 60,
        lambda r: _num(r["Pattern Confidence"]) + _num(r["Breakout Probability"]) * 0.25 + _num(r["Technical Score"]) * 0.2,
        limit,
    )


def scan_undervalued_stocks(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: 0 < _num(r["PE Ratio"]) < 30 and _num(r["ROE"]) > 15 and (_num(r["Debt to Equity"], 99) < 1.5) and _num(r["Profit Growth"]) > 0,
        lambda r: (30 - _num(r["PE Ratio"])) + _num(r["ROE"]) + max(0, 20 - _num(r["Debt to Equity"]) * 5),
        limit,
    )


def scan_swing_trade_stocks(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: r["MACD"] > r["MACD Signal"] and 55 <= r["RSI"] <= 70 and "uptrend" in str(r["Trend"]).lower(),
        lambda r: 50 + (r["RSI"] - 55) * 2 + min(20, r["Breakout Probability"] / 5) + r["Pattern Confidence"] * 0.1,
        limit,
    )


def scan_strong_fundamentals(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: _num(r["ROCE"]) > 18 and _num(r["Debt to Equity"], 99) < 1.5 and _num(r["Revenue Growth"]) > 0,
        lambda r: _num(r["ROCE"]) + _num(r["ROE"]) + max(0, 25 - _num(r["Debt to Equity"]) * 8),
        limit,
    )


def scan_technofunda(universe: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    rows = analyze_universe(universe or DEFAULT_NSE_UNIVERSE)
    return _rank(
        rows,
        lambda r: _num(r["Technical Score"]) >= 55 and _num(r["Fundamental Score"]) >= 45 and str(r.get("TradingView", "")).upper() in ("BUY", "STRONG_BUY", "NEUTRAL"),
        lambda r: _num(r["Final Score"]),
        limit,
    )


SCAN_FUNCTIONS = {
    "All-in-One Rank": scan_all_in_one,
    "Techno-Funda Stocks": scan_technofunda,
    "Breakout Stocks": scan_breakout_stocks,
    "Chart Pattern Stocks": scan_pattern_stocks,
    "Undervalued Stocks": scan_undervalued_stocks,
    "Swing Trade Stocks": scan_swing_trade_stocks,
    "Strong Fundamentals": scan_strong_fundamentals,
}
