"""Pattern detection + multi-timeframe breakout endpoints."""
from __future__ import annotations
import asyncio
import time
import logging
from typing import List, Optional
from fastapi import APIRouter, Query

from backend.deps import run_sync, gather_bounded
from backend.schemas import (
    PatternHit, BreakoutClassification, MultiTFBreakout,
    PatternScanRequest, PatternScanResult,
)
from backend.schemas.common import Direction, BreakoutState, Timeframe, TIMEFRAME_TO_YF_INTERVAL, TIMEFRAME_TO_YF_PERIOD
from backend.schemas.pattern import PatternStockResult

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _norm_dir(s: str) -> Direction:
    s = (s or "neutral").strip().lower()
    if s.startswith("bull"): return Direction.BULLISH
    if s.startswith("bear"): return Direction.BEARISH
    return Direction.NEUTRAL


# ─────────────────────────────────────────────────────────────────────────────
# Pattern-name matching
# The Learn library uses curated names ("Symmetrical Triangle"); the detection
# engine emits raw names ("Symmetrical Triangle Breakout"). Without aliasing,
# user-picked filters silently match nothing. The map below + fuzzy fallback
# closes the gap so picking "Channel Breakout" also matches Ascending/Descending
# Channel detections.
# ─────────────────────────────────────────────────────────────────────────────
NAME_ALIAS: dict[str, set[str]] = {
    "symmetrical triangle":   {"symmetrical triangle breakout"},
    "channel breakout":       {"ascending channel", "descending channel"},
    "falling wedge":          {"descending wedge breakout"},
    "52w high breakout":      {"52w high breakout", "near 52w high"},
    "52w low breakdown":      {"near 52w low"},
}


def _norm_pattern_name(s: str) -> str:
    """Lower + strip noise tokens so 'Symmetrical Triangle Breakout' ~ 'Symmetrical Triangle'."""
    s = (s or "").lower()
    for token in (" breakout", " breakdown", "near ", "the "):
        s = s.replace(token, " ")
    return " ".join(s.split())


def _name_matches(library_name: str, engine_name: str) -> bool:
    lib = (library_name or "").lower().strip()
    eng = (engine_name or "").lower().strip()
    if not lib or not eng:
        return False
    if lib == eng:
        return True
    aliases = NAME_ALIAS.get(lib, set())
    if eng in aliases:
        return True
    # Fuzzy: strip "Breakout"/"Near" then equality or substring containment
    nl, ne = _norm_pattern_name(lib), _norm_pattern_name(eng)
    return nl == ne or (len(nl) >= 4 and (nl in ne or ne in nl))


def _to_pattern_hit(p: dict, tf: Optional[Timeframe] = None) -> PatternHit:
    levels = p.get("key_levels") or {}
    return PatternHit(
        name=p.get("name", "?"),
        category=p.get("category", "Other"),
        direction=_norm_dir(p.get("direction", "Neutral")),
        confidence=float(p.get("confidence") or 0),
        status=p.get("status"),
        description=p.get("description"),
        target=levels.get("target"),
        stop=levels.get("stop"),
        support=levels.get("support"),
        resistance=levels.get("resistance"),
        points=p.get("points") or [],
        lines=p.get("lines") or [],
        zones=p.get("zones") or [],
        timeframe=tf,
    )


def _to_breakout_classification(d: dict, tf: Optional[Timeframe] = None) -> BreakoutClassification:
    return BreakoutClassification(
        state=BreakoutState(d.get("state", "NO_BREAKOUT")),
        label=d.get("label", ""),
        color=d.get("color", "#94a3b8"),
        level=d.get("level"),
        current_price=d.get("current_price"),
        distance_pct=d.get("distance_pct"),
        bars_since_breakout=int(d.get("bars_since_breakout") or 0),
        volume_confirmed=bool(d.get("volume_confirmed")),
        is_bullish=bool(d.get("is_bullish")),
        is_bearish=bool(d.get("is_bearish")),
        timeframe=tf,
    )


