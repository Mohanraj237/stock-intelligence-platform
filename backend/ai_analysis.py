from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from backend.config import get_settings
from backend.watchlist import get_app_setting


def _fallback_analysis(quote: dict[str, Any], technicals: dict[str, Any], fundamentals: dict[str, Any]) -> dict[str, Any]:
    score = 50
    rsi = technicals.get("RSI (14)") or 0
    trend = technicals.get("Trend", "")
    pe = fundamentals.get("PE Ratio")
    roe = fundamentals.get("ROE")
    debt = fundamentals.get("Debt to Equity")

    if "uptrend" in str(trend).lower():
        score += 12
    if 55 <= rsi <= 70:
        score += 10
    elif rsi > 75:
        score -= 8
    if roe and roe > 15:
        score += 10
    if debt is not None and debt < 1:
        score += 8
    if pe and pe < 35:
        score += 5

    score = max(0, min(100, int(score)))
    stance = "Bullish" if score >= 68 else "Bearish" if score <= 42 else "Neutral"
    return {
        "stance": stance,
        "short_term_outlook": f"{quote.get('symbol')} is showing {technicals.get('Trend', 'mixed')} price action with RSI near {rsi:.1f}.",
        "long_term_outlook": "Long-term quality depends on earnings growth, capital efficiency, and debt discipline.",
        "risks": [
            "Market-wide volatility can override stock-specific signals.",
            "Fundamental data may be incomplete if public sources block automated access.",
        ],
        "opportunities": [
            "Momentum can improve if price sustains above key moving averages.",
            "Better earnings growth and low leverage can support rerating.",
        ],
        "final_score": score,
        "model": "rule-based fallback",
    }


def generate_ai_analysis(
    quote: dict[str, Any],
    technicals: dict[str, Any],
    fundamentals: dict[str, Any],
    tradingview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    api_key = get_app_setting("OPENAI_API_KEY", settings.openai_api_key)
    if not api_key:
        return _fallback_analysis(quote, technicals, fundamentals)

    client = OpenAI(api_key=api_key)
    prompt = {
        "role": "user",
        "content": (
            "You are an Indian equity research assistant. Return strict JSON with keys: "
            "stance, short_term_outlook, long_term_outlook, risks, opportunities, final_score. "
            "Do not give financial advice; provide an educational analyst-style view.\n\n"
            f"Quote: {json.dumps(quote, default=str)}\n"
            f"Technicals: {json.dumps(technicals, default=str)}\n"
            f"Fundamentals: {json.dumps(fundamentals, default=str)}\n"
            f"TradingView: {json.dumps(tradingview or {}, default=str)}"
        ),
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Return concise JSON only. Be balanced, factual, and risk-aware.",
                },
                prompt,
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        data["model"] = "OpenAI"
        return data
    except Exception as exc:
        data = _fallback_analysis(quote, technicals, fundamentals)
        data["model"] = f"rule-based fallback after OpenAI error: {exc}"
        return data
