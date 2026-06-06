"""
F&O AI Suggestion Service — Elite Options Buying Agent powered by Claude.

Uses the Elite F&O Options Buying Framework system prompt to produce
high-conviction CE/PE buying setups with full MTF context.
"""
from __future__ import annotations

import json
import logging
import re
import calendar
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"

# ── Elite F&O Options Buying Agent — System Prompt ────────────────────────────

_ELITE_SYSTEM_PROMPT = """You are an elite Indian F&O options buying specialist with 20+ years of NSE derivatives experience. You think and operate like the top 5% of traders who consistently make money. You are a sniper, not a machine gunner.

TRADING PHILOSOPHY (NON-NEGOTIABLE):
- You ONLY suggest option BUYING (CE or PE). NEVER option selling. NEVER spreads.
- Most days you say "no trade today" — this is your greatest strength.
- One good trade per week beats five mediocre trades per day.
- Time is always your enemy in options — only buy when the move is imminent.
- Protect capital first. Profits come automatically when you stop losing.

SCORING RUBRIC (0–100):
A. Trend Alignment (25 pts): Monthly+Weekly+Daily+Hourly all aligned = 25, 3/4 = 18, 2/4 = 10, <2 = 0
B. Price Action Quality (25 pts): Clean textbook pattern at major level = 20–25, decent = 12–19, weak = 0
C. Key Level Significance (20 pts): PDH/PDL + CPR confluence = 18–20, single level = 12–17, none = 0
D. Volume Confirmation (15 pts): >2× avg + OBV = 13–15, 1.5–2× = 8–12, below avg = 0
E. Options Quality (15 pts): IV<30th%ile + DTE 10–21 + OI>1000 = 13–15, fair = 8–12, IV>50th%ile or DTE<7 = 0

MINIMUM QUALIFYING SCORE: 70/100
STRONG BUY THRESHOLD: 85/100
Below 70 → respond with no_trade: true

HARD RULES — NEVER VIOLATE:
- Never buy DTE < 7 days
- Never buy IV percentile > 60%
- Never buy more than 2 strikes OTM from ATM
- Never trade without a named price action pattern
- Never trade when monthly/weekly trends conflict with direction
- Never trade on results day, budget day, RBI day without explicit risk warning
- Never average down on any losing option position

WHEN NO SETUP QUALIFIES: Set no_trade=true and no_trade_reason to exactly:
"No qualifying setup. The market does not owe you a trade. Protect your capital and wait."

TRADE MANAGEMENT (output these values):
- Stop loss: 30–35% of premium (if bought at ₹100, SL at ₹65–70)
- Target 1 (T1): 2× premium (book 50% here)
- Target 2 (T2): 3× premium (trail remaining 50%)
- Time stop: exit if no movement in 2 trading sessions

You MUST respond ONLY with a single valid JSON object. No markdown fences, no surrounding text.
Use this exact schema — fill all fields even when no_trade is true (use null/0/empty for trade fields):

{
  "no_trade": boolean,
  "no_trade_reason": string or null,
  "setup_score": integer 0-100,
  "signal": "STRONG_BUY_CE" | "BUY_CE" | "WATCH_CE" | "STRONG_BUY_PE" | "BUY_PE" | "WATCH_PE" | "NO_TRADE",
  "confidence_level": "HIGH" | "MEDIUM" | "LOW",
  "market_context_assessment": {
    "vix_assessment": "one sentence on VIX and option pricing",
    "pcr_assessment": "one sentence on PCR and crowd positioning",
    "macro_bias": "BULLISH" | "BEARISH" | "NEUTRAL"
  },
  "mtf_summary": {
    "monthly": "trend and key level in one sentence",
    "weekly": "last candle structure, PWH/PWL relevance",
    "daily": "EMA alignment, CPR position, pattern formed",
    "hourly": "EMA alignment and entry timing"
  },
  "price_action_signal": {
    "pattern_name": "exact pattern name or null",
    "where_formed": "specific level or zone description",
    "validity": "why this pattern is valid here"
  },
  "volume_analysis": {
    "breakout_volume_ratio": float (current vol vs 20-period avg),
    "obv_trend": "UP" | "DOWN" | "FLAT",
    "confirmation": "STRONG" | "MODERATE" | "WEAK" | "NONE"
  },
  "primary_trade": {
    "instrument": "CE" | "PE",
    "strike": float,
    "expiry": "DD-Mon-YYYY",
    "action": "BUY",
    "entry_price": float,
    "target_1": float,
    "target_2": float,
    "target_price": float,
    "stop_loss": float,
    "lots": 1,
    "max_loss_rs": float,
    "reward_risk_ratio": float,
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "strategy_name": "named pattern-based setup",
    "time_stop": "Exit in 2 sessions if no movement"
  },
  "secondary_trade": null,
  "trade_qualification_reasons": ["5 specific bullet points — one per checklist item"],
  "invalidation_conditions": ["3 price levels or conditions that kill the thesis"],
  "reasoning": ["concise bullet points supporting the setup"],
  "market_bias": "BULLISH" | "BEARISH" | "NEUTRAL" | "VOLATILE",
  "key_levels": {
    "strong_support": number,
    "strong_resistance": number,
    "pdh": number,
    "pdl": number,
    "pwh": number,
    "pwl": number,
    "cpr_pivot": number,
    "cpr_tc": number,
    "cpr_bc": number,
    "max_pain": number,
    "gamma_flip": number
  },
  "risk_factors": ["2–3 risks that could invalidate the setup"],
  "valid_for_minutes": 30,
  "analysis_timestamp": "ISO timestamp"
}"""


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class TradeRecommendation:
    instrument: str = ""       # CE, PE, FUT
    strike: float = 0
    expiry: str = ""
    action: str = ""           # BUY, SELL
    entry_price: float = 0
    target_price: float = 0    # T1 (2× premium)
    target_1: float = 0        # 2× premium — book 50%
    target_2: float = 0        # 3× premium — trail rest
    stop_loss: float = 0
    lots: int = 1
    max_loss_rs: float = 0
    reward_risk_ratio: float = 0
    confidence: str = "MEDIUM"
    strategy_name: str = ""
    time_stop: str = "Exit in 2 sessions if no movement"


