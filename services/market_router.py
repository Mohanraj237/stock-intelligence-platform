"""
Market Router — region-aware data routing layer.

All pages should import market data functions from here instead of
calling nse_service / universe_sync / us_market_service directly.
The router reads st.session_state["market_region"] ("IN" or "US") and
dispatches to the correct backend.

Public API (mirrors both Indian and US service APIs):
  get_region()                   → "IN" | "US"
  get_universe_names()           → list[str]
  get_universe_display_map()     → dict[str, str]
  get_universe_symbols(name)     → list[str]
  scan_symbols_bulk(symbols)     → dict[str, dict]
  get_index_quotes(index_name)   → list[dict]
  get_market_status()            → dict
  get_quote(symbol)              → dict
  get_index_performance()        → list[dict]
  get_sector_performance()       → list[dict]
  get_ohlcv_history(symbol, ...) → pd.DataFrame | None
  get_market_analysis(symbol)    → dict | None
  get_fundamentals(symbol)       → dict

  fmt_currency(value)            → "₹1,234.56" or "$1,234.56"
  fmt_volume(value)              → "1.2L" or "1.2M"
  fmt_market_cap(value)          → "₹5.2Cr" or "$250B"
  currency_symbol()              → "₹" or "$"
"""
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Region detection
# ─────────────────────────────────────────────────────────────────────────────

def get_region() -> str:
    """Return 'IN' or 'US' based on session state, then settings fallback."""
    try:
        import streamlit as st
        r = st.session_state.get("market_region")
        if r in ("IN", "US"):
            return r
    except Exception:
        pass
    try:
        from storage.file_store import get_settings
        return get_settings().get("market_region", "IN")
    except Exception:
        return "IN"


def is_us() -> bool:
    return get_region() == "US"


# ─────────────────────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────────────────────

def get_universe_names() -> List[str]:
    if is_us():
        from services.us_universe_sync import get_all_us_universe_names
        return get_all_us_universe_names()
    else:
        from services.universe_sync import get_all_universe_names
        return get_all_universe_names()


def get_universe_display_map() -> Dict[str, str]:
    if is_us():
        from services.us_universe_sync import us_universe_display_map
        return us_universe_display_map()
    else:
        from services.universe_sync import universe_display_map
        return universe_display_map()


def get_universe_symbols(name: str, limit: Optional[int] = None, force_refresh: bool = False) -> List[str]:
    if is_us():
        from services.us_universe_sync import get_us_universe_symbols
        return get_us_universe_symbols(name, limit=limit, force_refresh=force_refresh)
    else:
        from services.universe_sync import get_universe_symbols
        return get_universe_symbols(name, limit=limit, force_refresh=force_refresh)


# ─────────────────────────────────────────────────────────────────────────────
# Market data
# ─────────────────────────────────────────────────────────────────────────────

def get_market_status() -> dict:
    if is_us():
        from services.us_market_service import get_market_status as _us
        return _us()
    else:
        from services.nse_service import get_market_status as _in
        return _in()


def get_index_quotes(index_name: str) -> List[dict]:
    if is_us():
        from services.us_market_service import get_index_quotes as _us
        return _us(index_name)
    else:
        from services.nse_service import get_index_quotes as _in
        return _in(index_name)


def get_quote(symbol: str) -> Optional[dict]:
    if is_us():
        from services.us_market_service import get_quote as _us
        return _us(symbol)
    else:
        from services.nse_service import get_quote as _in
        return _in(symbol)


def get_bulk_quotes(symbols: List[str], max_workers: int = 8) -> Dict[str, dict]:
    if is_us():
        from services.us_market_service import get_bulk_quotes as _us
        return _us(symbols, max_workers=max_workers)
    else:
        from services.nse_service import get_bulk_quotes as _in
        return _in(symbols, max_workers=max_workers)


def get_index_performance() -> List[dict]:
    if is_us():
        from services.us_market_service import get_index_performance as _us
        return _us()
    else:
        from services.nse_service import get_index_performance as _in
        return _in()


def get_sector_performance() -> List[dict]:
    if is_us():
        from services.us_market_service import get_sector_performance as _us
        return _us()
    else:
        from services.nse_service import get_sector_performance as _in
        return _in()


