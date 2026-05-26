"""Portfolio CRUD + live P&L."""
from __future__ import annotations
import asyncio
import logging
from typing import List
from fastapi import APIRouter, HTTPException

from backend.deps import run_sync
from backend.schemas import Holding, PortfolioRow, PortfolioSummary

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _load() -> list[dict]:
    from storage.file_store import get_holdings
    return list(get_holdings() or [])


def _save(items: list[dict]) -> None:
    from storage.file_store import save_portfolio, get_portfolio
    p = get_portfolio() or {}
    p["holdings"] = items
    save_portfolio(p)


@router.get("", response_model=PortfolioSummary)
async def get_portfolio() -> PortfolioSummary:
    from services.nse_service import get_quote
    holdings = await run_sync(_load)

    async def _enrich(h: dict) -> PortfolioRow:
        sym = h.get("symbol", "")
        try:
            q = await run_sync(get_quote, sym)
        except Exception:
            q = None
        cmp_ = float(q.get("lastPrice")) if q and q.get("lastPrice") else None
        invested = float(h.get("qty", 0)) * float(h.get("buy_price", 0))
        current_value = cmp_ * float(h.get("qty", 0)) if cmp_ else None
        pnl = (current_value - invested) if current_value is not None else None
        pnl_pct = (pnl / invested * 100) if (pnl is not None and invested) else None
        return PortfolioRow(
            symbol=sym, qty=float(h.get("qty", 0)),
            buy_price=float(h.get("buy_price", 0)),
            buy_date=h.get("buy_date"),
            cmp=cmp_,
            today_change_pct=float(q.get("pChange")) if q and q.get("pChange") is not None else None,
            invested=invested, current_value=current_value,
            pnl=pnl, pnl_pct=pnl_pct,
        )

    rows = await asyncio.gather(*[_enrich(h) for h in holdings])
    total_invested = sum(r.invested for r in rows)
    current_value = sum((r.current_value or 0) for r in rows)
    total_pnl = current_value - total_invested
    return PortfolioSummary(
        rows=rows,
        total_invested=total_invested,
        current_value=current_value,
        total_pnl=total_pnl,
        total_pnl_pct=(total_pnl / total_invested * 100) if total_invested else 0,
        holdings_count=len(rows),
    )


@router.post("/add", response_model=Holding)
async def add(h: Holding) -> Holding:
    items = await run_sync(_load)
    items.append(h.model_dump())
    await run_sync(_save, items)
    return h


@router.delete("/{symbol}")
async def remove(symbol: str) -> dict:
    items = await run_sync(_load)
    new_items = [h for h in items if (h.get("symbol", "").upper() != symbol.upper())]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Holding not found")
    await run_sync(_save, new_items)
    return {"removed": symbol, "remaining": len(new_items)}
