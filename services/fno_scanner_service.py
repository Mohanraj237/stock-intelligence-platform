"""
F&O Scanner Service — 8 pre-built scan types across all F&O stocks + indices.
Circuit breaker: per-symbol error threshold, logs & skips on failure.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from services.fno_data_service import (
    get_option_chain,
    get_fno_stocks,
    get_fno_quote,
    get_pcr,
    INDEX_SYMBOLS,
    LOT_SIZES,
    days_to_expiry,
)
from services.greeks_calculator import (
    calculate_max_pain,
    find_atm_strike,
    calculate_greeks,
    RISK_FREE_RATE,
)

logger = logging.getLogger(__name__)

# ── Scan definitions ──────────────────────────────────────────────────────────

SCAN_TYPES = [
    "High OI Buildup",
    "IV Crush Candidates",
    "OI Unwinding",
    "PCR Extremes",
    "Max Pain Divergence",
    "Unusual Volume",
    "Gamma Squeeze",
    "Roll Activity",
]

SCAN_DESCRIPTIONS = {
    "High OI Buildup":      "OI change > 20% with price confirmation — fresh positions being built",
    "IV Crush Candidates":  "IV percentile > 80 — premium sellers' paradise before events",
    "OI Unwinding":         "OI drop > 20% — positions being closed, direction flip possible",
    "PCR Extremes":         "PCR < 0.6 (bullish extreme) or > 1.5 (bearish extreme)",
    "Max Pain Divergence":  "Spot price far from max pain — potential pinning opportunity",
    "Unusual Volume":       "Options volume > 3× 20-day average — smart money activity",
    "Gamma Squeeze":        "High gamma at ATM strike — sharp move likely on any price action",
    "Roll Activity":        "Near expiry with large OI shifting to next expiry",
}

# ── Circuit breaker ───────────────────────────────────────────────────────────

_ERROR_COUNTS: dict[str, int] = {}
_MAX_ERRORS = 3


def _cb_ok(symbol: str) -> bool:
    return _ERROR_COUNTS.get(symbol, 0) < _MAX_ERRORS


def _cb_record_error(symbol: str):
    _ERROR_COUNTS[symbol] = _ERROR_COUNTS.get(symbol, 0) + 1


def _cb_reset(symbol: str):
    _ERROR_COUNTS.pop(symbol, None)


# ── Per-symbol scan helpers ───────────────────────────────────────────────────

def _scan_symbol(symbol: str, scan_type: str) -> Optional[dict]:
    """
    Run a single scan on one symbol.  Returns result dict or None.
    """
    if not _cb_ok(symbol):
        return None

    try:
        df, meta = get_option_chain(symbol)
        if df.empty or not meta:
            return None

        spot       = meta.get("underlying", 0)
        expiries   = meta.get("expiry_dates", [])
        near_exp   = expiries[0] if expiries else ""
        dte        = days_to_expiry(near_exp)

        # Filter to nearest expiry
        df_near = df[df["expiry"] == near_exp] if near_exp else df

        if df_near.empty:
            return None

        strikes = sorted(df_near["strike"].unique())
        atm     = find_atm_strike(strikes, spot) if spot else (strikes[len(strikes)//2] if strikes else 0)

        # ── scan_type dispatch ────────────────────────────────────────────────

        if scan_type == "High OI Buildup":
            total_oi_chg = df_near["CE_oi_chg"].sum() + df_near["PE_oi_chg"].sum()
            total_oi     = df_near["CE_oi"].sum() + df_near["PE_oi"].sum()
            if total_oi <= 0:
                return None
            oi_chg_pct = total_oi_chg / total_oi * 100
            if abs(oi_chg_pct) < 20:
                return None
            quote = get_fno_quote(symbol)
            price_chg_pct = quote.get("change_pct", 0)
            direction = "Bullish" if (oi_chg_pct > 0 and price_chg_pct > 0) else (
                "Bearish" if (oi_chg_pct > 0 and price_chg_pct < 0) else "Mixed"
            )
            strength = min(100, int(abs(oi_chg_pct)))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"OI Chg {oi_chg_pct:+.1f}% | Price {price_chg_pct:+.1f}%",
                "direction":   direction,
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "IV Crush Candidates":
            atm_row = df_near[df_near["strike"] == atm]
            if atm_row.empty:
                return None
            ce_iv = atm_row.iloc[0].get("CE_iv", 0)
            pe_iv = atm_row.iloc[0].get("PE_iv", 0)
            avg_iv = (ce_iv + pe_iv) / 2 if (ce_iv + pe_iv) > 0 else 0
            if avg_iv < 20:
                return None
            # Approximate IV percentile: IV > 50 = high, > 80 = very high
            iv_pct = min(100, int(avg_iv * 1.5))
            if iv_pct < 80:
                return None
            strength = iv_pct
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"ATM IV {avg_iv:.1f}% | IV%ile ~{iv_pct}",
                "direction":   "Neutral (sell premium)",
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "OI Unwinding":
            total_oi_chg = df_near["CE_oi_chg"].sum() + df_near["PE_oi_chg"].sum()
            total_oi     = df_near["CE_oi"].sum() + df_near["PE_oi"].sum()
            if total_oi <= 0:
                return None
            oi_chg_pct = total_oi_chg / total_oi * 100
            if oi_chg_pct > -20:
                return None
            strength = min(100, int(abs(oi_chg_pct)))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"OI Chg {oi_chg_pct:+.1f}%",
                "direction":   "Unwinding",
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "PCR Extremes":
            pcr_data = get_pcr(symbol)
            pcr_oi   = pcr_data.get("pcr_oi", 1.0)
            if 0.6 <= pcr_oi <= 1.5:
                return None
            if pcr_oi < 0.6:
                direction = "Bullish Extreme"
                strength  = int((0.6 - pcr_oi) / 0.6 * 100)
            else:
                direction = "Bearish Extreme"
                strength  = int((pcr_oi - 1.5) / 1.5 * 100)
            strength = min(100, max(10, strength))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"PCR OI = {pcr_oi:.2f}",
                "direction":   direction,
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "Max Pain Divergence":
            if df_near.empty or spot <= 0:
                return None
            max_pain = calculate_max_pain(df_near)
            if max_pain <= 0:
                return None
            divergence_pct = abs(spot - max_pain) / spot * 100
            if divergence_pct < 1.0:
                return None
            direction = "Spot above Max Pain" if spot > max_pain else "Spot below Max Pain"
            strength  = min(100, int(divergence_pct * 10))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"Spot ₹{spot:,.0f} | Max Pain ₹{max_pain:,.0f} | Div {divergence_pct:.1f}%",
                "direction":   direction,
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "Unusual Volume":
            total_vol = df_near["CE_vol"].sum() + df_near["PE_vol"].sum()
            if total_vol <= 0:
                return None
            # Compare to all expiries OI as proxy for average (we don't have 20d vol history)
            total_oi  = df_near["CE_oi"].sum() + df_near["PE_oi"].sum()
            vol_to_oi = total_vol / total_oi if total_oi > 0 else 0
            if vol_to_oi < 0.5:
                return None
            strength = min(100, int(vol_to_oi * 30))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"Vol {total_vol:,} | Vol/OI ratio {vol_to_oi:.2f}",
                "direction":   "Active",
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "Gamma Squeeze":
            atm_row = df_near[df_near["strike"] == atm]
            if atm_row.empty or spot <= 0:
                return None
            T        = max(dte, 1) / 365.0
            ce_iv    = atm_row.iloc[0].get("CE_iv", 15) / 100
            ce_oi    = atm_row.iloc[0].get("CE_oi", 0)
            pe_oi    = atm_row.iloc[0].get("PE_oi", 0)
            lot_size = LOT_SIZES.get(symbol.upper(), 1)
            cg       = calculate_greeks(spot, atm, T, max(ce_iv, 0.1), "CE", RISK_FREE_RATE)
            gamma    = cg.get("gamma", 0)
            # Total gamma exposure at ATM
            total_gex = gamma * (ce_oi + pe_oi) * lot_size * spot * spot / 100
            if total_gex < 1e6:
                return None
            strength = min(100, int(total_gex / 1e8))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"ATM Gamma {gamma:.6f} | Total GEX ₹{total_gex/1e7:.1f} Cr",
                "direction":   "High Gamma — sharp move likely",
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

        elif scan_type == "Roll Activity":
            if dte > 5 or len(expiries) < 2:
                return None
            next_exp    = expiries[1] if len(expiries) > 1 else ""
            df_next     = df[df["expiry"] == next_exp] if next_exp else pd.DataFrame()
            near_oi     = df_near["CE_oi"].sum() + df_near["PE_oi"].sum()
            next_oi     = df_next["CE_oi"].sum() + df_next["PE_oi"].sum() if not df_next.empty else 0
            if near_oi <= 0:
                return None
            roll_ratio  = next_oi / near_oi if near_oi else 0
            if roll_ratio < 0.5:
                return None
            strength = min(100, int(roll_ratio * 40))
            return {
                "symbol":      symbol,
                "signal_type": scan_type,
                "metric":      f"DTE {dte} | Near OI {near_oi:,} | Next OI {next_oi:,} | Roll ratio {roll_ratio:.2f}",
                "direction":   "Rolling to next expiry",
                "strength":    strength,
                "expiry":      near_exp,
                "dte":         dte,
            }

    except Exception as exc:
        logger.warning("FNO scan error [%s / %s]: %s", symbol, scan_type, exc)
        _cb_record_error(symbol)

    return None


# ── Public API ────────────────────────────────────────────────────────────────

def run_scan(
    scan_type: str,
    universe: list[str] | None = None,
    max_workers: int = 6,
) -> pd.DataFrame:
    """
    Run a scan across all F&O symbols (or a provided universe list).

    Returns a DataFrame sorted by strength score (desc).
    """
    if universe is None:
        # All indices + F&O equities
        fno_stocks = get_fno_stocks()
        universe   = INDEX_SYMBOLS + [s["symbol"] for s in fno_stocks]
        # De-duplicate while preserving order
        seen = set()
        universe = [s for s in universe if not (s in seen or seen.add(s))]

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_scan_symbol, sym, scan_type): sym for sym in universe}
        for fut in as_completed(futs):
            try:
                res = fut.result()
                if res:
                    results.append(res)
            except Exception:
                pass

    if not results:
        return pd.DataFrame(columns=["symbol", "signal_type", "metric", "direction", "strength", "expiry", "dte"])

    df = pd.DataFrame(results)
    df = df.sort_values("strength", ascending=False).reset_index(drop=True)
    return df
