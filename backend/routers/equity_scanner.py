"""
Equity scanner router — /api/equity-scanner/*

Scans India Equity (NSE indices, Nifty 50/100/200) and US Equity
(US indices, S&P 100, Tech) across Daily / Weekly / Monthly timeframes
using Yahoo Finance REST API.

Generates stock-level trade plans (entry / SL / T1 / T2) — no options.
Streaming via SSE — identical pattern to the F&O live scanner.

Endpoints:
  GET /api/equity-scanner/scan/stream  — SSE streaming (accepts market=IN|US)
  GET /api/equity-scanner/health
  GET /api/equity-scanner/chart-data
  GET /api/equity-scanner/universe     — returns all universes, filterable by market
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field as dataclass_field
from typing import Annotated, Any

# Isolated thread pool — equity scanner never competes with the F&O scanner
# or with the default pool used by other API endpoints.
_SCAN_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="equity-scan")

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from services.intraday_data import (
    fetch_symbol_equity_tfs,
    get_ohlcv,
    get_daily,
    UNIVERSE_PRESETS,
    EQUITY_TFS,
    # India broad
    get_india_nifty200,
    get_india_nifty500,
    get_india_midcap150,
    get_india_smallcap250,
    # India sectors
    get_india_bank,
    get_india_it,
    get_india_pharma,
    get_india_auto,
    get_india_fmcg,
    get_india_metal,
    get_india_energy,
    get_india_infra,
    get_india_realty,
    get_india_media,
    get_india_psu_bank,
    # US broad
    get_us_sp100,
    get_us_nasdaq100,
    get_us_dow30,
    get_us_sp500,
    # US sectors
    get_us_technology,
    get_us_financials,
    get_us_healthcare,
    get_us_energy_sector,
    get_us_consumer_disc,
    get_us_communication,
    get_us_industrials,
    get_us_consumer_staples,
    # All-market
    get_all_nse,
    get_all_us_listed,
    refresh_all_nse,
    _save_universe_json,
)
from services.intraday_data import exchange_tz, cache_stats, reset_cache_stats
from services.confluence_scorer import (
    add_indicators, score as confluence_score, MIN_BARS_TO_SCORE, ScoringWeights,
)
from backend.deps import run_sync
from services.equity_advisor import build_equity_plan, EquityPlan
from services.breakout_service import classify_breakout
from services.scan_support import (
    ScanInputError, ScanDiagnostics, apply_pattern_filters, backtest_pattern,
    parse_pattern_mode, parse_pattern_names, parse_timeframes, resolve_universe,
)

router = APIRouter(prefix="/api/equity-scanner", tags=["equity-scanner"])
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Universe registry  (market = "IN" | "US")
# ─────────────────────────────────────────────────────────────────────────────

def _u(label: str, market: str, desc: str) -> dict:
    return {"label": label, "currency": "₹" if market == "IN" else "$", "market": market, "desc": desc}

EQUITY_UNIVERSES: dict[str, dict] = {
    # ── India — Indices ──────────────────────────────────────────────────────
    "india_indices":      _u("NSE / BSE Indices",    "IN", "NIFTY · BANKNIFTY · SENSEX · FINNIFTY · MIDCPNIFTY · BANKEX"),
    # ── India — Broad Market ─────────────────────────────────────────────────
    "india_nifty50":      _u("Nifty 50",             "IN", "50 large-cap NSE blue-chips — ~60s"),
    "india_nifty100":     _u("Nifty 100",            "IN", "Nifty 50 + Nifty Next 50 — ~2 min"),
    "india_nifty200":     _u("Nifty 200",            "IN", "Top 200 NSE stocks — ~4 min"),
    "india_nifty500":     _u("Nifty 500",            "IN", "Top 500 NSE stocks — ~10 min"),
    "india_midcap150":    _u("Nifty Midcap 150",     "IN", "150 midcap stocks — ~3 min"),
    "india_smallcap250":  _u("Nifty Smallcap 250",   "IN", "250 smallcap stocks — ~5 min"),
    # ── India — Sectors ──────────────────────────────────────────────────────
    "india_bank":         _u("Nifty Bank",           "IN", "14 banking stocks — HDFC · ICICI · SBIN · AXIS"),
    "india_it":           _u("Nifty IT",             "IN", "10 IT stocks — TCS · INFY · HCLTECH · WIPRO"),
    "india_pharma":       _u("Nifty Pharma",         "IN", "20 pharma stocks — SUNPHARMA · DRREDDY · CIPLA"),
    "india_auto":         _u("Nifty Auto",           "IN", "15 auto stocks — MARUTI · TATAMOTORS · M&M"),
    "india_fmcg":         _u("Nifty FMCG",          "IN", "15 FMCG stocks — HINDUNILVR · ITC · NESTLEIND"),
    "india_metal":        _u("Nifty Metal",          "IN", "19 metal stocks — TATASTEEL · JSWSTEEL · VEDL"),
    "india_energy":       _u("Nifty Energy",         "IN", "40 energy stocks — RELIANCE · ONGC · NTPC"),
    "india_infra":        _u("Nifty Infra",          "IN", "30 infra stocks — LT · POWERGRID · NTPC"),
    "india_realty":       _u("Nifty Realty",         "IN", "10 realty stocks — DLF · LODHA · GODREJPROP"),
    "india_psu_bank":     _u("Nifty PSU Bank",       "IN", "12 PSU bank stocks — SBIN · PNB · BANKBARODA"),
    "india_media":        _u("Nifty Media",          "IN", "10 media stocks — ZEEL · SUNTV · PVRINOX"),
    # ── US — Indices ─────────────────────────────────────────────────────────
    "us_indices":         _u("US Major Indices",     "US", "S&P 500 · NASDAQ 100 · Dow Jones · Russell 2000"),
    # ── US — Broad Market ────────────────────────────────────────────────────
    "us_top30":           _u("US Top 30",            "US", "AAPL · MSFT · NVDA · GOOGL and 26 more — ~35s"),
    "us_dow30":           _u("US Dow Jones 30",      "US", "30 Dow Jones Industrial Average stocks — ~35s"),
    "us_nasdaq100":       _u("US NASDAQ 100",        "US", "101 NASDAQ-listed large-caps — ~2 min"),
    "us_sp100":           _u("US S&P 100",           "US", "Top 100 S&P 500 constituents by weight — ~2 min"),
    "us_sp500":           _u("US S&P 500",           "US", "503 S&P 500 stocks — ~10 min"),
    # ── US — Sectors ─────────────────────────────────────────────────────────
    "us_technology":      _u("US Technology",        "US", "30 tech stocks — AAPL · MSFT · NVDA · GOOGL"),
    "us_financials":      _u("US Financials",        "US", "30 financial stocks — JPM · BAC · GS · MS"),
    "us_healthcare":      _u("US Healthcare",        "US", "30 healthcare stocks — UNH · LLY · JNJ · ABBV"),
    "us_energy":          _u("US Energy",            "US", "20 energy stocks — XOM · CVX · COP · SLB"),
    "us_consumer_disc":   _u("US Consumer Discret.", "US", "20 consumer discretionary — AMZN · TSLA · HD"),
    "us_communication":   _u("US Communication",     "US", "20 communication stocks — META · GOOGL · NFLX"),
    "us_industrials":     _u("US Industrials",       "US", "20 industrial stocks — CAT · HON · GE · BA"),
    "us_consumer_staples":_u("US Consumer Staples",  "US", "20 consumer staples — WMT · PG · KO · COST"),
    # ── All-market ───────────────────────────────────────────────────────────
    "all_nse":            _u("All NSE Stocks",       "IN", "511 merged + ~1800 via nselib refresh — 20+ min"),
    "all_us":             _u("All US Listed (536)",  "US", "S&P 500 + NASDAQ 100 + all US sectors deduplicated — ~12 min"),
}


_LAZY: dict[str, object] = {
    # India broad
    "india_nifty200":     get_india_nifty200,
    "india_nifty500":     get_india_nifty500,
    "india_midcap150":    get_india_midcap150,
    "india_smallcap250":  get_india_smallcap250,
    # India sectors
    "india_bank":         get_india_bank,
    "india_it":           get_india_it,
    "india_pharma":       get_india_pharma,
    "india_auto":         get_india_auto,
    "india_fmcg":         get_india_fmcg,
    "india_metal":        get_india_metal,
    "india_energy":       get_india_energy,
    "india_infra":        get_india_infra,
    "india_realty":       get_india_realty,
    "india_media":        get_india_media,
    "india_psu_bank":     get_india_psu_bank,
    # US broad
    "us_sp100":           get_us_sp100,
    "us_nasdaq100":       get_us_nasdaq100,
    "us_dow30":           get_us_dow30,
    "us_sp500":           get_us_sp500,
    # US sectors
    "us_technology":      get_us_technology,
    "us_financials":      get_us_financials,
    "us_healthcare":      get_us_healthcare,
    "us_energy":          get_us_energy_sector,
    "us_consumer_disc":   get_us_consumer_disc,
    "us_communication":   get_us_communication,
    "us_industrials":     get_us_industrials,
    "us_consumer_staples":get_us_consumer_staples,
    # All-market
    "all_nse":            get_all_nse,
    "all_us":             get_all_us_listed,
}


# Every key the equity scanner can actually resolve. The F&O-only presets
# ("indices" / "stocks") are deliberately excluded — the equity scanner has its
# own india_indices key and its own currency/market metadata.
_EQUITY_UNIVERSE_KEYS: set[str] = (
    set(EQUITY_UNIVERSES) | set(_LAZY) | set(UNIVERSE_PRESETS)
) - {"indices", "stocks"}


def _resolve_symbols(universe: str) -> list[str]:
    """
    Symbol list for a universe key. Unknown keys raise ScanInputError → HTTP 400;
    they used to fall back to india_nifty50, so a typo silently scanned the
    wrong market.
    """
    resolve_universe(universe, _EQUITY_UNIVERSE_KEYS)
    fn = _LAZY.get(universe)
    if fn is not None:
        return fn()  # type: ignore[operator]
    return UNIVERSE_PRESETS[universe]


def _currency_for(universe: str) -> str:
    return EQUITY_UNIVERSES.get(universe, {}).get("currency", "₹")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sf(v: Any, default: float = 0.0, decimals: int = 2) -> float:
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else round(f, decimals)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol worker — fully async, fetches all TFs in parallel
# ─────────────────────────────────────────────────────────────────────────────

async def _run(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) in the equity scanner's dedicated thread pool."""
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
    Fetch only the requested TFs (subset of Daily/Weekly/Monthly) concurrently,
    then score each concurrently. Unselected TFs are never requested from Yahoo.
    Uses the isolated _SCAN_POOL so this scanner never starves the F&O scanner
    or default-pool endpoints (paper trades, health, etc.).

    Returns a SymbolOutcome so the scan summary can distinguish "no setups" from
    "the download failed" or "not enough history".
    """
    want_tfs = timeframes if timeframes else EQUITY_TFS
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

    # Fetch only the requested TFs simultaneously
    try:
        raw = await asyncio.gather(*[_fetch_tf(tf) for tf in want_tfs], return_exceptions=True)
    except Exception as exc:
        log.warning("Fetch failed %s: %s", symbol, exc)
        return SymbolOutcome(symbol, status="error", reason=f"fetch failed: {exc}")

    failures = [r for r in raw if isinstance(r, Exception)]
    tf_data = {tf: df for r in raw if not isinstance(r, Exception)
               for tf, df in [r] if not df.empty}

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
        log.info("  %s: %d setup(s)", symbol, len(qualifying))
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


def _plan_dict(plan: EquityPlan) -> dict[str, Any]:
    return {
        "action":         plan.action,
        "entry_price":    _sf(plan.entry_price),
        "sl_price":       _sf(plan.sl_price),
        "t1_price":       _sf(plan.t1_price),
        "t2_price":       _sf(plan.t2_price),
        "rr":             _sf(plan.rr),
        "rr_basis":       plan.rr_basis,
        "exit_rule":      plan.exit_rule,
        "risk_per_share": _sf(plan.risk_per_share),
        "currency":       plan.currency,
    }


def _to_card(result, timeframe: str, plan, backtest: dict | None,
             breakout_info: dict | None = None) -> dict[str, Any]:
    bi = breakout_info or {}
    card = {
        "symbol":           result.symbol,
        "timeframe":        timeframe,
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
        "volume_available": bool(result.volume_available),
        "bars_used":        int(result.bars_used),
    }
    if result.lookback_note:
        card["lookback_note"] = result.lookback_note
    return card


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_cards(qualifying: list[tuple], currency: str) -> list[dict]:
    cards: list[dict] = []
    daily_cache: dict[str, Any] = {}

    for result, timeframe, tf_df in qualifying:
        sym  = result.symbol
        plan = build_equity_plan(result, currency=currency)

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
        cards.append(_to_card(result, timeframe, plan, backtest, breakout_info))
    return cards


def _build_summary(cards: list[dict], total_symbols: int, unique_symbols: int,
                   diag: ScanDiagnostics, cache: dict) -> dict:
    by_dir: dict[str, int] = {"bullish": 0, "bearish": 0, "range": 0}
    by_tf:  dict[str, int] = {tf: 0 for tf in EQUITY_TFS}
    strong  = 0
    for c in cards:
        by_dir[c["direction"]] = by_dir.get(c["direction"], 0) + 1
        by_tf[c["timeframe"]]  = by_tf.get(c["timeframe"], 0) + 1
        if c["confluence_score"] >= 80:
            strong += 1
    return {
        "total_symbols":  total_symbols,
        "unique_setups":  unique_symbols,
        "total_setups":   len(cards),
        "bullish":        by_dir["bullish"],
        "bearish":        by_dir["bearish"],
        "range":          by_dir.get("range", 0),
        "strong_80plus":  strong,
        "by_timeframe":   by_tf,
        "cache_hit_rate": cache.get("hit_rate", 0.0),
        **diag.as_dict(),
    }


@router.get("/patterns")
async def list_patterns():
    """
    Every pattern name any detector can emit, grouped by family, with
    directional variants nested under their parent. Selecting a parent selects
    its variants.
    """
    from services.pattern_registry import patterns_grouped_by_family
    return patterns_grouped_by_family()


# ─────────────────────────────────────────────────────────────────────────────
# SSE streaming endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/scan/stream")
async def scan_stream(
    universe:         Annotated[str,   Query()] = "india_nifty50",
    threshold:        Annotated[int | None, Query()] = None,
    patterns:         Annotated[str,   Query()] = "",
    pattern_names:    Annotated[str,   Query()] = "",
    pattern_mode:     Annotated[str,   Query()] = "filter",
    min_pattern_conf: Annotated[float, Query()] = 0.0,
    timeframes:       Annotated[str | None, Query()] = None,
):
    """
    SSE streaming equity scan — over the requested subset of Daily / Weekly / Monthly
    (default: all three). Unselected TFs are never fetched from Yahoo.
    Events: start → progress → enriching → result → [DONE]

    patterns: comma-separated family filter (candlestick|price_action|volume|chart|harmonic)
    pattern_names: comma-separated pattern ids or display names. Matched by
      identity — selecting a parent also selects its directional variants.
    pattern_mode:
      "filter" (default) — score from the full detector set, then keep only
        cards containing a selected pattern. Scores are identical to an
        unfiltered scan.
      "shape" — legacy: only the selected patterns may contribute to the Candle
        Trigger / Structural bonus categories. This *lowers* scores (the
        reachable maximum drops to 70), so pair it with a lower threshold.

    Invalid inputs return HTTP 400 rather than silently scanning something else.
    """
    try:
        universe = resolve_universe(universe, _EQUITY_UNIVERSE_KEYS)
        symbols  = _resolve_symbols(universe)
        tf_list  = parse_timeframes(timeframes, EQUITY_TFS)
        names    = parse_pattern_names(pattern_names)
        mode     = parse_pattern_mode(pattern_mode)
    except ScanInputError as exc:
        return JSONResponse(exc.as_dict(), status_code=400)

    # Load the persisted scoring config once per scan (not per symbol) so a
    # Settings-page weight change actually takes effect, and so an explicit
    # ?threshold= query param can still override the configured default.
    from storage.file_store import get_scoring_config
    scoring_cfg = await run_sync(get_scoring_config)
    weights = ScoringWeights(
        trend=scoring_cfg["trend_weight"], momentum=scoring_cfg["momentum_weight"],
        volume=scoring_cfg["volume_weight"], candle=scoring_cfg["candle_weight"],
        structural=scoring_cfg["structural_weight"],
    )
    if threshold is None:
        threshold = scoring_cfg["default_threshold"]

    currency     = _currency_for(universe)
    resolved_tfs = tf_list or EQUITY_TFS
    log.info("Equity scan: %d symbols universe=%s threshold=%d tfs=%s mode=%s",
             len(symbols), universe, threshold, resolved_tfs, mode)

    async def generate():
        def _sse(obj) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        # Echo what was *actually* resolved so the UI can show what it scanned.
        yield _sse({
            "type":       "start",
            "total":      len(symbols),
            "universe":   universe,
            "timeframes": resolved_tfs,
            "threshold":  threshold,
            "pattern_mode": mode,
        })

        reset_cache_stats()

        # 10 concurrent symbols × 3 TFs each = 30 parallel Yahoo requests.
        # Each get_ohlcv() uses a fresh requests.Session() so no shared-session
        # rate limiting. Keeping concurrency at 10 avoids Yahoo's IP rate limit.
        queue: asyncio.Queue = asyncio.Queue()
        sem = asyncio.Semaphore(10)

        async def process_sym(sym: str) -> None:
            async with sem:
                try:
                    outcome = await _process_symbol_async(sym, threshold, tf_list, names, mode, weights)
                except Exception as exc:                       # never lose a symbol
                    outcome = SymbolOutcome(sym, status="error", reason=str(exc))
                await queue.put(outcome)

        tasks = [asyncio.create_task(process_sym(s)) for s in symbols]

        all_qualifying: list[tuple] = []
        processed_syms: set[str]   = set()
        diag = ScanDiagnostics()
        completed = 0

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
                "done":          completed,
                "total":         len(symbols),
                "setups_so_far": len(all_qualifying),
            })

        await asyncio.gather(*tasks, return_exceptions=True)
        yield _sse({"type": "enriching", "setups": len(all_qualifying)})

        all_qualifying.sort(key=lambda x: x[0].total, reverse=True)
        cards = await _run(_enrich_cards, all_qualifying, currency)
        # pattern_names is a HARD post-filter under pattern_mode="filter": scores
        # were computed from the full detector set, so they are comparable to an
        # unfiltered scan, and only cards actually containing a selected pattern
        # survive. Under "shape" the selection already shaped the score, so the
        # post-filter is not re-applied.
        cards = apply_pattern_filters(
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
            "currency":     currency,
            "threshold":    threshold,
            "timeframes":   resolved_tfs,
            "pattern_mode": mode,
            "disclaimer": (
                "Not financial advice. Algorithmically identified setups, not predictions. "
                "Every trade carries risk. Always use defined stop-losses."
            ),
        }
        yield _sse(jsonable_encoder(payload))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def health():
    return {"status": "ok", "scanner": "equity"}


@router.post("/refresh-universe/{universe_key}")
async def refresh_universe(universe_key: str):
    """
    Re-fetch and save a universe JSON file.
    all_nse  → tries nselib; falls back to merged NIFTY JSONs
    all_us   → merges all US_*.json files
    """
    if universe_key == "all_nse":
        syms = await asyncio.to_thread(refresh_all_nse)
        return {"universe": "all_nse", "count": len(syms), "preview": syms[:10]}

    if universe_key == "all_us":
        syms = await asyncio.to_thread(get_all_us_listed)
        await asyncio.to_thread(_save_universe_json, "ALL_US_LISTED.json", "ALL US Listed", syms)
        return {"universe": "all_us", "count": len(syms), "preview": syms[:10]}

    return JSONResponse({"error": f"Unknown refresh key: {universe_key}"}, status_code=400)


@router.get("/universe-count/{universe_key}")
async def universe_count(universe_key: str):
    """Quick count check for a universe (used by UI to show live symbol count)."""
    try:
        syms = await asyncio.to_thread(_resolve_symbols, universe_key)
    except ScanInputError as exc:
        return JSONResponse(exc.as_dict(), status_code=400)
    info = EQUITY_UNIVERSES.get(universe_key, {})
    return {"universe": universe_key, "count": len(syms), "market": info.get("market", "")}


@router.get("/universe")
async def get_universe(market: Annotated[str, Query()] = ""):
    """Return all equity universes, optionally filtered by market=IN or market=US."""
    result = {}
    for k, v in EQUITY_UNIVERSES.items():
        if market and v["market"] != market.upper():
            continue
        sym_count = len(_resolve_symbols(k))
        result[k] = {
            "label":    v["label"],
            "desc":     v["desc"],
            "currency": v["currency"],
            "market":   v["market"],
            "count":    sym_count,
        }
    return {"universes": result, "timeframes": EQUITY_TFS}


@router.get("/chart-data")
async def get_chart_data(
    symbol:   Annotated[str, Query()],
    interval: Annotated[str, Query()] = "1d",
    bars:     Annotated[int, Query()] = 80,
):
    import pandas as pd
    from services.intraday_data import get_ohlcv

    df = await asyncio.to_thread(get_ohlcv, symbol, interval)
    if df.empty:
        return JSONResponse({"candles": [], "symbol": symbol, "interval": interval})

    df = df.tail(max(1, bars))
    candles = []
    _intraday = interval not in ("1d", "1wk", "1mo")
    for ts, row in df.iterrows():
        t = pd.Timestamp(ts)
        # lightweight-charts needs "YYYY-MM-DD" for daily/weekly/monthly,
        # and unix seconds (int) for intraday intervals
        time_val: "str | int" = (
            int(t.timestamp()) if _intraday
            else t.strftime("%Y-%m-%d")
        )
        candles.append({
            "time":  time_val,
            "open":  _sf(row["open"]),
            "high":  _sf(row["high"]),
            "low":   _sf(row["low"]),
            "close": _sf(row["close"]),
        })
    return JSONResponse({"candles": candles, "symbol": symbol, "interval": interval})
