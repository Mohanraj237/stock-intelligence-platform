"""App settings schema."""
from __future__ import annotations
from typing import Optional, Dict
from pydantic import BaseModel


class AppSettings(BaseModel):
    refresh_interval_sec: int = 60
    default_universe: str = "NIFTY 50"
    max_parallel_workers: int = 8
    screener_csrf: Optional[str] = None
    screener_session: Optional[str] = None
    screener_cache_ttl_hours: int = 6
    market_cache_ttl_min: int = 5
    universe_cache_ttl_hours: int = 24
