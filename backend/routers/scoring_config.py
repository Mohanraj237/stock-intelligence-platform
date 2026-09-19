"""Confluence-scoring config GET/PATCH/reset — user-editable category weights.

Persisted separately from AppSettings/settings.json (storage/config/scoring.json)
since this is a distinct, structured config object rather than a flat settings
blob — mirrors the watchlist.json / rules.json sibling-file convention.
"""
from __future__ import annotations
from fastapi import APIRouter

from backend.deps import run_sync
from backend.schemas import ScoringConfig

router = APIRouter(prefix="/api/scoring-config", tags=["scoring-config"])


@router.get("", response_model=ScoringConfig)
async def get_scoring_config() -> ScoringConfig:
    from storage.file_store import get_scoring_config as gsc
    raw = await run_sync(gsc) or {}
    return ScoringConfig(**{k: v for k, v in raw.items() if k in ScoringConfig.model_fields})


@router.patch("", response_model=ScoringConfig)
async def patch_scoring_config(patch: ScoringConfig) -> ScoringConfig:
    from storage.file_store import get_scoring_config as gsc, save_scoring_config as ssc
    cur = await run_sync(gsc) or {}
    cur.update(patch.model_dump(exclude_unset=True))
    await run_sync(ssc, cur)
    return ScoringConfig(**{k: v for k, v in cur.items() if k in ScoringConfig.model_fields})


@router.post("/reset", response_model=ScoringConfig)
async def reset_scoring_config() -> ScoringConfig:
    from storage.file_store import reset_scoring_config as rsc, get_scoring_config as gsc
    await run_sync(rsc)
    raw = await run_sync(gsc) or {}
    return ScoringConfig(**{k: v for k, v in raw.items() if k in ScoringConfig.model_fields})
