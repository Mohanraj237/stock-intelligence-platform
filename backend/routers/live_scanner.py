"""
Live scanner router — /api/live-scanner/*

Scans all F&O symbols across 5m / 15m / 30m / 1h / 4h / 1d / 1wk / 1mo using Yahoo Finance REST API.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field as dataclass_field
from typing import Annotated, Any

# Isolated thread pool — F&O scanner never competes with the equity scanner
# or with the default pool used by other API endpoints.
_SCAN_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="fno-scan")

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from services.intraday_data import (
    fetch_symbol_all_tfs,
    get_ohlcv,
    get_daily,
    get_nse_stocks,
    resample_to_4h,
    exchange_tz,
    cache_stats,
    reset_cache_stats,
    UNIVERSE_PRESETS,
    _ALL_INDICES,
    _ALL_TIMEFRAMES,
)
from services.confluence_scorer import (
    add_indicators, score as confluence_score, MIN_BARS_TO_SCORE, ScoringWeights,
)
from services.pattern_registry import run_detectors, PatternResult
from services.option_advisor import build_plan_with_reason, OptionPlan
from services.breakout_service import classify_breakout
from services.scan_support import (
    ScanInputError, ScanDiagnostics, apply_pattern_filters, backtest_pattern,
    parse_pattern_mode, parse_pattern_names, parse_timeframes, resolve_universe,
)
from backend.deps import run_sync

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

async def _run(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) in the F&O scanner's dedicated thread pool."""
    import functools
    if kwargs:
        fn = functools.partial(fn, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_SCAN_POOL, fn, *args)


@dataclass
class SymbolOutcome:
    """Result of scanning one symbol — including *why* nothing came back."""
    symbol: str
    qualifying: list[tuple] = dataclass_field(default_factory=list)  # (result, tf, indicator df)
    status: str = "ok"      # ok | no_data | insufficient_bars | error
    reason: str = ""


async def _process_symbol_async(
    symbol: str,
    threshold: int,
    timeframes: list[str] | None = None,
    enabled_pattern_ids: set[str] | None = None,
    pattern_mode: str = "filter",
    weights: ScoringWeights | None = None,
) -> SymbolOutcome:
    """
    Fetch only the requested timeframes concurrently, then score each concurrently.
    timeframes: subset of _ALL_TIMEFRAMES to actually fetch — unselected TFs are
    never requested from Yahoo at all. Defaults to all 8 when omitted.
    "4h" has no native Yahoo interval — it's derived from "1h" bars, resampled on
    session-aligned buckets. If "4h" is requested but "1h" isn't, "1h" is still
    fetched internally (as a dependency) but dropped afterwards.
    Uses the isolated _SCAN_POOL so this scanner never starves the equity scanner
    or default-pool endpoints (paper trades, health, etc.).
    """
    want_tfs = timeframes if timeframes else _ALL_TIMEFRAMES
    need_1h_helper = "4h" in want_tfs and "1h" not in want_tfs
    tz = exchange_tz(symbol)

    async def _fetch_tf(tf: str) -> tuple[str, "pd.DataFrame"]:
        df = await _run(get_ohlcv, symbol, tf)
        return tf, df

    async def _score_tf(tf: str, df: "pd.DataFrame"):
        try:
            df_ind = await _run(add_indicators, df, timeframe=tf, session_tz=tz)
            result = await _run(
                confluence_score, symbol, df_ind,
                timeframe=tf, enabled_pattern_ids=enabled_pattern_ids,
                pattern_mode=pattern_mode, weights=weights,
            )
            return (result, tf, df_ind) if result and result.total >= threshold else None
        except Exception as exc:
            log.warning("Score error %s/%s: %s", symbol, tf, exc)
            return None

    fetch_tfs = [tf for tf in want_tfs if tf != "4h"]
    if need_1h_helper:
        fetch_tfs.append("1h")
    try:
        raw = await asyncio.gather(*[_fetch_tf(tf) for tf in fetch_tfs], return_exceptions=True)
    except Exception as exc:
        log.warning("Fetch failed %s: %s", symbol, exc)
        return SymbolOutcome(symbol, status="error", reason=f"fetch failed: {exc}")

    failures = [r for r in raw if isinstance(r, Exception)]
    tf_data = {tf: df for r in raw if not isinstance(r, Exception)
               for tf, df in [r] if not df.empty}

    if "4h" in want_tfs and "1h" in tf_data:
        df_4h = await _run(resample_to_4h, tf_data["1h"])
        if not df_4h.empty:
            tf_data["4h"] = df_4h
    if need_1h_helper:
        tf_data.pop("1h", None)

    if not tf_data:
        if failures:
            return SymbolOutcome(symbol, status="error",
                                 reason=f"fetch failed: {failures[0]}")
        return SymbolOutcome(symbol, status="no_data",
                             reason="no data returned for any requested timeframe")

    scorable = {tf: df for tf, df in tf_data.items() if len(df) >= MIN_BARS_TO_SCORE}
    if not scorable:
        longest = max(len(df) for df in tf_data.values())
        return SymbolOutcome(
            symbol, status="insufficient_bars",
            reason=f"longest history is {longest} bars, need {MIN_BARS_TO_SCORE}",
        )

    scored = await asyncio.gather(*[_score_tf(tf, df) for tf, df in scorable.items()])
    qualifying = [r for r in scored if r is not None]

    if qualifying:
        log.info("  %s: %d setup(s) → TFs %s",
                 symbol, len(qualifying), [t for _, t, _ in qualifying])
    return SymbolOutcome(symbol, qualifying=qualifying, status="ok")


