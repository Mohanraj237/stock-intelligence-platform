"""
Equity trade plan advisor — builds a stock-level trade plan from a ConfluenceResult.
Used by the equity scanner (India + US equities). No options involved.
All levels are ATR-based; the same maths as the F&O option advisor, applied directly
to the underlying stock price.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from services.confluence_scorer import ConfluenceResult

log = logging.getLogger(__name__)

_ATR_SL_MULT = 1.5   # stop = 1.5 × ATR from entry
_T1_MULT     = 1.5   # T1  = 1.5 × risk
_T2_MULT     = 2.5   # T2  = 2.5 × risk
_RR_FLOOR    = 1.0   # reject if R:R at T1 < 1.0


@dataclass
class EquityPlan:
    action:         str    # "BUY" | "SELL"
    entry_price:    float
    sl_price:       float
    t1_price:       float
    t2_price:       float
    rr:             float  # risk:reward at T1
    exit_rule:      str
    risk_per_share: float  # |entry - sl|
    currency:       str = "₹"  # "₹" India, "$" US


def build_equity_plan(
    result: ConfluenceResult,
    currency: str = "₹",
) -> EquityPlan | None:
    """
    Build a stock trade plan from a ConfluenceResult using ATR-based levels.
    Returns None for range setups or if data is insufficient.
    """
    direction = result.direction
    spot      = result.spot_price
    atr       = result.atr

    if direction == "range":
        return None
    if not spot or not atr or atr <= 0:
        return None

    risk = max(atr * _ATR_SL_MULT, spot * 0.003)

    if direction == "bullish":
        action   = "BUY"
        sl       = spot - risk
        t1       = spot + _T1_MULT * risk
        t2       = spot + _T2_MULT * risk
        exit_rule = (
            f"Exit when: price < {sl:.2f} (stop) | "
            f"price > {t1:.2f} T1 | {t2:.2f} T2. "
            f"Trail SL to entry after T1 hit. Max hold: 3–5 sessions."
        )
    else:
        action   = "SELL"
        sl       = spot + risk
        t1       = spot - _T1_MULT * risk
        t2       = spot - _T2_MULT * risk
        exit_rule = (
            f"Exit when: price > {sl:.2f} (stop) | "
            f"price < {t1:.2f} T1 | {t2:.2f} T2. "
            f"Trail SL to entry after T1 hit. Max hold: 3–5 sessions."
        )

    rr = round(_T1_MULT, 2)  # always 1.5 by design
    if rr < _RR_FLOOR:
        return None

    return EquityPlan(
        action=action,
        entry_price=round(spot, 2),
        sl_price=round(sl, 2),
        t1_price=round(t1, 2),
        t2_price=round(t2, 2),
        rr=rr,
        exit_rule=exit_rule,
        risk_per_share=round(risk, 2),
        currency=currency,
    )
