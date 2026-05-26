"""
Position sizing & AI capital allocation for swing/positional trades.

Provides:
  - calculate_position(): single-stock position sizing using % risk + stop
  - kelly_position(): Kelly criterion sizing for known win rate / payoff
  - ai_allocate_capital(): split a total capital across N stocks weighted
                            by AI score, with per-stock entry/SL/qty/risk
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Single-stock position sizing
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PositionSize:
    symbol: str
    entry: float
    stop_loss: float
    target: Optional[float]
    qty: int
    capital_at_risk: float
    capital_deployed: float
    risk_per_share: float
    reward_per_share: Optional[float]
    rr_ratio: Optional[float]
    risk_pct_of_total: float
    notes: List[str]

    def as_dict(self) -> dict:
        return asdict(self)


def calculate_position(
    total_capital: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    target: Optional[float] = None,
    symbol: str = "",
    max_position_pct: float = 25.0,
) -> PositionSize:
    """
    Compute number of shares to buy given:
      total_capital   — full account size in ₹
      risk_pct        — % of total capital you're willing to lose if SL hits (e.g. 1.0 = 1%)
      entry           — planned entry price
      stop_loss       — stop level
      target          — optional target for R:R
      max_position_pct — cap on what % of total capital this single position can use
    """
    notes: List[str] = []
    if total_capital <= 0 or entry <= 0:
        return PositionSize(symbol, entry, stop_loss, target, 0, 0, 0, 0, None, None, 0,
                            ["Invalid inputs (capital or entry <= 0)"])

    risk_per_share = abs(entry - stop_loss)
    if risk_per_share <= 0:
        return PositionSize(symbol, entry, stop_loss, target, 0, 0, 0, 0, None, None, 0,
                            ["Stop loss must differ from entry"])

    capital_at_risk = total_capital * (risk_pct / 100.0)
    raw_qty = int(capital_at_risk / risk_per_share)

    # Apply max position cap
    max_capital = total_capital * (max_position_pct / 100.0)
    max_qty_by_capital = int(max_capital / entry)
    if raw_qty > max_qty_by_capital:
        notes.append(f"Capped at {max_position_pct:.0f}% of capital — {max_qty_by_capital} shares")
        qty = max_qty_by_capital
    else:
        qty = raw_qty

    capital_deployed = qty * entry
    actual_risk = qty * risk_per_share
    risk_pct_actual = (actual_risk / total_capital * 100) if total_capital else 0

    reward_per_share = (target - entry) if target else None
    rr = (reward_per_share / risk_per_share) if (reward_per_share and risk_per_share > 0) else None

    if rr is not None and rr < 1:
        notes.append(f"⚠ Poor R:R ({rr:.2f}) — reward less than risk")
    if risk_pct > 2:
        notes.append("⚠ Risking >2% on one trade — aggressive")
    if qty <= 0:
        notes.append("Stop too wide for the chosen risk %")

    return PositionSize(
        symbol=symbol, entry=entry, stop_loss=stop_loss, target=target,
        qty=qty, capital_at_risk=actual_risk, capital_deployed=capital_deployed,
        risk_per_share=risk_per_share, reward_per_share=reward_per_share,
        rr_ratio=rr, risk_pct_of_total=risk_pct_actual, notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Kelly criterion sizing
# ─────────────────────────────────────────────────────────────────────────────
def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly fraction = W - (1-W)/R where W = win prob, R = avg_win/avg_loss
    Returns fraction of capital to allocate (0..1). Negative => don't trade.
    """
    if avg_loss <= 0 or avg_win <= 0 or win_rate <= 0:
        return 0.0
    R = avg_win / avg_loss
    f = win_rate - (1 - win_rate) / R
    return max(0.0, min(1.0, f))


