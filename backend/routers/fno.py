"""F&O endpoints — thin wrappers around fno_data_service.py."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.deps import run_sync


class PaperTradeIn(BaseModel):
    symbol: str
    instrument_type: str = "CE"
    strike: float = 0.0
    expiry: str
    action: str = "BUY"
    lots: int = 1
    lot_size: int = 1
    entry_price: float
    target_price: float = 0.0
    stop_loss: float = 0.0
    source: str = "MANUAL"
    ai_confidence: str = ""
    strategy_name: str = ""

router = APIRouter(prefix="/api/fno", tags=["fno"])


def _svc():
    from services import fno_data_service as svc  # lazy — avoids import at startup
    return svc


# ── Option Chain ──────────────────────────────────────────────────────────────

@router.get("/option-chain")
async def option_chain(
    symbol: str = Query("NIFTY"),
    expiry: str | None = Query(None),
) -> dict:
    svc = _svc()

    def _run():
        import math
        df, meta = svc.get_option_chain(symbol.upper(), expiry)
        if df is None or df.empty:
            # Fall back to synthetic Black-Scholes option chain
            df, meta = svc.get_synthetic_option_chain(symbol.upper(), expiry)
        if df is None or df.empty:
            return {"rows": [], "meta": meta or {}}
        rows = df.to_dict(orient="records")
        for row in rows:
            for k, v in row.items():
                if isinstance(v, float) and math.isnan(v):
                    row[k] = None
        return {"rows": rows, "meta": meta or {}}

    result = await run_sync(_run)
    return result


# ── Index Futures ─────────────────────────────────────────────────────────────

@router.get("/index-futures")
async def index_futures() -> list[dict]:
    svc = _svc()

    def _run():
        result = svc.get_index_futures()
        if result:
            return result
        # Fallback 1: cached futures from last session
        cached = svc._load_oi_cache("index_futures")
        if cached:
            for r in cached:
                r["cached"] = True
            return cached
        # Fallback 2: derive spot prices from cached allIndices
        data = svc._get_allindices_cached()
        if not data:
            return []
        index_map = [
            ("NIFTY",      "NIFTY 50"),
            ("BANKNIFTY",  "NIFTY BANK"),
            ("FINNIFTY",   "NIFTY FINANCIAL SERVICES"),
            ("MIDCPNIFTY", "NIFTY MIDCAP SELECT"),
        ]
        out = []
        import datetime, math
        for sym, idx_name in index_map:
            for item in data.get("data", []):
                if item.get("index") == idx_name:
                    spot = float(item.get("last") or 0)
                    chg  = float(item.get("variation") or 0)
                    chg_pct = float(item.get("percentChange") or 0)
                    # Approximate basis from VIX (typical 0.5-1% annualised carry ÷ 52 weeks)
                    vix = 15.0
                    for vi in data.get("data", []):
                        if "VIX" in vi.get("index", "").upper():
                            vix = float(vi.get("last") or 15.0)
                    days_to_exp = 7  # assume nearest weekly
                    basis = round(spot * (vix / 100) * math.sqrt(days_to_exp / 365) * 0.5, 2)
                    out.append({
                        "symbol":      sym,
                        "index_name":  idx_name,
                        "spot":        spot,
                        "futures_ltp": round(spot + basis, 2),
                        "basis":       basis,
                        "basis_pct":   round(basis / spot * 100, 3) if spot else 0,
                        "change":      chg,
                        "change_pct":  chg_pct,
                        "oi":          0,
                        "vol":         0,
                        "expiry":      "",
                        "synthetic":   True,
                    })
                    break
        return out

    return await run_sync(_run) or []


# ── VIX ───────────────────────────────────────────────────────────────────────

@router.get("/vix")
async def vix() -> dict:
    svc = _svc()
    result = await run_sync(svc.get_vix)
    return result or {}


# ── PCR ───────────────────────────────────────────────────────────────────────

@router.get("/pcr")
async def pcr(symbol: str = Query("NIFTY")) -> dict:
    svc = _svc()
    result = await run_sync(lambda: svc.get_pcr(symbol.upper()))
    return result or {}


# ── OI Spurts ─────────────────────────────────────────────────────────────────

@router.get("/oi-spurts")
async def oi_spurts() -> list[dict]:
    svc = _svc()

    def _run():
        df = svc.get_oi_spurts()
        if df is None or df.empty:
            return []
        import math
        rows = df.to_dict(orient="records")
        for row in rows:
            for k, v in row.items():
                if isinstance(v, float) and math.isnan(v):
                    row[k] = None
        return rows

    return await run_sync(_run) or []


# ── OI Variations (buildup) ───────────────────────────────────────────────────

@router.get("/oi-variations")
async def oi_variations() -> list[dict]:
    svc = _svc()

    def _run():
        df = svc.get_oi_variations()
        if df is None or df.empty:
            return []
        import math
        rows = df.to_dict(orient="records")
        for row in rows:
            for k, v in row.items():
                if isinstance(v, float) and math.isnan(v):
                    row[k] = None
        return rows

    return await run_sync(_run) or []


# ── F&O Symbols ───────────────────────────────────────────────────────────────

@router.get("/symbols")
async def fno_symbols() -> list[str]:
    svc = _svc()
    equities = await run_sync(svc.get_fno_symbols) or []
    # Always surface indices at the top regardless of NSE API availability
    indices = [s for s in svc.INDEX_SYMBOLS if s not in equities]
    return indices + equities


# ── Scanner (server-side, uses OI spurts — no option chain needed) ───────────

_SCAN_OI_BASED = {"High OI Buildup", "OI Unwinding", "Unusual Volume"}

@router.get("/scan")
async def scan(
    scan_type: str = Query("High OI Buildup"),
    symbols: str = Query(""),          # comma-separated; empty = all
) -> list[dict]:
    svc = _svc()

    def _run():
        import math
        df = svc.get_oi_spurts()
        if df is None or df.empty:
            return []

        # Filter by requested symbols if provided
        syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if syms:
            df = df[df["symbol"].isin(syms)]

        rows_out = []
        for _, r in df.iterrows():
            sym = r.get("symbol", "")
            oi_cur = float(r.get("oi_current", 0) or 0)
            oi_chg_pct = float(r.get("oi_change_pct", 0) or 0)
            vol = float(r.get("vol", 0) or 0)
            ltp = float(r.get("ltp", 0) or 0)

            if scan_type == "High OI Buildup":
                if oi_chg_pct < 10:
                    continue
                strength = min(99, int(oi_chg_pct))
                direction = "Bullish" if ltp > 0 else "Neutral"
                metric = f"OI +{oi_chg_pct:.1f}% | {oi_cur/1e5:.1f}L contracts"

            elif scan_type == "OI Unwinding":
                if oi_chg_pct > -10:
                    continue
                strength = min(99, int(abs(oi_chg_pct)))
                direction = "Bearish"
                metric = f"OI {oi_chg_pct:.1f}% | Unwinding"

            elif scan_type == "Unusual Volume":
                if oi_cur <= 0 or vol <= 0:
                    continue
                ratio = vol / oi_cur
                if ratio < 0.2:
                    continue
                strength = min(99, int(ratio * 50))
                direction = "Neutral"
                metric = f"Vol/OI {ratio:.2f} | {vol/1e3:.0f}K contracts"

            else:
                # Scan type needs option chain — not available
                continue

            rows_out.append({
                "symbol": sym,
                "signal_type": scan_type,
                "metric": metric,
                "direction": direction,
                "strength": strength,
                "expiry": "",
                "dte": 0,
            })

        rows_out.sort(key=lambda x: -x["strength"])
        return rows_out[:50]

    return await run_sync(_run) or []


# ── Index prices (from allIndices) ────────────────────────────────────────────

@router.get("/index-prices")
async def index_prices() -> list[dict]:
    svc = _svc()

    def _run():
        data = svc._get_allindices_cached()
        if not data:
            return []
        keep = {"NIFTY 50", "NIFTY BANK", "NIFTY FINANCIAL SERVICES",
                "NIFTY MIDCAP SELECT", "NIFTY IT", "INDIA VIX"}
        out = []
        for d in data.get("data", []):
            if d.get("index") in keep:
                out.append({
                    "index": d.get("index"),
                    "last": d.get("last"),
                    "change": d.get("variation"),
                    "change_pct": d.get("percentChange"),
                    "open": d.get("open"),
                    "high": d.get("high"),
                    "low": d.get("low"),
                    "prev_close": d.get("previousClose"),
                })
        return out

    return await run_sync(_run) or []


# ── F&O Watchlist CRUD (P1-2) ────────────────────────────────────────────────

@router.get("/watchlist")
async def fno_watchlist_get() -> list[str]:
    """Return the F&O watchlist symbols (default: NIFTY, BANKNIFTY)."""
    svc = _svc()
    return await run_sync(svc.get_fno_watchlist) or ["NIFTY", "BANKNIFTY"]


@router.post("/watchlist")
async def fno_watchlist_add(body: dict) -> dict:
    """Add a symbol to the F&O watchlist.  Body: {symbol: string}."""
    svc = _svc()
    symbol = str(body.get("symbol", "")).upper().strip()
    if not symbol:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="symbol is required")

    def _run():
        current = svc.get_fno_watchlist()
        if symbol not in current:
            current.append(symbol)
            svc.save_fno_watchlist(current)
        return {"ok": True, "watchlist": svc.get_fno_watchlist()}

    return await run_sync(_run)


@router.delete("/watchlist/{symbol}")
async def fno_watchlist_remove(symbol: str) -> dict:
    """Remove a symbol from the F&O watchlist."""
    svc = _svc()

    def _run():
        current = svc.get_fno_watchlist()
        updated = [s for s in current if s.upper() != symbol.upper()]
        svc.save_fno_watchlist(updated)
        return {"ok": True, "watchlist": svc.get_fno_watchlist()}

    return await run_sync(_run)


# ── Underlying Quotes (P1-7) ──────────────────────────────────────────────────

@router.get("/underlying-quotes")
async def underlying_quotes(
    symbols: str = "",   # comma-separated; empty = current watchlist
) -> list[dict]:
    """
    Live spot LTP + change% for the given symbols (or the F&O watchlist).
    Uses allIndices for index symbols; F&O securities list for equities.
    """
    svc = _svc()

    def _run():
        import math
        if symbols.strip():
            syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        else:
            syms = svc.get_fno_watchlist()

        rows = svc.get_underlying_quotes(syms)
        for r in rows:
            for k, v in r.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    r[k] = 0.0
        return rows

    return await run_sync(_run) or []


# ── IV Rank (WS-5) ───────────────────────────────────────────────────────────

@router.get("/iv-rank")
async def iv_rank_endpoint(symbol: str = Query("NIFTY")) -> dict:
    """
    True IV Rank for a symbol from stored ATM IV history (52-week high/low).
    Falls back to a VIX-proxy estimate with sufficient_history=False when
    fewer than 30 days of history are available.
    """
    svc = _svc()
    return await run_sync(lambda: svc.get_iv_rank(symbol.upper())) or {}


@router.post("/iv-snapshot")
async def iv_snapshot_endpoint() -> dict:
    """
    Manually trigger a daily ATM IV snapshot for all watchlist + index symbols.
    In production this is called once per day at startup. Expose as a POST so
    tests and admins can trigger it on demand.
    """
    svc = _svc()
    updated = await run_sync(svc.append_daily_iv_snapshot) or []
    return {"ok": True, "updated": updated, "count": len(updated)}


# ── F&O History (PCR + VIX 60-day rolling) ───────────────────────────────────

@router.get("/history")
async def fno_history() -> dict:
    """
    60-day rolling PCR + VIX history.  One entry per calendar day, appended at
    startup by append_daily_fno_snapshot().  Returns {pcr: [...], vix: [...]}.
    """
    svc = _svc()
    return await run_sync(svc.get_fno_history) or {"pcr": [], "vix": []}


# ── Saved Strategies ──────────────────────────────────────────────────────────

@router.get("/strategies")
async def list_strategies() -> list[dict]:
    svc = _svc()
    return await run_sync(svc.get_saved_strategies) or []


@router.post("/strategies")
async def create_strategy(body: dict) -> dict:
    svc = _svc()
    name: str = body.get("name", "")
    legs: list = body.get("legs", [])
    if not name or not legs:
        raise HTTPException(status_code=400, detail="name and legs are required")
    await run_sync(lambda: svc.save_strategy(name, legs))
    return {"ok": True}


@router.delete("/strategies/{name}")
async def remove_strategy(name: str) -> dict:
    svc = _svc()
    await run_sync(lambda: svc.delete_strategy(name))
    return {"ok": True}


# ── Paper Trades ──────────────────────────────────────────────────────────────

@router.get("/paper-trades/portfolio")
async def paper_trade_portfolio() -> dict:
    from services import paper_trade_service as pts
    return await run_sync(pts.get_portfolio_summary) or {}


@router.get("/paper-trades/equity-curve")
async def paper_trade_equity_curve() -> list[dict]:
    from services import paper_trade_service as pts
    return await run_sync(pts.get_equity_curve) or []


@router.get("/paper-trades/open")
async def list_open_trades() -> list[dict]:
    from services import paper_trade_service as pts
    return await run_sync(pts.get_open_trades) or []


@router.get("/paper-trades/closed")
async def list_closed_trades() -> list[dict]:
    from services import paper_trade_service as pts
    return await run_sync(pts.get_closed_trades) or []


@router.post("/paper-trades")
async def add_paper_trade_endpoint(body: PaperTradeIn) -> dict:
    from services import paper_trade_service as pts

    def _run():
        ok, msg = pts.add_trade(
            symbol=body.symbol.upper(),
            instrument_type=body.instrument_type,
            strike=body.strike,
            expiry=body.expiry,
            action=body.action,
            lots=body.lots,
            lot_size=body.lot_size,
            entry_price=body.entry_price,
            target_price=body.target_price,
            stop_loss=body.stop_loss,
            source=body.source,
            ai_confidence=body.ai_confidence,
            strategy_name=body.strategy_name,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}

    return await run_sync(_run)


@router.post("/paper-trades/{trade_id}/close")
async def close_paper_trade_endpoint(trade_id: str, body: dict) -> dict:
    from services import paper_trade_service as pts

    def _run():
        exit_price = float(body.get("exit_price", 0))
        exit_reason = str(body.get("exit_reason", "MANUAL"))
        ok, msg = pts.close_trade(trade_id, exit_price, exit_reason)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}

    return await run_sync(_run)


@router.post("/paper-trades/refresh-prices")
async def refresh_paper_trade_prices() -> list[dict]:
    """
    Fetch live LTP from NSE option chain for every open paper position and update
    current_price / pnl_rs / pnl_pct in storage.  Returns a list of update events
    (one per successfully refreshed trade), including sl_hit / tp_hit flags.

    Falls back gracefully: trades whose LTP cannot be fetched are left unchanged.
    """
    from services import paper_trade_service as pts
    return await run_sync(pts.update_all_prices) or []


@router.patch("/paper-trades/{trade_id}/price")
async def update_paper_trade_price_manual(trade_id: str, body: dict) -> dict:
    """Manually set current_price for a trade and recalculate P&L."""
    from services import paper_trade_service as pts
    current_price = float(body.get("current_price", 0))
    if current_price <= 0:
        raise HTTPException(status_code=400, detail="current_price must be > 0")
    updated = await run_sync(lambda: pts.update_trade_price(trade_id, current_price))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return updated


@router.post("/paper-trades/reset")
async def reset_paper_trades(body: dict) -> dict:
    from services import paper_trade_service as pts
    initial_capital = float(body.get("initial_capital", 500_000))
    await run_sync(lambda: pts.reset_portfolio(initial_capital))
    return {"ok": True}
