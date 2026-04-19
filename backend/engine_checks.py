from __future__ import annotations

from typing import Any

import pandas as pd


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _check(section: str, name: str, passed: bool, value: Any, rule: str, points: float) -> dict[str, Any]:
    return {
        "Section": section,
        "Check": name,
        "Status": "PASS" if passed else "FAIL",
        "Value": value,
        "Rule": rule,
        "Points": round(points if passed else 0, 1),
    }


def source_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    statuses = row.get("Source Status") or []
    ok_sources = [item for item in statuses if item.get("status") == "ok"]
    return [
        _check("Data Sources", "At least one OHLCV feed", len(ok_sources) >= 1, len(ok_sources), ">= 1 successful candle feed", 20),
        _check("Data Sources", "Multiple confirmations", len(ok_sources) >= 2, len(ok_sources), ">= 2 successful candle feeds", 10),
        _check("Data Sources", "TradingView available", bool(row.get("TradingView")), row.get("TradingView") or "N/A", "TradingView returns a recommendation", 10),
    ]


def technical_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    price = _num(row.get("Price"))
    dma50 = _num(row.get("50 DMA"))
    dma200 = _num(row.get("200 DMA"))
    rsi = _num(row.get("RSI"))
    volume = _num(row.get("Volume"))
    avg_volume = _num(row.get("Avg Volume"))
    return [
        _check("Technical", "Price above 50 DMA", price > dma50 > 0, f"{price:.2f} / {dma50:.2f}", "Price > 50 DMA", 20),
        _check("Technical", "Price above 200 DMA", price > dma200 > 0, f"{price:.2f} / {dma200:.2f}", "Price > 200 DMA", 20),
        _check("Technical", "RSI momentum zone", 55 <= rsi <= 70, f"{rsi:.2f}", "55 <= RSI <= 70", 15),
        _check("Technical", "MACD bullish", _num(row.get("MACD")) > _num(row.get("MACD Signal")), f"{_num(row.get('MACD')):.2f} / {_num(row.get('MACD Signal')):.2f}", "MACD > signal", 15),
        _check("Technical", "Volume expansion", avg_volume > 0 and volume > avg_volume, f"{volume:.0f} / {avg_volume:.0f}", "Volume > 20-day avg volume", 10),
        _check("Technical", "Breakout probability", _num(row.get("Breakout Probability")) >= 55, f"{_num(row.get('Breakout Probability')):.0f}%", "Breakout probability >= 55%", 15),
    ]


def pattern_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    pattern = row.get("Top Pattern") or "N/A"
    confidence = _num(row.get("Pattern Confidence"))
    direction = row.get("Pattern Direction") or "N/A"
    return [
        _check("Pattern", "Pattern detected", pattern != "N/A", pattern, "Any recognized chart pattern", 15),
        _check("Pattern", "Bullish setup", direction == "Bullish", direction, "Pattern direction is Bullish", 15),
        _check("Pattern", "Pattern confidence", confidence >= 65, f"{confidence:.0f}%", "Confidence >= 65%", 20),
    ]


def fundamental_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    pe = _num(row.get("PE Ratio"))
    roe = _num(row.get("ROE"))
    roce = _num(row.get("ROCE"))
    debt = _num(row.get("Debt to Equity"), 99)
    profit_growth = _num(row.get("Profit Growth"))
    return [
        _check("Fundamental", "Valuation sanity", 0 < pe <= 35, f"{pe:.2f}" if pe else "N/A", "0 < PE <= 35", 20),
        _check("Fundamental", "ROE quality", roe >= 15, f"{roe:.2f}%" if roe else "N/A", "ROE >= 15%", 25),
        _check("Fundamental", "ROCE quality", roce >= 18, f"{roce:.2f}%" if roce else "N/A", "ROCE >= 18%", 25),
        _check("Fundamental", "Low debt", debt <= 1, f"{debt:.2f}" if debt != 99 else "N/A", "Debt to Equity <= 1", 15),
        _check("Fundamental", "Profit growth", profit_growth > 0, f"{profit_growth:.2f}%" if profit_growth else "N/A", "Profit growth > 0", 15),
    ]


def tradingview_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    recommendation = str(row.get("TradingView") or "N/A").upper()
    return [
        _check("TradingView", "Not bearish", recommendation in ("STRONG_BUY", "BUY", "NEUTRAL"), recommendation, "TradingView is not SELL/STRONG_SELL", 10),
        _check("TradingView", "Buy signal", recommendation in ("STRONG_BUY", "BUY"), recommendation, "TradingView is BUY/STRONG_BUY", 20),
        _check("TradingView", "Strong buy signal", recommendation == "STRONG_BUY", recommendation, "TradingView is STRONG_BUY", 20),
    ]


def build_engine_checks(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *source_checks(row),
        *technical_checks(row),
        *pattern_checks(row),
        *fundamental_checks(row),
        *tradingview_checks(row),
    ]


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item["Status"] == "PASS")
    failed = sum(1 for item in checks if item["Status"] == "FAIL")
    points = sum(_num(item.get("Points")) for item in checks)
    sections: dict[str, dict[str, Any]] = {}
    for item in checks:
        section = item["Section"]
        sections.setdefault(section, {"Passed": 0, "Failed": 0, "Points": 0.0})
        if item["Status"] == "PASS":
            sections[section]["Passed"] += 1
        else:
            sections[section]["Failed"] += 1
        sections[section]["Points"] += _num(item.get("Points"))
    return {
        "Passed": passed,
        "Failed": failed,
        "Check Points": round(points, 1),
        "Sections": sections,
    }
