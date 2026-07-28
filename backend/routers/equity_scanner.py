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
from services.confluence_scorer import add_indicators, score as confluence_score
from services.equity_advisor import build_equity_plan, EquityPlan
from services.breakout_service import classify_breakout

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


def _resolve_symbols(universe: str) -> list[str]:
    """Return symbol list for a universe key. Lazy-loaded JSON universes via _LAZY map."""
    fn = _LAZY.get(universe)
    if fn is not None:
        return fn()  # type: ignore[operator]
    return UNIVERSE_PRESETS.get(universe, UNIVERSE_PRESETS["india_nifty50"])


def _currency_for(universe: str) -> str:
    return EQUITY_UNIVERSES.get(universe, {}).get("currency", "₹")


def _parse_timeframes(raw: str) -> list[str] | None:
    """Comma-separated TF subset → validated list, or None for 'all' (unfiltered)."""
    if not raw:
        return None
    wanted = [t.strip() for t in raw.split(",") if t.strip()]
    valid = [t for t in wanted if t in EQUITY_TFS]
    return valid or None


def _parse_pattern_names(raw: str) -> set[str] | None:
    """Comma-separated exact pattern names → set, or None for 'all patterns'."""
    if not raw:
        return None
    names = {n.strip() for n in raw.split(",") if n.strip()}
    return names or None


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


async def _process_symbol_async(
    symbol: str,
    threshold: int,
    timeframes: list[str] | None = None,
    enabled_pattern_names: set[str] | None = None,
) -> list[tuple]:
    """
    Fetch only the requested TFs (subset of Daily/Weekly/Monthly) concurrently,
    then score each concurrently. Unselected TFs are never requested from Yahoo.
    Uses the isolated _SCAN_POOL so this scanner never starves the F&O scanner
    or default-pool endpoints (paper trades, health, etc.).
    """
    want_tfs = timeframes if timeframes else EQUITY_TFS

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

    # Fetch only the requested TFs simultaneously
    try:
        raw = await asyncio.gather(*[_fetch_tf(tf) for tf in want_tfs], return_exceptions=True)
    except Exception as exc:
        log.warning("Fetch failed %s: %s", symbol, exc)
        return []

    tf_data = {tf: df for r in raw if not isinstance(r, Exception)
               for tf, df in [r] if not df.empty}

    # Score all fetched TFs simultaneously
    scored = await asyncio.gather(*[_score_tf(tf, df) for tf, df in tf_data.items()])
    qualifying = [r for r in scored if r is not None]

    if qualifying:
        log.info("  %s: %d setup(s)", symbol, len(qualifying))
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


def _plan_dict(plan: EquityPlan) -> dict[str, Any]:
    return {
        "action":         plan.action,
        "entry_price":    _sf(plan.entry_price),
        "sl_price":       _sf(plan.sl_price),
        "t1_price":       _sf(plan.t1_price),
        "t2_price":       _sf(plan.t2_price),
        "rr":             _sf(plan.rr),
        "exit_rule":      plan.exit_rule,
        "risk_per_share": _sf(plan.risk_per_share),
        "currency":       plan.currency,
    }


def _to_card(result, timeframe: str, plan, hit_rate, sample_size,
             breakout_info: dict | None = None) -> dict[str, Any]:
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

def _backtest_with_df(daily_df, pattern_name: str, direction: str) -> tuple[float | None, int]:
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
# Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_cards(qualifying: list[tuple], currency: str) -> list[dict]:
    cards: list[dict] = []
    daily_cache: dict[str, Any] = {}

    for result, timeframe in qualifying:
        sym  = result.symbol
        plan = build_equity_plan(result, currency=currency)

        # Daily data: shared between backtest and breakout_state
        if sym not in daily_cache:
            try:
                df = get_daily(sym, period="6mo")
                daily_cache[sym] = add_indicators(df) if not df.empty else None
            except Exception:
                daily_cache[sym] = None

        hit_rate, n = None, 0
        if result.pattern.name != "None":
            hit_rate, n = _backtest_with_df(
                daily_cache.get(sym), result.pattern.name, result.direction
            )

        breakout_info = _get_breakout_state(daily_cache.get(sym), result.direction)
        cards.append(_to_card(result, timeframe, plan, hit_rate, n, breakout_info))
    return cards


def _build_summary(cards: list[dict], total_symbols: int, unique_symbols: int) -> dict:
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
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pattern filtering
# ─────────────────────────────────────────────────────────────────────────────