# ─────────────────────────────────────────────────────────────────────────────
# Serialisers
# ─────────────────────────────────────────────────────────────────────────────

def _get_breakout_state(daily_df, direction: str) -> dict:
    """Classify breakout state using daily data. Renames lowercase cols for breakout_service."""
    if daily_df is None or daily_df.empty:
        return {"state": "NO_BREAKOUT", "label": "—", "color": "#94a3b8"}
    try:
        df_up = daily_df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        dir_arg = "long" if direction == "bullish" else ("short" if direction == "bearish" else "auto")
        return classify_breakout(df_up, direction=dir_arg)
    except Exception as exc:
        log.debug("classify_breakout failed: %s", exc)
        return {"state": "NO_BREAKOUT", "label": "—", "color": "#94a3b8"}


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
        "rr_basis":      plan.rr_basis,
        "exit_rule":     plan.exit_rule,
        "lot_size":      int(plan.lot_size),
        "lot_size_estimated": bool(plan.lot_size_estimated),
        "delta_assumption":   _sf(plan.delta_assumption),
        "iv_rank":       None if plan.iv_rank is None else _sf(plan.iv_rank, decimals=1),
        "iv_note":       plan.iv_note or "",
        "liquidity_ok":  bool(plan.liquidity_ok),
        "raw_risk_pts":  _sf(plan.raw_risk_pts),
    }


def _to_card(result, timeframe: str, plan, backtest: dict | None,
             source: str, breakout_info: dict | None = None,
             plan_reason: str = "") -> dict[str, Any]:
    bi = breakout_info or {}
    card = {
        "symbol":           result.symbol,
        "timeframe":        timeframe,
        "source":           source,
        "direction":        result.direction,
        "confluence_score": int(result.total),
        "score_breakdown": {
            "trend":      int(result.trend_score),
            "momentum":   int(result.momentum_score),
            "volume":     int(result.volume_score),
            "candle":     int(result.candle_score),
            "structural": int(result.structural_score),
        },
        "pattern":          result.pattern.name,
        "trigger_price":    _sf(result.spot_price),
        "atr":              _sf(result.atr),
        "rel_vol":          _sf(result.rel_vol),
        "reasons":          list(result.reasons),
        "plan":             _plan_dict(plan) if plan else None,
        "plan_unavailable_reason": "" if plan else plan_reason,
        "backtest":         backtest,
        "patterns":         list(result.patterns),
        "breakout_state":   bi.get("state",  "NO_BREAKOUT"),
        "breakout_label":   bi.get("label",  "—"),
        "breakout_color":   bi.get("color",  "#94a3b8"),
        "structural_score": int(result.structural_score),
        "volume_available": bool(result.volume_available),
        "bars_used":        int(result.bars_used),
    }
    if result.lookback_note:
        card["lookback_note"] = result.lookback_note
    return card


