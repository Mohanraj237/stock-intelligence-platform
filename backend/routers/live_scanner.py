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
    UNIVERSE_PRESETS,
    _ALL_INDICES,
    _ALL_TIMEFRAMES,
)
from services.confluence_scorer import add_indicators, score as confluence_score
from services.pattern_registry import run_detectors, PatternResult
from services.option_advisor import build_plan, OptionPlan
from services.breakout_service import classify_breakout

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


async def _process_symbol_async(
    symbol: str,
    threshold: int,
    timeframes: list[str] | None = None,
    enabled_pattern_names: set[str] | None = None,
) -> list[tuple]:
    """
    Fetch only the requested timeframes concurrently, then score each concurrently.
    timeframes: subset of _ALL_TIMEFRAMES to actually fetch — unselected TFs are
    never requested from Yahoo at all. Defaults to all 8 when omitted.
    "4h" has no native Yahoo interval — it's derived from "1h" bars. If "4h" is
    requested but "1h" isn't, "1h" is still fetched internally (as a dependency)
    but dropped afterwards rather than scored/returned.
    Uses the isolated _SCAN_POOL so this scanner never starves the equity scanner
    or default-pool endpoints (paper trades, health, etc.).
    """
    want_tfs = timeframes if timeframes else _ALL_TIMEFRAMES
    need_1h_helper = "4h" in want_tfs and "1h" not in want_tfs

    async def _fetch_tf(tf: str) -> tuple[str, "pd.DataFrame"]:
        df = await _run(get_ohlcv, symbol, tf)
        return tf, df

    async def _score_tf(tf: str, df: "pd.DataFrame"):
        if len(df) < 20:
            return None
        try:
            df_ind = await _run(add_indicators, df)
            result = await _run(
                confluence_score, symbol, df_ind,
                timeframe=tf, enabled_pattern_names=enabled_pattern_names,
            )
            return (result, tf) if result and result.total >= threshold else None
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
        return []

    tf_data = {tf: df for r in raw if not isinstance(r, Exception)
               for tf, df in [r] if not df.empty}

    if "4h" in want_tfs and "1h" in tf_data:
        df_4h = await _run(resample_to_4h, tf_data["1h"])
        if not df_4h.empty:
            tf_data["4h"] = df_4h
    if need_1h_helper:
        tf_data.pop("1h", None)

    scored = await asyncio.gather(*[_score_tf(tf, df) for tf, df in tf_data.items()])
    qualifying = [r for r in scored if r is not None]

    if qualifying:
        log.info("  %s: %d setup(s) → TFs %s",
                 symbol, len(qualifying), [t for _, t in qualifying])
    return qualifying


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
        "exit_rule":     plan.exit_rule,
        "lot_size":      int(plan.lot_size),
        "iv_note":       plan.iv_note or "",
        "liquidity_ok":  bool(plan.liquidity_ok),
        "raw_risk_pts":  _sf(plan.raw_risk_pts),
    }