def _apply_pattern_filters(
    cards: list[dict],
    pattern_families: str | None,
    min_pattern_conf: float,
    pattern_names: str | None = None,
) -> list[dict]:
    """
    Filter cards where ANY detected pattern matches name/family/confidence criteria —
    same behaviour as the F&O scanner.
    When the card passes via a non-primary pattern, the displayed card["pattern"] is
    updated to the best-confidence matched pattern so the UI always shows a pattern
    the user actually selected.
    """
    if not pattern_families and not pattern_names and min_pattern_conf <= 0.0:
        return cards
    names    = {n.strip().lower() for n in pattern_names.split(",")}    if pattern_names    else set()
    families = {f.strip().lower() for f in pattern_families.split(",")} if pattern_families else set()
    filtered = []
    for card in cards:
        pats = card.get("patterns", [])
        if not pats:
            continue
        matched = [
            p for p in pats
            if p.get("confidence", 0.0) >= min_pattern_conf
            and (not names    or p.get("name",   "").lower() in names)
            and (not families or p.get("family", "").lower() in families)
        ]
        if not matched:
            continue
        # If the primary displayed pattern isn't among the matched ones, update it
        # to the highest-confidence matched pattern so the UI reflects the filter.
        matched_names = {p.get("name", "").lower() for p in matched}
        if card.get("pattern", "").lower() not in matched_names:
            best = max(matched, key=lambda p: p.get("confidence", 0.0))
            card = {**card, "pattern": best["name"]}
        filtered.append(card)
    return filtered


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


# ─────────────────────────────────────────────────────────────────────────────
# SSE streaming endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/scan/stream")
async def scan_stream(
    universe:         Annotated[str,   Query()] = "india_nifty50",
    threshold:        Annotated[int,   Query()] = 65,
    patterns:         Annotated[str,   Query()] = "",
    pattern_names:    Annotated[str,   Query()] = "",
    min_pattern_conf: Annotated[float, Query()] = 0.0,
    timeframes:       Annotated[str,   Query()] = "",
):
    """
    SSE streaming equity scan — over the requested subset of Daily / Weekly / Monthly
    (default: all three). Unselected TFs are never fetched from Yahoo.
    Events: start → progress → enriching → result → [DONE]
    patterns: comma-separated family filter (candlestick|price_action|volume|chart|harmonic)
    pattern_names: comma-separated exact pattern names — only these contribute to
    each setup's Candle Trigger / Structural bonus score categories.
    """
    symbols  = _resolve_symbols(universe)
    currency = _currency_for(universe)
    tf_list  = _parse_timeframes(timeframes)
    names    = _parse_pattern_names(pattern_names)
    log.info("Equity scan: %d symbols universe=%s threshold=%d tfs=%s",
             len(symbols), universe, threshold, tf_list or "all")

    async def generate():
        def _sse(obj) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        yield _sse({"type": "start", "total": len(symbols), "universe": universe})

        # 10 concurrent symbols × 3 TFs each = 30 parallel Yahoo requests.
        # Each get_ohlcv() uses a fresh requests.Session() so no shared-session
        # rate limiting. Keeping concurrency at 10 avoids Yahoo's IP rate limit.
        queue: asyncio.Queue = asyncio.Queue()
        sem = asyncio.Semaphore(10)

        async def process_sym(sym: str) -> None:
            async with sem:
                results = await _process_symbol_async(sym, threshold, tf_list, names)
                await queue.put((sym, results))

        tasks = [asyncio.create_task(process_sym(s)) for s in symbols]

        all_qualifying: list[tuple] = []
        processed_syms: set[str]   = set()
        completed = 0

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
                "done":          completed,
                "total":         len(symbols),
                "setups_so_far": len(all_qualifying),
            })

        await asyncio.gather(*tasks, return_exceptions=True)
        yield _sse({"type": "enriching", "setups": len(all_qualifying)})

        all_qualifying.sort(key=lambda x: x[0].total, reverse=True)
        cards   = await _run(_enrich_cards, all_qualifying, currency)
        # pattern_names is no longer applied as a post-hoc hard filter here — it
        # already shaped each card's score at the source (see _process_symbol_async).
        # A card that still clears `threshold` via trend/momentum/volume alone,
        # despite none of the selected patterns firing, is a legitimate setup.
        cards   = _apply_pattern_filters(cards, patterns or None, min_pattern_conf)
        summary = _build_summary(cards, len(symbols), len(processed_syms))

        payload = {
            "type":       "result",
            "setups":     cards,
            "summary":    summary,
            "universe":   universe,
            "currency":   currency,
            "threshold":  threshold,
            "timeframes": tf_list or EQUITY_TFS,
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
    syms = await asyncio.to_thread(_resolve_symbols, universe_key)
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
