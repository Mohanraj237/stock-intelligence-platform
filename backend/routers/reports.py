"""PDF report generation + listing."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.deps import run_sync
from backend.schemas.common import Timeframe

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateReq(BaseModel):
    symbol: str
    timeframe: Timeframe = Timeframe.DAILY


@router.post("/generate")
async def generate(req: GenerateReq) -> dict:
    from services.pdf_report_service import build_pdf_report  # may not exist; gracefully fallback
    try:
        path = await run_sync(build_pdf_report, req.symbol, req.timeframe.value)
        return {"path": str(path), "filename": Path(path).name}
    except AttributeError:
        # Older API: try generate_report
        from services.pdf_report_service import generate_report
        path = await run_sync(generate_report, req.symbol, req.timeframe.value)
        return {"path": str(path), "filename": Path(path).name}


@router.get("/list")
async def list_reports() -> list[dict]:
    base = Path("storage/reports")
    if not base.exists():
        return []
    out = []
    for p in sorted(base.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"filename": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
    return out


@router.get("/file/{filename}")
async def get_report(filename: str) -> FileResponse:
    p = Path("storage/reports") / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(p, media_type="application/pdf", filename=filename)
