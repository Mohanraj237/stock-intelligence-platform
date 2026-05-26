from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd


from utils.theme import apply_theme
apply_theme()

from storage.file_store import get_settings, save_settings, DIRS
from storage.cache_manager import invalidate_prefix
from services.universe_sync import startup_sync, universe_sync_status

st.markdown("## 🛠️ Settings")

tabs = st.tabs(["⚙️ General", "📊 Data Sources", "🌐 Universe Sync", "🗄️ Storage", "ℹ️ About"])

# ── Tab 0: General ────────────────────────────────────────────────────────────
with tabs[0]:
    settings = get_settings()
    st.markdown("### General Settings")
    with st.form("general_settings"):
        refresh_interval = st.number_input("Data Refresh Interval (seconds)",
                                            min_value=60, max_value=3600,
                                            value=int(settings.get("refresh_interval", 300)))
        default_universe = st.selectbox("Default Universe",
                                         ["NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY MIDCAP 150",
                                          "NIFTY SMALLCAP 250", "NIFTY BANK", "NIFTY IT"],
                                         index=["NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY MIDCAP 150",
                                                "NIFTY SMALLCAP 250", "NIFTY BANK", "NIFTY IT"].index(
                                             settings.get("default_universe", "NIFTY 50")))
        max_workers = st.slider("Max Parallel Workers", 1, 20, int(settings.get("max_workers", 8)))
        if st.form_submit_button("💾 Save Settings", type="primary"):
            settings.update({"refresh_interval": refresh_interval, "default_universe": default_universe,
                              "max_workers": max_workers})
            save_settings(settings)
            st.success("Settings saved!")

# ── Tab 1: Data Sources ────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("### Data Source Configuration")
    settings = get_settings()

    with st.form("data_source_settings"):
        st.markdown("**Screener.in**")
        screener_csrf = st.text_input("Screener.in CSRF Token (optional)",
                                       value=settings.get("screener_csrf", ""),
                                       type="password", help="csrftoken cookie from browser DevTools")
        screener_session = st.text_input("Screener.in Session ID (optional)",
                                          value=settings.get("screener_session", ""),
                                          type="password", help="sessionid cookie from browser DevTools")

        st.markdown("**Cache TTL**")
        c1, c2, c3 = st.columns(3)
        with c1:
            ttl_screener = st.number_input("Screener cache (seconds)",
                                            value=int(settings.get("cache_ttl_screener", 21600)), min_value=300)
        with c2:
            ttl_market = st.number_input("Market data cache (seconds)",
                                      value=int(settings.get("cache_ttl_tv", 900)), min_value=60)
        with c3:
            ttl_universe = st.number_input("Universe cache (seconds)",
                                            value=int(settings.get("cache_ttl_universe", 86400)), min_value=3600)

        if st.form_submit_button("💾 Save Data Settings", type="primary"):
            settings.update({
                "screener_csrf": screener_csrf,
                "screener_session": screener_session,
                "cache_ttl_screener": ttl_screener,
                "cache_ttl_tv": ttl_market,
                "cache_ttl_universe": ttl_universe,
            })
            save_settings(settings)
            # Apply Screener session immediately if both provided
            if screener_csrf and screener_session:
                from services.screener_service import configure_session
                configure_session(screener_csrf, screener_session)
                st.success("Data settings saved! Screener.in session activated.")
            else:
                st.success("Data settings saved!")

    st.markdown("---")
    st.markdown("### Test Connections")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🧪 Test Market Data (Yahoo)"):
            from services.market_data_service import scan_market_bulk
            try:
                result = scan_market_bulk(["RELIANCE", "TCS", "INFY"])
                if result:
                    sample = result.get("RELIANCE") or next(iter(result.values()))
                    ind = sample.get("indicators", {})
                    rec = sample.get("recommendation", "N/A")
                    st.success(f"Yahoo Finance OK ✅ — {len(result)} stocks fetched. RELIANCE: {rec}, RSI={ind.get('rsi','—')}, Price=₹{ind.get('close','—')}")
                else:
                    st.error("Yahoo Finance returned no data.")
            except Exception as e:
                st.error(f"Yahoo Finance error: {e}")
    with col2:
        if st.button("🧪 Test Screener.in"):
            from services.screener_service import get_full_screener_data, get_screener_status
            try:
                status = get_screener_status()
                result = get_full_screener_data("RELIANCE")
                auth_tag = "🔐 Auth" if status.get("authenticated") else "🔓 Anon"
                if result and result.get("ratios"):
                    ratios = result["ratios"]
                    st.success(f"Screener.in OK ({auth_tag}): PE={ratios.get('pe')}, ROE={ratios.get('roe')}, OPM={ratios.get('opm')}, Insights={len(result.get('insights', []))}")
                else:
                    st.warning("Screener.in returned partial data.")
            except Exception as e:
                st.error(f"Screener.in error: {e}")
    with col3:
        if st.button("🧪 Test NSE India"):
            from services.nse_service import get_index_quotes, get_market_status
            try:
                mkt = get_market_status()
                stocks = get_index_quotes("NIFTY 50")
                nifty_price = mkt.get("nifty", "—")
                nifty_pct = mkt.get("pct", 0)
                mkt_status = mkt.get("message", "—")
                st.success(f"NSE India OK ✅ — NIFTY 50: ₹{nifty_price} ({nifty_pct:+.2f}%) · {mkt_status} · {len(stocks)} stocks in index")
            except Exception as e:
                st.error(f"NSE India error: {e}")

