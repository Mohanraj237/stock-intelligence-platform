"""Position-sizing endpoints."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from backend.deps import run_sync
from backend.schemas import PositionSize, KellyResult, AIAllocation

router = APIRouter(prefix="/api/positions", tags=["positions"])


class CalcReq(BaseModel):
    capital: float
    risk_pct: float = 1.0
    entry: float
    stop: float
    target: Optional[float] = None
    max_position_pct: float = 25


class KellyReq(BaseModel):
    capital: float
    win_rate: float           # 0-100 or 0-1
    avg_win_pct: float
    avg_loss_pct: float
    fractional: float = 0.5    # Half Kelly default


class AIAllocReq(BaseModel):
    universe: str = "NIFTY 50"
    capital: float
    risk_pct: float = 1.0
    top_n: int = 10
    max_position_pct: float = 15
    min_score: float = 60
    weighting: str = "score"   # score | score_squared | equal
    scan_limit: int = 50


@router.post("/calc", response_model=PositionSize)
async def calc(req: CalcReq) -> PositionSize:
    from services.position_sizing_service import calculate_position
    raw = await run_sync(
        calculate_position, req.capital, req.risk_pct, req.entry, req.stop,
        req.target, req.max_position_pct,
    )
    return PositionSize(
        qty=int(getattr(raw, "qty", 0)),
        deployed=float(getattr(raw, "deployed", 0)),
        at_risk=float(getattr(raw, "at_risk", 0)),
        rr=getattr(raw, "rr", None),
        risk_pct=req.risk_pct, capital=req.capital,
        entry=req.entry, stop=req.stop, target=req.target,
        notes=list(getattr(raw, "notes", []) or []),
    )


@router.post("/kelly", response_model=KellyResult)
async def kelly(req: KellyReq) -> KellyResult:
    from services.position_sizing_service import kelly_position
    win_rate = req.win_rate / 100 if req.win_rate > 1 else req.win_rate
    raw = await run_sync(
        kelly_position, req.capital, win_rate, req.avg_win_pct, req.avg_loss_pct, req.fractional,
    )
    return KellyResult(
        full_kelly_pct=float(raw.get("full_kelly_pct", 0)),
        used_kelly_pct=float(raw.get("used_kelly_pct", 0)),
        deploy_amount=float(raw.get("deploy_amount", 0)),
        edge=float(raw.get("edge", 0)),
        note=str(raw.get("note", "")),
    )


@router.post("/ai-allocate", response_model=AIAllocation)
async def ai_allocate(req: AIAllocReq) -> AIAllocation:
    """
    Run an AI-scored scan, take top-N, allocate capital weighted by score.
    """
    import asyncio
    from services.universe_sync import get_universe_symbols
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    from services.screener_service import get_full_screener_data
    from services.ai_service import analyze_stock
    from services.position_sizing_service import ai_allocate_capital
    from engines.pattern_engine import detect_patterns

    syms = await run_sync(get_universe_symbols, req.universe, req.scan_limit)

    async def _score(sym: str):
        df = await run_sync(get_ohlcv_history, sym, "1y", "1d")
        if df is None or len(df) < 50:
            return None
        ind = await run_sync(compute_indicators_from_ohlcv, df)
        funda = await run_sync(get_full_screener_data, sym)
        pats = await run_sync(detect_patterns, df)
        tv = {"indicators": ind, "recommendation": "NEUTRAL", "close": ind.get("close")}
        ai = await run_sync(analyze_stock, sym, tv, funda, pats)
        return {
            "symbol": sym, "score": float(getattr(ai, "composite_score", 0)),
            "verdict": getattr(ai, "verdict", "NEUTRAL"),
            "entry": ind.get("close"),
            "stop": getattr(ai, "stop_loss", None) or (ind.get("close", 0) * 0.95),
            "target": getattr(ai, "price_target", None),
            "atr": ind.get("atr"),
        }

    results = [r for r in await asyncio.gather(*[_score(s) for s in syms]) if r]
    raw = await run_sync(
        ai_allocate_capital, req.capital, results, req.risk_pct,
        req.max_position_pct, req.min_score, req.weighting,
    )
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    return AIAllocation(
        rows=[{**r, "weight_pct": r.get("weight_pct", 0), "qty": int(r.get("qty", 0))} for r in rows],
        total_deployed=float((raw or {}).get("total_deployed", 0)),
        total_at_risk=float((raw or {}).get("total_at_risk", 0)),
        cash_buffer=float((raw or {}).get("cash_buffer", req.capital)),
        rejected=list((raw or {}).get("rejected", [])),
    )