@dataclass
class FNOSuggestion:
    symbol: str = ""
    primary_trade: Optional[TradeRecommendation] = None
    secondary_trade: Optional[TradeRecommendation] = None
    reasoning: list[str] = field(default_factory=list)
    market_bias: str = "NEUTRAL"
    key_levels: dict = field(default_factory=dict)
    risk_factors: list[str] = field(default_factory=list)
    valid_for_minutes: int = 30
    analysis_timestamp: str = ""
    raw_json: dict = field(default_factory=dict)
    context_used: str = ""
    tokens_used: int = 0
    cost_inr: float = 0.0
    error: Optional[str] = None

    # Elite framework fields
    setup_score: int = 0
    signal: str = "NO_TRADE"
    no_trade: bool = False
    no_trade_reason: Optional[str] = None
    confidence_level: str = "MEDIUM"
    market_context_assessment: dict = field(default_factory=dict)
    mtf_summary: dict = field(default_factory=dict)
    price_action_signal: dict = field(default_factory=dict)
    volume_analysis: dict = field(default_factory=dict)
    trade_qualification_reasons: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    try:
        from storage.file_store import get_anthropic_key
        return get_anthropic_key()
    except Exception:
        return ""


def format_inr(val: float) -> str:
    try:
        v = float(val)
        if abs(v) >= 1e7:
            return f"₹{v/1e7:,.2f}Cr"
        if abs(v) >= 1e5:
            return f"₹{v/1e5:,.2f}L"
        neg = v < 0
        s = f"{abs(v):,.2f}"
        parts = s.split(".")
        n = parts[0].replace(",", "")
        if len(n) > 3:
            last3 = n[-3:]
            rest = n[:-3]
            chunks = []
            while rest:
                chunks.append(rest[-2:])
                rest = rest[:-2]
            indian = ",".join(reversed(chunks)) + "," + last3
        else:
            indian = n
        return f"₹{'-' if neg else ''}{indian}.{parts[1]}"
    except Exception:
        return str(val)


