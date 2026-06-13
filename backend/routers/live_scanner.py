"""
Live scanner router — /api/live-scanner/*

Scans all F&O symbols across 5m / 15m / 1h / 1d using Yahoo Finance REST API.
Provides SSE streaming (/scan/stream) so the frontend shows real per-symbol progress,
matching the behaviour of the equity scanner.

Endpoints:
  GET /api/live-scanner/scan           — plain JSON (used for backward-compat)
  GET /api/live-scanner/scan/stream    — SSE streaming with per-symbol progress
  GET /api/live-scanner/chart-data     — OHLCV for mini charts
  GET /api/live-scanner/health
  GET /api/live-scanner/universe
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from services.intraday_data import (
    fetch_symbol_all_tfs,
    get_daily,
    get_nse_stocks,
    UNIVERSE_PRESETS,
    _ALL_INDICES,
    INTRADAY_TFS,
)
from services.confluence_scorer import add_indicators, score as confluence_score
from services.option_advisor import build_plan, OptionPlan

router = APIRouter(prefix="/api/live-scanner", tags=["live-scanner"])
log = logging.getLogger(__name__)


def _sf(v: Any, default: float = 0.0, decimals: int = 2) -> float:
    """Safe float — converts v to a JSON-serialisable float, replacing NaN/Inf."""
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else round(f, decimals)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol worker
# ─────────────────────────────────────────────────────────────────────────────

def _process_symbol(symbol: str, threshold: int) -> list[tuple]:
    """
    Fetch all available timeframes for symbol, score confluence.
    Returns list of (ConfluenceResult, timeframe) tuples above threshold.
    """
    qualifying: list[tuple] = []
    try:
        tf_data = fetch_symbol_all_tfs(symbol)
    except Exception as exc:
        log.warning("Fetch failed %s: %s", symbol, exc)
        return qualifying

    for tf, df in tf_data.items():
        if len(df) < 20:
            continue
        try:
            df_ind = add_indicators(df)
            result = confluence_score(symbol, df_ind)
            if result and result.total >= threshold:
                qualifying.append((result, tf))
        except Exception as exc:
            log.debug("Score error %s/%s: %s", symbol, tf, exc)

    if qualifying:
        log.info("  %s: %d setup(s) → TFs %s",
                 symbol, len(qualifying), [t for _, t in qualifying])
    return qualifying


# ─────────────────────────────────────────────────────────────────────────────
# Serialisers
# ─────────────────────────────────────────────────────────────────────────────

def _plan_dict(plan: OptionPlan) -> dict[str, Any]:
    return {
        "action":        plan.action,
        "option_type":   plan.option_type,
        "strike":        int(plan.strike),
        "expiry":        plan.expiry,
        "entry_spot":    _sf(plan.entry_spot),
        "entry_premium": _sf(plan.entry_premium),
        "sl_spot":       _sf(plan.sl_spot),
        "sl_premium":    _sf(plan.sl_premium),
        "t1_spot":       _sf(plan.t1_spot),
        "t2_spot":       _sf(plan.t2_spot),
        "t1_premium":    _sf(plan.t1_premium),
        "t2_premium":    _sf(plan.t2_premium),
        "rr":            _sf(plan.rr),
        "exit_rule":     plan.exit_rule,
        "lot_size":      int(plan.lot_size),
        "iv_note":       plan.iv_note or "",
        "liquidity_ok":  bool(plan.liquidity_ok),
        "raw_risk_pts":  _sf(plan.raw_risk_pts),
    }


def _to_card(result, timeframe: str, plan, hit_rate, sample_size,
             source: str) -> dict[str, Any]:
    backtest: dict[str, Any] | None = None
    if hit_rate is not None:
        backtest = {"hit_rate": _sf(hit_rate), "sample_size": int(sample_size)}
    elif sample_size > 0:
        backtest = {"hit_rate": None, "sample_size": int(sample_size),
                    "note": "Low sample — unproven"}
    return {
        "symbol":           result.symbol,
        "timeframe":        timeframe,
        "source":           source,
        "direction":        result.direction,
        "confluence_score": int(result.total),
        "score_breakdown": {
            "trend":    int(result.trend_score),
            "momentum": int(result.momentum_score),
            "volume":   int(result.volume_score),
            "candle":   int(result.candle_score),
        },
        "pattern":       result.pattern.name,
        "trigger_price": _sf(result.spot_price),
        "atr":           _sf(result.atr),
        "rel_vol":       _sf(result.rel_vol),
        "reasons":       list(result.reasons),
        "plan":          _plan_dict(plan) if plan else None,
        "backtest":      backtest,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backtest
# ─────────────────────────────────────────────────────────────────────────────

def _backtest_with_df(
    daily_df,
    pattern_name: str,
    direction: str,
) -> tuple[float | None, int]:
    """Run backtest against a pre-loaded (and already indicator-enriched) daily DataFrame."""
    if pattern_name == "None" or daily_df is None or daily_df.empty or len(daily_df) < 30:
        return None, 0
    try:
        from services.pattern_detector import detect
        hits = total = 0
        for i in range(2, len(daily_df) - 6):
            sig = detect(daily_df, i)
            if sig.name != pattern_name or sig.direction != direction:
                continue
            entry = float(daily_df.iloc[i]["close"])
            atr   = float(daily_df["atr"].iloc[i]) if "atr" in daily_df.columns else entry * 0.005
            risk  = max(atr * 1.5, entry * 0.003)
            total += 1
            first_hit = next(
                (j for j in range(i + 1, i + 6)
                 if (direction == "bullish" and float(daily_df.iloc[j]["high"]) >= entry + 1.5 * risk)
                 or (direction == "bearish" and float(daily_df.iloc[j]["low"])  <= entry - 1.5 * risk)),
                None)
            first_stop = next(
                (j for j in range(i + 1, i + 6)
                 if (direction == "bullish" and float(daily_df.iloc[j]["low"])  <= entry - risk)
                 or (direction == "bearish" and float(daily_df.iloc[j]["high"]) >= entry + risk)),
                None)
            if first_hit is not None and (first_stop is None or first_hit <= first_stop):
                hits += 1
        return (round(hits / total, 2), total) if total >= 5 else (None, total)
    except Exception as exc:
        log.debug("Backtest error %s: %s", pattern_name, exc)
        return None, 0


# ─────────────────────────────────────────────────────────────────────────────
# Scan helpers  (each does one thing — keeps run_scan under complexity limit)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_symbols(universe: str) -> list[str]:
    """
    Two universes only:
      'indices' — 4 index derivatives (NIFTY/BANKNIFTY/FINNIFTY/SENSEX)
      'stocks'  — live NSE F&O eligible equities (fetched from NSE; static fallback)
    """
    if universe == "stocks":
        return get_nse_stocks()
    return UNIVERSE_PRESETS.get(universe, UNIVERSE_PRESETS["indices"])


async def _scatter_workers(
    symbols: list[str],
    threshold: int,
) -> tuple[list[tuple], set[str]]:
    """
    Process all symbols concurrently with a Semaphore-bounded pool.
    Uses asyncio.to_thread (Python 3.9+) so no manual executor management.
    Semaphore(4) limits simultaneous Yahoo Finance connections.
    """
    sem = asyncio.Semaphore(4)

    async def _bounded(sym: str):
        async with sem:
            return sym, await asyncio.to_thread(_process_symbol, sym, threshold)

    outcomes = await asyncio.gather(
        *[_bounded(sym) for sym in symbols],
        return_exceptions=True,
    )

    all_qualifying: list[tuple] = []
    processed: set[str] = set()
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            log.warning("Worker exception: %s", outcome)
            continue
        sym, results = outcome
        if results:
            processed.add(sym)
        all_qualifying.extend(results)
    return all_qualifying, processed


def _fetch_option_chain(sym: str) -> tuple[list, str]:
    """
    Fetch option chain for one symbol; returns (rows_for_plan, nearest_expiry).

    BUG FIX: get_option_chain() returns (DataFrame, meta_dict), NOT a dict.
    Previous code called .get("rows") on the tuple → AttributeError → caught → empty list.
    Every option plan was running without real chain data.

    rows_for_plan format (matches what option_advisor._get_premium expects):
      [{"strikePrice": K, "CE": {"lastPrice": ltp, "openInterest": oi, ...}, "PE": {...}}, ...]
    """
    try:
        from services.fno_data_service import get_option_chain, get_synthetic_option_chain
        import math

        # Unpack the (DataFrame, meta) tuple correctly
        df, meta = get_option_chain(sym)

        if df is None or df.empty:
            df, meta = get_synthetic_option_chain(sym)

        if df is None or df.empty:
            return [], ""

        dates  = meta.get("expiry_dates", [])
        expiry = dates[0] if dates else ""

        # Filter to nearest expiry to reduce noise
        if expiry:
            df_near = df[df["expiry"] == expiry]
            if df_near.empty:
                df_near = df
        else:
            df_near = df

        # Convert flat DataFrame columns → nested dict format for option_advisor
        rows: list[dict] = []
        for _, row in df_near.iterrows():
            def safe(v):
                try:
                    f = float(v)
                    return 0.0 if (math.isnan(f) or math.isinf(f)) else f
                except Exception:
                    return 0.0

            rows.append({
                "strikePrice": row.get("strike", 0),
                "expiryDate":  row.get("expiry", ""),
                "CE": {
                    "lastPrice":         safe(row.get("CE_ltp",  0)),
                    "openInterest":      safe(row.get("CE_oi",   0)),
                    "impliedVolatility": safe(row.get("CE_iv",   0)),
                    "totalTradedVolume": safe(row.get("CE_vol",  0)),
                },
                "PE": {
                    "lastPrice":         safe(row.get("PE_ltp",  0)),
                    "openInterest":      safe(row.get("PE_oi",   0)),
                    "impliedVolatility": safe(row.get("PE_iv",   0)),
                    "totalTradedVolume": safe(row.get("PE_vol",  0)),
                },
            })

        return rows, expiry

    except Exception as exc:
        log.warning("_fetch_option_chain failed for %s: %s", sym, exc)
        return [], ""


def _enrich_cards(qualifying: list[tuple]) -> list[dict]:
    """
    Add option plan + backtest to each qualifying setup.
    Caches option chain AND daily data per symbol so a symbol appearing in
    multiple timeframes only triggers one fetch each.
    """
    cards: list[dict] = []
    chain_cache: dict[str, tuple[list, str]] = {}
    daily_cache: dict[str, Any] = {}   # symbol → indicator-enriched daily DataFrame

    for result, timeframe in qualifying:
        sym    = result.symbol
        source = "NSE (daily)" if timeframe == "1d" else "Yahoo Finance (intraday)"

        # Option chain (one NSE call per symbol)
        if sym not in chain_cache:
            chain_cache[sym] = _fetch_option_chain(sym)
        opt_chain, expiry = chain_cache[sym]
        plan = build_plan(result, option_chain=opt_chain, nearest_expiry=expiry)

        # Backtest (one YF daily fetch + indicator computation per symbol)
        hit_rate, n = None, 0
        if result.pattern.name != "None":
            if sym not in daily_cache:
                try:
                    df = get_daily(sym, period="6mo")
                    daily_cache[sym] = add_indicators(df) if not df.empty else None
                except Exception:
                    daily_cache[sym] = None
            hit_rate, n = _backtest_with_df(
                daily_cache.get(sym), result.pattern.name, result.direction
            )

        cards.append(_to_card(result, timeframe, plan, hit_rate, n, source))
    return cards


def _build_summary(
    cards: list[dict],
    total_symbols: int,
    unique_symbols: int,
) -> dict:
    by_dir: dict[str, int] = {"bullish": 0, "bearish": 0, "range": 0}
    by_tf:  dict[str, int] = {"5m": 0, "15m": 0, "1h": 0, "1d": 0}
    strong = 0
    for c in cards:
        by_dir[c["direction"]] = by_dir.get(c["direction"], 0) + 1
        by_tf[c["timeframe"]]  = by_tf.get(c["timeframe"], 0) + 1
        if c["confluence_score"] >= 80:
            strong += 1
    n_daily = by_tf["1d"]
    return {
        "total_symbols":   total_symbols,
        "unique_setups":   unique_symbols,
        "total_setups":    len(cards),
        "daily_setups":    n_daily,
        "intraday_setups": len(cards) - n_daily,
        "bullish":         by_dir["bullish"],
        "bearish":         by_dir["bearish"],
        "range":           by_dir["range"],
        "strong_80plus":   strong,
        "by_timeframe":    by_tf,
    }


@router.get("/scan")
async def run_scan(
    universe:  Annotated[str, Query()] = "top30",
    threshold: Annotated[int, Query()] = 65,
):
    """
    Scan all symbols across 5m / 15m / 1h / 1d.
    Data source: Yahoo Finance REST API (fresh session per request).
    Architecture: one symbol at a time, all TFs sequentially, max 4 concurrent workers.
    """
    symbols = _resolve_symbols(universe)
    log.info("Scan start: %d symbols | threshold=%d", len(symbols), threshold)

    qualifying, processed = await _scatter_workers(symbols, threshold)
    log.info("Raw qualifying: %d setups", len(qualifying))

    qualifying.sort(key=lambda x: x[0].total, reverse=True)

    # _enrich_cards makes blocking HTTP calls (NSE option chain + YF backtest)
    # Run in a thread so it does NOT block the async event loop
    cards = await asyncio.to_thread(_enrich_cards, qualifying)

    payload = {
        "setups":    cards,
        "summary":   _build_summary(cards, len(symbols), len(processed)),
        "universe":  universe,
        "threshold": threshold,
        "timeframes": ["1d"] + INTRADAY_TFS,
        "data_sources": {
            "all": "Yahoo Finance REST API (fresh session per request) — all symbols, all timeframes",
        },
        "disclaimer": (
            "Not financial advice. Algorithmically identified setups, not predictions. "
            "Every trade carries risk. Use defined-risk positions."
        ),
    }
    # jsonable_encoder converts any remaining numpy/nan/inf to JSON-safe types
    return JSONResponse(jsonable_encoder(payload))


@router.get("/scan/stream")
async def scan_stream(
    universe:  Annotated[str, Query()] = "top30",
    threshold: Annotated[int, Query()] = 65,
):
    """
    SSE streaming scan — yields per-symbol progress events so the frontend
    shows a real-time symbol counter (like the equity scanner).

    Event types:
      start      — {"type":"start","total":N,"universe":"top30"}
      progress   — {"type":"progress","symbol":"NIFTY","found":3,"done":5,"total":30}
      enriching  — {"type":"enriching","setups":N}
      result     — {"type":"result", ...full scan payload...}
      [DONE]     — literal string, signals stream end
    """
    symbols = _resolve_symbols(universe)
    log.info("SSE scan: %d symbols threshold=%d", len(symbols), threshold)

    async def generate():
        def _sse(obj) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        yield _sse({"type": "start", "total": len(symbols), "universe": universe})

        queue: asyncio.Queue = asyncio.Queue()
        sem   = asyncio.Semaphore(6)

        async def process_sym(sym: str) -> None:
            async with sem:
                results = await asyncio.to_thread(_process_symbol, sym, threshold)
                await queue.put((sym, results))

        tasks = [asyncio.create_task(process_sym(s)) for s in symbols]

        all_qualifying: list[tuple] = []
        processed_syms: set[str]   = set()
        completed = 0          # counts EVERY symbol processed (not just ones with setups)

        for _ in symbols:
            sym, results = await queue.get()
            completed += 1
            if results:
                processed_syms.add(sym)
            all_qualifying.extend(results)
            yield _sse({
                "type":          "progress",
                "symbol":        sym,
                "found":         len(results),
                "done":          completed,           # all scanned symbols
                "total":         len(symbols),
                "setups_so_far": len(all_qualifying),
            })

        await asyncio.gather(*tasks, return_exceptions=True)

        yield _sse({"type": "enriching", "setups": len(all_qualifying)})

        all_qualifying.sort(key=lambda x: x[0].total, reverse=True)
        cards   = await asyncio.to_thread(_enrich_cards, all_qualifying)
        summary = _build_summary(cards, len(symbols), len(processed_syms))

        payload = {
            "type":       "result",
            "setups":     cards,
            "summary":    summary,
            "universe":   universe,
            "threshold":  threshold,
            "timeframes": ["1d"] + INTRADAY_TFS,
            "data_sources": {"all": "Yahoo Finance REST API"},
            "disclaimer": (
                "Not financial advice. Algorithmically identified setups, not predictions. "
                "Every trade carries risk. Use defined-risk positions."
            ),
        }
        yield _sse(jsonable_encoder(payload))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/universe")
async def get_universe():
    presets = {k: {"symbols": v, "count": len(v)} for k, v in UNIVERSE_PRESETS.items()}
    presets["dynamic"] = {"symbols": [], "count": "live NSE (~180)"}
    return {"universes": presets}


@router.get("/health")
async def health():
    """Lightweight health check — frontend polls this before showing the scan button."""
    return {"status": "ok", "scanner": "live"}


@router.get("/chart-data")
async def get_chart_data(
    symbol:   Annotated[str, Query()],
    interval: Annotated[str, Query()] = "1d",
    bars:     Annotated[int, Query()] = 80,
):
    """
    OHLCV candles for the mini chart in the expanded setup row.
    Returns time as unix seconds (for intraday) or ISO date string (for 1d).
    """
    import pandas as pd
    from services.intraday_data import get_ohlcv

    df = await asyncio.to_thread(get_ohlcv, symbol, interval)
    if df.empty:
        return JSONResponse({"candles": [], "symbol": symbol, "interval": interval})

    df = df.tail(max(1, bars))
    candles = []
    for ts, row in df.iterrows():
        t = pd.Timestamp(ts)
        # lightweight-charts needs "YYYY-MM-DD" for daily, unix seconds for intraday
        time_val: str | int = (
            t.strftime("%Y-%m-%d") if interval == "1d"
            else int(t.timestamp())
        )
        candles.append({
            "time":  time_val,
            "open":  _sf(row["open"]),
            "high":  _sf(row["high"]),
            "low":   _sf(row["low"]),
            "close": _sf(row["close"]),
        })
    return JSONResponse({"candles": candles, "symbol": symbol, "interval": interval})
