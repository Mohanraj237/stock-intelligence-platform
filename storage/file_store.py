from __future__ import annotations
import json
import csv
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"

DIRS = {
    "cache": STORAGE_DIR / "cache",
    "data": STORAGE_DIR / "data",
    "reports": STORAGE_DIR / "reports",
    "config": STORAGE_DIR / "config",
    "sessions": STORAGE_DIR / "sessions",
    "logs": STORAGE_DIR / "logs",
    "universe": STORAGE_DIR / "universe",
}

def ensure_dirs():
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)

def read_json(path: Path, default=None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
    return default

def write_json(path: Path, data: Any):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows: list[dict], fieldnames: list[str] = None):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

# ── Watchlist ──────────────────────────────────────────────────────────────
_WATCHLIST_PATH = DIRS["config"] / "watchlist.json"
_DEFAULT_WATCHLIST = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "TATAMOTORS", "WIPRO", "AXISBANK"]

def get_watchlist() -> list[str]:
    data = read_json(_WATCHLIST_PATH, {"symbols": _DEFAULT_WATCHLIST})
    return data.get("symbols", _DEFAULT_WATCHLIST)

def save_watchlist(symbols: list[str]):
    write_json(_WATCHLIST_PATH, {"symbols": list(dict.fromkeys(s.upper().strip() for s in symbols if s.strip())), "updated_at": datetime.now().isoformat()})

def add_to_watchlist(symbol: str):
    current = get_watchlist()
    sym = symbol.upper().strip()
    if sym not in current:
        current.append(sym)
        save_watchlist(current)

def remove_from_watchlist(symbol: str):
    current = get_watchlist()
    sym = symbol.upper().strip()
    save_watchlist([s for s in current if s != sym])

# ── Settings ───────────────────────────────────────────────────────────────
_SETTINGS_PATH = DIRS["config"] / "settings.json"
_DEFAULT_SETTINGS = {
    "refresh_interval": 300,
    "theme": "dark",
    "market_region": "IN",
    "default_universe": "NIFTY 50",
    "default_us_universe": "S&P 500",
    "max_workers": 8,
    "cache_ttl_screener": 21600,
    "cache_ttl_tv": 900,
    "cache_ttl_universe": 86400,
    "screener_csrf": "",
    "screener_session": "",
}

_LEGACY_SETTINGS_KEYS = {"tv_session"}

def get_settings() -> dict:
    data = read_json(_SETTINGS_PATH, {})
    data = {k: v for k, v in data.items() if k not in _LEGACY_SETTINGS_KEYS}
    return {**_DEFAULT_SETTINGS, **data}

def save_settings(settings: dict):
    cleaned = {k: v for k, v in settings.items() if k not in _LEGACY_SETTINGS_KEYS}
    cleaned["updated_at"] = datetime.now().isoformat()
    write_json(_SETTINGS_PATH, cleaned)


def get_anthropic_key() -> str:
    """Return stored Anthropic API key (empty string if not set)."""
    return get_settings().get("anthropic_api_key", "")


def save_anthropic_key(key: str):
    """Persist Anthropic API key in settings (never logged)."""
    s = get_settings()
    s["anthropic_api_key"] = key.strip()
    save_settings(s)

# ── Confluence scoring weights ───────────────────────────────────────────────
_SCORING_CONFIG_PATH = DIRS["config"] / "scoring.json"
_DEFAULT_SCORING_CONFIG = {
    "trend_weight": 30, "momentum_weight": 25, "volume_weight": 15,
    "candle_weight": 25, "structural_weight": 5, "default_threshold": 65,
}

def get_scoring_config() -> dict:
    data = read_json(_SCORING_CONFIG_PATH, {})
    return {**_DEFAULT_SCORING_CONFIG, **data}

def save_scoring_config(config: dict):
    cleaned = {k: v for k, v in config.items() if k in _DEFAULT_SCORING_CONFIG}
    cleaned["updated_at"] = datetime.now().isoformat()
    write_json(_SCORING_CONFIG_PATH, cleaned)