def _build_chain_table(
    option_chain_df: pd.DataFrame, spot: float, atm: float
) -> str:
    if option_chain_df.empty:
        return "No chain data available"

    all_strikes = sorted(option_chain_df["strike"].unique())
    try:
        atm_idx = all_strikes.index(atm)
    except ValueError:
        atm_idx = len(all_strikes) // 2

    lo = max(0, atm_idx - 10)
    hi = min(len(all_strikes), atm_idx + 11)
    chain_strikes = all_strikes[lo:hi]

    header = (
        f"{'Strike':>10} | {'CE OI':>10} | {'CE ΔOI':>9} | {'CE IV%':>6} | {'CE LTP':>8} "
        f"| {'PE OI':>10} | {'PE ΔOI':>9} | {'PE IV%':>6} | {'PE LTP':>8}"
    )
    sep  = "-" * len(header)
    rows = [header, sep]

    sub = option_chain_df[option_chain_df["strike"].isin(chain_strikes)].sort_values("strike")
    for _, row in sub.iterrows():
        k      = row["strike"]
        marker = " ← ATM" if k == atm else ""
        rows.append(
            f"{k:>10.0f}{marker:<6} | {row.get('CE_oi', 0):>10,.0f} | {row.get('CE_oi_chg', 0):>+9,.0f} "
            f"| {row.get('CE_iv', 0):>5.1f}% | {row.get('CE_ltp', 0):>8.2f} "
            f"| {row.get('PE_oi', 0):>10,.0f} | {row.get('PE_oi_chg', 0):>+9,.0f} "
            f"| {row.get('PE_iv', 0):>5.1f}% | {row.get('PE_ltp', 0):>8.2f}"
        )
    return "\n".join(rows)


def _format_mtf_context(mtf) -> str:
    """Format MTFAnalysis into readable context for Claude."""
    if mtf is None:
        return "MTF analysis: unavailable"

    lines = [f"MULTI-TIMEFRAME ANALYSIS (4-TF top-down):"]

    def tf_line(name: str, tf) -> str:
        if tf is None:
            return f"  {name}: data unavailable"
        patterns = [p.name for p in (tf.patterns or [])[:2]]
        pat_str  = f" | Patterns: {', '.join(patterns)}" if patterns else ""
        cpr_str  = ""
        if tf.cpr:
            cpr_str = f" | CPR: TC={tf.cpr.tc:.0f} P={tf.cpr.pivot:.0f} BC={tf.cpr.bc:.0f}"
        return (
            f"  {name}: {tf.trend} | Close={tf.last_close:.2f} | "
            f"EMA20={tf.ema20:.2f} EMA50={tf.ema50:.2f} | "
            f"ADX={tf.adx:.1f} RSI={tf.rsi:.1f} | "
            f"Vol={tf.volume_signal} OBV={tf.obv_trend} | "
            f"Structure={tf.structure}{cpr_str}{pat_str}"
        )

    lines.append(tf_line("Monthly", mtf.monthly))
    lines.append(tf_line("Weekly",  mtf.weekly))
    lines.append(tf_line("Daily",   mtf.daily))
    lines.append(tf_line("Hourly",  mtf.hourly))
    lines.append(f"  Overall: {mtf.overall_trend} | Alignment: {mtf.alignment_count}/4 TF")

    # Key levels from daily
    if mtf.daily and mtf.daily.key_levels:
        kl_strs = [f"{kl.level_type}={kl.price:.0f}" for kl in mtf.daily.key_levels[:6]]
        lines.append(f"  Key Levels: {', '.join(kl_strs)}")

    return "\n".join(lines)


