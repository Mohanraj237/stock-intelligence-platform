"""Universe endpoints: list available, sync, get symbols."""
from __future__ import annotations
import time
from typing import List, Optional
from fastapi import APIRouter, Query

from backend.deps import run_sync

router = APIRouter(prefix="/api/universe", tags=["universe"])


# In-memory cache for the merged symbol catalog (used by the typeahead)
_CATALOG_CACHE: dict = {"data": None, "loaded_at": 0.0}
_CATALOG_TTL_S = 60 * 60  # refresh once an hour


def _build_catalog() -> list[dict]:
    """Merge every available universe into a deduped {symbol, company} catalog.
    Defensive: any individual universe failure is swallowed; we always return
    whatever we could parse rather than 500-ing the typeahead."""
    seen: dict[str, str] = {}
    try:
        from services.universe_sync import get_all_universe_names, get_universe
        names = get_all_universe_names() or []
    except Exception:
        return []

    for name in names:
        try:
            d = get_universe(name) or {}
        except Exception:
            continue
        companies = d.get("companies") or {}
        symbols = d.get("symbols") or []
        for sym in symbols:
            try:
                sym = (sym or "").strip().upper()
                if not sym or sym in seen:
                    continue
                company = ""
                if isinstance(companies, dict):
                    company = companies.get(sym) or companies.get(sym.lower()) or ""
                elif isinstance(companies, list):
                    try:
                        idx = symbols.index(sym)
                        if 0 <= idx < len(companies):
                            company = str(companies[idx])
                    except ValueError:
                        pass
                seen[sym] = company
            except Exception:
                continue
    return [{"symbol": s, "company": c} for s, c in sorted(seen.items())]


def _get_catalog() -> list[dict]:
    now = time.time()
    try:
        if _CATALOG_CACHE["data"] is None or (now - _CATALOG_CACHE["loaded_at"]) > _CATALOG_TTL_S:
            _CATALOG_CACHE["data"] = _build_catalog()
            _CATALOG_CACHE["loaded_at"] = now
        return _CATALOG_CACHE["data"] or []
    except Exception:
        return []


@router.get("/list")
async def list_universes() -> dict:
    from services.universe_sync import universe_display_map
    return await run_sync(universe_display_map)


@router.get("/search")
async def search_symbols(
    q: str = Query("", max_length=100, description="Symbol prefix or company substring"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """Typeahead search across the merged catalog of every available universe.

    Ranking: exact symbol match > symbol prefix > symbol contains > company contains.
    Returns [{symbol, company}, ...] truncated to `limit`.
    """
    catalog = await run_sync(_get_catalog)
    qu = (q or "").upper().strip()
    if not qu:
        return catalog[:limit]
    ql = qu.lower()
    out: list[tuple[int, dict]] = []
    for entry in catalog:
        s = entry["symbol"]
        c = (entry.get("company") or "").lower()
        if s == qu:
            out.append((0, entry))
        elif s.startswith(qu):
            out.append((1, entry))
        elif qu in s:
            out.append((2, entry))
        elif ql in c:
            out.append((3, entry))
    out.sort(key=lambda t: (t[0], t[1]["symbol"]))
    return [e for _, e in out[:limit]]


@router.get("/all-symbols")
async def all_symbols() -> list[dict]:
    """Full deduped catalog. Cached server-side; client should also cache."""
    return await run_sync(_get_catalog)


@router.get("/{name}/symbols")
async def universe_symbols(name: str, limit: Optional[int] = Query(None)) -> List[str]:
    from services.universe_sync import get_universe_symbols
    return await run_sync(get_universe_symbols, name, limit)


@router.get("/{name}")
async def get_universe(name: str, force_refresh: bool = False) -> dict:
    from services.universe_sync import get_universe
    return await run_sync(get_universe, name, force_refresh)


@router.post("/{name}/sync")
async def sync_universe(name: str) -> dict:
    from services.universe_sync import fetch_and_cache_universe
    return await run_sync(fetch_and_cache_universe, name)


@router.get("/_meta/status")
async def sync_status() -> dict:
    from services.universe_sync import universe_sync_status
    return await run_sync(universe_sync_status)
