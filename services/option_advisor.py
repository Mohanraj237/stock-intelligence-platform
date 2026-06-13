"""
Option plan advisor — takes a ConfluenceResult and builds a concrete trade plan:
  • Buy vs sell decision (based on direction + IV rank)
  • Strike selection (ATM / slightly ITM, delta ~0.5)
  • Entry / stop-loss / T1 / T2 (ATR-based, with structural fallback)
  • Risk:reward gate (rejects < 1.3)
  • Exit rule (spot SL, targets, time/theta exit for buyers)
  • Option liquidity gate (checks chain data if available)

All monetary values in ₹.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.confluence_scorer import ConfluenceResult

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Symbol data
# ─────────────────────────────────────────────────────────────────────────────

LOT_SIZES: dict[str, int] = {
    "NIFTY": 75, "BANKNIFTY": 15, "FINNIFTY": 40,
    "MIDCPNIFTY": 75, "SENSEX": 10, "BANKEX": 15,
    "RELIANCE": 250, "TCS": 150, "INFY": 400,
    "HDFCBANK": 550, "ICICIBANK": 700, "AXISBANK": 1200,
    "SBIN": 1500, "WIPRO": 1500, "LT": 150,
    "BAJFINANCE": 125, "TATAMOTORS": 1425, "MARUTI": 75,
    "ADANIPORTS": 1250, "ONGC": 1925, "POWERGRID": 4700,
    "NTPC": 2250, "BPCL": 1800, "HINDUNILVR": 300,
    "NESTLEIND": 40, "TITAN": 175,
    "ETERNAL": 4500,  # formerly ZOMATO — renamed Feb 2025
    "NAUKRI":     200,
    "RBLBANK":    3175,
    "AUBANK":     1000,
    "ABCAPITAL":  6000,
    "MFSL":       4000,
    "PERSISTENT": 125,
    "360ONE":     1000,
    "POLICYBZR":  2000,
    "PIIND":      500,
    "DEEPAKNTR":  500,
    "AARTIIND":   1500,
    "ASTRAL":     700,
    "TATAPOWER":  4000,
    "NHPC":       8000,
    "RECLTD":     2250,
    "PFC":        2700,
    "RVNL":       3000,
    "IRFC":       6000,
    "APLAPOLLO":  500,
}

STRIKE_INTERVALS: dict[str, int] = {
    "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25,
    "SENSEX": 100, "BANKEX": 100,
}


def _strike_interval(symbol: str, spot: float) -> int:
    if symbol in STRIKE_INTERVALS:
        return STRIKE_INTERVALS[symbol]
    # Equity intervals based on price range
    if spot < 200:   return 5
    if spot < 500:   return 10
    if spot < 1000:  return 20
    if spot < 2000:  return 50
    if spot < 5000:  return 100
    return 200


def _atm(spot: float, symbol: str) -> int:
    iv = _strike_interval(symbol, spot)
    return int(round(spot / iv) * iv)


# ─────────────────────────────────────────────────────────────────────────────
# Plan dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OptionPlan:
    action: str          # "BUY" | "SELL"
    option_type: str     # "CE" | "PE"
    strike: int
    expiry: str          # "Weekly" or actual date string
    entry_spot: float
    entry_premium: float  # estimated (actual from chain when available)
    sl_spot: float
    sl_premium: float
    t1_spot: float
    t2_spot: float
    t1_premium: float
    t2_premium: float
    rr: float            # risk:reward at T1
    exit_rule: str
    lot_size: int = 75
    iv_note: str = ""    # warning when IV rank is elevated
    liquidity_ok: bool = True
    raw_risk_pts: float = 0.0  # spot move from entry to SL (informational)


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────

_RR_FLOOR = 1.3
_ATR_SL_MULT = 1.5   # stop = 1.5 × ATR from entry
_T1_MULT = 1.5       # T1  = 1.5 × risk
_T2_MULT = 2.5       # T2  = 2.5 × risk
_DELTA_ATM = 0.5     # approximate delta for ATM option


def build_plan(
    result: ConfluenceResult,
    option_chain: list[dict] | None = None,
    nearest_expiry: str = "",
    iv_rank: float = 30.0,    # 0-100; use 30 as neutral default
) -> OptionPlan | None:
    """
    Build an OptionPlan from a ConfluenceResult.
    Returns None if R:R is below the floor (setup rejected).
    """
    symbol    = result.symbol
    direction = result.direction
    spot      = result.spot_price
    atr       = result.atr

    if direction == "range":
        # Range setups: sell OTM side (prefer high IV-rank)
        return _range_sell_plan(result, option_chain, nearest_expiry, iv_rank)

    # ── Directional setup ────────────────────────────────────────────────────
    option_type = "CE" if direction == "bullish" else "PE"
    strike = _atm(spot, symbol)
    lot_size = LOT_SIZES.get(symbol, 500)
    expiry = nearest_expiry or "Weekly"

    # Stop-loss
    risk_pts = max(atr * _ATR_SL_MULT, spot * 0.003)  # at least 0.3% of spot
    if direction == "bullish":
        sl_spot = round(spot - risk_pts, 2)
        t1_spot = round(spot + _T1_MULT * risk_pts, 2)
        t2_spot = round(spot + _T2_MULT * risk_pts, 2)
    else:
        sl_spot = round(spot + risk_pts, 2)
        t1_spot = round(spot - _T1_MULT * risk_pts, 2)
        t2_spot = round(spot - _T2_MULT * risk_pts, 2)

    rr = round(_T1_MULT, 2)  # always 1.5 by design; spot R:R

    if rr < _RR_FLOOR:
        log.debug("Rejected %s — R:R %.2f < floor %.2f", symbol, rr, _RR_FLOOR)
        return None

    # ── Premium estimation ───────────────────────────────────────────────────
    entry_premium = _get_premium(option_chain, strike, option_type) or _estimate_premium(spot)
    sl_premium    = max(1.0, round(entry_premium - _DELTA_ATM * risk_pts, 1))
    t1_premium    = round(entry_premium + _DELTA_ATM * _T1_MULT * risk_pts, 1)
    t2_premium    = round(entry_premium + _DELTA_ATM * _T2_MULT * risk_pts, 1)

    # ── IV note ──────────────────────────────────────────────────────────────
    iv_note = ""
    if iv_rank > 70:
        iv_note = (
            f"IV rank {iv_rank:.0f} — premium is expensive. "
            "Consider a debit spread instead of an outright buy."
        )
    elif iv_rank > 50 and result.total < 75:
        iv_note = f"Moderate IV rank {iv_rank:.0f} — ensure conviction before buying."

    # ── Exit rule ────────────────────────────────────────────────────────────
    if direction == "bullish":
        exit_rule = (
            f"Exit when: spot < {sl_spot:.0f} (stop) | "
            f"spot > {t1_spot:.0f} T1 | {t2_spot:.0f} T2. "
            f"Intraday: exit by 3:10 PM or if stalled > 30 min (theta burn)."
        )
    else:
        exit_rule = (
            f"Exit when: spot > {sl_spot:.0f} (stop) | "
            f"spot < {t1_spot:.0f} T1 | {t2_spot:.0f} T2. "
            f"Intraday: exit by 3:10 PM or if stalled > 30 min (theta burn)."
        )

    # ── Liquidity gate ───────────────────────────────────────────────────────
    liquidity_ok = True
    if option_chain:
        liq = _check_liquidity(option_chain, strike, option_type)
        if not liq:
            iv_note = (iv_note + " | " if iv_note else "") + \
                "Liquidity unverified at this strike — check chain before trading."
            liquidity_ok = False

    return OptionPlan(
        action="BUY",
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        entry_spot=spot,
        entry_premium=entry_premium,
        sl_spot=sl_spot,
        sl_premium=sl_premium,
        t1_spot=t1_spot,
        t2_spot=t2_spot,
        t1_premium=t1_premium,
        t2_premium=t2_premium,
        rr=rr,
        exit_rule=exit_rule,
        lot_size=lot_size,
        iv_note=iv_note,
        liquidity_ok=liquidity_ok,
        raw_risk_pts=round(risk_pts, 2),
    )


def _range_sell_plan(
    result: ConfluenceResult,
    option_chain: list[dict] | None,
    nearest_expiry: str,
    iv_rank: float,
) -> OptionPlan | None:
    """Range-bound + high IV → sell OTM premium."""
    if iv_rank < 40:
        return None   # not worth selling when IV is low

    spot     = result.spot_price
    symbol   = result.symbol
    atr      = result.atr
    lot_size = LOT_SIZES.get(symbol, 500)

    # Sell 1 strike OTM on both sides conceptually; return the higher-premium side
    interval = _strike_interval(symbol, spot)
    atm      = _atm(spot, symbol)
    otm_ce   = atm + interval
    otm_pe   = atm - interval

    # Use CE sell if slight bullish lean, PE sell otherwise
    lean = "CE" if result.momentum_score >= 12 else "PE"
    strike   = otm_ce if lean == "CE" else otm_pe
    option_type = lean

    entry_premium = _get_premium(option_chain, strike, option_type) or _estimate_premium(spot) * 0.6
    max_loss_premium = entry_premium * 2.5  # 2.5× premium collected = stop

    # For selling: stop is when premium doubles, target is premium × 0.3
    sl_premium  = round(entry_premium * 2.5, 1)
    t1_premium  = round(entry_premium * 0.5, 1)
    t2_premium  = round(entry_premium * 0.1, 1)
    rr          = round((entry_premium - t1_premium) / (sl_premium - entry_premium), 2)

    if rr < _RR_FLOOR:
        return None

    exit_rule = (
        f"SELL {option_type} {strike} expiry {nearest_expiry or 'Weekly'}. "
        f"Exit (buy back) when: premium > {sl_premium:.0f} (stop) | "
        f"premium < {t1_premium:.0f} T1 | {t2_premium:.0f} T2. "
        f"Also exit if spot breaks out of range by > {atr:.0f}."
    )

    return OptionPlan(
        action="SELL",
        option_type=option_type,
        strike=strike,
        expiry=nearest_expiry or "Weekly",
        entry_spot=spot,
        entry_premium=entry_premium,
        sl_spot=round(spot + atr * 2 if lean == "CE" else spot - atr * 2, 1),
        sl_premium=sl_premium,
        t1_spot=spot,   # range — spot doesn't need to move
        t2_spot=spot,
        t1_premium=t1_premium,
        t2_premium=t2_premium,
        rr=rr,
        exit_rule=exit_rule,
        lot_size=lot_size,
        iv_note=f"IV rank {iv_rank:.0f} — selling premium is the edge here.",
        liquidity_ok=True,
        raw_risk_pts=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_premium(
    chain: list[dict] | None,
    strike: int,
    option_type: str,
) -> float | None:
    """Extract LTP from NSE option chain rows for the given strike."""
    if not chain:
        return None
    for row in chain:
        rs = row.get("strikePrice") or row.get("strike_price")
        if rs is None:
            continue
        try:
            if int(float(rs)) == strike:
                side = row.get(option_type, {}) or {}
                ltp = side.get("lastPrice") or side.get("ltp") or 0
                if ltp and float(ltp) > 0:
                    return float(ltp)
        except (ValueError, TypeError):
            continue
    return None


def _estimate_premium(spot: float) -> float:
    """
    Rough ATM premium ballpark: ~1% of spot price.
    Used when option chain is unavailable.
    """
    return max(1.0, round(spot * 0.01, 0))


def _check_liquidity(
    chain: list[dict],
    strike: int,
    option_type: str,
    min_oi: int = 500,
    min_vol: int = 100,
) -> bool:
    for row in chain:
        rs = row.get("strikePrice") or row.get("strike_price")
        if rs is None:
            continue
        try:
            if int(float(rs)) == strike:
                side = row.get(option_type, {}) or {}
                oi  = side.get("openInterest") or side.get("oi") or 0
                vol = side.get("totalTradedVolume") or side.get("volume") or 0
                return float(oi) >= min_oi and float(vol) >= min_vol
        except (ValueError, TypeError):
            continue
    return False  # strike not found in chain