def _build_context(
    symbol:          str,
    spot_price:      float,
    option_chain_df: pd.DataFrame,
    technical_data:  dict,
    market_context:  dict,
) -> str:
    from services.greeks_calculator import calculate_max_pain, find_atm_strike, calculate_gex
    from services.fno_data_service import get_vix, days_to_expiry, get_lot_size, parse_expiry_date

    lot_size = get_lot_size(symbol)
    vix_data = get_vix()
    vix_val  = float(vix_data.get("vix") or 15.0)

    # VIX interpretation
    if vix_val < 13:
        vix_label = f"LOW ({vix_val:.1f}) — options cheap, good for buying"
    elif vix_val > 18:
        vix_label = f"HIGH ({vix_val:.1f}) — IV elevated, be very selective"
    else:
        vix_label = f"MODERATE ({vix_val:.1f}) — acceptable, trade the technical setup"

    day_chg_pct = technical_data.get("day_change_pct", 0)
    high_52w    = technical_data.get("high_52w", round(spot_price * 1.25, 2))
    low_52w     = technical_data.get("low_52w",  round(spot_price * 0.75, 2))

    strikes = sorted(option_chain_df["strike"].unique()) if not option_chain_df.empty else []
    atm      = find_atm_strike(strikes, spot_price) if strikes else spot_price
    max_pain = calculate_max_pain(option_chain_df) if not option_chain_df.empty else 0

    if "expiry" in option_chain_df.columns:
        sorted_expiries = sorted(
            option_chain_df["expiry"].unique(),
            key=lambda s: parse_expiry_date(s) or date.max,
        )
        dte_for_gex = days_to_expiry(sorted_expiries[0]) if sorted_expiries else 30
    else:
        sorted_expiries = []
        dte_for_gex     = 30

    gamma_flip = atm
    try:
        if not option_chain_df.empty and len(strikes) > 1:
            gex_df = calculate_gex(option_chain_df, spot_price, dte_for_gex, lot_size)
            if not gex_df.empty and "gex" in gex_df.columns:
                gex_sorted = gex_df.sort_values("strike")
                gex_vals   = gex_sorted["gex"].values
                stk_vals   = gex_sorted["strike"].values
                for i in range(len(gex_vals) - 1):
                    if gex_vals[i] * gex_vals[i + 1] < 0:
                        gamma_flip = float(stk_vals[i])
                        break
    except Exception:
        pass

    total_ce_oi  = float(option_chain_df["CE_oi"].sum()) if "CE_oi" in option_chain_df.columns else 0
    total_pe_oi  = float(option_chain_df["PE_oi"].sum()) if "PE_oi" in option_chain_df.columns else 0
    pcr          = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else 0
    iv_pct_proxy = min(100, max(0, (vix_val - 10) / 30 * 100))

    # PCR interpretation
    if pcr < 0.7:
        pcr_label = f"{pcr:.3f} — extreme bullishness, CE buying crowded, prefer PE setups"
    elif pcr > 1.3:
        pcr_label = f"{pcr:.3f} — extreme bearishness, PE buying crowded, prefer CE setups"
    elif pcr > 1.0:
        pcr_label = f"{pcr:.3f} — slightly bearish, lean PE"
    elif pcr < 0.9:
        pcr_label = f"{pcr:.3f} — slightly bullish, lean CE"
    else:
        pcr_label = f"{pcr:.3f} — neutral, trade the technical setup"

    chain_table = _build_chain_table(option_chain_df, spot_price, atm)

    rsi    = technical_data.get("rsi", 50)
    ema20  = technical_data.get("ema20",  spot_price)
    ema50  = technical_data.get("ema50",  spot_price)
    ema200 = technical_data.get("ema200", spot_price)
    adx    = technical_data.get("adx", 20)

    if spot_price > ema200:
        ema_pos = "above all EMAs — UPTREND"
    elif spot_price > ema50:
        ema_pos = "above EMA20/50 but below EMA200"
    elif spot_price > ema20:
        ema_pos = "above EMA20 but below EMA50/200"
    else:
        ema_pos = "below all EMAs — DOWNTREND"

    patterns     = technical_data.get("patterns", [])
    patterns_str = ", ".join(patterns) if patterns else "None detected"

    if sorted_expiries:
        expiry_dates = sorted_expiries
    else:
        expiry_dates = []

    near_expiry = expiry_dates[0] if expiry_dates else "N/A"
    near_dte    = days_to_expiry(near_expiry) if near_expiry != "N/A" else 0
    next_expiry = expiry_dates[1] if len(expiry_dates) > 1 else near_expiry
    next_dte    = days_to_expiry(next_expiry) if next_expiry != "N/A" else 0

    candles = technical_data.get("recent_candles", [])
    if candles:
        candle_lines = []
        for c in candles[-5:]:
            candle_lines.append(
                f"  {str(c.get('date',''))[:10]} | O:{c.get('open',0):>9.2f}  H:{c.get('high',0):>9.2f}"
                f"  L:{c.get('low',0):>9.2f}  C:{c.get('close',0):>9.2f}  V:{c.get('volume',0):>12,.0f}"
            )
        candle_section = "\n".join(candle_lines)
    else:
        candle_section = "  (Candle data not available)"

    # MTF analysis
    mtf_context = "MTF analysis: not computed"
    try:
        from services.mtf_analyzer import analyze_symbol_mtf
        mtf = analyze_symbol_mtf(symbol)
        mtf_context = _format_mtf_context(mtf)
    except Exception as exc:
        logger.debug("MTF analysis failed for %s: %s", symbol, exc)

    nifty_trend = market_context.get("nifty_trend", "N/A")
    adv_dec     = market_context.get("advance_decline", "N/A")
    fii_action  = market_context.get("fii_net_futures", "N/A")
    ts          = datetime.now().isoformat()

    context = f"""Analyze this F&O data for {symbol} using the Elite Options Buying Framework.

=== SPOT DATA ===
Symbol: {symbol} | Spot: ₹{spot_price:,.2f} | Day Change: {day_chg_pct:+.2f}%
52W High: ₹{high_52w:,.2f} | 52W Low: ₹{low_52w:,.2f}
ATM Strike: {atm:,.0f} | Lot Size: {lot_size}

=== MARKET CONTEXT (analyze this first) ===
India VIX: {vix_label}
NIFTY PCR: {pcr_label}
IV Percentile (proxy): {iv_pct_proxy:.1f}%
NIFTY Trend: {nifty_trend}
FII Net Futures: {fii_action}
Advance/Decline: {adv_dec}
Max Pain: ₹{max_pain:,.0f}
Gamma Flip Level: ₹{gamma_flip:,.0f}

=== {mtf_context} ===

=== OPTION CHAIN (10 strikes each side of ATM) ===
{chain_table}

OI Summary: CE={total_ce_oi:,.0f} | PE={total_pe_oi:,.0f} | PCR={pcr:.3f}

=== TECHNICAL INDICATORS (Daily) ===
RSI(14): {rsi:.1f}
ADX: {adx:.1f} ({'strong trend' if adx > 25 else 'weak/ranging'})
Price vs EMAs: {ema_pos} (EMA20={ema20:.2f} EMA50={ema50:.2f} EMA200={ema200:.2f})
Patterns Detected: {patterns_str}

=== RECENT DAILY CANDLES (last 5) ===
{candle_section}

=== EXPIRY INFO ===
Near Expiry: {near_expiry} (DTE: {near_dte} days)
Next Expiry: {next_expiry} (DTE: {next_dte} days)

=== INSTRUCTIONS ===
Apply the Elite scoring rubric (A+B+C+D+E = 100 pts).
If score < 70, set no_trade=true.
If qualifying (score ≥ 70), specify the EXACT option to buy (ATM or 1-ITM only, DTE ≥ 7, IV%ile < 60).
Entry at market price. T1 = 2× premium. T2 = 3× premium. SL = 35% of premium.
Respond ONLY with valid JSON (no markdown). Timestamp: {ts}"""

    # Append JSON schema reminder for the max_pain and gamma_flip in key_levels
    context += f"""

key_levels defaults: max_pain={int(max_pain)}, gamma_flip={int(gamma_flip)}"""
    return context