def _to_card(result, timeframe: str, plan, hit_rate, sample_size,
             source: str, breakout_info: dict | None = None) -> dict[str, Any]:
    backtest: dict[str, Any] | None = None
    if hit_rate is not None:
        backtest = {"hit_rate": _sf(hit_rate), "sample_size": int(sample_size)}
    elif sample_size > 0:
        backtest = {"hit_rate": None, "sample_size": int(sample_size),
                    "note": "Low sample — unproven"}
    bi = breakout_info or {}
    return {
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
        "backtest":         backtest,
        "patterns":         list(result.patterns),
        "breakout_state":   bi.get("state",  "NO_BREAKOUT"),
        "breakout_label":   bi.get("label",  "—"),
        "breakout_color":   bi.get("color",  "#94a3b8"),
        "structural_score": int(result.structural_score),
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


def _parse_timeframes(raw: str) -> list[str] | None:
    """Comma-separated TF subset → validated list, or None for 'all' (unfiltered)."""
    if not raw:
        return None
    wanted = [t.strip() for t in raw.split(",") if t.strip()]
    valid = [t for t in wanted if t in _ALL_TIMEFRAMES]
    return valid or None


def _parse_pattern_names(raw: str) -> set[str] | None:
    """Comma-separated exact pattern names → set, or None for 'all patterns'."""
    if not raw:
        return None
    names = {n.strip() for n in raw.split(",") if n.strip()}
    return names or None


async def _scatter_workers(
    symbols: list[str],
    threshold: int,
    timeframes: list[str] | None = None,
    enabled_pattern_names: set[str] | None = None,
) -> tuple[list[tuple], set[str]]:
    """
    Process all symbols concurrently with a Semaphore-bounded pool.
    Each symbol fetches only the requested TFs in parallel via _process_symbol_async.
    """
    sem = asyncio.Semaphore(8)

    async def _bounded(sym: str):
        async with sem:
            return sym, await _process_symbol_async(sym, threshold, timeframes, enabled_pattern_names)

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
        plan = build_plan(result, option_chain=opt_chain, nearest_expiry=expiry)

        # Daily data: shared between backtest and breakout_state
        if sym not in daily_cache:
            try:
                df = get_daily(sym, period="6mo")
                daily_cache[sym] = add_indicators(df) if not df.empty else None
            except Exception:
                daily_cache[sym] = None

        # Backtest
        hit_rate, n = None, 0
        if result.pattern.name != "None":
            hit_rate, n = _backtest_with_df(
                daily_cache.get(sym), result.pattern.name, result.direction
            )

        breakout_info = _get_breakout_state(daily_cache.get(sym), result.direction)
        cards.append(_to_card(result, timeframe, plan, hit_rate, n, source, breakout_info))
    return cards


def _apply_pattern_filters(
    cards: list[dict],
    pattern_families: str | None,
    min_pattern_conf: float,
) -> list[dict]:
    """
    Filter cards by pattern family and minimum confidence.
    pattern_families: comma-separated list of families, e.g. "candlestick,chart"
    min_pattern_conf: 0.0–1.0
    A card passes if ANY of its detected patterns match the criteria.
    """
    if not pattern_families and min_pattern_conf <= 0.0:
        return cards

    families = {f.strip().lower() for f in pattern_families.split(",")} if pattern_families else set()
    filtered = []
    for card in cards:
        pats = card.get("patterns", [])
        if not pats:
            continue
        match = False
        for p in pats:
            conf_ok = p.get("confidence", 0.0) >= min_pattern_conf
            fam_ok  = not families or p.get("family", "").lower() in families
            if conf_ok and fam_ok:
                match = True
                break
        if match:
            filtered.append(card)
    return filtered


def _build_summary(
    cards: list[dict],
    total_symbols: int,
    unique_symbols: int,
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
    }


@router.get("/scan")
async def run_scan(
    universe:          Annotated[str,   Query()] = "top30",
    threshold:         Annotated[int,   Query()] = 65,
    patterns:          Annotated[str,   Query()] = "",
    min_pattern_conf:  Annotated[float, Query()] = 0.0,
    timeframes:        Annotated[str,   Query()] = "",
    pattern_names:     Annotated[str,   Query()] = "",
):
    """
    Scan all symbols across the requested timeframes (default: 5m/15m/30m/1h/4h/1d/1wk/1mo).
    timeframes: comma-separated subset to actually fetch/score — unselected TFs are
    never requested from Yahoo, cutting external API calls proportionally.
    pattern_names: comma-separated exact pattern names — only these contribute to
    each setup's Candle Trigger / Structural bonus score categories.
    patterns: comma-separated family filter (legacy, post-hoc card filter).
    min_pattern_conf: 0.0-1.0, filter cards where any pattern meets this confidence.
    """
    symbols  = _resolve_symbols(universe)
    tf_list  = _parse_timeframes(timeframes)
    names    = _parse_pattern_names(pattern_names)
    log.info("Scan start: %d symbols | threshold=%d | tfs=%s", len(symbols), threshold, tf_list or "all")

    qualifying, processed = await _scatter_workers(symbols, threshold, tf_list, names)
    log.info("Raw qualifying: %d setups", len(qualifying))

    qualifying.sort(key=lambda x: x[0].total, reverse=True)

    cards = await _run(_enrich_cards, qualifying)
    cards = _apply_pattern_filters(cards, patterns or None, min_pattern_conf)

    payload = {
        "setups":    cards,
        "summary":   _build_summary(cards, len(symbols), len(processed)),
        "universe":  universe,
        "threshold": threshold,
        "timeframes": tf_list or _ALL_TIMEFRAMES,
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
    universe:         Annotated[str,   Query()] = "top30",
    threshold:        Annotated[int,   Query()] = 65,
    patterns:         Annotated[str,   Query()] = "",
    min_pattern_conf: Annotated[float, Query()] = 0.0,
    timeframes:       Annotated[str,   Query()] = "",
    pattern_names:    Annotated[str,   Query()] = "",
):
    """
    SSE streaming scan — yields per-symbol progress events so the frontend
    shows a real-time symbol counter (like the equity scanner).

    timeframes: comma-separated subset to actually fetch/score — unselected TFs
    are never requested from Yahoo, cutting external API calls proportionally.
    pattern_names: comma-separated exact pattern names — only these contribute
    to each setup's Candle Trigger / Structural bonus score categories.

    Event types:
      start      — {"type":"start","total":N,"universe":"top30"}
      progress   — {"type":"progress","symbol":"NIFTY","found":3,"done":5,"total":30}
      enriching  — {"type":"enriching","setups":N}
      result     — {"type":"result", ...full scan payload...}
      [DONE]     — literal string, signals stream end
    """
    symbols = _resolve_symbols(universe)
    tf_list = _parse_timeframes(timeframes)
    names   = _parse_pattern_names(pattern_names)
    log.info("SSE scan: %d symbols threshold=%d tfs=%s", len(symbols), threshold, tf_list or "all")

    async def generate():
        def _sse(obj) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        yield _sse({"type": "start", "total": len(symbols), "universe": universe})

        queue: asyncio.Queue = asyncio.Queue()
        sem   = asyncio.Semaphore(12)

        async def process_sym(sym: str) -> None:
            async with sem:
                results = await _process_symbol_async(sym, threshold, tf_list, names)
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
        cards   = await _run(_enrich_cards, all_qualifying)
        cards   = _apply_pattern_filters(cards, patterns or None, min_pattern_conf)
        summary = _build_summary(cards, len(symbols), len(processed_syms))

        payload = {
            "type":       "result",
            "setups":     cards,
            "summary":    summary,
            "universe":   universe,
            "threshold":  threshold,
            "timeframes": tf_list or _ALL_TIMEFRAMES,
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


@router.get("/patterns")
async def list_patterns():
    """Return all pattern names from the registry, grouped by family."""
    from services.pattern_registry import REGISTRY
    groups: dict[str, list[dict]] = {}
    order  = ["candlestick", "price_action", "volume", "chart", "harmonic"]
    for entry in REGISTRY:
        fam = entry.family
        if fam not in groups:
            groups[fam] = []
        groups[fam].append({
            "name":      entry.name,
            "direction": entry.direction_bias,
            "tier":      entry.tier,
        })
    return {fam: groups[fam] for fam in order if fam in groups}


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
