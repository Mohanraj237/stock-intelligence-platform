"""Scanner endpoints."""
from __future__ import annotations
import time
import logging
from typing import List
from fastapi import APIRouter

from backend.deps import run_sync, gather_bounded
from backend.schemas import ScanRequest, ScanResult, ScanRow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.get("/types")
async def types() -> List[dict]:
    return [
        {"id": "all",                  "name": "All Stocks",           "desc": "Show everything"},
        {"id": "breakout_ready",       "name": "Breakout Ready",       "desc": "Price > SMA50, RSI 55-72, MACD bullish"},
        {"id": "oversold_bounce",      "name": "Oversold Bounce",      "desc": "RSI < 35"},
        {"id": "strong_momentum",      "name": "Strong Momentum",      "desc": "Above SMA50/200, ADX > 20, RSI 50-75"},
        {"id": "macd_crossover",       "name": "MACD Crossover",       "desc": "MACD just crossed signal up"},
        {"id": "quality_growth",       "name": "Quality Growth",       "desc": "ROE > 15%, sales growth > 15%"},
        {"id": "undervalued",          "name": "Undervalued",          "desc": "PE < 20, PB < 3, ROE > 10%"},
        {"id": "techno_funda",         "name": "Techno-Funda",         "desc": "PE < 30, ROE > 15%, RSI 45-70"},
        {"id": "high_promoter",        "name": "High Promoter",        "desc": "Promoter > 55%, profit growth > 10%"},
        {"id": "dividend_compounders", "name": "Dividend Compounders", "desc": "ROE > 12%, D/E < 1, promoter > 40%"},
        {"id": "high52w_breakout",     "name": "52W High Breakout",    "desc": "Price > SMA200, RSI 60-80"},
        {"id": "reversal_watch",       "name": "Reversal Watch",       "desc": "RSI 25-40, MACD turning bullish"},
    ]


SCAN_FILTERS = {
    "breakout_ready":       {"price_above_sma50": True, "rsi_min": 55, "rsi_max": 72, "macd_bullish": True},
    "oversold_bounce":      {"rsi_max": 35},
    "strong_momentum":      {"price_above_sma50": True, "price_above_sma200": True, "adx_min": 20, "rsi_min": 50, "rsi_max": 75},
    "macd_crossover":       {"macd_bullish": True},
    "quality_growth":       {"roe_min": 15, "sales_growth_min": 15, "de_max": 0.5},
    "undervalued":          {"pe_max": 20, "pb_max": 3, "roe_min": 10},
    "techno_funda":         {"pe_max": 30, "roe_min": 15, "rsi_min": 45, "rsi_max": 70, "price_above_sma50": True},
    "high_promoter":        {"promoter_min": 55, "profit_growth_min": 10},
    "dividend_compounders": {"roe_min": 12, "de_max": 1, "promoter_min": 40},
    "high52w_breakout":     {"price_above_sma200": True, "rsi_min": 60, "rsi_max": 80},
    "reversal_watch":       {"rsi_min": 25, "rsi_max": 40, "macd_bullish": True},
}


@router.post("/run", response_model=ScanResult)
async def run_scan(req: ScanRequest) -> ScanResult:
    """
    Pull universe → bulk OHLCV → compute indicators → apply filters → optional AI scoring.
    """
    from services.universe_sync import get_universe_symbols
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv

    t0 = time.perf_counter()
    syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
    if not syms:
        return ScanResult(request=req, rows=[], total_scanned=0, total_matched=0, duration_ms=0)

    # Merge preset filters with explicit user filters (explicit wins)
    preset = SCAN_FILTERS.get(req.scan_type, {})
    user = req.filters.model_dump(exclude_none=True)
    merged = {**preset, **user}

    async def _one(sym: str) -> dict | None:
        try:
            df = await run_sync(get_ohlcv_history, sym, "1y", "1d")
            if df is None or len(df) < 50:
                return {"_audit": (sym, "fail", "no_ohlcv")}
            ind = await run_sync(compute_indicators_from_ohlcv, df)
            rsi = ind.get("rsi")
            adx = ind.get("adx")
            if "rsi_min" in merged and (rsi is None or rsi < merged["rsi_min"]): return None
            if "rsi_max" in merged and (rsi is None or rsi > merged["rsi_max"]): return None
            if "adx_min" in merged and (adx is None or adx < merged["adx_min"]): return None
            if merged.get("price_above_sma50") and not (ind.get("close") and ind.get("sma50") and ind["close"] > ind["sma50"]):
                return None
            if merged.get("price_above_sma200") and not (ind.get("close") and ind.get("sma200") and ind["close"] > ind["sma200"]):
                return None
            if merged.get("macd_bullish"):
                mh = ind.get("macd_hist")
                if mh is None or mh <= 0:
                    return None
            return {
                "symbol": sym,
                "last_price": ind.get("close"),
                "rsi": ind.get("rsi"),
                "adx": ind.get("adx"),
                "macd_bullish": (ind.get("macd_hist") or 0) > 0,
                "sma50": ind.get("sma50"),
                "sma200": ind.get("sma200"),
                "change_pct": ind.get("change_pct"),
            }
        except Exception as e:
            log.debug("scan symbol failed %s: %s", sym, e)
            return {"_audit": (sym, "fail", f"exception: {type(e).__name__}")}

    raw = await gather_bounded(*[_one(s) for s in syms], limit=24)
    rows: list[ScanRow] = []
    audit: list[dict] = []
    for r in raw:
        if not r or isinstance(r, BaseException):
            continue
        if r.get("_audit"):
            audit.append({"symbol": r["_audit"][0], "status": r["_audit"][1], "reason": r["_audit"][2]})
            continue
        rows.append(ScanRow(**r))
    rows.sort(key=lambda x: (x.change_pct or -1e9), reverse=True)
    return ScanResult(
        request=req, rows=rows, audit_log=audit,
        total_scanned=len(syms), total_matched=len(rows),
        duration_ms=(time.perf_counter() - t0) * 1000,
    )


