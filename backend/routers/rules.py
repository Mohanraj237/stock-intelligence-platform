"""Rule-engine: CRUD + apply to universe."""
from __future__ import annotations
import asyncio
import uuid
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import run_sync, gather_bounded
from backend.schemas import Rule, RuleSet, RuleMatchRow

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _load() -> list[dict]:
    from storage.file_store import get_rules
    return list(get_rules() or [])


def _save(rules: list[dict]) -> None:
    from storage.file_store import save_rules
    save_rules(rules)


@router.get("", response_model=List[Rule])
async def list_rules() -> List[Rule]:
    raw = await run_sync(_load)
    return [Rule(**r) for r in raw]


@router.post("", response_model=Rule)
async def create_rule(rule: Rule) -> Rule:
    rules = await run_sync(_load)
    if not rule.id:
        rule.id = uuid.uuid4().hex[:12]
    rules.append(rule.model_dump())
    await run_sync(_save, rules)
    return rule


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str) -> dict:
    rules = await run_sync(_load)
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    await run_sync(_save, new_rules)
    return {"removed": rule_id, "remaining": len(new_rules)}


class ApplyReq(BaseModel):
    universe: str = "NIFTY 50"
    ruleset: RuleSet
    max_symbols: int | None = None
    region: str = "IN"


@router.post("/apply", response_model=List[RuleMatchRow])
async def apply(req: ApplyReq) -> List[RuleMatchRow]:
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    from engines.rule_engine import apply_rules_to_universe

    if req.region == "US":
        from services.us_universe_sync import get_us_universe_symbols
        all_syms = await run_sync(get_us_universe_symbols, req.universe)
        syms = (all_syms or [])[:req.max_symbols] if req.max_symbols else (all_syms or [])
    else:
        from services.universe_sync import get_universe_symbols
        syms = await run_sync(get_universe_symbols, req.universe, req.max_symbols)

    funda_fn = None
    if req.region != "US":
        from services.screener_service import get_full_screener_data as funda_fn

    async def _gather(sym: str) -> dict | None:
        df = await run_sync(get_ohlcv_history, sym, "1y", "1d", req.region)
        ind = await run_sync(compute_indicators_from_ohlcv, df) if df is not None else {}
        funda = await run_sync(funda_fn, sym) if funda_fn else {}
        return {"symbol": sym, "indicators": ind, "fundamentals": funda or {}, "close": ind.get("close")}

    stocks = [s for s in await gather_bounded(*[_gather(s) for s in syms], limit=12) if s]
    rules_dicts = [r.model_dump() for r in req.ruleset.rules]
    matches = await run_sync(apply_rules_to_universe, rules_dicts, stocks, req.ruleset.cross_logic.value)
    out: list[RuleMatchRow] = []
    for m in (matches or []):
        out.append(RuleMatchRow(
            symbol=m.get("symbol", ""),
            company=m.get("company"),
            last_price=m.get("close") or m.get("last_price"),
            change_pct=m.get("change_pct"),
            rules_passed=list(m.get("rules_passed", [])),
            rules_failed=list(m.get("rules_failed", [])),
            pass_count=int(m.get("pass_count", 0)),
        ))
    return out
