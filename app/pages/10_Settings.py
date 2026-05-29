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
from services.market_router import get_region

region = get_region()

st.markdown("## 🛠️ Settings")

tabs = st.tabs(["⚙️ General", "📊 Data Sources", "🌐 Universe Sync", "🗄️ Storage", "ℹ️ About"])

# ── Tab 0: General ────────────────────────────────────────────────────────────
with tabs[0]:
    settings = get_settings()
    st.markdown("### General Settings")
    with st.form("general_settings"):
        st.markdown("**Market Region**")
        market_region = st.radio(
            "Active Market",
            options=["🇮🇳 India (NSE)", "🇺🇸 United States (NYSE/NASDAQ)"],
            index=0 if settings.get("market_region", "IN") == "IN" else 1,
            horizontal=True,
        )
        new_region = "US" if "United States" in market_region else "IN"

        st.markdown("---")
        st.markdown("**Performance**")
        refresh_interval = st.number_input(
            "Data Refresh Interval (seconds)",
            min_value=60, max_value=3600,
            value=int(settings.get("refresh_interval", 300)),
        )
        max_workers = st.slider("Max Parallel Workers", 1, 20, int(settings.get("max_workers", 8)))

        st.markdown("**Default Universe**")
        _DEFAULT_INDIA_UNI = "NIFTY 50"
        _DEFAULT_US_UNI = "S&P 500"
        c1, c2 = st.columns(2)
        with c1:
            india_universes = [
                _DEFAULT_INDIA_UNI, "NIFTY 100", "NIFTY 200", "NIFTY MIDCAP 150",
                "NIFTY SMALLCAP 250", "NIFTY BANK", "NIFTY IT",
            ]
            cur_india = settings.get("default_universe", _DEFAULT_INDIA_UNI)
            if cur_india not in india_universes:
                cur_india = _DEFAULT_INDIA_UNI
            default_universe = st.selectbox(
                "Default Indian Universe",
                india_universes,
                index=india_universes.index(cur_india),
            )
        with c2:
            us_universes = [_DEFAULT_US_UNI, "NASDAQ 100", "DOW 30", "US TECHNOLOGY", "US FINANCIALS"]
            cur_us = settings.get("default_us_universe", _DEFAULT_US_UNI)
            if cur_us not in us_universes:
                cur_us = _DEFAULT_US_UNI
            default_us_universe = st.selectbox(
                "Default US Universe",
                us_universes,
                index=us_universes.index(cur_us),
            )

        if st.form_submit_button("💾 Save Settings", type="primary"):
            settings.update({
                "market_region":      new_region,
                "refresh_interval":   refresh_interval,
                "default_universe":   default_universe,
                "default_us_universe": default_us_universe,
                "max_workers":        max_workers,
            })
            save_settings(settings)
            st.session_state["market_region"] = new_region
            st.success("Settings saved! Market region updated.")
            st.rerun()

