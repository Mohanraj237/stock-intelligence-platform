"""Backend configuration."""
from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Environment-driven settings (12-factor)."""
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    # Local-first dev tool — no public deployment. Allow any origin so the app
    # works whether you open it at localhost:3001, 127.0.0.1:3001, the LAN IP
    # (192.168.x.x), or a Tailscale/ngrok hostname. Starlette will echo the
    # actual Origin back in Access-Control-Allow-Origin (compatible with
    # allow_credentials=True; the wildcard "*" wouldn't be).
    cors_origin_regex: str = r".*"
    max_workers: int = 16
    log_level: str = "INFO"


@lru_cache
def get_settings() -> BackendSettings:
    return BackendSettings()