@router.get("/library")
async def pattern_library() -> List[dict]:
    """All 69 registry patterns enriched with curated Learn-page metadata.
    Source of truth for both the Learn page and the scanner pattern chips."""
    from services.pattern_examples import PATTERN_LIBRARY
    from services.pattern_registry import REGISTRY

    curated = {p["name"]: p for p in PATTERN_LIBRARY}

    DIRECTION_MAP = {
        "bullish": "Bullish",
        "bearish": "Bearish",
        "neutral": "Neutral",
    }
    FAMILY_CATEGORY = {
        "candlestick":  "Candlestick — Reversal",
        "price_action": "Price Action",
        "volume":       "Volume / Momentum",
        "chart":        "Chart Pattern",
        "harmonic":     "Harmonic",
    }

    out = []
    for entry in sorted(REGISTRY, key=lambda e: (e.family, e.name)):
        name = entry.name
        c    = curated.get(name)
        out.append({
            "name":               name,
            "category":           (c or {}).get("category") or FAMILY_CATEGORY.get(entry.family, "Other"),
            "direction":          (c or {}).get("direction") or DIRECTION_MAP.get(entry.direction_bias, "Neutral"),
            "description":        (c or {}).get("description") or "",
            "when_to_trade":      (c or {}).get("when_to_trade"),
            "target_rule":        (c or {}).get("target_rule"),
            "stop":               (c or {}).get("stop"),
            "confidence_factors": (c or {}).get("confidence_factors") or [],
            "best_timeframes":    (c or {}).get("best_timeframes") or "1d, 1w",
            "has_example":        name in curated,
        })
    return out


@router.get("/library/{name}/example")
async def pattern_example(name: str) -> dict:
    """Synthetic OHLCV example for the named pattern (for the Learn page)."""
    from services.pattern_examples import PATTERN_LIBRARY
    match = next((p for p in PATTERN_LIBRARY if p["name"].lower() == name.lower()), None)
    if not match:
        return {"error": f"Pattern '{name}' not found"}
    df = await run_sync(match["generator"])
    bars = []
    for i, (ts, row) in enumerate(df.iterrows()):
        bars.append({
            "time": int(i),  # bar index — synthetic data has no real timestamps
            "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": float(row["Close"]),
            "volume": float(row.get("Volume") or 0),
        })
    return {
        "name": match["name"],
        "category": match.get("category"),
        "direction": match.get("direction"),
        "description": match.get("description"),
        "bars": bars,
    }


@router.get("/detect/{symbol}", response_model=List[PatternHit])
async def detect_for_symbol(symbol: str, region: str = Query("IN"), timeframe: Timeframe = Query(Timeframe.DAILY)) -> List[PatternHit]:
    from services.market_data_service import get_ohlcv_history
    from engines.pattern_engine import detect_patterns
    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    period = TIMEFRAME_TO_YF_PERIOD[timeframe]
    df = await run_sync(get_ohlcv_history, symbol, period, interval, region)
    if df is None or len(df) < 30:
        return []
    raw = await run_sync(detect_patterns, df)
    return [_to_pattern_hit(p, timeframe) for p in (raw or [])]