# ── Tab 1: Data Sources ────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("### Data Source Configuration")
    settings = get_settings()

    with st.form("data_source_settings"):
        st.markdown("**Screener.in** (India only — for fundamentals)")
        screener_csrf = st.text_input(
            "Screener.in CSRF Token (optional)",
            value=settings.get("screener_csrf", ""),
            type="password", help="csrftoken cookie from browser DevTools",
        )
        screener_session = st.text_input(
            "Screener.in Session ID (optional)",
            value=settings.get("screener_session", ""),
            type="password", help="sessionid cookie from browser DevTools",
        )

        st.markdown("**Cache TTL**")
        c1, c2, c3 = st.columns(3)
        with c1:
            ttl_screener = st.number_input(
                "Screener/Fundamentals cache (s)",
                value=int(settings.get("cache_ttl_screener", 21600)), min_value=300,
            )
        with c2:
            ttl_market = st.number_input(
                "Market data cache (s)",
                value=int(settings.get("cache_ttl_tv", 900)), min_value=60,
            )
        with c3:
            ttl_universe = st.number_input(
                "Universe cache (s)",
                value=int(settings.get("cache_ttl_universe", 86400)), min_value=3600,
            )

        if st.form_submit_button("💾 Save Data Settings", type="primary"):
            settings.update({
                "screener_csrf":       screener_csrf,
                "screener_session":    screener_session,
                "cache_ttl_screener":  ttl_screener,
                "cache_ttl_tv":        ttl_market,
                "cache_ttl_universe":  ttl_universe,
            })
            save_settings(settings)
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
                test_sym = "AAPL" if region == "US" else "RELIANCE"
                result = scan_market_bulk([test_sym, "MSFT" if region == "US" else "TCS"],
                                          region=region)
                if result:
                    sample = result.get(test_sym) or next(iter(result.values()))
                    ind = sample.get("indicators", {})
                    rec = sample.get("recommendation", "N/A")
                    cur = "$" if region == "US" else "₹"
                    st.success(
                        f"Yahoo Finance OK ✅ — {len(result)} stocks. "
                        f"{test_sym}: {rec}, RSI={ind.get('rsi', '—')}, "
                        f"Price={cur}{ind.get('close', '—')}"
                    )
                else:
                    st.error("Yahoo Finance returned no data.")
            except Exception as e:
                st.error(f"Yahoo Finance error: {e}")
    with col2:
        if st.button("🧪 Test Screener.in (India)"):
            from services.screener_service import get_full_screener_data, get_screener_status
            try:
                status = get_screener_status()
                result = get_full_screener_data("RELIANCE")
                auth_tag = "🔐 Auth" if status.get("authenticated") else "🔓 Anon"
                if result and result.get("ratios"):
                    ratios = result["ratios"]
                    st.success(
                        f"Screener.in OK ({auth_tag}): PE={ratios.get('pe')}, "
                        f"ROE={ratios.get('roe')}, OPM={ratios.get('opm')}"
                    )
                else:
                    st.warning("Screener.in returned partial data.")
            except Exception as e:
                st.error(f"Screener.in error: {e}")
    with col3:
        if region == "US":
            if st.button("🧪 Test US Market (Yahoo Finance)"):
                from services.us_market_service import get_market_status, get_index_performance
                try:
                    mkt = get_market_status()
                    idx = get_index_performance()
                    sp500 = mkt.get("sp500", "—")
                    status_msg = mkt.get("message", "—")
                    st.success(
                        f"Yahoo Finance (US) OK ✅ — S&P 500: {sp500} · {status_msg} · "
                        f"{len(idx)} indices fetched"
                    )
                except Exception as e:
                    st.error(f"Yahoo Finance (US) error: {e}")
        else:
            if st.button("🧪 Test NSE India"):
                from services.nse_service import get_index_quotes, get_market_status
                try:
                    mkt = get_market_status()
                    stocks = get_index_quotes("NIFTY 50")
                    nifty_price = mkt.get("nifty", "—")
                    nifty_pct = mkt.get("pct", 0)
                    mkt_status = mkt.get("message", "—")
                    st.success(
                        f"NSE India OK ✅ — NIFTY 50: ₹{nifty_price} ({nifty_pct:+.2f}%) "
                        f"· {mkt_status} · {len(stocks)} stocks"
                    )
                except Exception as e:
                    st.error(f"NSE India error: {e}")