# ─────────────────────────────────────────────────────────────────────────────
# Scan helpers  (each does one thing — keeps run_scan under complexity limit)
# ─────────────────────────────────────────────────────────────────────────────

# The only universes this scanner can resolve. "top30" was the documented
# default but was never registered, so every default scan silently fell back to
# `indices` (6 symbols) instead of scanning F&O stocks.
FNO_UNIVERSE_KEYS: set[str] = {"indices", "stocks", "dynamic"}
DEFAULT_FNO_UNIVERSE = "stocks"


def _resolve_symbols(universe: str) -> list[str]:
    """
    Three universes:
      'indices' — index derivatives (NIFTY/BANKNIFTY/FINNIFTY/SENSEX/…)
      'stocks'  — live NSE F&O eligible equities (fetched from NSE; static fallback)
      'dynamic' — indices + stocks
    Anything else raises ScanInputError → HTTP 400.
    """
    resolve_universe(universe, FNO_UNIVERSE_KEYS)
    if universe == "stocks":
        return get_nse_stocks()
    if universe == "dynamic":
        return list(_ALL_INDICES) + get_nse_stocks()
    return UNIVERSE_PRESETS["indices"]


async def _scatter_workers(
    symbols: list[str],
    threshold: int,
    timeframes: list[str] | None = None,
    enabled_pattern_ids: set[str] | None = None,
    pattern_mode: str = "filter",
    weights: ScoringWeights | None = None,
) -> tuple[list[tuple], set[str], ScanDiagnostics]:
    """
    Process all symbols concurrently with a Semaphore-bounded pool.
    Each symbol fetches only the requested TFs in parallel via _process_symbol_async.
    """
    sem = asyncio.Semaphore(8)

    async def _bounded(sym: str) -> SymbolOutcome:
        async with sem:
            try:
                return await _process_symbol_async(
                    sym, threshold, timeframes, enabled_pattern_ids, pattern_mode, weights)
            except Exception as exc:
                return SymbolOutcome(sym, status="error", reason=str(exc))

    outcomes = await asyncio.gather(
        *[_bounded(sym) for sym in symbols],
        return_exceptions=True,
    )

    all_qualifying: list[tuple] = []
    processed: set[str] = set()
    diag = ScanDiagnostics()
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            log.warning("Worker exception: %s", outcome)
            diag.add_error("<unknown>", str(outcome))
            continue
        diag.record(outcome.symbol, outcome.status, outcome.reason)
        if outcome.qualifying:
            processed.add(outcome.symbol)
        all_qualifying.extend(outcome.qualifying)
    return all_qualifying, processed, diag


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


def _iv_rank_for(symbol: str) -> float | None:
    """
    IV rank (0-100) from the stored ATM-IV history. None when there is not
    enough history to define a range — the caller then declines to build a
    premium-sell plan *and says why*, instead of failing a gate against a
    hardcoded 30.0 that could never clear it.
    """
    try:
        from services.fno_data_service import get_iv_rank
        data = get_iv_rank(symbol)
        if not data.get("sufficient_history"):
            return None
        rank = data.get("iv_rank")
        return float(rank) if rank is not None else None
    except Exception as exc:
        log.debug("iv_rank lookup failed for %s: %s", symbol, exc)
        return None


