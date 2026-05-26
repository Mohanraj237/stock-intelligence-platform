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
def _background_startup():
    try:
        from storage.file_store import ensure_dirs, get_settings
        ensure_dirs()
        s = get_settings()
        csrf = s.get("screener_csrf", "")
        sid  = s.get("screener_session", "")
        if csrf and sid:
            from services.screener_service import configure_session
            configure_session(csrf, sid)
        from services.universe_sync import startup_sync
        startup_sync(parallel=True)
    except Exception:
        pass

if "startup_done" not in st.session_state:
    st.session_state.startup_done = True
    threading.Thread(target=_background_startup, daemon=True).start()

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
