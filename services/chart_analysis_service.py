"""
Rule-based professional chart analysis for NSE/BSE stocks.

This module produces the same 14-section institutional-grade analysis that the
old Claude-based version produced, but uses **no external API and no API key**.
All analysis is done locally by reasoning over the OHLCV + indicators +
detected patterns + fundamentals payload.

Public API (kept stable):
  - analyze_chart_data(symbol, timeframe, ohlcv_df, indicators, patterns,
                       fundamentals, extra_context, sector, company_name)
  - resample_ohlcv(df, timeframe)
  - compute_indicators_from_ohlcv(df)
  - has_api_key()  -> always True now (kept for backwards compatibility)
"""
from __future__ import annotations
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Backwards-compat shim — no API key needed anymore
# ─────────────────────────────────────────────────────────────────────────────
def has_api_key() -> bool:
    """Always True — analysis is fully local."""
    return True


# ─────────────────────────────────────────────────────────────────────────────
# OHLCV resample helper
# ─────────────────────────────────────────────────────────────────────────────
def resample_ohlcv(df, timeframe: str):
    if df is None or df.empty:
        return df
    tf = timeframe.lower()
    if tf.startswith("d"):
        return df
    rule = "W" if tf.startswith("w") else "ME"
    try:
        return df.resample(rule).agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna()
    except Exception as e:
        logger.debug(f"Resample failed: {e}")
        return df


