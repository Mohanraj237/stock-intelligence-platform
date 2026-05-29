from __future__ import annotations
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM
apply_theme()

from storage.file_store import (get_reports_index, add_report_entry, DIRS)
from services.market_router import (
    get_region, get_universe_names as get_all_universe_names,
    get_universe_display_map as universe_display_map,
    get_universe_symbols, get_ohlcv_history, get_market_analysis as get_market_analysis,
    get_fundamentals as get_full_screener_data, fmt_currency,
)
region = get_region()

def is_screener_healthy():
    return True
from services.ai_service import analyze_stock
from services.chart_analysis_service import analyze_chart_data, compute_indicators_from_ohlcv
from services.breakout_service import classify_multi_timeframe
from services.pdf_report_service import build_pdf_report
from engines.pattern_engine import detect_patterns

st.markdown("## 📄 Reports")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.86rem;margin-bottom:10px">'
    f'Generate full PDF research reports — chart, indicators, patterns, '
    f'multi-timeframe breakout state, AI Chart Analysis, fundamentals, '
    f'quarterly results, pros/cons. Saves locally and offers PDF download.'
    f'</div>',
    unsafe_allow_html=True,
)

_disp_map  = universe_display_map()
_all_names = get_all_universe_names()
_labels    = [_disp_map.get(n, n) for n in _all_names]

tabs = st.tabs(["📊 Generate PDF Report", "📁 Report Library"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Generate
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    g1, g2, g3 = st.columns([2, 2, 1])
    with g1:
        _uni_label = st.selectbox("Index / Universe", _labels, key="rep_uni")
        _uni = _all_names[_labels.index(_uni_label)]
        _uni_syms = get_universe_symbols(_uni)
    with g2:
        report_sym = st.selectbox("Symbol", _uni_syms, key="rep_sym")
    with g3:
        period = st.selectbox("Chart period", ["6m", "1y", "2y", "5y"], index=1, key="rep_period")

    incl1, incl2, incl3 = st.columns(3)
    with incl1:
        incl_ai = st.checkbox("Include AI Chart Analysis", value=True, key="rep_ai")
    with incl2:
        incl_patterns = st.checkbox("Include detected patterns", value=True, key="rep_pat")
    with incl3:
        incl_fund = st.checkbox("Include fundamentals (Screener)", value=True, key="rep_fund")

    if not is_screener_healthy() and incl_fund:
        st.warning(
            "⚠️ Screener is currently unreachable — fundamentals section will be empty. "
            "Other sections (chart, technicals, patterns, AI analysis) will work fine.",
            icon=None,
        )

    if st.button("🧾 Generate PDF Report", type="primary", key="rep_gen"):
        with st.spinner(f"Building report for {report_sym}…"):
            df = get_ohlcv_history(report_sym, period=period, interval="1d")
            if df is None or df.empty:
                st.error("OHLCV unavailable — cannot generate report.")
                st.stop()

            # Indicators
            ind = compute_indicators_from_ohlcv(df)
            # Patterns
            patterns = []
            if incl_patterns:
                try:
                    patterns = detect_patterns(df) or []
                except Exception:
                    patterns = []
            # Fundamentals
            screener = {}
            if incl_fund:
                try:
                    screener = get_full_screener_data(report_sym) or {}
                except Exception:
                    screener = {}
            fundamentals = (screener or {}).get("ratios", {}) or {}
            quarterly = (screener or {}).get("pl", {}) or {}

            # AI verdict
            ma = get_market_analysis(report_sym) or {"indicators": ind, "recommendation": "NEUTRAL"}
            ai_v = analyze_stock(report_sym, tv=ma, screener=screener, patterns=patterns)

            # AI Chart Analysis narrative
            chart_analysis = ""
            if incl_ai:
                ca = analyze_chart_data(report_sym, "Daily", df,
                                         indicators=ind, patterns=patterns,
                                         fundamentals=fundamentals,
                                         company_name=screener.get("name", ""),
                                         sector=screener.get("sector", ""))
                if ca["success"]:
                    chart_analysis = ca["analysis"]

            # Multi-timeframe breakout
            mtf = classify_multi_timeframe(
                report_sym,
                lambda s, p, i: get_ohlcv_history(s, period=p, interval=i),
            )

            # Build PDF
            pdf_bytes = build_pdf_report(
                symbol=report_sym,
                df_daily=df,
                indicators=ind,
                patterns=patterns,
                fundamentals=fundamentals,
                ai_verdict=ai_v,
                chart_analysis=chart_analysis,
                multi_tf_breakout=mtf,
                quarterly=quarterly,
                pros=screener.get("pros", []),
                cons=screener.get("cons", []),
                company_name=screener.get("name", ""),
                sector=screener.get("sector", ""),
            )

            # Save locally
            fname = f"{report_sym}_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
            (DIRS["reports"] / fname).write_bytes(pdf_bytes)
            add_report_entry(report_sym, "PDF Full Analysis", fname)

        st.success(f"Report generated: **{fname}** ({len(pdf_bytes) // 1024} KB)")

        # Live preview metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("AI Verdict", ai_v.verdict)
        c2.metric("Score", f"{ai_v.score:.0f}/100")
        c3.metric("Target", fmt_currency(ai_v.price_target) if ai_v.price_target else "—")
        c4.metric("Stop", fmt_currency(ai_v.stop_loss) if ai_v.stop_loss else "—")

        st.markdown("---")
        st.download_button(
            "⬇ Download PDF Report",
            pdf_bytes,
            file_name=fname,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

        st.markdown(
            f'<div style="color:{TEXT_DIM};font-size:0.83rem;margin-top:10px">'
            f'Report includes: cover with verdict box · daily price chart with EMAs and pattern overlays · '
            f'multi-timeframe breakout table · 12 technical indicators · {len(patterns)} detected patterns · '
            f'AI Chart Analysis (~{len(chart_analysis)} chars) · fundamentals snapshot · '
            f'quarterly results · pros/cons/risk flags.'
            f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Library
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    idx = get_reports_index()
    if not idx:
        st.info("No reports generated yet. Use the **Generate PDF Report** tab.")
    else:
        st.success(f"**{len(idx)} reports** in library.")
        df_idx = pd.DataFrame(idx)
        if "created_at" in df_idx.columns:
            df_idx = df_idx.sort_values("created_at", ascending=False)
        st.dataframe(df_idx, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Download saved report")
        report_files = sorted([r["file"] for r in idx if (DIRS["reports"] / r["file"]).exists()],
                               reverse=True)
        if report_files:
            sel_file = st.selectbox("Select report", report_files, key="rep_lib_sel")
            rpath = DIRS["reports"] / sel_file
            if rpath.exists():
                file_bytes = rpath.read_bytes()
                st.download_button(
                    f"⬇ Download {sel_file}",
                    file_bytes,
                    file_name=sel_file,
                    mime="application/pdf" if sel_file.endswith(".pdf") else "application/octet-stream",
                )
                st.caption(f"File size: {len(file_bytes) // 1024} KB")
        else:
            st.warning("No saved report files found on disk (index may be stale).")
