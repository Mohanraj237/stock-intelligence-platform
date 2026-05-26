"""
Rule-based AI analysis engine for Indian stocks.
Combines Technical + Fundamental + Pattern signals into a weighted verdict.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


# ── Verdict constants ──────────────────────────────────────────────────────────
STRONG_BUY  = "STRONG BUY"
BUY         = "BUY"
HOLD        = "HOLD"
SELL        = "SELL"
STRONG_SELL = "STRONG SELL"


@dataclass
class AIVerdict:
    verdict: str = HOLD
    score: float = 50.0          # 0–100 composite
    tech_score: float = 50.0
    fund_score: float = 50.0
    pattern_score: float = 50.0
    momentum_score: float = 50.0
    confidence: str = "Medium"   # Low / Medium / High
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    upside_pct: Optional[float] = None
    bull_case: str = ""
    bear_case: str = ""
    risk_flags: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    summary: str = ""


# ── Technical Scoring ──────────────────────────────────────────────────────────

def score_technicals(tv: dict) -> tuple[float, list[str]]:
    """Score 0-100 from TradingView indicators."""
    if not tv:
        return 50.0, []

    ind = tv.get("indicators") or {}
    signals: list[str] = []
    score = 50.0

    rsi = ind.get("rsi")
    close = ind.get("close") or 0
    sma20 = ind.get("sma20")
    sma50 = ind.get("sma50")
    sma200 = ind.get("sma200")
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    ema200 = ind.get("ema200")
    macd = ind.get("macd") or 0
    macd_sig = ind.get("macd_signal") or 0
    adx = ind.get("adx")
    stoch_k = ind.get("stoch_k")
    stoch_d = ind.get("stoch_d")
    bb_upper = ind.get("bb_upper")
    bb_lower = ind.get("bb_lower")
    bb_mid = ind.get("bb_mid")
    change = ind.get("change") or 0
    ao = ind.get("ao")

    # Base from TV recommendation
    rec = tv.get("recommendation", "NEUTRAL")
    rec_map = {"STRONG_BUY": 82, "BUY": 68, "NEUTRAL": 50, "SELL": 32, "STRONG_SELL": 18}
    score = float(rec_map.get(rec.upper(), 50))

    # RSI scoring
    if rsi is not None:
        if rsi < 30:
            score += 8
            signals.append(f"RSI oversold ({rsi:.1f}) — potential bounce")
        elif rsi < 45:
            score += 3
            signals.append(f"RSI low ({rsi:.1f}) — room to rise")
        elif rsi > 75:
            score -= 8
            signals.append(f"RSI overbought ({rsi:.1f}) — caution")
        elif rsi > 60:
            score += 5
            signals.append(f"RSI momentum ({rsi:.1f}) — bullish zone")

    # EMA/SMA trend
    if close and ema20 and close > ema20:
        score += 4
        signals.append("Price above EMA20 (short-term bullish)")
    elif close and ema20 and close < ema20:
        score -= 4

    if close and ema50 and close > ema50:
        score += 5
        signals.append("Price above EMA50 (medium-term trend up)")
    elif close and ema50 and close < ema50:
        score -= 5

    if close and (sma200 or ema200):
        ma200 = sma200 or ema200
        if close > ma200:
            score += 6
            signals.append("Price above 200 SMA (long-term uptrend)")
        else:
            score -= 6
            signals.append("Price below 200 SMA (long-term downtrend)")

    # Golden/Death cross
    if sma50 and sma200:
        if sma50 > sma200:
            score += 4
            signals.append("Golden cross (50 SMA > 200 SMA)")
        else:
            score -= 4
            signals.append("Death cross (50 SMA < 200 SMA)")

    # MACD
    if macd and macd_sig:
        if macd > macd_sig:
            score += 5
            signals.append("MACD bullish crossover")
        else:
            score -= 4
            signals.append("MACD bearish")
        if macd > 0:
            score += 2

    # ADX (trend strength)
    if adx is not None:
        if adx > 30:
            signals.append(f"Strong trend (ADX {adx:.1f})")
        elif adx < 20:
            signals.append(f"Weak trend (ADX {adx:.1f}) — range-bound")

    # Stochastic
    if stoch_k is not None and stoch_d is not None:
        if stoch_k < 20 and stoch_d < 20:
            score += 5
            signals.append("Stochastic oversold")
        elif stoch_k > 80 and stoch_d > 80:
            score -= 5
            signals.append("Stochastic overbought")

    # Bollinger position
    if close and bb_lower and bb_upper:
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            pct_b = (close - bb_lower) / bb_range
            if pct_b < 0.2:
                score += 5
                signals.append("Near lower Bollinger Band (oversold)")
            elif pct_b > 0.8:
                score -= 4
                signals.append("Near upper Bollinger Band (overbought)")

    # Momentum
    if change > 3:
        score += 3
        signals.append(f"Strong day momentum (+{change:.2f}%)")
    elif change < -3:
        score -= 3

    return min(100, max(0, score)), signals[:8]


# ── Fundamental Scoring ────────────────────────────────────────────────────────

def score_fundamentals(screener: dict) -> tuple[float, list[str]]:
    """Score 0-100 from Screener.in fundamentals."""
    if not screener or screener.get("error"):
        return 50.0, []

    ratios = screener.get("ratios") or {}
    signals: list[str] = []
    score = 50.0

    pe = ratios.get("pe")
    pb = ratios.get("pb")
    roe = ratios.get("roe")
    roce = ratios.get("roce")
    opm = ratios.get("opm")
    npm = ratios.get("npm")
    div_yield = ratios.get("dividend_yield")
    debt_eq = ratios.get("debt_equity")
    promoter = ratios.get("promoter_holding")
    sales_growth = ratios.get("sales_growth")
    profit_growth = ratios.get("profit_growth")
    interest_cov = ratios.get("interest_coverage")

    # PE ratio
    if pe is not None and pe > 0:
        if pe < 15:
            score += 8
            signals.append(f"Attractive PE ({pe:.1f}x) — potentially undervalued")
        elif pe < 25:
            score += 4
            signals.append(f"Fair PE ({pe:.1f}x)")
        elif pe < 40:
            score -= 2
            signals.append(f"Premium PE ({pe:.1f}x) — growth expected")
        else:
            score -= 8
            signals.append(f"High PE ({pe:.1f}x) — expensive")

    # PB ratio
    if pb is not None and pb > 0:
        if pb < 1:
            score += 7
            signals.append(f"PB < 1 ({pb:.1f}x) — trading below book")
        elif pb < 3:
            score += 4
        elif pb > 8:
            score -= 5
            signals.append(f"High PB ({pb:.1f}x)")

    # ROE
    if roe is not None:
        if roe > 25:
            score += 10
            signals.append(f"Excellent ROE ({roe:.1f}%) — high returns")
        elif roe > 15:
            score += 6
            signals.append(f"Good ROE ({roe:.1f}%)")
        elif roe > 10:
            score += 2
        elif roe < 5:
            score -= 6
            signals.append(f"Weak ROE ({roe:.1f}%)")

    # ROCE
    if roce is not None:
        if roce > 20:
            score += 8
            signals.append(f"Strong ROCE ({roce:.1f}%)")
        elif roce > 15:
            score += 4
        elif roce < 10:
            score -= 5

    # OPM
    if opm is not None:
        if opm > 25:
            score += 6
            signals.append(f"High operating margin ({opm:.1f}%)")
        elif opm > 15:
            score += 3
        elif opm < 5:
            score -= 4
            signals.append(f"Low operating margin ({opm:.1f}%)")

    # Debt/Equity
    if debt_eq is not None:
        if debt_eq < 0.3:
            score += 6
            signals.append(f"Low debt (D/E {debt_eq:.1f}x)")
        elif debt_eq < 1.0:
            score += 2
        elif debt_eq > 2.0:
            score -= 7
            signals.append(f"High debt (D/E {debt_eq:.1f}x) — risk")
        elif debt_eq > 1.5:
            score -= 4

    # Promoter holding
    if promoter is not None:
        if promoter > 65:
            score += 6
            signals.append(f"High promoter holding ({promoter:.1f}%) — aligned")
        elif promoter > 50:
            score += 3
        elif promoter < 25:
            score -= 5
            signals.append(f"Low promoter holding ({promoter:.1f}%) — caution")

    # Sales growth
    if sales_growth is not None:
        if sales_growth > 20:
            score += 7
            signals.append(f"Strong revenue growth ({sales_growth:.1f}%)")
        elif sales_growth > 10:
            score += 3
        elif sales_growth < 0:
            score -= 5
            signals.append(f"Declining revenue ({sales_growth:.1f}%)")

    # Profit growth
    if profit_growth is not None:
        if profit_growth > 25:
            score += 7
            signals.append(f"Strong profit growth ({profit_growth:.1f}%)")
        elif profit_growth > 10:
            score += 3
        elif profit_growth < -10:
            score -= 6
            signals.append(f"Profit declining ({profit_growth:.1f}%)")

    # Interest coverage
    if interest_cov is not None and interest_cov > 0:
        if interest_cov > 5:
            score += 4
            signals.append(f"Comfortable interest coverage ({interest_cov:.1f}x)")
        elif interest_cov < 2:
            score -= 6
            signals.append(f"Weak interest coverage ({interest_cov:.1f}x) — risk")

    return min(100, max(0, score)), signals[:8]


# ── Pattern Scoring ────────────────────────────────────────────────────────────

def score_patterns(patterns: list) -> tuple[float, list[str]]:
    """Score 0-100 from detected chart patterns."""
    if not patterns:
        return 50.0, []

    bullish_patterns = {
        "Bull Flag", "Ascending Channel", "Double Bottom", "Inverse Head & Shoulders",
        "Rounding Bottom", "V Bottom", "Hammer", "Bullish Engulfing", "Morning Star",
        "Doji at Support", "52W High Breakout", "Volume Breakout", "Gap Up with Volume",
        "Cup & Handle", "Trendline Breakout", "Symmetrical Triangle Breakout",
        "Pullback to 20 EMA", "Pullback to 50 DMA", "Oversold Bounce",
        "Ascending Triangle", "Accumulation Phase", "Volume Surge on Breakout",
        "Descending Wedge Breakout", "Rectangle Breakout",
    }
    bearish_patterns = {
        "Bear Flag", "Descending Channel", "Double Top", "Head & Shoulders",
        "Shooting Star", "Bearish Engulfing", "Evening Star", "Doji at Resistance",
        "Overbought Reversal", "Descending Triangle", "Distribution Phase",
        "Rising Wedge", "Near 52W High",
    }

    score = 50.0
    signals = []
    bull_conf = 0.0
    bear_conf = 0.0

    for p in patterns:
        name = getattr(p, "name", str(p)) if not isinstance(p, dict) else p.get("name", "")
        raw_conf = getattr(p, "confidence", 70) if not isinstance(p, dict) else p.get("confidence", 70)
        raw_conf = float(raw_conf or 70)
        # Normalise: engine stores 0-100 integers; convert to 0-1 fraction
        conf = raw_conf / 100.0 if raw_conf > 1 else raw_conf

        if name in bullish_patterns:
            bull_conf = max(bull_conf, conf)
            score += conf * 15
            signals.append(f"{name} ({conf*100:.0f}%) — bullish")
        elif name in bearish_patterns:
            bear_conf = max(bear_conf, conf)
            score -= conf * 15
            signals.append(f"{name} ({conf*100:.0f}%) — bearish")

    if bull_conf > 0.65 and bear_conf < 0.4:
        signals.insert(0, "Strong bullish pattern confluence")
    elif bear_conf > 0.65 and bull_conf < 0.4:
        signals.insert(0, "Strong bearish pattern confluence")

    return min(100, max(0, score)), signals[:6]


# ── Momentum Scoring ───────────────────────────────────────────────────────────

def score_momentum(tv: dict, screener: dict) -> tuple[float, list[str]]:
    """Score 0-100 based on price momentum across timeframes."""
    score = 50.0
    signals = []

    ind = (tv or {}).get("indicators") or {}
    close = ind.get("close") or 0
    change = ind.get("change") or 0
    volume = ind.get("volume") or 0
    market_cap = ind.get("market_cap")

    # Daily change momentum
    if change > 5:
        score += 10
        signals.append(f"Strong up move +{change:.2f}% today")
    elif change > 2:
        score += 5
        signals.append(f"Positive momentum +{change:.2f}%")
    elif change < -5:
        score -= 10
        signals.append(f"Sharp decline {change:.2f}% today")
    elif change < -2:
        score -= 5

    # Trend alignment (price vs EMA ladder)
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    ema200 = ind.get("ema200")
    if close and ema20 and ema50 and ema200:
        if close > ema20 > ema50 > ema200:
            score += 12
            signals.append("Perfect EMA alignment (bullish)")
        elif close < ema20 < ema50 < ema200:
            score -= 12
            signals.append("Perfect EMA alignment (bearish)")

    # AO (Awesome Oscillator)
    ao = ind.get("ao")
    if ao is not None:
        if ao > 0:
            score += 4
        else:
            score -= 3

    # Promoter pledge check
    ratios = (screener or {}).get("ratios") or {}
    pledge = (screener or {}).get("shareholding", {}).get("pledge")
    if pledge is not None and pledge > 10:
        score -= 6
        signals.append(f"Promoter pledge {pledge:.1f}% — caution")

    return min(100, max(0, score)), signals[:5]


# ── Risk Flags ─────────────────────────────────────────────────────────────────

def extract_risk_flags(tv: dict, screener: dict) -> list[str]:
    flags = []
    ratios = (screener or {}).get("ratios") or {}
    ind = (tv or {}).get("indicators") or {}

    pe = ratios.get("pe")
    debt_eq = ratios.get("debt_equity")
    promoter = ratios.get("promoter_holding")
    roe = ratios.get("roe")
    npm = ratios.get("npm")
    rsi = ind.get("rsi")
    pledge = (screener or {}).get("shareholding", {}).get("pledge")

    if pe and pe > 60:
        flags.append(f"Very high PE ({pe:.0f}x) — valuation risk")
    if debt_eq and debt_eq > 2.0:
        flags.append(f"High leverage D/E {debt_eq:.1f}x")
    if promoter is not None and promoter < 30:
        flags.append(f"Low promoter stake ({promoter:.1f}%)")
    if pledge is not None and pledge > 15:
        flags.append(f"High promoter pledge ({pledge:.1f}%)")
    if roe is not None and roe < 5:
        flags.append(f"Poor capital efficiency ROE {roe:.1f}%")
    if npm is not None and npm < 2:
        flags.append(f"Thin profit margin ({npm:.1f}%)")
    if rsi is not None and rsi > 80:
        flags.append(f"Severely overbought RSI {rsi:.0f}")
    if rsi is not None and rsi < 25:
        flags.append(f"Severely oversold RSI {rsi:.0f} — high risk")

    return flags[:6]


# ── Price Target Engine ────────────────────────────────────────────────────────

def estimate_price_targets(close: float, score: float, tv: dict, screener: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (target, stop_loss, upside_pct)."""
    if not close or close <= 0:
        return None, None, None

    ind = (tv or {}).get("indicators") or {}
    atr = ind.get("atr")
    if atr is None:
        atr = close * 0.015  # ~1.5% ATR estimate

    # Upside based on score (score 70 → ~10% upside, score 80 → ~18%)
    if score >= 75:
        upside_pct = 12 + (score - 75) * 0.4
    elif score >= 60:
        upside_pct = 4 + (score - 60) * 0.5
    elif score <= 40:
        upside_pct = -5 - (40 - score) * 0.3
    else:
        upside_pct = 0

    target = round(close * (1 + upside_pct / 100), 2) if upside_pct != 0 else None
    stop_loss = round(close - atr * 2.5, 2)
    return target, stop_loss, round(upside_pct, 1) if upside_pct else None