def kelly_position(total_capital: float, win_rate: float, avg_win_pct: float,
                   avg_loss_pct: float, fractional: float = 0.5) -> dict:
    """
    Kelly-sized position using historical strategy stats.
    `fractional` = 0.5 means use Half-Kelly (recommended for swing trading).
    """
    f = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
    f_used = f * fractional
    capital = total_capital * f_used
    return {
        "kelly_full": round(f * 100, 2),
        "kelly_used_pct": round(f_used * 100, 2),
        "capital_to_deploy": round(capital, 2),
        "fractional": fractional,
        "note": "Half-Kelly used (less variance)" if fractional == 0.5 else f"{int(fractional*100)}% Kelly",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI capital allocator across multiple stocks
# ─────────────────────────────────────────────────────────────────────────────
def ai_allocate_capital(
    total_capital: float,
    candidates: List[dict],
    risk_pct_per_trade: float = 1.0,
    max_position_pct: float = 25.0,
    min_score_threshold: float = 50.0,
    weighting: str = "score",
) -> dict:
    """
    Split a fixed capital across multiple stocks weighted by their AI score.

    Each candidate dict must have:
        symbol, entry, stop_loss, score (0-100)
        target (optional), verdict (optional), name (optional)

    weighting: "score" (linear) | "score_squared" (concentrate on top scorers) | "equal"

    Returns:
        {
          allocations: [PositionSize-as-dict, ...],
          total_deployed, total_at_risk, capital_left,
          summary, weights
        }
    """
    if not candidates or total_capital <= 0:
        return {"allocations": [], "total_deployed": 0, "total_at_risk": 0,
                "capital_left": total_capital, "summary": "No candidates supplied.",
                "weights": {}}

    # Filter out candidates below threshold
    eligible = [c for c in candidates if (c.get("score") or 0) >= min_score_threshold
                and c.get("entry") and c.get("stop_loss")]
    skipped = [c for c in candidates if c not in eligible]

    if not eligible:
        return {"allocations": [], "total_deployed": 0, "total_at_risk": 0,
                "capital_left": total_capital,
                "summary": f"All {len(candidates)} candidates were filtered out "
                           f"(score < {min_score_threshold} or missing entry/stop).",
                "weights": {}}

    # Compute weights
    if weighting == "equal":
        raw_weights = {c["symbol"]: 1.0 for c in eligible}
    elif weighting == "score_squared":
        raw_weights = {c["symbol"]: ((c.get("score") or 50) / 100) ** 2 for c in eligible}
    else:  # "score"
        raw_weights = {c["symbol"]: (c.get("score") or 50) / 100 for c in eligible}

    total_w = sum(raw_weights.values()) or 1
    weights = {sym: w / total_w for sym, w in raw_weights.items()}

    # Allocate capital per-stock with hard cap
    allocations: List[dict] = []
    total_deployed = 0.0
    total_at_risk = 0.0

    for c in eligible:
        sym = c["symbol"]
        target_capital = total_capital * weights[sym]
        target_capital = min(target_capital, total_capital * max_position_pct / 100.0)

        # Compute position size respecting both the target capital AND risk%
        pos = calculate_position(
            total_capital=total_capital,
            risk_pct=risk_pct_per_trade,
            entry=float(c["entry"]),
            stop_loss=float(c["stop_loss"]),
            target=float(c["target"]) if c.get("target") else None,
            symbol=sym,
            max_position_pct=max_position_pct,
        )

        # If risk-based qty would deploy more than weighted target capital, cap it
        if pos.capital_deployed > target_capital and target_capital > 0:
            new_qty = int(target_capital / float(c["entry"]))
            risk_per_share = abs(float(c["entry"]) - float(c["stop_loss"]))
            pos.qty = new_qty
            pos.capital_deployed = new_qty * float(c["entry"])
            pos.capital_at_risk = new_qty * risk_per_share
            pos.risk_pct_of_total = (pos.capital_at_risk / total_capital * 100) if total_capital else 0
            pos.notes.append(f"Capped to AI weight ({weights[sym]*100:.1f}% of capital)")

        d = pos.as_dict()
        d["weight_pct"] = round(weights[sym] * 100, 2)
        d["score"] = c.get("score")
        d["verdict"] = c.get("verdict", "")
        d["name"] = c.get("name", "")
        allocations.append(d)
        total_deployed += pos.capital_deployed
        total_at_risk  += pos.capital_at_risk

    capital_left = total_capital - total_deployed
    summary = (
        f"Allocated **₹{total_deployed:,.0f}** across {len(allocations)} stocks "
        f"(₹{capital_left:,.0f} cash buffer). Total at risk: **₹{total_at_risk:,.0f}** "
        f"({total_at_risk/total_capital*100:.2f}% of capital)."
    )
    if skipped:
        summary += f" Skipped {len(skipped)} stocks (below score threshold)."

    return {
        "allocations": allocations,
        "total_deployed": round(total_deployed, 2),
        "total_at_risk":  round(total_at_risk, 2),
        "capital_left":   round(capital_left, 2),
        "summary": summary,
        "weights": weights,
        "skipped_count": len(skipped),
    }