def _enrich_cards(qualifying: list[tuple]) -> list[dict]:
    """
    Add option plan + backtest to each qualifying setup.
    Caches option chain, IV rank AND daily data per symbol so a symbol appearing
    in multiple timeframes only triggers one fetch each.
    """
    cards: list[dict] = []
    chain_cache: dict[str, tuple[list, str]] = {}
    iv_cache:    dict[str, float | None] = {}
    daily_cache: dict[str, Any] = {}   # symbol → indicator-enriched daily DataFrame

    for result, timeframe, tf_df in qualifying:
        sym = result.symbol
        if timeframe == "1d":
            source = "NSE (daily)"
        elif timeframe in ("1wk", "1mo"):
            source = "Yahoo Finance (positional)"
        else:
            source = "Yahoo Finance (intraday)"

        # Option chain (one NSE call per symbol)
        if sym not in chain_cache:
            chain_cache[sym] = _fetch_option_chain(sym)
        opt_chain, expiry = chain_cache[sym]

        if sym not in iv_cache:
            iv_cache[sym] = _iv_rank_for(sym)

        plan, plan_reason = build_plan_with_reason(
            result, option_chain=opt_chain, nearest_expiry=expiry,
            iv_rank=iv_cache[sym],
        )

        # Backtest runs on the card's OWN timeframe, not always on daily.
        backtest = backtest_pattern(tf_df, timeframe, result.pattern.name, result.direction)

        # Daily data drives the breakout badge only.
        if sym not in daily_cache:
            try:
                df = get_daily(sym, period="1y")
                daily_cache[sym] = add_indicators(df, timeframe="1d") if not df.empty else None
            except Exception:
                daily_cache[sym] = None

        breakout_info = _get_breakout_state(daily_cache.get(sym), result.direction)
        cards.append(_to_card(result, timeframe, plan, backtest, source,
                              breakout_info, plan_reason))
    return cards


def _build_summary(
    cards: list[dict],
    total_symbols: int,
    unique_symbols: int,
    diag: ScanDiagnostics,
    cache: dict,
) -> dict:
    by_dir: dict[str, int] = {"bullish": 0, "bearish": 0, "range": 0}
    by_tf:  dict[str, int] = {tf: 0 for tf in _ALL_TIMEFRAMES}
    strong = 0
    for c in cards:
        by_dir[c["direction"]] = by_dir.get(c["direction"], 0) + 1
        by_tf[c["timeframe"]]  = by_tf.get(c["timeframe"], 0) + 1
        if c["confluence_score"] >= 80:
            strong += 1
    n_positional = by_tf["1d"] + by_tf["1wk"] + by_tf["1mo"]
    return {
        "total_symbols":   total_symbols,
        "unique_setups":   unique_symbols,
        "total_setups":    len(cards),
        "daily_setups":    n_positional,
        "intraday_setups": len(cards) - n_positional,
        "bullish":         by_dir["bullish"],
        "bearish":         by_dir["bearish"],
        "range":           by_dir["range"],
        "strong_80plus":   strong,
        "by_timeframe":    by_tf,
        "cache_hit_rate":  cache.get("hit_rate", 0.0),
        **diag.as_dict(),
    }


@router.get("/scan")
async def run_scan(
    universe:          Annotated[str,   Query()] = DEFAULT_FNO_UNIVERSE,
    threshold:         Annotated[int | None, Query()] = None,
    patterns:          Annotated[str,   Query()] = "",
    min_pattern_conf:  Annotated[float, Query()] = 0.0,
    timeframes:        Annotated[str | None, Query()] = None,
    pattern_names:     Annotated[str,   Query()] = "",
    pattern_mode:      Annotated[str,   Query()] = "filter",
):
    """
    Scan all symbols across the requested timeframes (default: 5m/15m/30m/1h/4h/1d/1wk/1mo).
    timeframes: comma-separated subset to actually fetch/score — unselected TFs are
    never requested from Yahoo, cutting external API calls proportionally.
    pattern_names: comma-separated pattern ids or display names, matched by identity.
    pattern_mode: "filter" (default, hard post-filter, scores unchanged) or
      "shape" (legacy, selection lowers the reachable score).
    patterns: comma-separated family filter (post-hoc card filter).
    min_pattern_conf: 0.0-1.0, filter cards where any pattern meets this confidence.

    Invalid inputs return HTTP 400 rather than silently scanning something else.
    """
    try:
        universe = resolve_universe(universe, FNO_UNIVERSE_KEYS)
        symbols  = _resolve_symbols(universe)
        tf_list  = parse_timeframes(timeframes, _ALL_TIMEFRAMES)
        names    = parse_pattern_names(pattern_names)
        mode     = parse_pattern_mode(pattern_mode)
    except ScanInputError as exc:
        return JSONResponse(exc.as_dict(), status_code=400)

    from storage.file_store import get_scoring_config
    scoring_cfg = await run_sync(get_scoring_config)
    weights = ScoringWeights(
        trend=scoring_cfg["trend_weight"], momentum=scoring_cfg["momentum_weight"],
        volume=scoring_cfg["volume_weight"], candle=scoring_cfg["candle_weight"],
        structural=scoring_cfg["structural_weight"],
    )
    if threshold is None:
        threshold = scoring_cfg["default_threshold"]

    resolved_tfs = tf_list or _ALL_TIMEFRAMES
    log.info("Scan start: %d symbols | threshold=%d | tfs=%s | mode=%s",
             len(symbols), threshold, resolved_tfs, mode)

    reset_cache_stats()
    qualifying, processed, diag = await _scatter_workers(
        symbols, threshold, tf_list, names, mode, weights)
    log.info("Raw qualifying: %d setups", len(qualifying))

    qualifying.sort(key=lambda x: x[0].total, reverse=True)

    cards = await _run(_enrich_cards, qualifying)
    cards = apply_pattern_filters(
        cards, patterns or None, min_pattern_conf,
        names if mode == "filter" else None,
    )

    payload = {
        "setups":    cards,
        "summary":   _build_summary(cards, len(symbols), len(processed), diag, cache_stats()),
        "universe":  universe,
        "threshold": threshold,
        "timeframes": resolved_tfs,
        "pattern_mode": mode,
        "data_sources": {
            "all": "Yahoo Finance REST API (fresh session per request) — all symbols, all timeframes",
        },
        "disclaimer": (
            "Not financial advice. Algorithmically identified setups, not predictions. "
            "Every trade carries risk. Use defined-risk positions."
        ),
    }
    return JSONResponse(jsonable_encoder(payload))


