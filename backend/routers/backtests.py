"""Pattern backtesting endpoints."""
from __future__ import annotations
import asyncio
import json
import time
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.deps import run_sync
from backend.schemas import BacktestRequest, BacktestResult, TradeRow

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


# Library name -> primary engine name. Same alias map used by Pattern Lab,
# but the backtest service only accepts a single name so we resolve to the
# strongest engine pattern for each library entry. Without this, picking
# "Symmetrical Triangle" gives 0 trades because the engine emits
# "Symmetrical Triangle Breakout".
LIBRARY_TO_ENGINE: dict[str, str] = {
    "symmetrical triangle":  "Symmetrical Triangle Breakout",
    "channel breakout":      "Ascending Channel",       # bullish channel; "Descending Channel" needs a separate run
    "falling wedge":         "Descending Wedge Breakout",
    "52w high breakout":     "52W High Breakout",
}


def _resolve_engine_name(picked: str) -> str:
    """Translate a library/UI name to the engine's actual emitted name."""
    if not picked:
        return picked
    return LIBRARY_TO_ENGINE.get(picked.lower().strip(), picked)


def _verdict_from(stats: dict) -> str:
    pf = stats.get("profit_factor", 0)
    exp = stats.get("expectancy", 0)
    trades = stats.get("total_trades", 0) or 0
    if trades < 10:
        return "Insufficient trades"
    if pf >= 1.5 and exp > 0.5:
        return "Tradeable edge"
    if pf >= 1.1 and exp > 0:
        return "Marginal edge"
    return "No edge"


@router.post("/run", response_model=BacktestResult)
async def run_backtest(req: BacktestRequest) -> BacktestResult:
    from services.universe_sync import get_universe_symbols
    from services.backtest_service import run_pattern_backtest
    syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
    engine_name = _resolve_engine_name(req.pattern_name)
    t0 = time.perf_counter()
    result = await run_sync(
        run_pattern_backtest,
        syms, engine_name, req.period, req.rolling_window,
        req.step_size, req.min_confidence, req.max_holding_bars,
    )
    raw = result.as_dict() if hasattr(result, "as_dict") else (result or {})
    trades: list[TradeRow] = []
    for t in (raw.get("trades") or []):
        try:
            trades.append(TradeRow(
                symbol=t.get("symbol", ""),
                entry_date=str(t.get("entry_date", "")),
                exit_date=str(t.get("exit_date", "")),
                entry_price=float(t.get("entry_price", 0)),
                exit_price=float(t.get("exit_price", 0)),
                return_pct=float(t.get("return_pct", 0)),
                bars_held=int(t.get("holding_days") or t.get("bars_held") or 0),
                exit_reason=str(t.get("exit_reason", "")),
            ))
        except Exception:
            continue
    return BacktestResult(
        request=req,
        win_rate=float(raw.get("win_rate", 0)),
        avg_return=float(raw.get("avg_return_pct") or raw.get("avg_return") or 0),
        expectancy=float(raw.get("expectancy", 0)),
        profit_factor=float(raw.get("profit_factor", 0)),
        max_drawdown=float(raw.get("max_drawdown_pct") or raw.get("max_drawdown") or 0),
        avg_holding_days=float(raw.get("avg_holding_days", 0)),
        avg_winner=float(raw.get("avg_winner_pct") or raw.get("avg_winner") or 0),
        avg_loser=float(raw.get("avg_loser_pct") or raw.get("avg_loser") or 0),
        best_winner=float(raw.get("max_winner_pct") or raw.get("best_winner") or 0),
        worst_loser=float(raw.get("max_loser_pct") or raw.get("worst_loser") or 0),
        total_trades=int(raw.get("total_trades", len(trades))),
        equity_curve=list(raw.get("equity_curve", [])),
        return_distribution=[t.return_pct for t in trades],
        trades=trades,
        verdict=_verdict_from({**raw, "total_trades": int(raw.get("total_trades", len(trades)))}),
        audit_log=(
            ([f"Resolved pattern: '{req.pattern_name}' -> '{engine_name}'"] if engine_name != req.pattern_name else [])
            + list(raw.get("audit") or raw.get("audit_log") or [])
        ),
        duration_ms=(time.perf_counter() - t0) * 1000,
    )