# ── Tab 2: Universe Sync ───────────────────────────────────────────────────────
with tabs[2]:
    sync_tab_in, sync_tab_us = st.tabs(["🇮🇳 India (NSE)", "🇺🇸 United States"])

    with sync_tab_in:
        st.markdown("### Indian Universe Sync Status")
        try:
            from services.universe_sync import universe_sync_status, startup_sync
            status = universe_sync_status()
            rows = [{"Universe": n, "Stocks": v.get("count", 0), "Age (h)": v.get("age_hours", "N/A"),
                     "Status": "✅" if v.get("synced") else "❌",
                     "Fallback": "⚠️" if v.get("fallback") else ""}
                    for n, v in status.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        except Exception as e:
            st.error(f"Error loading sync status: {e}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Sync All Indian Universes", type="primary"):
                with st.spinner("Syncing all universes from NSE..."):
                    results = startup_sync(parallel=True)
                ok = sum(1 for v in results.values() if v.get("ok"))
                st.success(f"Synced {ok}/{len(results)} universes.")
                st.rerun()
        with col2:
            if st.button("🗑️ Clear Indian Universe Cache"):
                invalidate_prefix("universe")
                st.success("Indian universe cache cleared.")

    with sync_tab_us:
        st.markdown("### US Universe Sync Status")
        try:
            from services.us_universe_sync import us_universe_sync_status, us_startup_sync
            us_status = us_universe_sync_status()
            us_rows = [{"Universe": n, "Stocks": v.get("count", 0),
                        "Age (h)": v.get("age_hours", "N/A"),
                        "Status": "✅" if v.get("synced") else "❌",
                        "Fallback": "⚠️" if v.get("fallback") else ""}
                       for n, v in us_status.items()]
            st.dataframe(pd.DataFrame(us_rows), use_container_width=True)
        except Exception as e:
            st.error(f"Error loading US sync status: {e}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Sync All US Universes", type="primary"):
                with st.spinner("Syncing S&P 500, NASDAQ 100 from Wikipedia…"):
                    results = us_startup_sync(parallel=True)
                ok = sum(1 for v in results.values() if v.get("ok"))
                st.success(f"Synced {ok}/{len(results)} US universes.")
                st.rerun()
        with col2:
            if st.button("🗑️ Clear US Universe Cache"):
                from pathlib import Path
                import os
                us_dir = Path("storage/universe")
                removed = 0
                if us_dir.exists():
                    for f in us_dir.glob("US_*.json"):
                        f.unlink()
                        removed += 1
                st.success(f"Cleared {removed} US universe files.")


# ── Tab 3: Storage ─────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("### Local Storage")
    st.markdown("All data is stored locally in the `storage/` directory.")
    for name, path in DIRS.items():
        size  = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024
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
        if st.button("🗑️ Clear Screener/Fundamentals Cache"):
            invalidate_prefix("screener")
            st.success("Fundamentals cache cleared.")

# ── Tab 4: About ──────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown("### About Stock Intelligence Platform")
    st.markdown("""
**Version:** 2.1 — Multi-Market Edition (India + US)

**Supported Markets:**
- 🇮🇳 **India (NSE)** — NIFTY indices, live quotes, FII/DII flows
- 🇺🇸 **United States (NYSE/NASDAQ)** — S&P 500, NASDAQ 100, DOW 30, sector ETFs

**Data Sources:**
- 📈 **Yahoo Finance** — OHLCV history; technical indicators computed locally with `ta`
- 🇮🇳 **NSE India** — Live quotes, index constituents, FII/DII flows, market status (India only)
- 📊 **Screener.in** — Company fundamentals, P&L, Balance Sheet (India only)
- 🇺🇸 **Yahoo Finance (US)** — US live quotes, fundamentals, sector ETF data
- 📰 **Moneycontrol / ET / Reuters RSS** — News headlines (no API key needed)

**Analysis Engines:**
- Pattern Engine — 10 chart patterns with backtest stats
- Rule Engine — Visual rule builder with AND/OR logic
- Filter Engine — 25+ multi-criteria filters with presets
- Scoring Engine — Composite 0-100 score

**Storage:**
- 100% local — all data in `storage/` directory
- JSON cache with TTL

**Universe Support:**
- 🇮🇳 16+ NSE indices (NIFTY 50, 100, 200, 500, Midcap, Smallcap, sector indices)
- 🇺🇸 S&P 500, NASDAQ 100, DOW 30, Russell 2000 + US sector indices
""")
    st.markdown("---")
    st.markdown("Built with Streamlit + Yahoo Finance + NSE India + Screener.in")
