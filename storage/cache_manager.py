from __future__ import annotations
import json
import time
import logging
from pathlib import Path
from typing import Any, Optional, Callable
from storage.file_store import DIRS, ensure_dirs

logger = logging.getLogger(__name__)

TTL = {
    "universe": 86400,
    "screener": 21600,
    "tv_analysis": 900,
    "tv_history": 3600,
    "quote": 300,
    "peers": 43200,
    "pl": 86400,
    "bs": 86400,
    "cf": 86400,
    "shareholding": 86400,
}

def _cache_path(prefix: str, key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_").replace(" ", "_")
    return DIRS["cache"] / prefix / f"{safe}.json"

def get_cached(prefix: str, key: str, ttl: Optional[int] = None) -> Optional[Any]:
    path = _cache_path(prefix, key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        max_age = ttl if ttl is not None else TTL.get(prefix, 3600)
        if time.time() - raw.get("_ts", 0) > max_age:
            return None
        return raw.get("_data")
    except Exception:
        return None

def set_cached(prefix: str, key: str, data: Any):
    if data is None or data == {} or data == []:
        return
    path = _cache_path(prefix, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"_ts": time.time(), "_data": data}, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Cache write failed {prefix}/{key}: {e}")

def invalidate(prefix: str, key: str):
    path = _cache_path(prefix, key)
    if path.exists():
        path.unlink()

def invalidate_prefix(prefix: str):
    d = DIRS["cache"] / prefix
    if d.exists():
        for f in d.glob("*.json"):
            f.unlink()

def cache_age(prefix: str, key: str) -> Optional[float]:
    path = _cache_path(prefix, key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return time.time() - raw.get("_ts", 0)
    except Exception:
        return None

def is_fresh(prefix: str, key: str, ttl: Optional[int] = None) -> bool:
    age = cache_age(prefix, key)
    if age is None:
        return False
    max_age = ttl if ttl is not None else TTL.get(prefix, 3600)
    return age < max_age

def cached(prefix: str, ttl: Optional[int] = None):
    """Decorator: cache first positional arg (symbol) as key."""
    def decorator(fn: Callable):
        def wrapper(symbol: str, *args, **kwargs):
            result = get_cached(prefix, symbol, ttl)
            if result is not None:
                return result
            result = fn(symbol, *args, **kwargs)
            if result is not None:
                set_cached(prefix, symbol, result)
            return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator
