from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from backend.engine_checks import build_engine_checks, summarize_checks
from backend.fundamentals import get_fundamentals
from backend.patterns import detect_chart_patterns
from backend.stock_data import collect_price_histories, get_quote
from backend.technical_analysis import technical_summary
from backend.tradingview_analysis import get_tradingview_summary


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def stock_analysis_snapshot(symbol: str, include_fundamentals: bool = True, include_tradingview: bool = True) -> dict[str, Any] | None:
    try:
        quote = get_quote(symbol)
        collected = collect_price_histories(symbol, period="1y")
        successful_histories = [item for item in collected["histories"] if item.get("status") == "ok"]
        if not successful_histories:
            return None
        primary = max(successful_histories, key=lambda item: item.get("rows", 0))
        history = primary["data"]
        tech_df, tech = technical_summary(history)
        latest = tech_df.iloc[-1]
        patterns = detect_chart_patterns(tech_df)
        fundamentals = get_fundamentals(symbol) if include_fundamentals else {}
        tradingview = get_tradingview_summary(symbol) if include_tradingview else {}
        tv_recommendation = tradingview.get("Recommendation")

        technical_score = 0
        technical_score += 20 if _num(quote.current_price) > _num(tech.get("50 DMA")) else 0
        technical_score += 20 if _num(quote.current_price) > _num(tech.get("200 DMA")) else 0
        technical_score += 15 if 55 <= _num(tech.get("RSI (14)")) <= 70 else 5 if _num(tech.get("RSI (14)")) > 45 else 0
        technical_score += 15 if _num(tech.get("MACD")) > _num(tech.get("MACD Signal")) else 0
        technical_score += min(15, _num(tech.get("Breakout Probability")) / 6)
        technical_score += 15 if patterns and patterns[0]["Direction"] == "Bullish" else 0

        fundamental_score = 0
        pe = _num(fundamentals.get("PE Ratio") or fundamentals.get("Trendlyne PE TTM"))
        roe = _num(fundamentals.get("ROE"))
        roce = _num(fundamentals.get("ROCE"))
        debt = _num(fundamentals.get("Debt to Equity"), 99)
        profit_growth = _num(fundamentals.get("Profit Growth"))
        fundamental_score += 20 if 0 < pe <= 35 else 5 if pe else 0
        fundamental_score += 25 if roe >= 15 else 10 if roe >= 8 else 0
        fundamental_score += 25 if roce >= 18 else 10 if roce >= 10 else 0
        fundamental_score += 15 if debt <= 1 else 8 if debt <= 2 else 0
        fundamental_score += 15 if profit_growth > 0 else 0

        tv_score = 0
        if tv_recommendation:
            tv_score = {"STRONG_BUY": 100, "BUY": 80, "NEUTRAL": 50, "SELL": 25, "STRONG_SELL": 5}.get(str(tv_recommendation).upper(), 45)

        source_count = len(successful_histories) + (1 if tradingview.get("Recommendation") else 0) + (1 if fundamentals else 0)
        final_score = round((technical_score * 0.45) + (fundamental_score * 0.4) + (tv_score * 0.15), 1)

        row = {
            "Symbol": quote.symbol,
            "Company": quote.company_name,
            "Price": quote.current_price,
            "Change %": quote.day_change_pct,
            "Market Cap": quote.market_cap,
            "Primary Source": primary["source"],
            "Source Count": source_count,
            "Source Status": collected["status"],
            "RSI": _num(tech.get("RSI (14)")),
            "MACD": _num(tech.get("MACD")),
            "MACD Signal": _num(tech.get("MACD Signal")),
            "Trend": tech.get("Trend"),
            "Volume": quote.volume,
            "Avg Volume": _num(latest.get("AVG_VOLUME_20")),
            "50 DMA": _num(tech.get("50 DMA")),
            "200 DMA": _num(tech.get("200 DMA")),
            "Resistance": _num(tech.get("Resistance")),
            "Support": _num(tech.get("Support")),
            "Breakout Probability": _num(tech.get("Breakout Probability")),
            "TradingView": tv_recommendation,
            "Top Pattern": patterns[0]["Pattern"] if patterns else "",
            "Pattern Direction": patterns[0]["Direction"] if patterns else "",
            "Pattern Confidence": patterns[0]["Confidence"] if patterns else 0,
            "PE Ratio": fundamentals.get("PE Ratio") or fundamentals.get("Trendlyne PE TTM"),
            "ROE": fundamentals.get("ROE"),
            "ROCE": fundamentals.get("ROCE"),
            "Debt to Equity": fundamentals.get("Debt to Equity"),
            "Revenue Growth": fundamentals.get("Revenue Growth"),
            "Profit Growth": fundamentals.get("Profit Growth"),
            "Promoter Holding": fundamentals.get("Promoter Holding"),
            "Technical Score": round(technical_score, 1),
            "Fundamental Score": round(fundamental_score, 1),
            "TV Score": round(tv_score, 1),
            "Final Score": final_score,
        }
        checks = build_engine_checks(row)
        summary = summarize_checks(checks)
        row["Engine Checks"] = checks
        row["Passed Checks"] = summary["Passed"]
        row["Failed Checks"] = summary["Failed"]
        row["Check Points"] = summary["Check Points"]
        row["Section Summary"] = summary["Sections"]
        return row
    except Exception:
        return None


def analyze_universe(
    symbols: list[str],
    include_fundamentals: bool = True,
    include_tradingview: bool = True,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(stock_analysis_snapshot, symbol, include_fundamentals, include_tradingview): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            row = future.result()
            if row:
                rows.append(row)
    return sorted(rows, key=lambda item: item.get("Final Score", 0), reverse=True)
