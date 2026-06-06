"""
Options Strategy Calculator.
Computes payoff diagrams, net Greeks, breakevens, and max P&L
for multi-leg options/futures strategies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from services.greeks_calculator import calculate_greeks, RISK_FREE_RATE

# ── Leg definition ────────────────────────────────────────────────────────────

@dataclass
class Leg:
    symbol:      str
    expiry:      str
    strike:      float
    option_type: str          # "CE", "PE", "FUT"
    action:      str          # "BUY" or "SELL"
    lots:        int
    lot_size:    int
    ltp:         float        # last traded price (premium for options, spot for futures)
    iv:          float = 0.0  # annualised IV (0-1)
    dte:         int   = 30   # days to expiry

    @property
    def sign(self) -> int:
        return 1 if self.action.upper() == "BUY" else -1

    @property
    def qty(self) -> int:
        return self.lots * self.lot_size


# ── Pre-built strategy templates ──────────────────────────────────────────────

STRATEGY_TEMPLATES: dict[str, list[dict]] = {
    "Long Call": [
        {"action": "BUY", "option_type": "CE", "strike_offset": 0},
    ],
    "Long Put": [
        {"action": "BUY", "option_type": "PE", "strike_offset": 0},
    ],
    "Bull Call Spread": [
        {"action": "BUY",  "option_type": "CE", "strike_offset": 0},
        {"action": "SELL", "option_type": "CE", "strike_offset": +1},
    ],
    "Bear Put Spread": [
        {"action": "BUY",  "option_type": "PE", "strike_offset": 0},
        {"action": "SELL", "option_type": "PE", "strike_offset": -1},
    ],
    "Long Straddle": [
        {"action": "BUY", "option_type": "CE", "strike_offset": 0},
        {"action": "BUY", "option_type": "PE", "strike_offset": 0},
    ],
    "Short Straddle": [
        {"action": "SELL", "option_type": "CE", "strike_offset": 0},
        {"action": "SELL", "option_type": "PE", "strike_offset": 0},
    ],
    "Long Strangle": [
        {"action": "BUY", "option_type": "CE", "strike_offset": +1},
        {"action": "BUY", "option_type": "PE", "strike_offset": -1},
    ],
    "Short Strangle": [
        {"action": "SELL", "option_type": "CE", "strike_offset": +1},
        {"action": "SELL", "option_type": "PE", "strike_offset": -1},
    ],
    "Iron Condor": [
        {"action": "BUY",  "option_type": "PE", "strike_offset": -2},
        {"action": "SELL", "option_type": "PE", "strike_offset": -1},
        {"action": "SELL", "option_type": "CE", "strike_offset": +1},
        {"action": "BUY",  "option_type": "CE", "strike_offset": +2},
    ],
    "Iron Butterfly": [
        {"action": "BUY",  "option_type": "PE", "strike_offset": -1},
        {"action": "SELL", "option_type": "PE", "strike_offset": 0},
        {"action": "SELL", "option_type": "CE", "strike_offset": 0},
        {"action": "BUY",  "option_type": "CE", "strike_offset": +1},
    ],
    "Covered Call": [
        {"action": "BUY",  "option_type": "FUT", "strike_offset": 0},
        {"action": "SELL", "option_type": "CE",  "strike_offset": +1},
    ],
    "Protective Put": [
        {"action": "BUY", "option_type": "FUT", "strike_offset": 0},
        {"action": "BUY", "option_type": "PE",  "strike_offset": -1},
    ],
}


# ── Payoff calculation ────────────────────────────────────────────────────────

def _leg_payoff_at_expiry(leg: Leg, spot_at_expiry: float) -> float:
    """
    P&L for a single leg at expiry (intrinsic value method).
    Positive = profit, Negative = loss (per 1 lot, i.e. per lot_size contracts).
    """
    S = spot_at_expiry
    K = leg.strike

    if leg.option_type.upper() == "CE":
        intrinsic = max(0.0, S - K)
        pnl_per_unit = (intrinsic - leg.ltp) * leg.sign
    elif leg.option_type.upper() == "PE":
        intrinsic = max(0.0, K - S)
        pnl_per_unit = (intrinsic - leg.ltp) * leg.sign
    else:  # FUT
        pnl_per_unit = (S - leg.ltp) * leg.sign

    return pnl_per_unit * leg.qty


def calculate_payoff(
    legs: list[Leg],
    spot: float,
    spot_range_pct: float = 0.10,
    n_points: int = 200,
) -> tuple[list[float], list[float]]:
    """
    Compute payoff across a price range of ±spot_range_pct from spot.

    Returns (spot_prices, total_pnl) — two parallel lists.
    """
    low  = spot * (1 - spot_range_pct)
    high = spot * (1 + spot_range_pct)
    spot_prices = list(np.linspace(low, high, n_points))

    total_pnl = []
    for S in spot_prices:
        pnl = sum(_leg_payoff_at_expiry(leg, S) for leg in legs)
        total_pnl.append(round(pnl, 2))

    return spot_prices, total_pnl


# ── Max profit / max loss ─────────────────────────────────────────────────────

def calculate_max_profit_loss(
    legs: list[Leg],
    spot: float,
    spot_range_pct: float = 0.30,
) -> dict:
    """
    Estimate max profit and max loss within a ±30% range.
    Returns {max_profit, max_loss, net_premium, is_debit}
    """
    _, pnl_arr = calculate_payoff(legs, spot, spot_range_pct=spot_range_pct, n_points=500)

    # Net premium (positive = debit paid, negative = credit received)
    net_premium = sum(
        leg.ltp * leg.qty * leg.sign
        for leg in legs
        if leg.option_type.upper() in ("CE", "PE")
    )

    max_profit = max(pnl_arr) if pnl_arr else 0.0
    max_loss   = min(pnl_arr) if pnl_arr else 0.0

    # Unlimited risk strategies — tag them
    unlimited_profit = any(
        leg.option_type.upper() == "FUT" and leg.action.upper() == "BUY" for leg in legs
    ) or any(
        leg.option_type.upper() == "CE" and leg.action.upper() == "BUY" for leg in legs
    )
    unlimited_loss = any(
        leg.option_type.upper() in ("CE", "PE") and leg.action.upper() == "SELL"
        and not any(
            l.option_type == leg.option_type and l.action.upper() == "BUY" for l in legs
        )
        for leg in legs
    )

    return {
        "max_profit":       round(max_profit, 2),
        "max_loss":         round(max_loss, 2),
        "net_premium":      round(net_premium, 2),
        "is_debit":         net_premium > 0,
        "unlimited_profit": unlimited_profit,
        "unlimited_loss":   unlimited_loss,
    }


# ── Breakeven calculation ─────────────────────────────────────────────────────

def calculate_breakevens(
    legs: list[Leg],
    spot: float,
    spot_range_pct: float = 0.20,
    n_points: int = 2000,
) -> list[float]:
    """
    Find prices where total P&L crosses zero (sign changes).
    Returns list of breakeven prices.
    """
    prices, pnl = calculate_payoff(legs, spot, spot_range_pct=spot_range_pct, n_points=n_points)
    breakevens: list[float] = []

    for i in range(1, len(pnl)):
        if (pnl[i-1] < 0 <= pnl[i]) or (pnl[i-1] > 0 >= pnl[i]):
            # Linear interpolation
            p0, p1 = prices[i-1], prices[i]
            v0, v1 = pnl[i-1], pnl[i]
            if abs(v1 - v0) > 1e-6:
                be = p0 + (0 - v0) * (p1 - p0) / (v1 - v0)
                breakevens.append(round(be, 2))

    return breakevens


# ── Net Greeks for the full position ─────────────────────────────────────────

def calculate_position_greeks(
    legs: list[Leg],
    spot: float,
    r: float = RISK_FREE_RATE,
) -> dict:
    """
    Net position Greeks (delta, gamma, theta, vega) for the whole strategy.
    """
    net = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    for leg in legs:
        if leg.option_type.upper() == "FUT":
            # Futures: delta = 1 per unit, others ≈ 0
            net["delta"] += leg.sign * leg.qty
            continue

        T  = max(leg.dte, 1) / 365.0
        iv = leg.iv if leg.iv > 0 else 0.15
        g  = calculate_greeks(spot, leg.strike, T, iv, leg.option_type, r)

        scale = leg.sign * leg.qty
        net["delta"] += g["delta"] * scale
        net["gamma"] += g["gamma"] * scale
        net["theta"] += g["theta"] * scale
        net["vega"]  += g["vega"]  * scale

    return {k: round(v, 4) for k, v in net.items()}


# ── Margin estimate (simplified SPAN-like) ────────────────────────────────────

def estimate_margin(legs: list[Leg], spot: float) -> dict:
    """
    Rough margin estimate (not exchange-accurate — use as indicative only).
    Uses a simplified 10% of notional for sold legs + premium for bought legs.
    """
    span_margin    = 0.0
    exposure_margin = 0.0
    premium_paid   = 0.0
    premium_recv   = 0.0

    for leg in legs:
        notional = spot * leg.qty

        if leg.action.upper() == "SELL":
            if leg.option_type.upper() == "FUT":
                span_margin     += notional * 0.10
                exposure_margin += notional * 0.03
            else:  # short option
                span_margin     += notional * 0.07
                exposure_margin += notional * 0.02
            premium_recv += leg.ltp * leg.qty
        else:
            premium_paid += leg.ltp * leg.qty

    # Spread credit reduces margin
    net_premium = premium_recv - premium_paid
    if net_premium > 0:
        span_margin = max(0, span_margin - net_premium)

    total_margin = span_margin + exposure_margin
    return {
        "span_margin":     round(span_margin, 2),
        "exposure_margin": round(exposure_margin, 2),
        "total_margin":    round(total_margin, 2),
        "premium_paid":    round(premium_paid, 2),
        "premium_received": round(premium_recv, 2),
        "net_premium":     round(premium_recv - premium_paid, 2),
    }
