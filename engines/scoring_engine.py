from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _num(v, default=0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default

def compute_technical_score(tv_indicators: dict, patterns: list[dict]) -> tuple[float, list[dict]]:
    """Returns (score 0-100, check_list)."""
    checks = []
    score = 0

    rsi   = _num(tv_indicators.get("rsi"))
    macd  = _num(tv_indicators.get("macd"))
    sig   = _num(tv_indicators.get("macd_signal"))
    close = _num(tv_indicators.get("close"))
    sma50 = _num(tv_indicators.get("sma50"))
    sma200= _num(tv_indicators.get("sma200"))
    vol   = _num(tv_indicators.get("volume"))
    adx   = _num(tv_indicators.get("adx"))

    # Price vs moving averages
    if sma50 > 0:
        above50 = close > sma50
        pts = 20 if above50 else 0
        score += pts
        checks.append({"check": "Price > SMA 50", "passed": above50, "actual": f"₹{close:.2f} vs ₹{sma50:.2f}", "points": pts, "max": 20})

    if sma200 > 0:
        above200 = close > sma200
        pts = 20 if above200 else 0
        score += pts
        checks.append({"check": "Price > SMA 200", "passed": above200, "actual": f"₹{close:.2f} vs ₹{sma200:.2f}", "points": pts, "max": 20})

    # RSI zone
    if rsi > 0:
        if 55 <= rsi <= 70:
            rsi_pts = 15
        elif 45 <= rsi < 55:
            rsi_pts = 8
        elif rsi > 70:
            rsi_pts = 5
        elif 30 <= rsi < 45:
            rsi_pts = 3
        else:
            rsi_pts = 0
        score += rsi_pts
        checks.append({"check": f"RSI Zone (55-70 ideal)", "passed": 55 <= rsi <= 70, "actual": f"RSI={rsi:.1f}", "points": rsi_pts, "max": 15})

    # MACD bullish
    if macd != 0 or sig != 0:
        macd_bull = macd > sig
        pts = 15 if macd_bull else 0
        score += pts
        checks.append({"check": "MACD > Signal (bullish)", "passed": macd_bull, "actual": f"MACD={macd:.4f}, Signal={sig:.4f}", "points": pts, "max": 15})

    # ADX trend strength
    if adx > 0:
        strong = adx > 25
        pts = 10 if strong else 5 if adx > 15 else 0
        score += pts
        checks.append({"check": "ADX > 25 (strong trend)", "passed": strong, "actual": f"ADX={adx:.1f}", "points": pts, "max": 10})

    # Pattern check
    if patterns:
        top = patterns[0]
        is_bullish = top.get("direction") == "Bullish" or top.get("Direction") == "Bullish"
        conf = _num(top.get("confidence") or top.get("Confidence"))
        pts = int(20 * conf / 100) if is_bullish else 0
        score += pts
        pname = top.get("name") or top.get("Pattern", "")
        checks.append({"check": f"Bullish Pattern: {pname}", "passed": is_bullish and conf >= 60, "actual": f"Confidence={conf:.0f}%", "points": pts, "max": 20})

    return round(min(score, 100), 1), checks

def compute_fundamental_score(ratios: dict) -> tuple[float, list[dict]]:
    """Returns (score 0-100, check_list)."""
    checks = []
    score = 0

    pe   = _num(ratios.get("pe"))
    pb   = _num(ratios.get("pb"))
    roe  = _num(ratios.get("roe"))
    roce = _num(ratios.get("roce"))
    de   = _num(ratios.get("debt_equity"), 99)
    pg   = _num(ratios.get("profit_growth"))
    sg   = _num(ratios.get("sales_growth"))
    prom = _num(ratios.get("promoter_holding"))

    # PE
    if pe > 0:
        if pe <= 20:
            pe_pts = 20
        elif pe <= 35:
            pe_pts = 12
        elif pe <= 50:
            pe_pts = 5
        else:
            pe_pts = 0
        score += pe_pts
        checks.append({"check": "PE Ratio (< 20 ideal)", "passed": pe <= 25, "actual": f"PE={pe:.1f}x", "points": pe_pts, "max": 20})

    # ROE
    if roe != 0:
        roe_pts = 25 if roe >= 20 else 18 if roe >= 15 else 10 if roe >= 8 else 0
        score += roe_pts
        checks.append({"check": "ROE >= 15%", "passed": roe >= 15, "actual": f"ROE={roe:.1f}%", "points": roe_pts, "max": 25})

    # ROCE
    if roce != 0:
        roce_pts = 20 if roce >= 20 else 14 if roce >= 15 else 8 if roce >= 10 else 0
        score += roce_pts
        checks.append({"check": "ROCE >= 15%", "passed": roce >= 15, "actual": f"ROCE={roce:.1f}%", "points": roce_pts, "max": 20})

    # Debt/Equity
    if de < 99:
        de_pts = 15 if de <= 0.5 else 12 if de <= 1 else 5 if de <= 2 else 0
        score += de_pts
        checks.append({"check": "Debt/Equity <= 1", "passed": de <= 1, "actual": f"D/E={de:.2f}x", "points": de_pts, "max": 15})

    # Profit growth
    if pg != 0:
        pg_pts = 12 if pg > 20 else 8 if pg > 10 else 4 if pg > 0 else 0
        score += pg_pts
        checks.append({"check": "Profit Growth > 0%", "passed": pg > 0, "actual": f"PG={pg:.1f}%", "points": pg_pts, "max": 12})

    # Sales growth
    if sg != 0:
        sg_pts = 8 if sg > 15 else 5 if sg > 5 else 2 if sg > 0 else 0
        score += sg_pts
        checks.append({"check": "Sales Growth > 5%", "passed": sg > 5, "actual": f"SG={sg:.1f}%", "points": sg_pts, "max": 8})

    # Promoter holding
    if prom > 0:
        prom_pts = 10 if prom >= 60 else 7 if prom >= 50 else 3 if prom >= 30 else 0
        score += prom_pts
        checks.append({"check": "Promoter >= 50%", "passed": prom >= 50, "actual": f"Promoter={prom:.1f}%", "points": prom_pts, "max": 10})

    return round(min(score, 100), 1), checks

def compute_tv_score(recommendation: str) -> tuple[float, list[dict]]:
    score = {"STRONG_BUY": 100, "BUY": 80, "NEUTRAL": 50, "SELL": 25, "STRONG_SELL": 5}.get(
        str(recommendation).upper(), 50)
    is_buy = str(recommendation).upper() in ("BUY", "STRONG_BUY")
    return float(score), [
        {"check": f"TV: {recommendation}", "passed": is_buy, "actual": recommendation, "points": score, "max": 100}
    ]

def compute_final_score(tech: float, funda: float, tv: float) -> float:
    return round(tech * 0.45 + funda * 0.40 + tv * 0.15, 1)

def build_stock_snapshot(symbol: str, tv_data: Optional[dict], screener_data: Optional[dict], patterns: list[dict]) -> dict:
    """Build the unified stock data dict used across the app."""
    snap: dict[str, Any] = {"Symbol": symbol.upper(), "tv_analysis": tv_data or {}, "screener_data": screener_data or {}}

    # Extract from TV indicators
    ind = (tv_data or {}).get("indicators") or {}
    snap["Price"] = ind.get("close")
    snap["Change %"] = ind.get("change")
    snap["Volume"] = ind.get("volume")
    snap["SMA 50"]  = ind.get("sma50")
    snap["SMA 200"] = ind.get("sma200")
    snap["EMA 20"]  = ind.get("ema20")
    snap["RSI"]     = ind.get("rsi")
    snap["MACD"]    = ind.get("macd")
    snap["MACD Signal"] = ind.get("macd_signal")
    snap["TradingView"] = (tv_data or {}).get("recommendation", "NEUTRAL")
    snap["TV Exchange"]  = (tv_data or {}).get("exchange", "NSE")

    # Extract from screener
    ratios = (screener_data or {}).get("ratios") or {}
    snap["Company"] = (screener_data or {}).get("name", symbol)
    snap["Sector"]  = (screener_data or {}).get("sector", "")
    snap["Industry"] = (screener_data or {}).get("industry", "")
    snap["PE Ratio"]     = ratios.get("pe")
    snap["PB Ratio"]     = ratios.get("pb")
    snap["ROE"]          = ratios.get("roe")
    snap["ROCE"]         = ratios.get("roce")
    snap["Debt to Equity"] = ratios.get("debt_equity")
    snap["Revenue Growth"] = ratios.get("sales_growth")
    snap["Profit Growth"]  = ratios.get("profit_growth")
    snap["Promoter Holding"] = ratios.get("promoter_holding")
    snap["Market Cap"]   = ratios.get("market_cap")
    snap["Dividend Yield"] = ratios.get("dividend_yield")
    snap["Book Value"]   = ratios.get("book_value")

    # Patterns
    snap["Patterns"] = patterns
    snap["Top Pattern"] = patterns[0]["name"] if patterns else ""
    snap["Pattern Direction"] = patterns[0]["direction"] if patterns else ""
    snap["Pattern Confidence"] = patterns[0]["confidence"] if patterns else 0

    # Scores
    tech_score, tech_checks = compute_technical_score(ind, patterns)
    funda_score, funda_checks = compute_fundamental_score(ratios)
    tv_score, tv_checks = compute_tv_score(snap["TradingView"])
    final = compute_final_score(tech_score, funda_score, tv_score)

    snap["Technical Score"]    = tech_score
    snap["Fundamental Score"]  = funda_score
    snap["TV Score"]           = tv_score
    snap["Final Score"]        = final
    snap["Tech Checks"]        = tech_checks
    snap["Funda Checks"]       = funda_checks
    snap["TV Checks"]          = tv_checks
    snap["All Checks"]         = tech_checks + funda_checks + tv_checks
    snap["Passed Checks"]      = sum(1 for c in snap["All Checks"] if c["passed"])
    snap["Total Checks"]       = len(snap["All Checks"])

    return snap
