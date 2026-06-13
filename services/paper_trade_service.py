"""
Paper Trade Service — virtual F&O position management.
All trades are purely simulated; no real broker connection.
Data persisted in storage/data/paper_trades.json.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[1]
_TRADES_PATH = _BASE / "storage" / "data" / "paper_trades.json"
_LOCK = threading.Lock()

INITIAL_CAPITAL = 500_000.0


# ── JSON helpers ───────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        if _TRADES_PATH.exists():
            import json
            return json.loads(_TRADES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("paper_trades load error: %s", exc)
    return {
        "portfolio": {
            "initial_capital": INITIAL_CAPITAL,
            "available_capital": INITIAL_CAPITAL,
        },
        "trades": [],
        "closed_trades": [],
    }


def _save(data: dict):
    try:
        import json
        _TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TRADES_PATH.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
    except Exception as exc:
        logger.error("paper_trades save error: %s", exc)


# ── Portfolio helpers ──────────────────────────────────────────────────────────

def _margin_for(entry_price: float, lot_size: int, lots: int, action: str, instrument: str) -> float:
    """Approximate margin: options BUY = full premium; SELL/FUT = 15% notional."""
    premium = entry_price * lot_size * lots
    if instrument == "FUT" or action == "SELL":
        # SPAN-like margin: 15% of notional (entry_price used as proxy for underlying for simplicity)
        return premium * 1.5
    return premium


def get_portfolio_summary() -> dict:
    """Return current capital state and P&L summary."""
    data = _load()
    port = data.get("portfolio", {})
    open_trades = data.get("trades", [])
    closed_trades = data.get("closed_trades", [])

    open_pnl = sum(float(t.get("pnl_rs", 0)) for t in open_trades)
    closed_pnl = sum(float(t.get("pnl_rs", 0)) for t in closed_trades)
    deployed = sum(float(t.get("margin_used", 0)) for t in open_trades)
    available = float(port.get("available_capital", INITIAL_CAPITAL))
    initial = float(port.get("initial_capital", INITIAL_CAPITAL))
    total_equity = available + deployed + open_pnl

    wins = sum(1 for t in closed_trades if float(t.get("pnl_rs", 0)) > 0)
    win_rate = round(wins / len(closed_trades) * 100, 1) if closed_trades else 0

    gross_profit = sum(float(t.get("pnl_rs", 0)) for t in closed_trades if float(t.get("pnl_rs", 0)) > 0)
    gross_loss = abs(sum(float(t.get("pnl_rs", 0)) for t in closed_trades if float(t.get("pnl_rs", 0)) < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    return {
        "initial_capital":  initial,
        "available_capital": available,
        "deployed_capital":  deployed,
        "total_equity":      total_equity,
        "open_pnl":          open_pnl,
        "closed_pnl":        closed_pnl,
        "total_pnl":         open_pnl + closed_pnl,
        "total_pnl_pct":     round((open_pnl + closed_pnl) / initial * 100, 2) if initial else 0,
        "open_trades_count": len(open_trades),
        "closed_trades_count": len(closed_trades),
        "win_rate":           win_rate,
        "profit_factor":      profit_factor,
    }


def get_open_trades() -> list[dict]:
    return _load().get("trades", [])


def get_closed_trades() -> list[dict]:
    return _load().get("closed_trades", [])


# ── Trade operations ───────────────────────────────────────────────────────────

def add_trade(
    symbol: str,
    instrument_type: str,   # CE, PE, FUT
    strike: float,
    expiry: str,
    action: str,            # BUY, SELL
    lots: int,
    lot_size: int,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    source: str = "MANUAL",
    ai_confidence: str = "",
    strategy_name: str = "",
) -> tuple[bool, str]:
    """
    Add a new paper trade. Returns (success, message).
    Validates that available_capital covers the margin required.
    """
    with _LOCK:
        data = _load()
        port = data.setdefault("portfolio", {
            "initial_capital": INITIAL_CAPITAL,
            "available_capital": INITIAL_CAPITAL,
        })

        margin = _margin_for(entry_price, lot_size, lots, action, instrument_type)
        available = float(port.get("available_capital", INITIAL_CAPITAL))

        if margin > available:
            return False, (
                f"Insufficient capital. Required: ₹{margin:,.0f}, Available: ₹{available:,.0f}"
            )

        trade_id = str(uuid.uuid4())[:8].upper()
        now = datetime.now().isoformat()
        pnl = 0.0

        trade = {
            "trade_id":       trade_id,
            "symbol":         symbol.upper(),
            "instrument_type": instrument_type.upper(),
            "strike":         strike,
            "expiry":         expiry,
            "action":         action.upper(),
            "lots":           lots,
            "lot_size":       lot_size,
            "entry_price":    entry_price,
            "entry_time":     now,
            "current_price":  entry_price,
            "target_price":   target_price,
            "stop_loss":      stop_loss,
            "status":         "OPEN",
            "source":         source,
            "ai_confidence":  ai_confidence,
            "strategy_name":  strategy_name,
            "pnl_rs":         pnl,
            "pnl_pct":        0.0,
            "margin_used":    margin,
            "exit_price":     None,
            "exit_time":      None,
            "exit_reason":    None,
        }

        data.setdefault("trades", []).append(trade)
        port["available_capital"] = available - margin
        _save(data)

    instr = f"{symbol} {strike:.0f} {instrument_type}" if instrument_type != "FUT" else f"{symbol} FUT"
    return True, f"Trade added: {action} {lots}x {instr} @ ₹{entry_price:.2f} [ID: {trade_id}]"


def close_trade(
    trade_id: str,
    exit_price: float,
    exit_reason: str = "MANUAL",
) -> tuple[bool, str]:
    """Close an open trade and move it to closed_trades. Returns (success, message)."""
    with _LOCK:
        data = _load()
        open_trades = data.get("trades", [])

        idx = next((i for i, t in enumerate(open_trades) if t.get("trade_id") == trade_id), None)
        if idx is None:
            return False, f"Trade {trade_id} not found."

        trade = open_trades.pop(idx)
        action = trade.get("action", "BUY")
        entry = float(trade.get("entry_price", 0))
        lots = int(trade.get("lots", 1))
        lot_sz = int(trade.get("lot_size", 1))
        margin = float(trade.get("margin_used", 0))

        multiplier = 1 if action == "BUY" else -1
        pnl = round(multiplier * (exit_price - entry) * lots * lot_sz, 2)
        pnl_pct = round(pnl / margin * 100, 2) if margin > 0 else 0

        trade["exit_price"] = exit_price
        trade["exit_time"] = datetime.now().isoformat()
        trade["exit_reason"] = exit_reason
        trade["current_price"] = exit_price
        trade["pnl_rs"] = pnl
        trade["pnl_pct"] = pnl_pct
        trade["status"] = "CLOSED"

        data.setdefault("closed_trades", []).append(trade)
        data["trades"] = open_trades

        port = data.setdefault("portfolio", {"available_capital": INITIAL_CAPITAL})
        port["available_capital"] = float(port.get("available_capital", 0)) + margin + pnl
        _save(data)

    sign = "+" if pnl >= 0 else ""
    return True, f"Closed {trade_id}: P&L {sign}₹{pnl:,.0f} ({sign}{pnl_pct:.1f}%) — {exit_reason}"


def update_trade_price(trade_id: str, current_price: float, price_source: str = "manual") -> dict | None:
    """
    Update current_price, pnl_rs, pnl_pct, and price_source for a single open trade.
    price_source: "live" | "cached" | "manual"
    Returns updated trade dict or None if trade not found.
    """
    with _LOCK:
        data = _load()
        for trade in data.get("trades", []):
            if trade.get("trade_id") == trade_id:
                action    = trade.get("action", "BUY")
                entry     = float(trade.get("entry_price", 0))
                lots      = int(trade.get("lots", 1))
                lot_sz    = int(trade.get("lot_size", 1))
                margin    = float(trade.get("margin_used", 0))
                mult      = 1 if action == "BUY" else -1
                pnl       = round(mult * (current_price - entry) * lots * lot_sz, 2)
                pnl_pct   = round(pnl / margin * 100, 2) if margin > 0 else 0.0
                trade["current_price"] = current_price
                trade["pnl_rs"]        = pnl
                trade["pnl_pct"]       = pnl_pct
                trade["price_source"]  = price_source
                _save(data)
                return dict(trade)
    return None


def _normalize_expiry(exp: str) -> str:
    """Normalize any expiry string to 'DD-Mon-YYYY' for robust comparison."""
    exp = exp.strip()
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(exp, fmt).strftime("%d-%b-%Y")
        except ValueError:
            pass
    return exp.lower()  # last-resort: lower-cased original


def _ltp_from_chain(sym: str, strike: float, expiry: str, instr: str) -> tuple[float | None, str]:
    """
    Resolve a single option LTP using the same get_option_chain() path the scanner uses.
    This path is: live NSE → disk cache (last-traded prices) → synthetic BS.
    Synthetic prices are REJECTED because they are model estimates, not traded prices.

    Returns (ltp, source) where source is "live" | "cached" | "none".
    """
    from services.fno_data_service import get_option_chain
    try:
        df, meta = get_option_chain(sym)
    except Exception as exc:
        logger.warning("get_option_chain failed for %s: %s", sym, exc)
        return None, "none"

    if df is None or df.empty:
        return None, "none"

    # Reject synthetic (Black-Scholes) prices — they are not real traded prices.
    if meta.get("synthetic"):
        logger.debug("Skipping synthetic chain for %s — not real market data", sym)
        return None, "none"

    col = f"{instr}_ltp"
    if col not in df.columns:
        logger.warning("Column %s missing in chain for %s", col, sym)
        return None, "none"

    expiry_norm = _normalize_expiry(expiry)
    df_match = df[
        df["expiry"].apply(_normalize_expiry).eq(expiry_norm)
        & df["strike"].apply(lambda s: abs(float(s) - strike) < 0.5)
    ]

    if df_match.empty:
        logger.info("No chain row for %s %.1f %s %s", sym, strike, instr, expiry)
        return None, "none"

    ltp = float(df_match.iloc[0][col])
    if ltp <= 0:
        logger.info("Chain row found for %s %.1f %s but lastPrice=0", sym, strike, instr)
        return None, "none"

    source = "cached" if meta.get("cached") else "live"
    return ltp, source


def update_all_prices() -> list[dict]:
    """
    Fetch current LTP for every open trade using the option chain path (same as scanner).
    Fallback order: live NSE → disk cache (real last-close) → no update.
    Synthetic Black-Scholes prices are explicitly excluded.

    Returns one dict per trade:
      - on success: trade_id, symbol, current_price, pnl_rs, price_source, sl_hit, tp_hit
      - on failure: trade_id, symbol, current_price=None, error=<reason>, price_source="none"
    """
    results = []
    for trade in get_open_trades():
        sym    = trade.get("symbol", "")
        strike = float(trade.get("strike", 0))
        expiry = trade.get("expiry", "")
        instr  = trade.get("instrument_type", "CE")

        ltp, source = _ltp_from_chain(sym, strike, expiry, instr)

        if ltp is not None and ltp > 0:
            updated = update_trade_price(trade["trade_id"], ltp, price_source=source)
            if updated:
                sl     = float(trade.get("stop_loss", 0))
                tp     = float(trade.get("target_price", 0))
                action = trade.get("action", "BUY")
                sl_hit = (action == "BUY" and ltp <= sl) or (action == "SELL" and ltp >= sl)
                tp_hit = (action == "BUY" and ltp >= tp) or (action == "SELL" and ltp <= tp)
                results.append({
                    "trade_id":      trade["trade_id"],
                    "symbol":        sym,
                    "current_price": ltp,
                    "pnl_rs":        updated["pnl_rs"],
                    "price_source":  source,
                    "sl_hit":        sl_hit,
                    "tp_hit":        tp_hit,
                })
                logger.info("Price updated: %s %.1f %s → %.2f (%s)", sym, strike, instr, ltp, source)
        else:
            reason = "NSE blocked and no disk cache" if source == "none" else "lastPrice=0"
            logger.warning("No real LTP for %s %.1f %s %s — %s", sym, strike, instr, trade["trade_id"], reason)
            results.append({
                "trade_id":      trade["trade_id"],
                "symbol":        sym,
                "current_price": None,
                "pnl_rs":        None,
                "price_source":  "none",
                "sl_hit":        False,
                "tp_hit":        False,
                "error":         f"No real market price available for {sym} {strike:.0f} {instr} ({expiry}). "
                                 f"NSE API is unavailable and no cached chain exists. "
                                 f"Use 'set price' to enter the current price manually.",
            })
    return results


def check_sl_tp_hits() -> list[dict]:
    """
    Check all open trades against SL/TP. Auto-close any that are hit.
    Returns list of dicts describing each auto-close event.
    """
    updates = update_all_prices()
    events = []
    for u in updates:
        if u.get("sl_hit"):
            ok, msg = close_trade(u["trade_id"], u["current_price"], "SL_HIT")
            if ok:
                events.append({"type": "SL_HIT", "trade_id": u["trade_id"],
                                "symbol": u["symbol"], "pnl_rs": u["pnl_rs"], "message": msg})
        elif u.get("tp_hit"):
            ok, msg = close_trade(u["trade_id"], u["current_price"], "TARGET_HIT")
            if ok:
                events.append({"type": "TARGET_HIT", "trade_id": u["trade_id"],
                                "symbol": u["symbol"], "pnl_rs": u["pnl_rs"], "message": msg})
    return events


def edit_trade_levels(trade_id: str, stop_loss: float | None = None, target_price: float | None = None) -> bool:
    """Edit SL or target for an open trade."""
    with _LOCK:
        data = _load()
        for trade in data.get("trades", []):
            if trade.get("trade_id") == trade_id:
                if stop_loss is not None:
                    trade["stop_loss"] = stop_loss
                if target_price is not None:
                    trade["target_price"] = target_price
                _save(data)
                return True
    return False


def reset_portfolio(initial_capital: float = INITIAL_CAPITAL):
    """Reset all trades and restore capital — for testing / fresh start."""
    _save({
        "portfolio": {
            "initial_capital": initial_capital,
            "available_capital": initial_capital,
        },
        "trades": [],
        "closed_trades": [],
    })


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_equity_curve() -> list[dict]:
    """
    Build cumulative P&L curve from closed trades, sorted by exit time.
    Returns list of {date, cumulative_pnl}.
    """
    closed = sorted(
        get_closed_trades(),
        key=lambda t: t.get("exit_time") or "",
    )
    cumulative = 0.0
    curve = []
    for t in closed:
        cumulative += float(t.get("pnl_rs", 0))
        curve.append({
            "date":           (t.get("exit_time") or "")[:10],
            "cumulative_pnl": round(cumulative, 2),
            "trade_pnl":      float(t.get("pnl_rs", 0)),
            "symbol":         t.get("symbol", ""),
        })
    return curve


def get_performance_by_dimension(dimension: str = "symbol") -> list[dict]:
    """
    Win rate and P&L grouped by a dimension (symbol, instrument_type, source, ai_confidence).
    """
    closed = get_closed_trades()
    groups: dict[str, dict] = {}
    for t in closed:
        key = str(t.get(dimension, "Unknown"))
        g = groups.setdefault(key, {"wins": 0, "losses": 0, "total_pnl": 0.0, "count": 0})
        pnl = float(t.get("pnl_rs", 0))
        g["count"] += 1
        g["total_pnl"] += pnl
        if pnl > 0:
            g["wins"] += 1
        else:
            g["losses"] += 1

    result = []
    for key, g in groups.items():
        wr = round(g["wins"] / g["count"] * 100, 1) if g["count"] else 0
        result.append({
            dimension:    key,
            "count":      g["count"],
            "wins":       g["wins"],
            "losses":     g["losses"],
            "win_rate":   wr,
            "total_pnl":  round(g["total_pnl"], 2),
            "avg_pnl":    round(g["total_pnl"] / g["count"], 2) if g["count"] else 0,
        })
    return sorted(result, key=lambda x: x["total_pnl"], reverse=True)