@router.post("/run/stream")
async def run_scan_stream(req: ScanRequest):
    """Streaming scan with live progress (SSE). Same shape as /run + progress events."""
    from fastapi.responses import StreamingResponse
    from services.universe_sync import get_universe_symbols
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    import asyncio
    import json

    preset = SCAN_FILTERS.get(req.scan_type, {})
    user = req.filters.model_dump(exclude_none=True)
    merged = {**preset, **user}

    async def _one(sym: str) -> dict | None:
        try:
            df = await run_sync(get_ohlcv_history, sym, "1y", "1d")
            if df is None or len(df) < 50:
                return {"_audit": (sym, "fail", "no_ohlcv")}
            ind = await run_sync(compute_indicators_from_ohlcv, df)
            rsi = ind.get("rsi")
            adx = ind.get("adx")
            if "rsi_min" in merged and (rsi is None or rsi < merged["rsi_min"]): return None
            if "rsi_max" in merged and (rsi is None or rsi > merged["rsi_max"]): return None
            if "adx_min" in merged and (adx is None or adx < merged["adx_min"]): return None
            if merged.get("price_above_sma50") and not (ind.get("close") and ind.get("sma50") and ind["close"] > ind["sma50"]):
                return None
            if merged.get("price_above_sma200") and not (ind.get("close") and ind.get("sma200") and ind["close"] > ind["sma200"]):
                return None
            if merged.get("macd_bullish"):
                mh = ind.get("macd_hist")
                if mh is None or mh <= 0:
                    return None
            return {
                "symbol": sym, "last_price": ind.get("close"),
                "rsi": ind.get("rsi"), "adx": ind.get("adx"),
                "macd_bullish": (ind.get("macd_hist") or 0) > 0,
                "sma50": ind.get("sma50"), "sma200": ind.get("sma200"),
                "change_pct": ind.get("change_pct"),
            }
        except Exception as e:
            log.debug("scan symbol failed %s: %s", sym, e)
            return {"_audit": (sym, "fail", f"exception: {type(e).__name__}")}

    async def event_gen():
        def sse(p): return f"data: {json.dumps(p, default=str)}\n\n"

        t0 = time.perf_counter()
        syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
        total = len(syms)
        yield sse({"type": "started", "total": total, "universe": req.universe})

        if total == 0:
            yield sse({"type": "result", "rows": [], "audit_log": [], "total_scanned": 0, "total_matched": 0, "duration_ms": 0, "request": req.model_dump()})
            yield sse({"type": "done"}); return

        sem = asyncio.Semaphore(24)
        async def wrapped(sym):
            async with sem:
                try: return sym, await _one(sym)
                except Exception: return sym, None

        tasks = [asyncio.create_task(wrapped(s)) for s in syms]
        rows: list[ScanRow] = []
        audit: list[dict] = []
        done = 0
        emit_every = max(1, total // 30)
        for fut in asyncio.as_completed(tasks):
            sym, r = await fut
            done += 1
            if r and not isinstance(r, BaseException):
                if r.get("_audit"):
                    audit.append({"symbol": r["_audit"][0], "status": r["_audit"][1], "reason": r["_audit"][2]})
                else:
                    try: rows.append(ScanRow(**r))
                    except Exception: pass
            if done == total or done % emit_every == 0:
                yield sse({"type": "progress", "done": done, "total": total, "matched": len(rows), "current": sym, "elapsed_ms": (time.perf_counter() - t0) * 1000})

        rows.sort(key=lambda x: (x.change_pct or -1e9), reverse=True)
        result = ScanResult(request=req, rows=rows, audit_log=audit, total_scanned=total, total_matched=len(rows), duration_ms=(time.perf_counter() - t0) * 1000)
        yield sse({"type": "result", **result.model_dump()})
        yield sse({"type": "done"})

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })
