from __future__ import annotations
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

st.set_page_config(
    page_title="Stock Intelligence Platform",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Indian Stock AI Research Terminal — Yahoo Finance · NSE India · Screener.in · Moneycontrol/ET RSS"},
)

from utils.theme import apply_theme
apply_theme()

# ── Background startup ────────────────────────────────────────────────────────
def _background_startup(region: str = "IN"):
    try:
        from storage.file_store import ensure_dirs, get_settings
        ensure_dirs()
        s = get_settings()
        csrf = s.get("screener_csrf", "")
        sid  = s.get("screener_session", "")
        if csrf and sid:
            from services.screener_service import configure_session
            configure_session(csrf, sid)
        if region == "US":
            from services.us_universe_sync import us_startup_sync
            us_startup_sync(parallel=True)
        else:
            from services.universe_sync import startup_sync
            startup_sync(parallel=True)
    except Exception:
        pass

if "startup_done" not in st.session_state:
    st.session_state.startup_done = True
    from storage.file_store import get_settings as _gs
    _initial_region = _gs().get("market_region", "IN")
    if "market_region" not in st.session_state:
        st.session_state["market_region"] = _initial_region
    threading.Thread(target=_background_startup, args=(_initial_region,), daemon=True).start()

# ── Market Region Toggle ──────────────────────────────────────────────────────
from utils.theme import GREEN, RED, TEXT, TEXT_DIM, CARD, BORDER, BLUE

_current_region = st.session_state.get("market_region", "IN")

# Sidebar toggle (above nav items)
with st.sidebar:
    _region_choice = st.radio(
        "🌍 Market Region",
        options=["🇮🇳 India", "🇺🇸 United States"],
        index=0 if _current_region == "IN" else 1,
        horizontal=True,
        key="market_region_radio",
    )

_new_region = "US" if "United States" in _region_choice else "IN"
if _new_region != _current_region:
    st.session_state["market_region"] = _new_region
    # Clear all page-level data caches so stale region data doesn't persist
    _PAGE_DATA_KEYS = [
        "dash_movers_data", "dash_sector_data", "dash_fii_data",
        "dash_uni_data", "dash_uni_data_key",
        "ue_tv_data", "ue_symbols", "_ue_key",
        "news_data", "news_anns",
        "ec_upcoming", "ec_recent_data",
        "bt_result",
        "pl_table", "pl_details", "pl_stats", "pl_ss",
        "_sa_cache_key", "_sa_tv", "_sa_screener", "_sa_nse", "_sa_ohlcv",
        "cmp_tv", "cmp_screener", "cmp_ohlcv", "_cmp_key",
    ]
    for _k in _PAGE_DATA_KEYS:
        st.session_state.pop(_k, None)
    from storage.file_store import get_settings as _gs2, save_settings as _ss
    _s = _gs2()
    _s["market_region"] = _new_region
    _ss(_s)
    st.cache_data.clear()
    # Trigger background universe sync for the new region
    threading.Thread(target=_background_startup, args=(_new_region,), daemon=True).start()
    st.rerun()

# ── Navigation — controls exactly what appears in the sidebar ─────────────────
_pages_dir = Path(__file__).resolve().parent / "pages"

def _page(filename, **kwargs):
    return st.Page(str((_pages_dir / filename).resolve()), **kwargs)

pg = st.navigation(
    {
        "Market": [
            _page("1_Dashboard.py",         title="Dashboard",         icon="📊"),
            _page("2_Universe_Explorer.py", title="Universe Explorer", icon="🌐"),
            _page("14_News.py",             title="News",              icon="📰"),
            _page("13_Earnings_Calendar.py", title="Earnings Calendar", icon="📅"),
        ],
        "Analysis": [
            _page("3_Stock_Analyzer.py",    title="Stock Analyzer",    icon="🔍"),
            _page("4_Scanner.py",           title="Scanner",           icon="📡"),
            _page("5_Pattern_Lab.py",       title="Pattern Lab",       icon="🧬"),
            _page("11_Compare.py",          title="Compare",           icon="⚖️"),
            _page("15_Backtest.py",         title="Backtest",          icon="📊"),
        ],
        "Tools": [
            _page("12_Position_Sizing.py",  title="Position Sizing",   icon="💰"),
            _page("6_Rule_Engine.py",       title="Rule Engine",       icon="⚙️"),
            _page("7_Portfolio.py",         title="Portfolio",         icon="💼"),
            _page("8_Watchlist.py",         title="Watchlist",         icon="⭐"),
            _page("9_Reports.py",           title="Reports",           icon="📄"),
            _page("10_Settings.py",         title="Settings",          icon="🛠️"),
        ],
        "Help": [
            _page("16_Learn.py",            title="Learn",             icon="🎓"),
        ],
    },
    position="sidebar",
)

pg.run()