# ── Tab 2: Universe Sync ───────────────────────────────────────────────────────
with tabs[2]:
    st.markdown("### Universe Sync Status")
    try:
        status = universe_sync_status()
        rows = [{"Universe": n, "Stocks": v.get("count", 0), "Age (h)": v.get("age_hours", "N/A"),
                 "Status": "✅" if v.get("synced") else "❌", "Fallback": "⚠️" if v.get("fallback") else ""}
                for n, v in status.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    except Exception as e:
        st.error(f"Error loading sync status: {e}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Sync All Universes", type="primary"):
            with st.spinner("Syncing all universes from NSE..."):
                results = startup_sync(parallel=True)
            ok = sum(1 for v in results.values() if v.get("ok"))
            st.success(f"Synced {ok}/{len(results)} universes.")
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Universe Cache"):
            invalidate_prefix("universe")
            st.success("Universe cache cleared.")

# ── Tab 3: Storage ─────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("### Local Storage")
    st.markdown("All data is stored locally in the `storage/` directory.")
    for name, path in DIRS.items():
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024
        count = sum(1 for f in path.rglob("*") if f.is_file())
        st.markdown(f"📁 **{name}**: `{path}` — {count} files, {size:.1f} KB")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear All Cache"):
            invalidate_prefix("screener")
            invalidate_prefix("tv_analysis")
            invalidate_prefix("quote")
            st.success("All caches cleared.")
    with col2:
        if st.button("🗑️ Clear Screener Cache"):
            invalidate_prefix("screener")
            st.success("Screener cache cleared.")

# ── Tab 4: About ──────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown("### About Stock Intelligence Platform")
    st.markdown("""
**Version:** 2.0 — Full Local File System Edition

**Data Sources:**
- 📈 **Yahoo Finance** — OHLCV history; technical indicators computed locally with `ta`
- 🇮🇳 **NSE India** — Live quotes, index constituents, FII/DII flows, market status
- 📊 **Screener.in** — Company fundamentals, P&L, Balance Sheet, Cash Flow, Shareholding
- 📰 **Moneycontrol / ET RSS** — News headlines (no API key needed)

**Analysis Engines:**
- Pattern Engine — 10 chart patterns with backtest stats
- Rule Engine — Visual rule builder with AND/OR logic
- Filter Engine — 25+ multi-criteria filters with presets
- Scoring Engine — Composite 0-100 score (45% Tech + 40% Funda + 15% TV)

**Storage:**
- 100% local — all data in `storage/` directory
- JSON cache with TTL
- No external database required

**Universe Support:**
- 16+ NSE indices (NIFTY 50, 100, 200, 500, Midcap, Smallcap, sector indices)
- Background sync on startup
""")
    st.markdown("---")
    st.markdown("Built with Streamlit + Yahoo Finance + NSE India + Screener.in")
