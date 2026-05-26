"""FastAPI entry point — mounts every domain router."""
from __future__ import annotations
import logging
import sys
import time
import traceback
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Silence noisy upstream deprecations (numpy / pandas / ta library).
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class ConditionalGZipMiddleware:
    """GZipMiddleware that bypasses paths ending in /stream — those are SSE
    endpoints, and gzip buffering breaks the real-time event flow because
    chunks get accumulated for compression before being flushed."""

    def __init__(self, app: ASGIApp, minimum_size: int = 500, compresslevel: int = 9):
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path", "").endswith("/stream"):
            await self.app(scope, receive, send)
            return
        await self._gzip(scope, receive, send)

from backend import __version__
from backend.config import get_settings
from backend.routers import (
    market, stocks, patterns, scans, news, earnings, positions,
    backtests, portfolio, watchlist, rules, universe, settings as settings_router,
    reports,
)

# ─────────────────────────────────────────────────────────────────────────────
# Logging — both stdout (uvicorn console) and rotating file at storage/logs/backend.log
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / "storage" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_handlers: list[logging.Handler] = [
    logging.StreamHandler(sys.stdout),
    RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
]
for h in _handlers:
    h.setFormatter(logging.Formatter(_fmt))
root = logging.getLogger()
root.handlers = _handlers
root.setLevel(logging.INFO)

log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Stock Intelligence Platform backend v%s starting (log: %s)", __version__, LOG_FILE)
    try:
        from services.universe_sync import startup_sync
        import asyncio
        asyncio.create_task(asyncio.to_thread(startup_sync, True))
    except Exception as e:
        log.warning("Background universe sync skipped: %s", e)
    yield
    log.info("Backend shutting down")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Stock Intelligence Platform API",
        version=__version__,
        description="Indian stock-market research, scanning, AI verdicts. No API keys required.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_origin_regex=s.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=86400,  # cache preflight for a day
    )
    app.add_middleware(ConditionalGZipMiddleware, minimum_size=512)

    # ── Per-request timing log ──────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.perf_counter()
        resp = await call_next(request)
        dur = (time.perf_counter() - t0) * 1000
        if dur > 1000 or resp.status_code >= 400:
            log.info("%s %s -> %d in %.0fms",
                     request.method, request.url.path, resp.status_code, dur)
        return resp

    # ── Global exception handler ────────────────────────────────────────
    # Registered via @app.exception_handler so it runs INSIDE Starlette's
    # ExceptionMiddleware — this is the only way to actually surface
    # uncaught route exceptions to the client (middleware-based handlers
    # never see them in FastAPI).
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        tb = traceback.format_exc()
        log.error("UNCAUGHT %s %s\n%s", request.method, request.url.path, tb)
        return JSONResponse(
            status_code=500,
            content={
                "error":   "internal_server_error",
                "type":    type(exc).__name__,
                "message": str(exc) or "(no message)",
                "path":    str(request.url.path),
                "traceback": tb.splitlines()[-15:],
            },
        )

    # Domain routers
    app.include_router(market.router)
    app.include_router(stocks.router)
    app.include_router(patterns.router)
    app.include_router(scans.router)
    app.include_router(news.router)
    app.include_router(earnings.router)
    app.include_router(positions.router)
    app.include_router(backtests.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(rules.router)
    app.include_router(universe.router)
    app.include_router(settings_router.router)
    app.include_router(reports.router)

    @app.get("/api/health", tags=["meta"])
    async def health() -> JSONResponse:
        # build_marker proves the running process matches what's on disk
        marker = "v2.0.0+cors-allow-any-origin"
        return JSONResponse({"status": "ok", "version": __version__, "build": marker})

    @app.get("/api/_logs/tail", tags=["meta"])
    async def log_tail(lines: int = 200) -> dict:
        """Return the last N lines of the backend log — handy when terminal output isn't visible."""
        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            return {"file": str(LOG_FILE), "lines": text.splitlines()[-max(1, min(lines, 2000)):]}
        except FileNotFoundError:
            return {"file": str(LOG_FILE), "lines": [], "error": "no log file yet"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("backend.main:app", host=s.host, port=s.port, reload=True, log_level=s.log_level.lower())