# ── Narrative Generator ────────────────────────────────────────────────────────

def generate_narrative(verdict: str, signals: list[str], risk_flags: list[str],
                        screener: dict, tv: dict) -> tuple[str, str, str]:
    """Returns (summary, bull_case, bear_case)."""
    ratios = (screener or {}).get("ratios") or {}
    name = (screener or {}).get("name", "This stock")
    pe = ratios.get("pe")
    roe = ratios.get("roe")
    roce = ratios.get("roce")
    opm = ratios.get("opm")
    debt_eq = ratios.get("debt_equity")
    promoter = ratios.get("promoter_holding")

    fundamentals_ok = roe and roe > 12 and (debt_eq is None or debt_eq < 1.5)
    growth_ok = ratios.get("sales_growth") and ratios.get("sales_growth", 0) > 10

    ind = (tv or {}).get("indicators") or {}
    rsi = ind.get("rsi")
    trend_up = ind.get("close") and ind.get("ema50") and ind.get("close", 0) > ind.get("ema50", 0)

    bull_parts = []
    bear_parts = []

    if fundamentals_ok:
        bull_parts.append(f"strong fundamentals (ROE {roe:.1f}%)")
    if growth_ok:
        bull_parts.append(f"healthy revenue growth ({ratios.get('sales_growth'):.1f}%)")
    if trend_up:
        bull_parts.append("bullish price trend above EMA50")
    if roce and roce > 18:
        bull_parts.append(f"high capital efficiency ROCE {roce:.1f}%")
    if promoter and promoter > 55:
        bull_parts.append(f"high promoter confidence ({promoter:.1f}% holding)")

    if risk_flags:
        bear_parts.extend(risk_flags[:3])
    if rsi and rsi > 70:
        bear_parts.append(f"near-term overbought (RSI {rsi:.0f})")
    if not fundamentals_ok:
        bear_parts.append("below-average return ratios")
    if not growth_ok and ratios.get("sales_growth") is not None:
        bear_parts.append("slow revenue growth")

    bull_case = "Bull case: " + "; ".join(bull_parts[:3]) if bull_parts else "Limited upside catalysts identified."
    bear_case = "Bear case: " + "; ".join(bear_parts[:3]) if bear_parts else "No major red flags detected."

    top_signal = signals[0] if signals else "Mixed signals"
    summary = f"{verdict} with {len(signals)} confirming signals. {top_signal}."

    return summary, bull_case, bear_case


