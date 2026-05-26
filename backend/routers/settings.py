"""Settings GET + PATCH."""
from __future__ import annotations
from fastapi import APIRouter

from backend.deps import run_sync
from backend.schemas import AppSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_settings() -> AppSettings:
    from storage.file_store import get_settings as gs
    raw = await run_sync(gs) or {}
    return AppSettings(**{k: v for k, v in raw.items() if k in AppSettings.model_fields})


@router.patch("", response_model=AppSettings)
async def patch_settings(patch: AppSettings) -> AppSettings:
    from storage.file_store import get_settings as gs, save_settings as ss
    cur = await run_sync(gs) or {}
    cur.update(patch.model_dump(exclude_unset=True))
    await run_sync(ss, cur)
    return AppSettings(**{k: v for k, v in cur.items() if k in AppSettings.model_fields})