@router.get("/scan/stream")
async def scan_stream(
    universe:         Annotated[str,   Query()] = DEFAULT_FNO_UNIVERSE,
    threshold:        Annotated[int | None, Query()] = None,
    patterns:         Annotated[str,   Query()] = "",
    min_pattern_conf: Annotated[float, Query()] = 0.0,
    timeframes:       Annotated[str | None, Query()] = None,
    pattern_names:    Annotated[str,   Query()] = "",
    pattern_mode:     Annotated[str,   Query()] = "filter",
):
    """
    SSE streaming scan — yields per-symbol progress events so the frontend
    shows a real-time symbol counter (like the equity scanner).

    See GET /scan for parameter semantics. Invalid inputs return HTTP 400
    before the stream starts.

    Event types:
      start      — {"type":"start","total":N,"universe":"stocks",
                    "timeframes":[…],"threshold":65,"pattern_mode":"filter"}
      progress   — {"type":"progress","symbol":"NIFTY","found":3,"status":"ok",…}
      enriching  — {"type":"enriching","setups":N}
      result     — {"type":"result", ...full scan payload...}
      [DONE]     — literal string, signals stream end
    """
    try:
        universe = resolve_universe(universe, FNO_UNIVERSE_KEYS)
        symbols  = _resolve_symbols(universe)
        tf_list  = parse_timeframes(timeframes, _ALL_TIMEFRAMES)
        names    = parse_pattern_names(pattern_names)
        mode     = parse_pattern_mode(pattern_mode)
    except ScanInputError as exc:
        return JSONResponse(exc.as_dict(), status_code=400)

    from storage.file_store import get_scoring_config
    scoring_cfg = await run_sync(get_scoring_config)
    weights = ScoringWeights(
        trend=scoring_cfg["trend_weight"], momentum=scoring_cfg["momentum_weight"],
        volume=scoring_cfg["volume_weight"], candle=scoring_cfg["candle_weight"],
        structural=scoring_cfg["structural_weight"],
    )
    if threshold is None:
        threshold = scoring_cfg["default_threshold"]

    resolved_tfs = tf_list or _ALL_TIMEFRAMES
    log.info("SSE scan: %d symbols threshold=%d tfs=%s mode=%s",
             len(symbols), threshold, resolved_tfs, mode)

    async def generate():
        def _sse(obj) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        # Echo what was *actually* resolved so the UI can show what it scanned.
        yield _sse({
            "type":         "start",
            "total":        len(symbols),
            "universe":     universe,
            "timeframes":   resolved_tfs,
            "threshold":    threshold,
            "pattern_mode": mode,
        })

        reset_cache_stats()

        queue: asyncio.Queue = asyncio.Queue()
        sem   = asyncio.Semaphore(12)

        async def process_sym(sym: str) -> None:
            async with sem:
                try:
                    outcome = await _process_symbol_async(
                        sym, threshold, tf_list, names, mode, weights)
                except Exception as exc:
                    outcome = SymbolOutcome(sym, status="error", reason=str(exc))
                await queue.put(outcome)

        tasks = [asyncio.create_task(process_sym(s)) for s in symbols]

        all_qualifying: list[tuple] = []
        processed_syms: set[str]   = set()
        diag = ScanDiagnostics()
        completed = 0          # counts EVERY symbol processed (not just ones with setups)

        for _ in symbols:
            outcome = await queue.get()
            completed += 1
            diag.record(outcome.symbol, outcome.status, outcome.reason)
            if outcome.qualifying:
                processed_syms.add(outcome.symbol)
            all_qualifying.extend(outcome.qualifying)
            yield _sse({
                "type":          "progress",
                "symbol":        outcome.symbol,
                "found":         len(outcome.qualifying),
                "status":        outcome.status,
                "done":          completed,           # all scanned symbols
                "total":         len(symbols),
                "setups_so_far": len(all_qualifying),
            })

        await asyncio.gather(*tasks, return_exceptions=True)

        yield _sse({"type": "enriching", "setups": len(all_qualifying)})

        all_qualifying.sort(key=lambda x: x[0].total, reverse=True)
        cards   = await _run(_enrich_cards, all_qualifying)
        cards   = apply_pattern_filters(
            cards, patterns or None, min_pattern_conf,
            names if mode == "filter" else None,
        )
        summary = _build_summary(cards, len(symbols), len(processed_syms),
                                 diag, cache_stats())

        payload = {
            "type":         "result",
            "setups":       cards,
            "summary":      summary,
            "universe":     universe,
            "threshold":    threshold,
            "timeframes":   resolved_tfs,
            "pattern_mode": mode,
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
    """Only the universes this scanner actually accepts — see FNO_UNIVERSE_KEYS."""
    indices = UNIVERSE_PRESETS["indices"]
    return {
        "universes": {
            "indices": {"symbols": indices, "count": len(indices)},
            "stocks":  {"symbols": [], "count": "live NSE F&O equities (~180)"},
            "dynamic": {"symbols": [], "count": "indices + live NSE F&O equities"},
        },
        "default": DEFAULT_FNO_UNIVERSE,
    }


@router.get("/health")
async def health():
    """Lightweight health check — frontend polls this before showing the scan button."""
    return {"status": "ok", "scanner": "live"}


@router.get("/patterns")
async def list_patterns():
    """
    Every pattern name any detector can emit, grouped by family, with
    directional variants nested under their parent. Selecting a parent selects
    its variants.
    """
    from services.pattern_registry import patterns_grouped_by_family
    return patterns_grouped_by_family()


@router.get("/chart-data")
async def get_chart_data(
    symbol:   Annotated[str, Query()],
    interval: Annotated[str, Query()] = "1d",
    bars:     Annotated[int, Query()] = 80,
):
    """
    OHLCV candles for the mini chart in the expanded setup row.
    Returns time as unix seconds (for intraday) or ISO date string (for 1d/1wk/1mo).
    """
    import pandas as pd
    from services.intraday_data import get_ohlcv

    if interval == "4h":
        # Yahoo has no native 4h interval — derive it from 1h bars.
        df_1h = await asyncio.to_thread(get_ohlcv, symbol, "1h")
        df = resample_to_4h(df_1h)
    else:
        df = await asyncio.to_thread(get_ohlcv, symbol, interval)
    if df.empty:
        return JSONResponse({"candles": [], "symbol": symbol, "interval": interval})

    df = df.tail(max(1, bars))
    candles = []
    for ts, row in df.iterrows():
        t = pd.Timestamp(ts)
        # lightweight-charts needs "YYYY-MM-DD" for daily/weekly/monthly, unix seconds for intraday
        time_val: str | int = (
            t.strftime("%Y-%m-%d") if interval in ("1d", "1wk", "1mo")
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