# ── Main Composite Scorer ──────────────────────────────────────────────────────

def analyze_stock(
    symbol: str,
    tv: Optional[dict] = None,
    screener: Optional[dict] = None,
    patterns: Optional[list] = None,
) -> AIVerdict:
    """
    Full AI analysis. Returns AIVerdict with verdict, scores, narrative.
    Weights: Technical 35%, Fundamental 35%, Pattern 15%, Momentum 15%
    """
    tech_score, tech_signals = score_technicals(tv or {})
    fund_score, fund_signals = score_fundamentals(screener or {})
    pat_score, pat_signals = score_patterns(patterns or [])
    mom_score, mom_signals = score_momentum(tv or {}, screener or {})

    # Weighted composite
    composite = (
        tech_score * 0.35 +
        fund_score * 0.35 +
        pat_score  * 0.15 +
        mom_score  * 0.15
    )

    all_signals = tech_signals + fund_signals + pat_signals + mom_signals

    # Verdict thresholds
    if composite >= 78:
        verdict = STRONG_BUY
    elif composite >= 63:
        verdict = BUY
    elif composite >= 45:
        verdict = HOLD
    elif composite >= 32:
        verdict = SELL
    else:
        verdict = STRONG_SELL

    # Confidence based on data availability + signal convergence
    has_tv = bool(tv and (tv.get("indicators") or {}).get("close"))
    has_screener = bool(screener and (screener.get("ratios") or {}).get("pe") is not None)
    has_patterns = bool(patterns)
    data_count = sum([has_tv, has_screener, has_patterns])
    if data_count == 3 and len(all_signals) >= 6:
        confidence = "High"
    elif data_count >= 2:
        confidence = "Medium"
    elif data_count == 1:
        confidence = "Low"
    else:
        confidence = "Low"  # no real data — scores are defaults

    # Price targets
    close = ((tv or {}).get("indicators") or {}).get("close") or 0
    target, stop_loss, upside = estimate_price_targets(close, composite, tv or {}, screener or {})

    # Risk flags
    risk_flags = extract_risk_flags(tv or {}, screener or {})

    # Narrative
    summary, bull_case, bear_case = generate_narrative(
        verdict, all_signals, risk_flags, screener or {}, tv or {}
    )

    return AIVerdict(
        verdict=verdict,
        score=round(composite, 1),
        tech_score=round(tech_score, 1),
        fund_score=round(fund_score, 1),
        pattern_score=round(pat_score, 1),
        momentum_score=round(mom_score, 1),
        confidence=confidence,
        price_target=target,
        stop_loss=stop_loss,
        upside_pct=upside,
        bull_case=bull_case,
        bear_case=bear_case,
        risk_flags=risk_flags,
        signals=all_signals[:10],
        summary=summary,
    )


def analyze_batch(
    symbols: list[str],
    tv_data: dict,
    screener_data: dict,
    patterns_data: dict,
) -> dict[str, AIVerdict]:
    """Analyze multiple stocks. Returns {symbol: AIVerdict}."""
    return {
        sym: analyze_stock(
            sym,
            tv=tv_data.get(sym),
            screener=screener_data.get(sym),
            patterns=patterns_data.get(sym, []),
        )
        for sym in symbols
    }
