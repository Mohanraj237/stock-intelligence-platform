"""Shared dependencies + async helpers.

Strategy: existing services are sync (requests-based). We wrap them in
asyncio.to_thread so FastAPI workers don't block on I/O. For bulk ops we
hand off to a shared ProcessPoolExecutor / ThreadPoolExecutor from
backend.config.
"""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, partial
from typing import Any, Callable, TypeVar, ParamSpec, Awaitable

from backend.config import get_settings

P = ParamSpec("P")
R = TypeVar("R")


@lru_cache
def thread_pool() -> ThreadPoolExecutor:
    s = get_settings()
    return ThreadPoolExecutor(max_workers=s.max_workers, thread_name_prefix="sip-svc")


async def run_sync(fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    """Run a blocking sync function in the shared thread pool."""
    loop = asyncio.get_running_loop()
    if kwargs:
        fn = partial(fn, **kwargs)  # type: ignore[assignment]
    return await loop.run_in_executor(thread_pool(), fn, *args)  # type: ignore[arg-type]


async def gather_bounded(*aws: Awaitable[R], limit: int = 16,
                          return_exceptions: bool = True) -> list[R | BaseException]:
    """asyncio.gather with concurrency cap. Defaults to return_exceptions=True
    so a single failing task never aborts the whole batch — callers should
    filter out BaseException entries."""
    sem = asyncio.Semaphore(limit)

    async def _with_sem(coro: Awaitable[R]) -> R:
        async with sem:
            return await coro

    return await asyncio.gather(
        *(_with_sem(c) for c in aws),
        return_exceptions=return_exceptions,
    )