# ─────────────────────────────────────────────────────────────────────────────
# Indicator computation (re-exported for compatibility with the old API)
# ─────────────────────────────────────────────────────────────────────────────
def compute_indicators_from_ohlcv(df) -> dict:
    if df is None or df.empty:
        return {}
    try:
        import ta
        c = df["Close"]; h = df["High"]; l = df["Low"]; v = df.get("Volume")
        ind: dict = {
            "close":  float(c.iloc[-1]),
            "open":   float(df["Open"].iloc[-1]),
            "high":   float(h.iloc[-1]),
            "low":    float(l.iloc[-1]),
            "volume": float(v.iloc[-1]) if v is not None else None,
            "change": float((c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100) if len(c) > 1 else 0,
        }
        if len(c) >= 14:
            ind["rsi"] = float(ta.momentum.RSIIndicator(c, window=14).rsi().iloc[-1])
            macd = ta.trend.MACD(c)
            ind["macd"] = float(macd.macd().iloc[-1])
            ind["macd_signal"] = float(macd.macd_signal().iloc[-1])
            ind["macd_hist"]   = float(macd.macd_diff().iloc[-1])
            adx = ta.trend.ADXIndicator(h, l, c)
            ind["adx"]     = float(adx.adx().iloc[-1])
            ind["adx_pos"] = float(adx.adx_pos().iloc[-1])
            ind["adx_neg"] = float(adx.adx_neg().iloc[-1])
            ind["atr"]     = float(ta.volatility.AverageTrueRange(h, l, c).average_true_range().iloc[-1])
        if len(c) >= 20:
            ind["sma20"] = float(ta.trend.SMAIndicator(c, window=20).sma_indicator().iloc[-1])
            ind["ema20"] = float(ta.trend.EMAIndicator(c, window=20).ema_indicator().iloc[-1])
            bb = ta.volatility.BollingerBands(c)
            ind["bb_upper"] = float(bb.bollinger_hband().iloc[-1])
            ind["bb_lower"] = float(bb.bollinger_lband().iloc[-1])
            ind["bb_mid"]   = float(bb.bollinger_mavg().iloc[-1])
            stoch = ta.momentum.StochasticOscillator(h, l, c)
            ind["stoch_k"] = float(stoch.stoch().iloc[-1])
            ind["stoch_d"] = float(stoch.stoch_signal().iloc[-1])
            ind["cci20"]   = float(ta.trend.CCIIndicator(h, l, c, window=20).cci().iloc[-1])
        if len(c) >= 50:
            ind["sma50"] = float(ta.trend.SMAIndicator(c, window=50).sma_indicator().iloc[-1])
            ind["ema50"] = float(ta.trend.EMAIndicator(c, window=50).ema_indicator().iloc[-1])
        if len(c) >= 200:
            ind["sma200"] = float(ta.trend.SMAIndicator(c, window=200).sma_indicator().iloc[-1])
            ind["ema200"] = float(ta.trend.EMAIndicator(c, window=200).ema_indicator().iloc[-1])
        return {k: (None if (v is not None and v != v) else v) for k, v in ind.items()}
    except Exception as e:
        logger.debug(f"compute_indicators failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities for analysis sections
# ─────────────────────────────────────────────────────────────────────────────
def _safe(v, default=None):
    if v is None:
        return default
    try:
        f = float(v)
        if f != f:  # NaN
            return default
        return f
    except Exception:
        return default


def _trend_context(df, ind: dict) -> dict:
    """Compute trend metadata used by multiple sections."""
    close = _safe(ind.get("close"), 0)
    sma20 = _safe(ind.get("sma20"))
    sma50 = _safe(ind.get("sma50"))
    sma200 = _safe(ind.get("sma200"))
    ema20 = _safe(ind.get("ema20"))
    ema50 = _safe(ind.get("ema50"))
    ema200 = _safe(ind.get("ema200"))
    adx = _safe(ind.get("adx"), 0)
    adx_pos = _safe(ind.get("adx_pos"), 0)
    adx_neg = _safe(ind.get("adx_neg"), 0)

    bull_stack = (close and ema20 and ema50 and ema200
                  and close > ema20 > ema50 > ema200)
    bear_stack = (close and ema20 and ema50 and ema200
                  and close < ema20 < ema50 < ema200)

    primary = "sideways"
    if bull_stack or (close and sma200 and close > sma200 * 1.05):
        primary = "uptrend"
    elif bear_stack or (close and sma200 and close < sma200 * 0.95):
        primary = "downtrend"

    short_term = "sideways"
    if close and sma20 and close > sma20 * 1.02:
        short_term = "uptrend"
    elif close and sma20 and close < sma20 * 0.98:
        short_term = "downtrend"

    long_term = "sideways"
    if close and sma200:
        if close > sma200 * 1.10: long_term = "strong uptrend"
        elif close > sma200:      long_term = "uptrend"
        elif close < sma200 * 0.90: long_term = "strong downtrend"
        else: long_term = "downtrend"

    if adx >= 35:    strength = "very strong"
    elif adx >= 25:  strength = "strong"
    elif adx >= 20:  strength = "moderate"
    else:            strength = "weak"

    golden_cross = sma50 and sma200 and sma50 > sma200
    death_cross  = sma50 and sma200 and sma50 < sma200

    return {
        "close": close, "sma20": sma20, "sma50": sma50, "sma200": sma200,
        "ema20": ema20, "ema50": ema50, "ema200": ema200,
        "adx": adx, "adx_pos": adx_pos, "adx_neg": adx_neg,
        "primary": primary, "short_term": short_term, "long_term": long_term,
        "strength": strength,
        "bull_stack": bull_stack, "bear_stack": bear_stack,
        "golden_cross": golden_cross, "death_cross": death_cross,
    }


def _support_resistance(df, ind: dict) -> dict:
    """Identify key S/R levels using recent pivots + 52w + MAs."""
    close = _safe(ind.get("close"), 0)
    h = df["High"]; l = df["Low"]
    hi_52 = float(h.tail(252).max()) if len(h) >= 20 else float(h.max())
    lo_52 = float(l.tail(252).min()) if len(l) >= 20 else float(l.min())
    pivot_hi_20 = float(h.tail(20).max())
    pivot_lo_20 = float(l.tail(20).min())
    pivot_hi_60 = float(h.tail(60).max()) if len(h) >= 60 else pivot_hi_20
    pivot_lo_60 = float(l.tail(60).min()) if len(l) >= 60 else pivot_lo_20

    # Find immediate S/R relative to current price
    candidates_above = sorted({pivot_hi_20, pivot_hi_60, hi_52,
                                _safe(ind.get("sma50"), 0),
                                _safe(ind.get("sma200"), 0),
                                _safe(ind.get("bb_upper"), 0)} - {0})
    candidates_below = sorted({pivot_lo_20, pivot_lo_60, lo_52,
                                _safe(ind.get("sma50"), 0),
                                _safe(ind.get("sma200"), 0),
                                _safe(ind.get("bb_lower"), 0)} - {0}, reverse=True)

    immediate_resistance = next((v for v in candidates_above if v > close), pivot_hi_60)
    major_resistance     = max(candidates_above) if candidates_above else hi_52
    immediate_support    = next((v for v in candidates_below if v < close), pivot_lo_60)
    major_support        = min(candidates_below) if candidates_below else lo_52

    return {
        "immediate_resistance": immediate_resistance,
        "major_resistance":     major_resistance,
        "immediate_support":    immediate_support,
        "major_support":        major_support,
        "hi_52": hi_52, "lo_52": lo_52,
        "pivot_hi_20": pivot_hi_20, "pivot_lo_20": pivot_lo_20,
    }


def _volume_profile(df, ind: dict) -> dict:
    v = df.get("Volume")
    if v is None or len(v) < 20:
        return {"summary": "(no volume data)"}
    cur = float(v.iloc[-1])
    avg20 = float(v.tail(20).mean())
    avg5 = float(v.tail(5).mean())
    rel_cur = cur / avg20 if avg20 else 1
    rel_5 = avg5 / avg20 if avg20 else 1

    if rel_cur > 2.0:    note = "exceptional volume spike — institutional involvement"
    elif rel_cur > 1.5:  note = "above-average volume — accumulation likely"
    elif rel_cur > 0.7:  note = "normal volume"
    else:                note = "low volume — lack of conviction"

    accum_dist = "accumulation" if rel_5 > 1.2 else ("distribution" if rel_5 < 0.8 else "neutral")

    return {
        "current": cur, "avg20": avg20, "rel_cur": rel_cur,
        "accum_dist": accum_dist, "note": note,
    }


def _momentum_assessment(ind: dict) -> dict:
    rsi = _safe(ind.get("rsi"))
    macd = _safe(ind.get("macd"))
    macd_sig = _safe(ind.get("macd_signal"))
    stoch_k = _safe(ind.get("stoch_k"))
    stoch_d = _safe(ind.get("stoch_d"))
    cci = _safe(ind.get("cci20"))

    score = 0
    notes = []
    if rsi is not None:
        if rsi > 70:    score -= 2; notes.append(f"RSI overbought ({rsi:.1f})")
        elif rsi > 60:  score += 1; notes.append(f"RSI bullish momentum ({rsi:.1f})")
        elif rsi < 30:  score += 2; notes.append(f"RSI oversold bounce zone ({rsi:.1f})")
        elif rsi < 40:  score -= 1; notes.append(f"RSI bearish ({rsi:.1f})")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig:
            score += 1; notes.append("MACD bullish crossover")
        else:
            score -= 1; notes.append("MACD bearish")
    if stoch_k is not None and stoch_d is not None:
        if stoch_k > 80:    score -= 1; notes.append("Stochastic overbought")
        elif stoch_k < 20:  score += 1; notes.append("Stochastic oversold")
        elif stoch_k > stoch_d: score += 1
    if cci is not None:
        if cci > 100:    notes.append(f"CCI strong ({cci:.0f})")
        elif cci < -100: notes.append(f"CCI weak ({cci:.0f})")

    if score >= 3:    label = "strong bullish"
    elif score >= 1:  label = "weak bullish"
    elif score <= -3: label = "strong bearish"
    elif score <= -1: label = "weak bearish"
    else:             label = "neutral / mixed"

    if rsi is not None and (rsi > 75 or rsi < 25):
        cont = "Low (extreme reading — reversal risk)"
    elif abs(score) >= 3:
        cont = "High"
    elif abs(score) >= 1:
        cont = "Medium"
    else:
        cont = "Low (range-bound)"

    return {"score": score, "label": label, "notes": notes, "continuation": cont}


def _trade_setup(df, ind: dict, sr: dict, mom: dict, trend: dict) -> dict:
    close = _safe(ind.get("close"), 0)
    atr = _safe(ind.get("atr"), close * 0.015 if close else 0)

    bullish_bias = (mom["score"] > 0 and trend["primary"] != "downtrend")
    bearish_bias = (mom["score"] < 0 and trend["primary"] != "uptrend")

    if bullish_bias:
        best_low  = max(close - atr * 0.5, sr["immediate_support"])
        best_high = close + atr * 0.3
        safe = sr["immediate_support"] + atr * 0.2
        aggressive = close + atr * 0.5
        stop = sr["immediate_support"] - atr * 1.0
        t1 = sr["immediate_resistance"]
        t2 = sr["major_resistance"]
        positional = max(t2 + atr * 2, close * 1.20)
        risk = close - stop
        reward = t1 - close
        rr = (reward / risk) if risk > 0 else 0
    elif bearish_bias:
        best_high = min(close + atr * 0.5, sr["immediate_resistance"])
        best_low  = close - atr * 0.3
        safe = sr["immediate_resistance"] - atr * 0.2
        aggressive = close - atr * 0.5
        stop = sr["immediate_resistance"] + atr * 1.0
        t1 = sr["immediate_support"]
        t2 = sr["major_support"]
        positional = min(t2 - atr * 2, close * 0.80)
        risk = stop - close
        reward = close - t1
        rr = (reward / risk) if risk > 0 else 0
    else:
        # Neutral — wait-and-watch setup
        best_low = sr["immediate_support"]
        best_high = sr["immediate_support"] + atr * 0.5
        safe = sr["immediate_support"]
        aggressive = close
        stop = sr["immediate_support"] - atr * 1.5
        t1 = sr["immediate_resistance"]
        t2 = sr["major_resistance"]
        positional = sr["major_resistance"]
        rr = 0

    return {
        "bias": "bullish" if bullish_bias else ("bearish" if bearish_bias else "neutral"),
        "best_low": best_low, "best_high": best_high,
        "safe": safe, "aggressive": aggressive, "stop": stop,
        "t1": t1, "t2": t2, "positional": positional,
        "rr": rr,
    }


def _probability_scores(trend: dict, sr: dict, vol: dict, mom: dict, setup: dict, ind: dict) -> dict:
    close = _safe(ind.get("close"), 0)
    # Breakout probability
    near_resistance = sr["immediate_resistance"] and close > 0 and (sr["immediate_resistance"] - close) / close < 0.02
    bp = 5
    if near_resistance and vol.get("rel_cur", 1) > 1.5 and mom["score"] >= 2: bp = 8
    elif near_resistance and mom["score"] >= 1: bp = 7
    elif near_resistance: bp = 6
    elif setup["bias"] == "bullish" and trend["primary"] == "uptrend": bp = 7
    elif setup["bias"] == "bearish": bp = 4

    # Trend quality from ADX + EMA stack
    if trend["bull_stack"] or trend["bear_stack"]: tq = 9
    elif trend["adx"] >= 30:  tq = 8
    elif trend["adx"] >= 25:  tq = 7
    elif trend["adx"] >= 20:  tq = 6
    else: tq = 4

    # R:R quality
    rr = setup["rr"]
    if rr >= 3:    rq = 9
    elif rr >= 2:  rq = 7
    elif rr >= 1.5: rq = 6
    elif rr >= 1:  rq = 5
    else:          rq = 3

    overall = round((bp + tq + rq) / 3)
    return {"breakout": bp, "trend_quality": tq, "rr": rq, "overall": overall}


def _red_flags(trend: dict, sr: dict, vol: dict, mom: dict, ind: dict, df) -> list:
    flags = []
    close = _safe(ind.get("close"), 0)
    rsi = _safe(ind.get("rsi"))
    if rsi is not None and rsi > 75:
        flags.append(f"Severely overbought RSI ({rsi:.1f}) — pullback risk")
    if rsi is not None and rsi < 25:
        flags.append(f"Severely oversold RSI ({rsi:.1f}) — falling-knife risk")
    if close and sr.get("hi_52") and (sr["hi_52"] - close) / sr["hi_52"] < 0.03:
        flags.append("Right at 52W high — fakeout risk if volume weak")
    if vol.get("rel_cur", 1) < 0.6 and trend["primary"] == "uptrend":
        flags.append("Low volume rally — distribution / lack of conviction")
    if trend["death_cross"]:
        flags.append("Death cross active (50 SMA below 200 SMA)")
    if close and trend.get("ema20") and (close - trend["ema20"]) / trend["ema20"] > 0.10:
        flags.append("Price overextended >10% from EMA20 — mean-reversion likely")
    if mom["score"] >= 2 and trend["primary"] == "downtrend":
        flags.append("Bullish momentum inside a downtrend — potential bull trap")
    if mom["score"] <= -2 and trend["primary"] == "uptrend":
        flags.append("Bearish momentum inside an uptrend — potential bear trap")
    return flags[:5]


def _smart_money_read(trend: dict, vol: dict, mom: dict, sr: dict, ind: dict) -> str:
    close = _safe(ind.get("close"), 0)
    if vol.get("rel_cur", 1) > 1.8 and mom["score"] >= 2 and trend["primary"] != "downtrend":
        return "**Institutional accumulation** — high-volume bullish bars near support suggest smart money is loading."
    if vol.get("rel_cur", 1) > 1.8 and mom["score"] <= -2:
        return "**Distribution detected** — heavy volume on down days indicates institutional offloading."
    if close and sr["immediate_resistance"] and (sr["immediate_resistance"] - close) / close < 0.015 and vol.get("rel_cur", 1) > 1.4:
        return "**Institutional breakout setup** — price compressing under resistance with rising volume."
    if mom["score"] >= 2 and vol.get("rel_cur", 1) < 0.7:
        return "**Possible retail trap** — momentum positive but volume weak; smart money is not participating."
    if vol.get("accum_dist") == "accumulation":
        return "Mild accumulation pattern — building base, not yet decisive."
    if vol.get("accum_dist") == "distribution":
        return "Mild distribution pattern — selling pressure building."
    return "No clear institutional footprint — broad market behavior."


def _verdict(setup: dict, prob: dict, mom: dict, trend: dict) -> tuple:
    bias = setup["bias"]
    overall = prob["overall"]
    if bias == "bullish" and overall >= 8 and prob["rr"] >= 7:
        return "Strong Buy Setup", "High"
    if bias == "bullish" and overall >= 6:
        return "Buy on Dip", "Medium"
    if bias == "bearish" and overall >= 7:
        return "Breakdown Risk", "High"
    if bias == "bearish":
        return "Avoid", "Medium"
    if overall >= 6:
        return "Watchlist Only", "Medium"
    return "Watchlist Only", "Low"


def _pro_explanation(verdict: str, trend: dict, mom: dict, setup: dict, sr: dict, vol: dict, sym: str) -> str:
    parts = []
    if verdict == "Strong Buy Setup":
        parts.append(f"{sym} is showing a high-quality bullish setup")
    elif verdict == "Buy on Dip":
        parts.append(f"{sym} looks attractive but better bought on a pullback to support")
    elif verdict == "Watchlist Only":
        parts.append(f"{sym} is in no-man's-land — track but don't act yet")
    elif verdict == "Avoid":
        parts.append(f"{sym} has too many red flags right now")
    elif verdict == "Breakdown Risk":
        parts.append(f"{sym} is at risk of a fresh breakdown")

    parts.append(f"primary trend is {trend['primary']} with {trend['strength']} strength (ADX {trend['adx']:.1f})")
    parts.append(f"momentum is {mom['label']}")
    parts.append(f"the trade should target {setup['t1']:.0f} with stop at {setup['stop']:.0f}, giving roughly 1:{setup['rr']:.1f} R:R")
    if vol.get("note"):
        parts.append(f"volume note: {vol['note']}")
    return ". ".join(parts).capitalize() + "."


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — produces the 14-section markdown analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_chart_data(
    symbol: str,
    timeframe: str,
    ohlcv_df: Any,
    indicators: Optional[dict] = None,
    patterns: Optional[list] = None,
    fundamentals: Optional[dict] = None,
    extra_context: str = "",
    sector: str = "",
    company_name: str = "",
) -> dict:
    """
    Returns dict {success, analysis, error}.
    Generates a complete institutional-style 14-section markdown report.
    """
    if ohlcv_df is None or ohlcv_df.empty:
        return {"success": False, "analysis": "", "error": "No OHLCV data provided."}

    ind  = indicators or {}
    pats = patterns or []
    fund = fundamentals or {}

    trend = _trend_context(ohlcv_df, ind)
    sr    = _support_resistance(ohlcv_df, ind)
    vol   = _volume_profile(ohlcv_df, ind)
    mom   = _momentum_assessment(ind)
    setup = _trade_setup(ohlcv_df, ind, sr, mom, trend)
    prob  = _probability_scores(trend, sr, vol, mom, setup, ind)
    flags = _red_flags(trend, sr, vol, mom, ind, ohlcv_df)
    smart = _smart_money_read(trend, vol, mom, sr, ind)
    verdict, confidence = _verdict(setup, prob, mom, trend)
    pro_text = _pro_explanation(verdict, trend, mom, setup, sr, vol, symbol)

    # Bullish/Bearish stack labels
    if trend["bull_stack"]:
        ema_align = "**bullish stack** (Price > EMA20 > EMA50 > EMA200) — strongest configuration"
    elif trend["bear_stack"]:
        ema_align = "**bearish stack** (Price < EMA20 < EMA50 < EMA200) — weakest configuration"
    else:
        ema_align = "mixed alignment — no clear EMA hierarchy"

    cross_note = ""
    if trend["golden_cross"]:
        cross_note = "Golden Cross active (50 SMA above 200 SMA) — long-term bullish."
    elif trend["death_cross"]:
        cross_note = "Death Cross active (50 SMA below 200 SMA) — long-term bearish."

    # Pattern section
    if pats:
        pat_lines = []
        for p in pats[:6]:
            name = p.get("name", "?") if isinstance(p, dict) else str(p)
            conf = p.get("confidence", 0) if isinstance(p, dict) else 0
            d = p.get("direction", "neutral") if isinstance(p, dict) else "neutral"
            pat_lines.append(f"- **{name}** — {d}, {conf}% confidence")
        pat_block = "\n".join(pat_lines)
    else:
        pat_block = "- No high-confidence chart patterns detected by the engine on this timeframe"

    # Fundamentals snapshot
    fund_lines = []
    fund_pairs = [
        ("PE", fund.get("pe"), "x"),
        ("ROE", fund.get("roe"), "%"),
        ("ROCE", fund.get("roce"), "%"),
        ("D/E", fund.get("debt_equity"), "x"),
        ("Promoter %", fund.get("promoter_holding"), "%"),
        ("Sales Gr.", fund.get("sales_growth"), "%"),
        ("Profit Gr.", fund.get("profit_growth"), "%"),
    ]
    for k, v, suf in fund_pairs:
        if v is not None:
            try:
                fund_lines.append(f"- {k}: **{float(v):.2f}{suf}**")
            except Exception:
                pass
    fund_block = "\n".join(fund_lines) if fund_lines else "- (fundamentals not available)"

    close = trend["close"]
    rsi = _safe(ind.get("rsi"))
    macd = _safe(ind.get("macd"))
    macd_sig = _safe(ind.get("macd_signal"))

    md = f"""# {symbol} — {timeframe} Chart Analysis
{f"_{company_name}_  · " if company_name else ""}{f"_{sector}_" if sector else ""}

**1. TREND ANALYSIS**
- Primary trend: **{trend['primary']}**
- Short-term: {trend['short_term']} · Long-term: {trend['long_term']}
- Trend strength: **{trend['strength']}** (ADX {trend['adx']:.1f}, +DI {trend['adx_pos']:.1f}, -DI {trend['adx_neg']:.1f})

**2. PRICE STRUCTURE**
- Current Price: ₹{close:,.2f}
- Recent 20-bar range: ₹{sr['pivot_lo_20']:,.2f} – ₹{sr['pivot_hi_20']:,.2f}
- 52-period: ₹{sr['lo_52']:,.2f} – ₹{sr['hi_52']:,.2f}
- Phase: {"compression near resistance" if sr['immediate_resistance'] - close < (close * 0.02) else ("expansion" if abs(_safe(ind.get('change'), 0)) > 2 else "consolidation")}

**3. CHART PATTERNS**
{pat_block}

**4. MOVING AVERAGES**
- EMA alignment: {ema_align}
- {cross_note if cross_note else "No active golden/death cross"}
- Price vs key MAs: SMA50 {f'₹{trend["sma50"]:,.2f}' if trend['sma50'] else '—'} · SMA200 {f'₹{trend["sma200"]:,.2f}' if trend['sma200'] else '—'}

**5. SUPPORT & RESISTANCE**
- Immediate Resistance: **₹{sr['immediate_resistance']:,.2f}**
- Major Resistance: ₹{sr['major_resistance']:,.2f}
- Immediate Support: **₹{sr['immediate_support']:,.2f}**
- Major Support: ₹{sr['major_support']:,.2f}

**6. VOLUME ANALYSIS**
- Latest volume: {vol.get('current', 0):,.0f}
- 20-bar avg volume: {vol.get('avg20', 0):,.0f}
- Relative: {vol.get('rel_cur', 1):.2f}x average
- Pattern: **{vol.get('accum_dist', 'neutral')}** — {vol.get('note', '')}

**7. MOMENTUM**
- Overall momentum: **{mom['label']}** (composite score {mom['score']:+d})
- Trend continuation probability: **{mom['continuation']}**
- Key signals: {', '.join(mom['notes'][:4]) if mom['notes'] else '—'}

**8. RISK MANAGEMENT — TRADE SETUP**
Bias: **{setup['bias'].upper()}**
- Best Entry Zone: ₹{setup['best_low']:,.2f} to ₹{setup['best_high']:,.2f}
- Safe Entry: ₹{setup['safe']:,.2f}
- Aggressive Entry: ₹{setup['aggressive']:,.2f}
- Stop Loss: **₹{setup['stop']:,.2f}**
- Swing Target 1: ₹{setup['t1']:,.2f}
- Swing Target 2: ₹{setup['t2']:,.2f}
- Positional Target: ₹{setup['positional']:,.2f}
- **Risk : Reward = 1 : {setup['rr']:.2f}**

**9. PROBABILITY SCORES**
- Breakout Probability: **{prob['breakout']}/10**
- Trend Quality: **{prob['trend_quality']}/10**
- Risk-Reward Quality: **{prob['rr']}/10**
- Overall Setup Quality: **{prob['overall']}/10**

**10. RED FLAGS & WARNINGS**
{chr(10).join(f"- {f}" for f in flags) if flags else "- No major red flags detected on current data."}

**11. SMART MONEY PERSPECTIVE**
{smart}

**12. FUNDAMENTALS SNAPSHOT**
{fund_block}

**13. FINAL VERDICT: {verdict}**

**CONFIDENCE LEVEL: {confidence}**

**14. PRO TRADER EXPLANATION**
{pro_text}
{f"_Additional context noted: {extra_context}_" if extra_context else ""}
"""
    return {"success": True, "analysis": md, "error": ""}