def _to_trade_rows(raw_trades: list[dict]) -> list[TradeRow]:
    out: list[TradeRow] = []
    for t in raw_trades:
        try:
            out.append(TradeRow(
                symbol=t.get("symbol", ""),
                entry_date=str(t.get("entry_date", "")),
                exit_date=str(t.get("exit_date", "")),
                entry_price=float(t.get("entry_price", 0)),
                exit_price=float(t.get("exit_price", 0)),
                return_pct=float(t.get("return_pct", 0)),
                bars_held=int(t.get("holding_days") or t.get("bars_held") or 0),
                exit_reason=str(t.get("exit_reason", "")),
            ))
        except Exception:
            continue
    return out


def _build_backtest_result(req: BacktestRequest, raw: dict, engine_name: str, t0: float) -> BacktestResult:
    trades = _to_trade_rows(raw.get("trades") or [])
    return BacktestResult(
        request=req,
        win_rate=float(raw.get("win_rate", 0)),
        avg_return=float(raw.get("avg_return_pct") or raw.get("avg_return") or 0),
        expectancy=float(raw.get("expectancy", 0)),
        profit_factor=float(raw.get("profit_factor", 0)),
        max_drawdown=float(raw.get("max_drawdown_pct") or raw.get("max_drawdown") or 0),
        avg_holding_days=float(raw.get("avg_holding_days", 0)),
        avg_winner=float(raw.get("avg_winner_pct") or raw.get("avg_winner") or 0),
        avg_loser=float(raw.get("avg_loser_pct") or raw.get("avg_loser") or 0),
        best_winner=float(raw.get("max_winner_pct") or raw.get("best_winner") or 0),
        worst_loser=float(raw.get("max_loser_pct") or raw.get("worst_loser") or 0),
        total_trades=int(raw.get("total_trades", len(trades))),
        equity_curve=list(raw.get("equity_curve", [])),
        return_distribution=[t.return_pct for t in trades],
        trades=trades,
        verdict=_verdict_from({**raw, "total_trades": int(raw.get("total_trades", len(trades)))}),
        audit_log=(
            ([f"Resolved pattern: '{req.pattern_name}' -> '{engine_name}'"] if engine_name != req.pattern_name else [])
            + list(raw.get("audit") or raw.get("audit_log") or [])
        ),
        duration_ms=(time.perf_counter() - t0) * 1000,
    )


@router.post("/run/stream")
async def run_backtest_stream(req: BacktestRequest):
    """Streaming backtest with live progress (SSE).

    The underlying `run_pattern_backtest` accepts a sync `progress_cb(done, total, sym)`.
    We bridge it to an asyncio.Queue so the SSE generator can yield progress events
    as the backtest threads complete each symbol.
    """
    from services.universe_sync import get_universe_symbols
    from services.backtest_service import run_pattern_backtest

    async def event_gen():
        def sse(p): return f"data: {json.dumps(p, default=str)}\n\n"

        t0 = time.perf_counter()
        engine_name = _resolve_engine_name(req.pattern_name)
        syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
        total = len(syms)
        yield sse({"type": "started", "total": total, "universe": req.universe, "pattern": engine_name})

        if total == 0:
            yield sse({"type": "result", **_build_backtest_result(req, {}, engine_name, t0).model_dump()})
            yield sse({"type": "done"}); return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def progress_cb(done: int, total_: int, sym: str):
            # Called from worker threads — bounce onto the event loop
            try:
                loop.call_soon_threadsafe(queue.put_nowait, ("progress", done, total_, sym))
            except RuntimeError:
                pass

        async def runner():
            res = await run_sync(
                run_pattern_backtest,
                syms, engine_name, req.period, req.rolling_window,
                req.step_size, req.min_confidence, req.max_holding_bars,
                6, progress_cb,
            )
            await queue.put(("result", res))

        run_task = asyncio.create_task(runner())
        last_emit = 0.0
        try:
            while True:
                msg = await queue.get()
                kind = msg[0]
                if kind == "progress":
                    _, done, tot, sym = msg
                    now = time.perf_counter()
                    if done == tot or now - last_emit > 0.5:
                        last_emit = now
                        yield sse({"type": "progress", "done": done, "total": tot, "current": sym, "elapsed_ms": (now - t0) * 1000})
                elif kind == "result":
                    raw_obj = msg[1]
                    raw = raw_obj.as_dict() if hasattr(raw_obj, "as_dict") else (raw_obj or {})
                    result = _build_backtest_result(req, raw, engine_name, t0)
                    yield sse({"type": "result", **result.model_dump()})
                    yield sse({"type": "done"})
                    return
        finally:
            run_task.cancel()

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })
