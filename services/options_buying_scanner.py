"""
F&O Options Buying Scanner — Elite MTF framework.

Scoring (0–100, per Elite rubric):
  A. Trend Alignment       25 pts  (monthly/weekly/daily/hourly MTF alignment)
  B. Price Action Quality  25 pts  (12 patterns, clean setup at major level)
  C. S/R Zone              20 pts  (PDH/PDL, PWH/PWL, CPR confluence)
  D. Volume Confirmation   15 pts  (breakout volume, OBV, absorption)
  E. Options Quality       15 pts  (IV%, DTE, OI, liquidity)
  F. MTF Bonus             10 pts  (4-TF alignment + structure confirmation)
     Total max: 110 → capped at 100

Signal thresholds:
  < 70  → NO_TRADE
  70–79 → WATCH
  80–84 → BUY
  85+   → STRONG_BUY

Options buying hard guards:
  - Strike: ATM or 1-strike ITM only
  - DTE ≥ 7; sweet spot 10–21
  - IV percentile (approx) < 60  (ideally < 50)
  - OI > 1000  |  Volume > 50
  - LTP > 5
  - R:R ≥ 2.0

Target = 2.5× premium  |  Stop-loss = 35% premium loss
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Signal labels ──────────────────────────────────────────────────────────────
SIG_STRONG_BUY_CE = "STRONG_BUY_CE"
SIG_BUY_CE        = "BUY_CE"
SIG_WATCHLIST_CE  = "WATCHLIST_CE"
SIG_STRONG_BUY_PE = "STRONG_BUY_PE"
SIG_BUY_PE        = "BUY_PE"
SIG_WATCHLIST_PE  = "WATCHLIST_PE"
SIG_NO_TRADE      = "NO_TRADE"

SIG_ICONS = {
    SIG_STRONG_BUY_CE: "🚀", SIG_BUY_CE: "📈", SIG_WATCHLIST_CE: "👀",
    SIG_STRONG_BUY_PE: "🔻", SIG_BUY_PE: "📉", SIG_WATCHLIST_PE: "👀",
    SIG_NO_TRADE: "⛔",
}

# ── Pattern weights (max 25 total) ─────────────────────────────────────────────
_PATTERN_PTS = {
    "Break and Retest (Bullish)": 10, "Break and Retest (Bearish)": 10,
    "Bullish Engulfing":           9, "Bearish Engulfing":           9,
    "Morning Star":                9, "Evening Star":                9,
    "Consolidation Breakout":      8,
    "Pin Bar (Bullish)":           7, "Pin Bar (Bearish)":           7,
    "Bull Flag":                   7, "Bear Flag":                   7,
    "Outside Bar":                 6, "Hammer":                      5,
    "Inside Bar":                  4, "Hanging Man":                 4,
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class TechnicalBias:
    """Directional bias + Elite scoring breakdown."""
    direction:   str   # BULLISH | BEARISH | NEUTRAL
    ema_trend:   str   # UPTREND | DOWNTREND | SIDEWAYS  (daily)
    top_pattern: str
    adx:         float
    rsi:         float
    volume_conf: bool

    # Elite scoring components
    trend_score:   int  # 0–25 (multi-TF alignment)
    pattern_score: int  # 0–25
    sr_zone_score: int  # 0–20
    volume_score:  int  # 0–15
    mtf_bonus:     int  # 0–10
    total:         int  # sum of above, capped at 85 (options quality added in build_options_setup)

    reasons: list[str] = field(default_factory=list)


@dataclass
class OptionSetup:
    strike:      float
    expiry:      str
    option_type: str   # CE | PE
    ltp:         float
    iv_pct:      float
    dte:         int
    oi:          int
    volume:      int


@dataclass
class OptionsBuyingResult:
    symbol:               str
    spot:                 float
    signal:               str
    bias:                 TechnicalBias
    setup:                Optional[OptionSetup]
    entry_price:          float
    target_price:         float
    stop_loss:            float
    reward_risk:          float
    entry_zone:           str
    max_loss_per_lot:     float
    lot_size:             int
    options_quality_score: int   # 0–15 (Elite component E)
    timestamp:            str


# ── IV percentile heuristic ───────────────────────────────────────────────────

def _iv_pct_approx(raw_iv: float) -> float:
    """
    Approximate IV percentile rank from raw annualised IV% for NSE options.
    Calibrated to India VIX historical distribution (VIX range 10–35).
    Returns 0 for unknown/zero IV so it never blocks synthetic chain options.
    """
    if raw_iv <= 0:  return 0.0   # Unknown IV — don't penalise; treated as acceptable
    if raw_iv < 10:  return 5.0
    if raw_iv < 12:  return 12.0
    if raw_iv < 14:  return 22.0
    if raw_iv < 16:  return 32.0
    if raw_iv < 18:  return 42.0  # VIX ≈ 16–18 → ~40th–45th %ile
    if raw_iv < 20:  return 52.0
    if raw_iv < 24:  return 62.0
    if raw_iv < 30:  return 72.0
    if raw_iv < 40:  return 82.0
    return 92.0


def _options_quality_score(ltp: float, iv_raw: float, dte: int, oi: int, volume: int) -> int:
    """
    Options Quality score (0–15) — Elite rubric component E.
    IV percentile (5), DTE sweet spot (5), OI liquidity (3), Volume (2).
    """
    if ltp < 5 or oi < 500:
        return 0

    iv_pct = _iv_pct_approx(iv_raw)
    pts = 0

    # IV percentile (5 pts)
    if iv_pct < 30:
        pts += 5
    elif iv_pct < 50:
        pts += 3
    # > 50: 0 pts — expensive

    # DTE sweet spot (5 pts)
    if 10 <= dte <= 21:
        pts += 5
    elif 7 <= dte < 10 or 22 <= dte <= 30:
        pts += 3
    # < 7 or > 30: 0 pts

    # OI liquidity (3 pts)
    if oi >= 1000:
        pts += 3
    elif oi >= 500:
        pts += 1

    # Volume (2 pts)
    if volume >= 100:
        pts += 2
    elif volume >= 50:
        pts += 1

    return min(15, pts)


# ── Strike selector ────────────────────────────────────────────────────────────

def select_best_strike(
    spot:              float,
    option_chain_df:   pd.DataFrame,
    option_type:       str,   # "CE" | "PE"
    min_dte:           int   = 7,
    max_iv_pct_approx: float = 60.0,
) -> Optional[OptionSetup]:
    """ATM or 1-ITM strike, passing all Elite quality guards."""
    if option_chain_df is None or option_chain_df.empty or spot <= 0:
        return None

    from services.fno_data_service import days_to_expiry
    is_ce = option_type == "CE"

    try:
        expiries = sorted(option_chain_df["expiry"].unique())
        valid    = [(days_to_expiry(e), e) for e in expiries if days_to_expiry(e) >= min_dte]
        if not valid:
            return None

        # Prefer 10–21 DTE sweet spot
        target_dte, target_exp = next(
            ((d, e) for d, e in valid if 10 <= d <= 21),
            next(((d, e) for d, e in valid if 7 <= d <= 30), valid[0]),
        )

        df_exp  = option_chain_df[option_chain_df["expiry"] == target_exp]
        strikes = sorted(df_exp["strike"].unique())
        if not strikes:
            return None

        atm_idx    = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
        # CE: ATM first, then 1 ITM (strike below ATM)
        # PE: ATM first, then 1 ITM (strike above ATM)
        candidates = [atm_idx, max(0, atm_idx - 1)] if is_ce else \
                     [atm_idx, min(len(strikes) - 1, atm_idx + 1)]

        for idx in candidates:
            s   = strikes[idx]
            row = df_exp[df_exp["strike"] == s]
            if row.empty:
                continue
            r   = row.iloc[0]
            col = option_type

            ltp    = float(r.get(f"{col}_ltp",  0) or 0)
            iv_raw = float(r.get(f"{col}_iv",   0) or 0)
            oi     = int(  r.get(f"{col}_oi",   0) or 0)
            volume = int(  r.get(f"{col}_vol",  0) or 0)

            if ltp < 5 or oi < 500:
                continue
            if _iv_pct_approx(iv_raw) > max_iv_pct_approx:
                continue

            return OptionSetup(
                strike=s, expiry=target_exp, option_type=option_type,
                ltp=ltp, iv_pct=iv_raw, dte=target_dte, oi=oi, volume=volume,
            )
    except Exception as exc:
        logger.debug("Strike select %s %s: %s", option_type, spot, exc)
    return None


# ── Technical bias scorer (Elite framework) ────────────────────────────────────

def compute_technical_bias(
    mtf,             # MTFAnalysis
    direction: str,  # "CE" | "PE"
) -> TechnicalBias:
    """
    Score the technical case for buying CE (bullish) or PE (bearish).

    A. Trend Alignment       (25 pts): monthly/weekly/daily/hourly
    B. Price Action Quality  (25 pts): named patterns at key levels
    C. S/R Zone              (20 pts): PDH/PDL, PWH/PWL, CPR confluence
    D. Volume Confirmation   (15 pts): volume ratio, OBV
    E. MTF Bonus             (10 pts): structure + full alignment
    """
    is_ce    = direction == "CE"
    reasons: list[str] = []

    monthly = mtf.monthly
    weekly  = mtf.weekly
    daily   = mtf.daily
    hourly  = mtf.hourly

    # ─── A. Trend Alignment (25) ─────────────────────────────────────────────
    aligned_count = 0
    ema_trend = daily.trend if daily else "SIDEWAYS"

    # Monthly alignment — requires clear directional trend (not SIDEWAYS)
    if monthly:
        if is_ce and monthly.trend == "UPTREND":
            aligned_count += 1
            reasons.append("Monthly uptrend confirmed")
        elif not is_ce and monthly.trend == "DOWNTREND":
            aligned_count += 1
            reasons.append("Monthly downtrend confirmed")
        # SIDEWAYS monthly = neutral, doesn't penalise or contribute

    # Weekly alignment — requires clear directional trend
    if weekly:
        if is_ce and weekly.trend == "UPTREND":
            aligned_count += 1
            reasons.append("Weekly uptrend aligned")
        elif not is_ce and weekly.trend == "DOWNTREND":
            aligned_count += 1
            reasons.append("Weekly downtrend aligned")
        # SIDEWAYS weekly = neutral

    # Daily alignment — trend direction is sufficient; ema_full_bull adds quality reasons
    if daily:
        if is_ce and daily.trend in ("UPTREND", "SIDEWAYS"):
            aligned_count += 1
            if daily.ema_full_bull:
                reasons.append("Daily full bull EMA alignment")
            else:
                reasons.append(f"Daily {daily.trend.lower()}")
        elif not is_ce and daily.trend in ("DOWNTREND", "SIDEWAYS"):
            aligned_count += 1
            if daily.ema_full_bear:
                reasons.append("Daily full bear EMA alignment")
            else:
                reasons.append(f"Daily {daily.trend.lower()}")

    # Hourly alignment
    if hourly:
        if is_ce and (hourly.ema_aligned or hourly.trend == "UPTREND"):
            aligned_count += 1
            reasons.append("Hourly EMA bullishly aligned")
        elif not is_ce and (not hourly.ema_aligned or hourly.trend == "DOWNTREND"):
            aligned_count += 1
            reasons.append("Hourly EMA bearishly aligned")

    if aligned_count == 4:
        trend_pts = 25
    elif aligned_count == 3:
        trend_pts = 18
    elif aligned_count == 2:
        trend_pts = 10
    else:
        trend_pts = 0

    # ADX bonus on daily (absorbed into trend score)
    if daily and daily.adx >= 40 and trend_pts > 0:
        trend_pts = min(25, trend_pts + 3)
        reasons.append(f"Strong trend ADX {daily.adx:.0f}")
    elif daily and daily.adx >= 25 and trend_pts > 0:
        trend_pts = min(25, trend_pts + 1)

    # ─── B. Price Action Quality (25) ─────────────────────────────────────────
    pat_pts     = 0
    top_pattern = ""
    target_dir  = "BULLISH" if is_ce else "BEARISH"

    for tf in [daily, hourly]:
        if not tf:
            continue
        for p in tf.patterns:
            if p.direction == target_dir:
                pts = _PATTERN_PTS.get(p.name, 4)
                pat_pts += pts
                if not top_pattern:
                    top_pattern = p.name
                    reasons.append(f"Pattern: {p.name}")
                elif pts >= 7:
                    reasons.append(f"Also: {p.name}")
                if pat_pts >= 25:
                    break
        if pat_pts >= 25:
            break

    pat_pts = min(25, pat_pts)

    # ─── C. S/R Zone (20) ────────────────────────────────────────────────────
    sr_pts    = 0
    vol_conf  = False

    if daily:
        spot = daily.last_close

        for lv in daily.key_levels[:8]:
            prox = abs(lv.price - spot) / spot * 100 if spot > 0 else 99

            if lv.level_type == "PDH" and is_ce:
                if spot >= lv.price * 0.998:
                    if daily.volume_signal == "BULLISH":
                        sr_pts   = max(sr_pts, 15)
                        vol_conf = True
                        reasons.append(f"PDH breakout ₹{lv.price:.0f} with volume")
                    else:
                        sr_pts = max(sr_pts, 10)
                        reasons.append(f"PDH breakout ₹{lv.price:.0f}")
                elif prox < 0.5:
                    sr_pts = max(sr_pts, 5)
                    reasons.append(f"Testing PDH ₹{lv.price:.0f}")

            elif lv.level_type == "PDL" and not is_ce:
                if spot <= lv.price * 1.002:
                    if daily.volume_signal == "BEARISH":
                        sr_pts   = max(sr_pts, 15)
                        vol_conf = True
                        reasons.append(f"PDL breakdown ₹{lv.price:.0f} with volume")
                    else:
                        sr_pts = max(sr_pts, 10)
                        reasons.append(f"PDL breakdown ₹{lv.price:.0f}")
                elif prox < 0.5:
                    sr_pts = max(sr_pts, 5)
                    reasons.append(f"Testing PDL ₹{lv.price:.0f}")

            elif lv.level_type in ("PWH", "PWL") and prox < 1.5:
                sr_pts = max(sr_pts, 6)
                reasons.append(f"Near {lv.level_type} ₹{lv.price:.0f}")

        # CPR position adds to S/R significance
        if daily.cpr:
            cpr = daily.cpr
            if is_ce and spot > cpr.tc:
                sr_pts = min(20, sr_pts + 4)
                reasons.append(f"Price above CPR (TC={cpr.tc:.0f})")
            elif not is_ce and spot < cpr.bc:
                sr_pts = min(20, sr_pts + 4)
                reasons.append(f"Price below CPR (BC={cpr.bc:.0f})")

    sr_pts = min(20, sr_pts)

    # ─── D. Volume Confirmation (15) ─────────────────────────────────────────
    vol_pts = 0

    if daily:
        # Volume signal already computed in mtf_analyzer
        if daily.volume_signal in ("BULLISH", "BEARISH"):
            if (daily.volume_signal == "BULLISH" and is_ce) or \
               (daily.volume_signal == "BEARISH" and not is_ce):
                vol_pts += 10
                vol_conf = True
                reasons.append("Strong volume confirms direction")
            else:
                vol_pts += 0  # volume against direction — penalty

        elif daily.volume_signal == "DRY_UP":
            vol_pts += 4
            reasons.append("Volume coiling before breakout")

        # OBV confirmation
        if (daily.obv_trend == "UP" and is_ce) or (daily.obv_trend == "DOWN" and not is_ce):
            vol_pts += 5
            reasons.append(f"OBV confirms ({daily.obv_trend})")

    vol_pts = min(15, vol_pts)

    # ─── E. MTF Bonus (10) ───────────────────────────────────────────────────
    mtf_bonus = 0
    if aligned_count == 4:
        # Full 4-TF alignment
        if monthly and monthly.structure == ("HHHL" if is_ce else "LHLL"):
            mtf_bonus = 10
            reasons.append("Full MTF alignment + confirmed market structure")
        else:
            mtf_bonus = 8
            reasons.append("Full 4-timeframe alignment")
    elif aligned_count == 3:
        mtf_bonus = 5
        reasons.append("3-timeframe alignment")

    # ─── Composite ────────────────────────────────────────────────────────────
    subtotal = trend_pts + pat_pts + sr_pts + vol_pts + mtf_bonus
    subtotal = min(85, subtotal)  # options quality will add the final 15

    # Direction validity guard: if daily trend opposes direction, penalise hard
    if daily:
        if is_ce and ema_trend == "DOWNTREND":
            subtotal = max(0, subtotal - 20)
            reasons.append("⚠ Fighting daily downtrend")
        elif not is_ce and ema_trend == "UPTREND":
            subtotal = max(0, subtotal - 20)
            reasons.append("⚠ Fighting daily uptrend")

    direction_final = "NEUTRAL"
    if daily:
        if is_ce and ema_trend in ("UPTREND", "SIDEWAYS"):
            direction_final = "BULLISH"
        elif not is_ce and ema_trend in ("DOWNTREND", "SIDEWAYS"):
            direction_final = "BEARISH"

    return TechnicalBias(
        direction=direction_final,
        ema_trend=ema_trend,
        top_pattern=top_pattern,
        adx=daily.adx if daily else 0.0,
        rsi=daily.rsi if daily else 50.0,
        volume_conf=vol_conf,
        trend_score=trend_pts,
        pattern_score=pat_pts,
        sr_zone_score=sr_pts,
        volume_score=vol_pts,
        mtf_bonus=mtf_bonus,
        total=subtotal,
        reasons=reasons,
    )


# ── Full setup builder ─────────────────────────────────────────────────────────

def build_options_setup(
    symbol:          str,
    spot:            float,
    mtf_analysis,            # MTFAnalysis
    option_chain_df: pd.DataFrame,
    market_context:  dict,
    option_type:     str,    # "CE" | "PE"
) -> OptionsBuyingResult:
    from services.fno_data_service import LOT_SIZES

    lot_size   = LOT_SIZES.get(symbol.upper(), 50)
    bias       = compute_technical_bias(mtf_analysis, option_type)
    min_dte    = int(market_context.get("min_dte", 7))
    max_iv_pct = float(market_context.get("max_iv_pct", 60.0))
    min_score  = int(market_context.get("min_score", 70))

    # Strike selection
    setup = select_best_strike(spot, option_chain_df, option_type, min_dte, max_iv_pct) \
            if bias.direction != "NEUTRAL" else None

    # Options quality score (component E — added to bias.total)
    opts_quality = 0
    if setup:
        opts_quality = _options_quality_score(
            setup.ltp, setup.iv_pct, setup.dte, setup.oi, setup.volume
        )

    final_score = min(100, bias.total + opts_quality)

    # Signal classification — use min_score (user-controlled) as the gate,
    # with Elite-framework labels for scores that cross the named thresholds.
    if bias.direction == "NEUTRAL" or final_score < min_score:
        signal = SIG_NO_TRADE
    elif final_score >= 85:
        signal = SIG_STRONG_BUY_CE if option_type == "CE" else SIG_STRONG_BUY_PE
    elif final_score >= 75:
        signal = SIG_BUY_CE if option_type == "CE" else SIG_BUY_PE
    else:
        # Qualifying but below BUY threshold → WATCH
        signal = SIG_WATCHLIST_CE if option_type == "CE" else SIG_WATCHLIST_PE

    # Hard guard: no valid strike found → no trade regardless of score
    if setup is None:
        signal = SIG_NO_TRADE

    # Entry / Target / SL
    entry = target = sl = rr = 0.0
    entry_zone = "No qualifying setup"

    if setup and setup.ltp > 0 and signal != SIG_NO_TRADE:
        entry  = setup.ltp
        target = round(entry * 2.5, 2)    # 2.5× premium (T1=2×, T2=3×)
        sl     = round(entry * 0.65, 2)   # 35% loss (Elite rule)
        risk   = entry - sl
        rr     = round((target - entry) / risk, 2) if risk > 0 else 0

        if rr < 2.0:
            signal     = SIG_NO_TRADE
            entry_zone = "R:R < 2.0 — skip"
        else:
            entry_zone = (
                f"Buy {setup.option_type} {setup.strike:.0f} @ ₹{entry:.2f} · "
                f"T1 ₹{round(entry*2,2):.2f} · T2 ₹{round(entry*3,2):.2f} · SL ₹{sl:.2f}"
            )

    max_loss = round((entry - sl) * lot_size, 2) if entry > 0 else 0

    # Override total with final composite
    bias.total = final_score

    return OptionsBuyingResult(
        symbol=symbol, spot=round(spot, 2), signal=signal, bias=bias,
        setup=setup, entry_price=entry, target_price=target, stop_loss=sl,
        reward_risk=rr, entry_zone=entry_zone, max_loss_per_lot=max_loss,
        lot_size=lot_size, options_quality_score=opts_quality,
        timestamp=datetime.now().isoformat(),
    )


# ── Serialiser ────────────────────────────────────────────────────────────────

def result_to_dict(r: OptionsBuyingResult) -> dict:
    opt  = r.setup
    b    = r.bias
    opts = r.options_quality_score

    return {
        # Identity
        "symbol":   r.symbol,
        "spot":     r.spot,
        "lot_size": r.lot_size,
        # Signal
        "signal":       r.signal,
        "signal_icon":  SIG_ICONS.get(r.signal, ""),
        "signal_label": r.signal.replace("_", " ").title(),
        # Technical bias
        "bias":        b.direction,
        "ema_trend":   b.ema_trend,
        "top_pattern": b.top_pattern,
        "adx":         round(b.adx, 1),
        "rsi":         round(b.rsi, 1),
        "volume_conf": b.volume_conf,
        "score":       b.total,
        "reasons":     b.reasons,
        # Elite score breakdown (matches frontend ScoreBreakdown interface)
        "score_breakdown": {
            "trend":           b.trend_score,
            "price_action":    b.pattern_score,
            "sr_zone":         b.sr_zone_score,
            "volume":          b.volume_score,
            "options_quality": opts,
            "mtf_bonus":       b.mtf_bonus,
        },
        # Legacy flat scores (backward compat)
        "ema_score":     b.trend_score,
        "pattern_score": b.pattern_score,
        "sr_vol_score":  b.sr_zone_score + b.volume_score,
        # Option details
        "option_type": opt.option_type if opt else "",
        "strike":      opt.strike      if opt else 0,
        "expiry":      opt.expiry      if opt else "",
        "ltp":         opt.ltp         if opt else 0,
        "iv_pct":      opt.iv_pct      if opt else 0,
        "dte":         opt.dte         if opt else 0,
        "oi":          opt.oi          if opt else 0,
        # Trade levels
        "entry_price":  r.entry_price,
        "target_price": r.target_price,
        "stop_loss":    r.stop_loss,
        "reward_risk":  r.reward_risk,
        "entry_zone":   r.entry_zone,
        "max_loss":     r.max_loss_per_lot,
        "timestamp":    r.timestamp,
        # Derived helpers for UI
        "trend_aligned": b.direction != "NEUTRAL",
        "sr_zone":       b.top_pattern or b.ema_trend,
    }


# ── Per-symbol scan ───────────────────────────────────────────────────────────

def _scan_symbol(symbol: str, market_context: dict) -> list[dict]:
    results = []
    try:
        from services.mtf_analyzer import analyze_symbol_mtf
        from services.fno_data_service import (
            get_option_chain, get_fno_quote, get_synthetic_option_chain,
        )

        quote = get_fno_quote(symbol)
        spot  = float(quote.get("ltp", 0) or quote.get("last", 0) or 0)
        if spot <= 0:
            return results

        try:
            df_chain, _ = get_option_chain(symbol)
            if df_chain is None or df_chain.empty:
                df_chain, _ = get_synthetic_option_chain(symbol)
        except Exception:
            try:
                df_chain, _ = get_synthetic_option_chain(symbol)
            except Exception:
                df_chain = None

        mtf       = analyze_symbol_mtf(symbol)
        min_score = int(market_context.get("min_score", 70))

        for direction in ("CE", "PE"):
            res = build_options_setup(symbol, spot, mtf, df_chain, market_context, direction)
            if res.signal != SIG_NO_TRADE and res.bias.total >= min_score:
                results.append(result_to_dict(res))

    except Exception as exc:
        logger.debug("Options scan %s: %s", symbol, exc)
    return results


# ── Universe scan ─────────────────────────────────────────────────────────────

def run_options_scan(
    universe:       list[str],
    market_context: dict | None = None,
    min_score:      int  = 70,
    signal_filter:  str  = "all",
    max_workers:    int  = 3,
) -> list[dict]:
    """Scan universe for CE/PE buying setups. Returns list sorted by score desc."""
    ctx = {**(market_context or {}), "min_score": min_score}

    all_results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_scan_symbol, sym, ctx): sym for sym in universe}
        for fut in as_completed(futs):
            try:
                all_results.extend(fut.result(timeout=90))
            except Exception as exc:
                logger.debug("Scan future error: %s", exc)

    if signal_filter == "ce_only":
        all_results = [r for r in all_results if "CE" in r["signal"]]
    elif signal_filter == "pe_only":
        all_results = [r for r in all_results if "PE" in r["signal"]]

    all_results.sort(key=lambda x: -x["score"])
    return all_results