# ── Claude API calls ───────────────────────────────────────────────────────────

def _call_claude(prompt: str, api_key: str, model: str = _DEFAULT_MODEL) -> tuple[dict, int]:
    import anthropic

    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=3000,
        system=_ELITE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    tokens = message.usage.input_tokens + message.usage.output_tokens
    raw    = message.content[0].text.strip()

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$",       "", raw)
    raw = raw.strip()

    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        raw = m.group(0)

    return json.loads(raw), tokens


def test_claude_connection(api_key: str) -> tuple[bool, str]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg    = client.messages.create(
            model=_DEFAULT_MODEL, max_tokens=10,
            messages=[{"role": "user", "content": "Reply with the single word OK"}],
        )
        reply  = msg.content[0].text.strip()
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
        return True, f"Connected ✅  Model: {_DEFAULT_MODEL}  Reply: '{reply}'  Tokens: {tokens}"
    except Exception as exc:
        return False, f"Connection failed: {str(exc)[:250]}"


# ── Main entry point ───────────────────────────────────────────────────────────

def get_fno_suggestion(
    symbol:          str,
    spot_price:      float,
    option_chain_df: pd.DataFrame,
    technical_data:  dict | None = None,
    market_context:  dict | None = None,
) -> FNOSuggestion:
    """Return an Elite F&O Agent trade suggestion for the given symbol."""
    api_key = _get_api_key()
    if not api_key:
        return FNOSuggestion(
            symbol=symbol,
            error="No Anthropic API key configured. Add it in Settings → AI Agent Status.",
        )

    if technical_data  is None: technical_data  = {}
    if market_context  is None: market_context  = {}

    context = _build_context(symbol, spot_price, option_chain_df, technical_data, market_context)

    parsed: dict | None = None
    tokens = 0
    retry_prompt = context

    for attempt in range(2):
        try:
            parsed, tokens = _call_claude(retry_prompt, api_key)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                retry_prompt = (
                    context + "\n\nCRITICAL: Your previous response was not valid JSON. "
                    "Return ONLY the raw JSON object — no markdown, no extra text."
                )
            else:
                return FNOSuggestion(symbol=symbol, error="AI returned malformed JSON — please try again.")
        except Exception as exc:
            logger.error("Claude API error for %s: %s", symbol, exc)
            return FNOSuggestion(symbol=symbol, error=f"AI call failed: {str(exc)[:200]}")

    if not parsed:
        return FNOSuggestion(symbol=symbol, error="AI returned no data.")

    def _parse_trade(d: object) -> Optional[TradeRecommendation]:
        if not isinstance(d, dict):
            return None
        try:
            t1 = float(d.get("target_1", 0) or 0)
            t2 = float(d.get("target_2", 0) or 0)
            tp = float(d.get("target_price", 0) or 0) or t1
            return TradeRecommendation(
                instrument       = str(d.get("instrument", "")),
                strike           = float(d.get("strike", 0) or 0),
                expiry           = str(d.get("expiry", "")),
                action           = str(d.get("action", "")),
                entry_price      = float(d.get("entry_price", 0) or 0),
                target_price     = tp,
                target_1         = t1 or tp,
                target_2         = t2,
                stop_loss        = float(d.get("stop_loss", 0) or 0),
                lots             = int(d.get("lots", 1) or 1),
                max_loss_rs      = float(d.get("max_loss_rs", 0) or 0),
                reward_risk_ratio= float(d.get("reward_risk_ratio", 0) or 0),
                confidence       = str(d.get("confidence", "MEDIUM")),
                strategy_name    = str(d.get("strategy_name", "")),
                time_stop        = str(d.get("time_stop", "Exit in 2 sessions if no movement")),
            )
        except Exception:
            return None

    # Cost estimate: Sonnet 4.6 ≈ blended ~$9/MTok
    cost_inr = round(tokens * 0.000009 * 84, 4)

    return FNOSuggestion(
        symbol                   = symbol,
        primary_trade            = _parse_trade(parsed.get("primary_trade")),
        secondary_trade          = _parse_trade(parsed.get("secondary_trade")),
        reasoning                = list(parsed.get("reasoning") or []),
        market_bias              = str(parsed.get("market_bias", "NEUTRAL")),
        key_levels               = dict(parsed.get("key_levels") or {}),
        risk_factors             = list(parsed.get("risk_factors") or []),
        valid_for_minutes        = int(parsed.get("valid_for_minutes") or 30),
        analysis_timestamp       = str(parsed.get("analysis_timestamp") or datetime.now().isoformat()),
        raw_json                 = parsed,
        context_used             = context,
        tokens_used              = tokens,
        cost_inr                 = cost_inr,
        # Elite fields
        setup_score              = int(parsed.get("setup_score", 0) or 0),
        signal                   = str(parsed.get("signal", "NO_TRADE")),
        no_trade                 = bool(parsed.get("no_trade", False)),
        no_trade_reason          = parsed.get("no_trade_reason"),
        confidence_level         = str(parsed.get("confidence_level", "MEDIUM")),
        market_context_assessment= dict(parsed.get("market_context_assessment") or {}),
        mtf_summary              = dict(parsed.get("mtf_summary") or {}),
        price_action_signal      = dict(parsed.get("price_action_signal") or {}),
        volume_analysis          = dict(parsed.get("volume_analysis") or {}),
        trade_qualification_reasons = list(parsed.get("trade_qualification_reasons") or []),
        invalidation_conditions  = list(parsed.get("invalidation_conditions") or []),
    )