@router.get("/multi-tf-breakout/{symbol}", response_model=MultiTFBreakout)
async def multi_tf_breakout(symbol: str, region: str = Query("IN")) -> MultiTFBreakout:
    from services.market_data_service import get_ohlcv_history
    from services.breakout_service import classify_breakout
    out: dict[str, BreakoutClassification] = {}
    plans = [
        (Timeframe.DAILY,   "1y",  "1d"),
        (Timeframe.WEEKLY,  "5y",  "1wk"),
        (Timeframe.MONTHLY, "max", "1mo"),
    ]
    async def _one(tf: Timeframe, period: str, interval: str):
        df = await run_sync(get_ohlcv_history, symbol, period, interval, region)
        if df is None or len(df) < 30:
            return tf, None
        cls = await run_sync(classify_breakout, df)
        return tf, cls
    results = await asyncio.gather(*[_one(*p) for p in plans])
    overall = "—"
    for tf, cls in results:
        if cls:
            out[tf.value] = _to_breakout_classification(cls, tf)
    daily = out.get(Timeframe.DAILY.value)
    weekly = out.get(Timeframe.WEEKLY.value)
    if daily and weekly:
        if daily.state == BreakoutState.CONFIRMED_BREAKOUT and weekly.state == BreakoutState.FRESH_BREAKOUT:
            overall = "🟢 Ideal swing-buy setup (1D confirmed + 1W fresh)"
        elif daily.is_bullish and weekly.is_bullish:
            overall = "🟢 Bullish breakout in progress"
        elif daily.state == BreakoutState.VERGE_BREAKOUT or weekly.state == BreakoutState.VERGE_BREAKOUT:
            overall = "🟡 Approaching breakout — watch closely"
        elif daily.is_bearish and weekly.is_bearish:
            overall = "🔴 Bearish breakdown across timeframes"
    return MultiTFBreakout(symbol=symbol.upper(), by_timeframe=out, overall=overall)


def _build_scanner(req: PatternScanRequest):
    """Returns (tf_plans, scan_one_async). Used by both /scan and /scan/stream."""
    from services.market_data_service import get_ohlcv_history
    from services.breakout_service import classify_breakout
    from engines.pattern_engine import detect_patterns

    tf_plans = [(tf, TIMEFRAME_TO_YF_PERIOD[tf], TIMEFRAME_TO_YF_INTERVAL[tf]) for tf in req.timeframes]
    name_filter = list(req.pattern_names or [])
    state_filter = {s for s in (req.breakout_states or [])}
    dir_filter = req.direction

    async def scan_one(sym: str) -> Optional[PatternStockResult]:
        try:
            per_tf_patterns: list[PatternHit] = []
            per_tf_breakouts: dict[str, BreakoutClassification] = {}
            last_price: Optional[float] = None
            tfs_present: list[Timeframe] = []
            for tf, period, interval in tf_plans:
                try:
                    df = await run_sync(get_ohlcv_history, sym, period, interval, req.region)
                except Exception as e:
                    log.debug("OHLCV failed %s @%s: %s", sym, tf.value, e)
                    continue
                if df is None or len(df) < 30:
                    continue
                try:
                    last_price = float(df["Close"].iloc[-1])
                except Exception:
                    pass
                try:
                    pats = await run_sync(detect_patterns, df) or []
                except Exception as e:
                    log.debug("detect_patterns failed %s @%s: %s", sym, tf.value, e)
                    pats = []
                kept = []
                for p in pats:
                    try:
                        eng_name = p.get("name", "")
                        if name_filter and not any(_name_matches(w, eng_name) for w in name_filter):
                            continue
                        if dir_filter and _norm_dir(p.get("direction", "")) != dir_filter:
                            continue
                        if float(p.get("confidence") or 0) < req.min_confidence:
                            continue
                        kept.append(_to_pattern_hit(p, tf))
                    except Exception as e:
                        log.debug("pattern coerce failed %s: %s", sym, e)
                if kept:
                    tfs_present.append(tf)
                    per_tf_patterns.extend(kept)
                try:
                    cls = await run_sync(classify_breakout, df)
                    bc = _to_breakout_classification(cls, tf)
                    if not state_filter or bc.state in state_filter:
                        per_tf_breakouts[tf.value] = bc
                except Exception as e:
                    log.debug("breakout failed %s @%s: %s", sym, tf.value, e)
            if not per_tf_patterns:
                return None
        except Exception as e:
            log.warning("scan-symbol fatal %s: %s", sym, e)
            return None
        confluence = len(tfs_present) * 25
        for bc in per_tf_breakouts.values():
            if bc.state in (BreakoutState.FRESH_BREAKOUT, BreakoutState.CONFIRMED_BREAKOUT):
                confluence += 15
            elif bc.state == BreakoutState.VERGE_BREAKOUT:
                confluence += 8
        return PatternStockResult(
            symbol=sym, last_price=last_price, confluence_score=min(confluence, 100),
            patterns=per_tf_patterns, breakouts=per_tf_breakouts,
            timeframes_present=tfs_present,
        )

    return scan_one