# ─────────────────────────────────────────────────────────────────────────────
# Technical analysis (OHLCV + indicators)
# ─────────────────────────────────────────────────────────────────────────────

def get_ohlcv_history(symbol: str, period: str = "1y", interval: str = "1d"):
    """Fetch OHLCV history. Uses .NS suffix for India, no suffix for US."""
    from services.market_data_service import get_ohlcv_history as _ohlcv
    region = get_region()
    return _ohlcv(symbol, period=period, interval=interval, region=region)


def get_market_analysis(symbol: str, interval: str = "1d") -> Optional[Dict[str, Any]]:
    """Fetch OHLCV, compute indicators, derive recommendation."""
    from services.market_data_service import get_market_analysis as _analysis
    region = get_region()
    return _analysis(symbol, interval=interval, region=region)


def scan_symbols_bulk(symbols: List[str], max_workers: int = 8) -> Dict[str, Dict]:
    """Parallel OHLCV + indicator fetch for many symbols."""
    from services.market_data_service import scan_market_bulk as _bulk
    region = get_region()
    return _bulk(symbols, max_workers=max_workers, region=region)


# Alias used by Universe Explorer and Scanner (backwards compat)
scan_market_bulk = scan_symbols_bulk


def tv_score(recommendation: str) -> int:
    """Convert recommendation string to numeric score 0-100."""
    from services.market_data_service import score_signal
    return score_signal(recommendation)


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals
# ─────────────────────────────────────────────────────────────────────────────

def get_fundamentals(symbol: str) -> dict:
    """Get company fundamentals (Screener.in for IN, Yahoo Finance for US)."""
    if is_us():
        from services.us_market_service import get_us_fundamentals
        return get_us_fundamentals(symbol)
    else:
        from services.screener_service import get_full_screener_data
        return get_full_screener_data(symbol) or {}


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def currency_symbol() -> str:
    return "$" if is_us() else "₹"


def fmt_currency(value, decimals: int = 2) -> str:
    """Format a price value with the region's currency symbol."""
    sym = currency_symbol()
    try:
        return f"{sym}{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def fmt_volume(value) -> str:
    """Format volume: Indian uses Lakhs/Crores, US uses K/M/B."""
    try:
        v = float(value)
        if is_us():
            if v >= 1e9:  return f"{v/1e9:.2f}B"
            if v >= 1e6:  return f"{v/1e6:.2f}M"
            if v >= 1e3:  return f"{v/1e3:.1f}K"
            return str(int(v))
        else:
            if v >= 1e7:  return f"{v/1e7:.2f}Cr"
            if v >= 1e5:  return f"{v/1e5:.2f}L"
            return str(int(v))
    except (TypeError, ValueError):
        return "—"


def fmt_market_cap(value) -> str:
    """Format market cap with appropriate scale."""
    try:
        v = float(value)
        if is_us():
            if v >= 1e12: return f"${v/1e12:.2f}T"
            if v >= 1e9:  return f"${v/1e9:.2f}B"
            if v >= 1e6:  return f"${v/1e6:.2f}M"
            return f"${v:,.0f}"
        else:
            # Indian: value in Crores already
            if v >= 1e5:  return f"₹{v/1e5:.2f}L Cr"
            return f"₹{v:,.0f} Cr"
    except (TypeError, ValueError):
        return "—"


def fmt_price_row(price) -> str:
    """Format price with currency symbol for table display."""
    return fmt_currency(price)


# ─────────────────────────────────────────────────────────────────────────────
# Startup helpers
# ─────────────────────────────────────────────────────────────────────────────

def startup_sync_for_region(region: str) -> dict:
    """Trigger universe sync for the given region."""
    if region == "US":
        from services.us_universe_sync import us_startup_sync
        return us_startup_sync(parallel=True)
    else:
        from services.universe_sync import startup_sync
        return startup_sync(parallel=True)


def get_default_universe() -> str:
    """Return the default universe name for the active region."""
    if is_us():
        return "S&P 500"
    else:
        from storage.file_store import get_settings
        return get_settings().get("default_universe", "NIFTY 50")