def reset_scoring_config():
    write_json(_SCORING_CONFIG_PATH, {})

# ── Rules ──────────────────────────────────────────────────────────────────
_RULES_PATH = DIRS["config"] / "rules.json"

def get_rules() -> list[dict]:
    data = read_json(_RULES_PATH, {"rules": []})
    return data.get("rules", [])

def save_rules(rules: list[dict]):
    write_json(_RULES_PATH, {"rules": rules, "updated_at": datetime.now().isoformat()})

def add_rule(rule: dict):
    rules = get_rules()
    rule["id"] = f"rule_{int(time.time())}_{len(rules)}"
    rule["created_at"] = datetime.now().isoformat()
    rules.append(rule)
    save_rules(rules)
    return rule["id"]

def delete_rule(rule_id: str):
    rules = [r for r in get_rules() if r.get("id") != rule_id]
    save_rules(rules)

# ── Portfolio ──────────────────────────────────────────────────────────────
_PORTFOLIO_PATH = DIRS["config"] / "portfolio.json"

def get_portfolio() -> dict:
    return read_json(_PORTFOLIO_PATH, {"holdings": [], "updated_at": datetime.now().isoformat()})

def save_portfolio(portfolio: dict):
    portfolio["updated_at"] = datetime.now().isoformat()
    write_json(_PORTFOLIO_PATH, portfolio)

def get_holdings() -> list[dict]:
    return get_portfolio().get("holdings", [])

def add_holding(symbol: str, qty: float, buy_price: float, buy_date: str = None):
    portfolio = get_portfolio()
    holdings = portfolio.get("holdings", [])
    holdings.append({
        "symbol": symbol.upper().strip(),
        "qty": qty,
        "buy_price": buy_price,
        "buy_date": buy_date or datetime.now().strftime("%Y-%m-%d"),
        "added_at": datetime.now().isoformat(),
    })
    portfolio["holdings"] = holdings
    save_portfolio(portfolio)

def remove_holding(symbol: str):
    portfolio = get_portfolio()
    portfolio["holdings"] = [h for h in portfolio.get("holdings", []) if h.get("symbol") != symbol.upper()]
    save_portfolio(portfolio)

# ── Reports Index ──────────────────────────────────────────────────────────
_REPORTS_INDEX_PATH = DIRS["config"] / "reports_index.json"

def get_reports_index() -> list[dict]:
    data = read_json(_REPORTS_INDEX_PATH, {"reports": []})
    return data.get("reports", [])

def add_report_entry(symbol: str, report_type: str, filename: str):
    idx = get_reports_index()
    idx.append({"symbol": symbol, "type": report_type, "file": filename, "created_at": datetime.now().isoformat()})
    write_json(_REPORTS_INDEX_PATH, {"reports": idx})

# ── Saved Scans ────────────────────────────────────────────────────────────
_SCANS_PATH = DIRS["config"] / "saved_scans.json"

def get_saved_scans() -> list[dict]:
    data = read_json(_SCANS_PATH, {"scans": []})
    return data.get("scans", [])

def save_scan_result(name: str, symbols: list[str], filters: dict, results_file: str):
    scans = get_saved_scans()
    scans.append({"name": name, "symbols": symbols, "filters": filters, "results_file": results_file, "created_at": datetime.now().isoformat()})
    write_json(_SCANS_PATH, {"scans": scans})

# ── Session Metadata ───────────────────────────────────────────────────────
def save_session_meta(session_id: str, data: dict):
    path = DIRS["sessions"] / f"{session_id}.json"
    data["session_id"] = session_id
    data["updated_at"] = datetime.now().isoformat()
    write_json(path, data)

def get_session_meta(session_id: str) -> dict:
    path = DIRS["sessions"] / f"{session_id}.json"
    return read_json(path, {})

# ── Log helpers ────────────────────────────────────────────────────────────
def append_log(name: str, entry: dict):
    path = DIRS["logs"] / f"{name}.jsonl"
    entry["ts"] = datetime.now().isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