@router.post("/scan", response_model=PatternScanResult)
async def scan(req: PatternScanRequest) -> PatternScanResult:
    """Bulk pattern scan — synchronous, returns full result. Use /scan/stream for live progress."""
    t0 = time.perf_counter()
    if req.region == "US":
        from services.us_universe_sync import get_us_universe_symbols
        all_syms = await run_sync(get_us_universe_symbols, req.universe)
        syms = (all_syms or [])[:req.max_symbols] if req.max_symbols else (all_syms or [])
    else:
        from services.universe_sync import get_universe_symbols
        syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
    if not syms:
        return PatternScanResult(request=req, rows=[], total_scanned=0, total_matched=0, duration_ms=0)

    scan_one = _build_scanner(req)
    tasks = [scan_one(s) for s in syms]
    results = await gather_bounded(*tasks, limit=24)
    rows = [r for r in results if isinstance(r, PatternStockResult)]
    rows.sort(key=lambda r: r.confluence_score, reverse=True)
    return PatternScanResult(
        request=req, rows=rows, total_scanned=len(syms),
        total_matched=len(rows), duration_ms=(time.perf_counter() - t0) * 1000,
    )


@router.post("/scan/stream")
async def scan_stream(req: PatternScanRequest):
    """Streaming variant of /scan. Emits Server-Sent Events:

      data: {"type":"started","total":500}
      data: {"type":"progress","done":42,"total":500,"matched":12,"current":"RELIANCE"}
      ...
      data: {"type":"result","rows":[...],"total_scanned":500,"total_matched":N,"duration_ms":...}
      data: {"type":"done"}
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    import json

    async def event_gen():
        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload, default=str)}\n\n"

        t0 = time.perf_counter()
        if req.region == "US":
            from services.us_universe_sync import get_us_universe_symbols
            all_syms = await run_sync(get_us_universe_symbols, req.universe)
            syms = (all_syms or [])[:req.max_symbols] if req.max_symbols else (all_syms or [])
        else:
            from services.universe_sync import get_universe_symbols
            syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)
        total = len(syms)
        yield sse({"type": "started", "total": total, "universe": req.universe})

        if total == 0:
            yield sse({"type": "result", "rows": [], "total_scanned": 0, "total_matched": 0, "duration_ms": 0, "request": req.model_dump()})
            yield sse({"type": "done"})
            return

        scan_one = _build_scanner(req)
        sem = asyncio.Semaphore(24)

        async def wrapped(sym: str):
            async with sem:
                try:
                    return sym, await scan_one(sym)
                except Exception:
                    return sym, None

        tasks = [asyncio.create_task(wrapped(s)) for s in syms]
        rows: list[PatternStockResult] = []
        done = 0
        # Throttle: at most ~30 progress events for the whole scan, plus the final
        emit_every = max(1, total // 30)
        for fut in asyncio.as_completed(tasks):
            sym, r = await fut
            done += 1
            if isinstance(r, PatternStockResult):
                rows.append(r)
            if done == total or done % emit_every == 0:
                yield sse({
                    "type": "progress",
                    "done": done, "total": total,
                    "matched": len(rows),
                    "current": sym,
                    "elapsed_ms": (time.perf_counter() - t0) * 1000,
                })

        rows.sort(key=lambda r: r.confluence_score, reverse=True)
        result = PatternScanResult(
            request=req, rows=rows, total_scanned=total,
            total_matched=len(rows), duration_ms=(time.perf_counter() - t0) * 1000,
        )
        yield sse({"type": "result", **result.model_dump()})
        yield sse({"type": "done"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            "Connection": "keep-alive",
        },
    )


