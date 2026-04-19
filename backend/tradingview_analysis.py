from __future__ import annotations

from typing import Any

from backend.stock_data import normalize_symbol


def get_tradingview_summary(symbol: str) -> dict[str, Any]:
    try:
        from tradingview_ta import Interval, TA_Handler
    except Exception as exc:
        return {"Source": "TradingView unavailable", "Error": str(exc)}

    clean = normalize_symbol(symbol)
    errors: list[str] = []
    for exchange in ("NSE", "BSE"):
        try:
            handler = TA_Handler(
                symbol=clean,
                screener="india",
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY,
            )
            analysis = handler.get_analysis()
            return {
                "Source": f"TradingView {exchange}",
                "Recommendation": analysis.summary.get("RECOMMENDATION"),
                "Buy": analysis.summary.get("BUY"),
                "Neutral": analysis.summary.get("NEUTRAL"),
                "Sell": analysis.summary.get("SELL"),
                "Indicators": analysis.indicators,
            }
        except Exception as exc:
            errors.append(f"{exchange}: {exc}")
    return {"Source": "TradingView unavailable", "Error": " | ".join(errors)}
