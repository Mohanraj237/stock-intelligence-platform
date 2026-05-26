from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.theme import apply_theme, GREEN, RED, BLUE, YELLOW, ORANGE, CARD, BORDER, TEXT, TEXT_DIM
apply_theme()

from services.universe_sync import get_universe_symbols, get_all_universe_names, universe_display_map
from services.tradingview_service import scan_symbols_bulk, tv_score
from services.ai_service import analyze_stock, AIVerdict
from engines.filter_engine import FilterCriteria, apply_filters, FILTER_PRESETS

st.markdown("## 📡 Stock Scanner")

# ── Scan Type Definitions ─────────────────────────────────────────────────────
SCAN_TYPES = {
    "All Stocks": {
        "desc": "Show all stocks in universe with full technical data.",
        "preset": {},
    },
    "Breakout Ready": {
        "desc": "Price above SMA50, RSI 55–72, MACD bullish. Strong upward momentum building.",
        "preset": {"rsi_min": 55, "rsi_max": 72, "price_above_sma50": True, "macd_bullish": True},
    },
    "Oversold Bounce": {
        "desc": "RSI < 35, price near 52W low zone. Potential mean-reversion candidates.",
        "preset": {"rsi_max": 35},
    },
    "Strong Momentum": {
        "desc": "Price above both SMA50 & SMA200, ADX > 20, RSI 50–75. Trending strongly.",
        "preset": {"rsi_min": 50, "rsi_max": 75, "price_above_sma50": True, "price_above_sma200": True, "adx_min": 20},
    },
    "MACD Crossover": {
        "desc": "MACD line just crossed above signal line. Early momentum entry signals.",
        "preset": {"macd_bullish": True, "rsi_min": 40, "rsi_max": 65},
    },
    "Quality Growth": {
        "desc": "ROE > 15%, sales growth > 15%, low debt. Fundamentally strong compounders.",
        "preset": {"roe_min": 15, "sales_growth_min": 15, "debt_max": 1.0},
    },
    "Undervalued": {
        "desc": "PE < 20, PB < 3, ROE > 10%. Fundamentally cheap with quality floor.",
        "preset": {"pe_max": 20, "pb_max": 3, "roe_min": 10},
    },
    "Techno-Funda": {
        "desc": "Combined: PE < 30, ROE > 15%, RSI 45–70, price above SMA50. Best of both worlds.",
        "preset": {"pe_max": 30, "roe_min": 15, "rsi_min": 45, "rsi_max": 70, "price_above_sma50": True},
    },
    "High Promoter Holding": {
        "desc": "Promoter stake > 55%, profit growth > 10%. Skin-in-the-game quality.",
        "preset": {"promoter_min": 55, "profit_growth_min": 10},
    },
    "Dividend Compounders": {
        "desc": "ROE > 12%, D/E < 1, promoter > 40%. Stable businesses with cash generation.",
        "preset": {"roe_min": 12, "debt_max": 1.0, "promoter_min": 40},
    },
    "52W High Breakout": {
        "desc": "Price > SMA200, RSI 60–80, strong trend. Near or at multi-year highs.",
        "preset": {"rsi_min": 60, "rsi_max": 80, "price_above_sma200": True},
    },
    "Reversal Watch": {
        "desc": "RSI 25–40, price below SMA50 but MACD turning bullish. Catching reversals early.",
        "preset": {"rsi_min": 25, "rsi_max": 40, "macd_bullish": True},
    },
}

# ── Selection Row ─────────────────────────────────────────────────────────────
disp_map  = universe_display_map()
all_names = get_all_universe_names()
labels    = [disp_map.get(n, n) for n in all_names]

sc1, sc2, sc3 = st.columns([3, 2, 1])
with sc1:
    sel_label = st.selectbox("Universe / Index", labels, key="sc_idx")
    sel_name  = all_names[labels.index(sel_label)]
with sc2:
    scan_type = st.selectbox("Scan Type", list(SCAN_TYPES.keys()), key="sc_type")
with sc3:
    run_ai = st.checkbox("AI Scoring", value=False, key="sc_ai",
                         help="Adds AI verdict per stock. Slower.")

# Show scan type description
FUNDA_ONLY_TYPES = {"Quality Growth", "Undervalued", "High Promoter Holding", "Dividend Compounders"}

if scan_type in SCAN_TYPES:
    sdesc = SCAN_TYPES[scan_type]["desc"]
    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:6px;'
        f'padding:8px 14px;color:{TEXT_DIM};font-size:0.82rem;margin-bottom:8px">'
        f'<b style="color:{BLUE}">{scan_type}</b> — {sdesc}</div>',
        unsafe_allow_html=True,
    )
    if scan_type in FUNDA_ONLY_TYPES:
        st.warning(
            "⚠️ This scan type uses **fundamental filters** (PE, ROE, D/E, Promoter%). "
            "The scanner fetches technical data only — fundamental filters will show **all stocks** "
            "since screener data is not fetched here. Use the **Stock Analyzer** for deep fundamental analysis, "
            "or enable **AI Scoring** which incorporates available fundamental signals.",
            icon=None,
        )

# ── Filter Customisation ───────────────────────────────────────────────────────
preset_vals = SCAN_TYPES.get(scan_type, {}).get("preset", {})

with st.expander("🔧 Customize Filters", expanded=False):
    fp1, fp2, fp3 = st.columns(3)
    with fp1:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">VALUATION</span>', unsafe_allow_html=True)
        pe_max  = st.number_input("PE Max",  value=float(preset_vals.get("pe_max", 80)),  min_value=0.0, key="sc_pe")
        pb_max  = st.number_input("PB Max",  value=float(preset_vals.get("pb_max", 20)),  min_value=0.0, key="sc_pb")
        de_max  = st.number_input("D/E Max", value=float(preset_vals.get("debt_max", 5)), min_value=0.0, key="sc_de")
    with fp2:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">QUALITY / GROWTH</span>', unsafe_allow_html=True)
        roe_min  = st.number_input("ROE Min %",          value=float(preset_vals.get("roe_min", 0)),          min_value=0.0, key="sc_roe")
        roce_min = st.number_input("ROCE Min %",         value=float(preset_vals.get("roce_min", 0)),         min_value=0.0, key="sc_roce")
        sg_min   = st.number_input("Sales Growth Min %", value=float(preset_vals.get("sales_growth_min", 0)), min_value=0.0, key="sc_sg")
        pg_min   = st.number_input("Profit Growth Min %",value=float(preset_vals.get("profit_growth_min",0)), min_value=0.0, key="sc_pg")
        prom_min = st.number_input("Promoter Min %",     value=float(preset_vals.get("promoter_min", 0)),     min_value=0.0, key="sc_prom")
    with fp3:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">TECHNICAL</span>', unsafe_allow_html=True)
        rsi_min   = st.number_input("RSI Min",   value=float(preset_vals.get("rsi_min", 0)),   min_value=0.0, max_value=100.0, key="sc_rsi_min")
        rsi_max   = st.number_input("RSI Max",   value=float(preset_vals.get("rsi_max", 100)), min_value=0.0, max_value=100.0, key="sc_rsi_max")
        adx_min   = st.number_input("ADX Min",   value=float(preset_vals.get("adx_min", 0)),   min_value=0.0, key="sc_adx")
        above50   = st.checkbox("Price > SMA 50",  value=bool(preset_vals.get("price_above_sma50", False)),  key="sc_sma50")
        above200  = st.checkbox("Price > SMA 200", value=bool(preset_vals.get("price_above_sma200", False)), key="sc_sma200")
        macd_bull = st.checkbox("MACD Bullish",    value=bool(preset_vals.get("macd_bullish", False)),       key="sc_macd")

filter_criteria = FilterCriteria(
    pe_max=pe_max           if pe_max   < 80  else None,
    pb_max=pb_max           if pb_max   < 20  else None,
    debt_max=de_max         if de_max   < 5   else None,
    roe_min=roe_min         if roe_min  > 0   else None,
    roce_min=roce_min       if roce_min > 0   else None,
    sales_growth_min=sg_min if sg_min   > 0   else None,
    profit_growth_min=pg_min if pg_min  > 0   else None,
    promoter_min=prom_min   if prom_min > 0   else None,
    rsi_min=rsi_min         if rsi_min  > 0   else None,
    rsi_max=rsi_max         if rsi_max  < 100 else None,
    adx_min=adx_min         if adx_min  > 0   else None,
    macd_bullish=macd_bull,
    price_above_sma50=above50,
    price_above_sma200=above200,
)

# ── Run Scan ───────────────────────────────────────────────────────────────────
run_col, _ = st.columns([1, 4])
with run_col:
    do_scan = st.button("🚀 Run Scan", type="primary", key="sc_run")

if not do_scan:
    st.info("Configure your scan type and filters above, then click **Run Scan**.")
    st.stop()

# ── Fetch all symbols (NO limit) ──────────────────────────────────────────────
symbols = get_universe_symbols(sel_name)
st.info(f"Scanning **{len(symbols)}** stocks from **{sel_label}**…")
prog = st.progress(0.0, text="Fetching market data (Yahoo + NSE)…")

all_tv: dict = {}
batches = [symbols[i:i+100] for i in range(0, len(symbols), 100)]
for bi, batch in enumerate(batches):
    all_tv.update(scan_symbols_bulk(batch))
    prog.progress((bi + 1) / len(batches), text=f"Fetched {len(all_tv)}/{len(symbols)}…")
prog.empty()

# Fall back to NSE index quotes when TV scanner is blocked
if not all_tv:
    from services.nse_service import get_index_quotes
    st.warning("⚠️ Market data scan returned no results — falling back to NSE live quotes only. Technical indicators (RSI, MACD, ADX) will not be available.", icon=None)
    nse_quotes = get_index_quotes(sel_name)
    for q in nse_quotes:
        sym_q = q.get("symbol", "")
        if not sym_q:
            continue
        all_tv[sym_q] = {
            "symbol": sym_q,
            "recommendation": "NEUTRAL",
            "indicators": {
                "close":   q.get("price"),
                "change":  float(q.get("change_pct") or 0),
                "volume":  q.get("volume"),
                "rsi":     None, "macd": None, "macd_signal": None,
                "sma50":   None, "sma200": None, "adx": None,
            },
        }
    if not all_tv:
        st.error("No data available from Yahoo Finance or NSE. Check network connection.")
        st.stop()

# ── Build results + audit trail ───────────────────────────────────────────────
audit_log   = []
results_raw = []
skipped     = []

audit_log.append(f"**Universe:** {sel_label} — {len(symbols)} symbols")
audit_log.append(f"**Scan Type:** {scan_type}")
audit_log.append(f"**Market data received:** {len(all_tv)} symbols")
audit_log.append("---")
audit_log.append("**Active filter rules:**")

active_rules = []
if filter_criteria.pe_max:       active_rules.append(f"PE ≤ {filter_criteria.pe_max:.0f}")
if filter_criteria.pb_max:       active_rules.append(f"PB ≤ {filter_criteria.pb_max:.0f}")
if filter_criteria.debt_max:     active_rules.append(f"D/E ≤ {filter_criteria.debt_max:.1f}")
if filter_criteria.roe_min:      active_rules.append(f"ROE ≥ {filter_criteria.roe_min:.0f}%")
if filter_criteria.roce_min:     active_rules.append(f"ROCE ≥ {filter_criteria.roce_min:.0f}%")
if filter_criteria.sales_growth_min: active_rules.append(f"Sales Growth ≥ {filter_criteria.sales_growth_min:.0f}%")
if filter_criteria.profit_growth_min: active_rules.append(f"Profit Growth ≥ {filter_criteria.profit_growth_min:.0f}%")
if filter_criteria.promoter_min: active_rules.append(f"Promoter ≥ {filter_criteria.promoter_min:.0f}%")
if filter_criteria.rsi_min:      active_rules.append(f"RSI ≥ {filter_criteria.rsi_min:.0f}")
if filter_criteria.rsi_max and filter_criteria.rsi_max < 100: active_rules.append(f"RSI ≤ {filter_criteria.rsi_max:.0f}")
if filter_criteria.adx_min:      active_rules.append(f"ADX ≥ {filter_criteria.adx_min:.0f}")
if filter_criteria.macd_bullish: active_rules.append("MACD > Signal")
if filter_criteria.price_above_sma50:  active_rules.append("Price > SMA50")
if filter_criteria.price_above_sma200: active_rules.append("Price > SMA200")

for ar in (active_rules or ["_(no filters — showing all)_"]):
    audit_log.append(f"  ✔ {ar}")

audit_log.append("---")
audit_log.append("**Per-symbol evaluation:**")

for sym in symbols:
    tv = all_tv.get(sym, {})
    ind = tv.get("indicators") or {}
    rec = tv.get("recommendation", "NEUTRAL")

    close_v  = ind.get("close")
    chg_v    = ind.get("change")
    rsi_v    = ind.get("rsi")
    macd_v   = ind.get("macd")
    macd_s   = ind.get("macd_signal")
    sma50_v  = ind.get("sma50") or ind.get("ema50")
    sma200_v = ind.get("sma200")
    adx_v    = ind.get("adx")
    vol_v    = ind.get("volume")

    row = {
        "Symbol":    sym,
        "Price":     close_v or 0,
        "Change %":  chg_v,
        "RSI":       rsi_v,
        "MACD":      macd_v,
        "MACD Sig":  macd_s,
        "SMA 50":    sma50_v,
        "SMA 200":   sma200_v,
        "ADX":       adx_v,
        "Volume":    vol_v,
        "Signal": rec,
        "TV Score":  tv_score(rec),
        "_tv":       tv,
        "AI Verdict": "—",
        "AI Score":   0,
    }
    results_raw.append(row)

# Apply filter engine
filtered = apply_filters(results_raw, filter_criteria)
filtered_syms = {r["Symbol"] for r in filtered}

# Build detailed audit per symbol (first 60 for readability)
audit_sample_count = 0
for row in results_raw:
    sym = row["Symbol"]
    passed = sym in filtered_syms
    if audit_sample_count >= 60:
        continue
    if passed:
        checks = []
        if rsi_v := row.get("RSI"):
            checks.append(f"RSI={float(rsi_v):.1f}")
        if rec := row.get("Signal"):
            checks.append(f"Signal={rec}")
        audit_log.append(f"  ✅ **{sym}** — PASSED" + (f" [{', '.join(checks)}]" if checks else ""))
    else:
        fail_reasons = []
        rsi_v2  = row.get("RSI")
        close_v2 = row.get("Price")
        sma50_2  = row.get("SMA 50")
        sma200_2 = row.get("SMA 200")
        macd_v2  = row.get("MACD")
        macd_s2  = row.get("MACD Sig")
        if filter_criteria.rsi_min and rsi_v2 and float(rsi_v2) < filter_criteria.rsi_min:
            fail_reasons.append(f"RSI={float(rsi_v2):.1f} < {filter_criteria.rsi_min:.0f}")
        if filter_criteria.rsi_max and filter_criteria.rsi_max < 100 and rsi_v2 and float(rsi_v2) > filter_criteria.rsi_max:
            fail_reasons.append(f"RSI={float(rsi_v2):.1f} > {filter_criteria.rsi_max:.0f}")
        if filter_criteria.price_above_sma50 and close_v2 and sma50_2 and float(close_v2) <= float(sma50_2):
            fail_reasons.append(f"Price≤SMA50")
        if filter_criteria.price_above_sma200 and close_v2 and sma200_2 and float(close_v2) <= float(sma200_2):
            fail_reasons.append(f"Price≤SMA200")
        if filter_criteria.macd_bullish and macd_v2 is not None and macd_s2 is not None and float(macd_v2) <= float(macd_s2):
            fail_reasons.append(f"MACD≤Signal")
        if filter_criteria.adx_min and row.get("ADX") and float(row["ADX"]) < filter_criteria.adx_min:
            fail_reasons.append(f"ADX={float(row['ADX']):.1f}<{filter_criteria.adx_min:.0f}")
        reason_str = "; ".join(fail_reasons) if fail_reasons else "fundamental filters"
        audit_log.append(f"  ✗ **{sym}** — skipped: {reason_str}")
    audit_sample_count += 1

if len(results_raw) > 60:
    audit_log.append(f"  _(…{len(results_raw) - 60} more symbols not shown in audit)_")

audit_log.append("---")
audit_log.append(f"**Final count: {len(filtered)} / {len(results_raw)} passed all filters**")

# ── Optional AI Scoring — fetch screener first for consistency with Stock Analyzer ─
if run_ai and filtered:
    from services.screener_service import get_full_screener_data

    # Step 1: parallel screener fetch for all matched stocks
    screener_map: dict = {}
    scr_prog = st.progress(0.0, text="Fetching fundamental data for AI…")

    def _safe_screener(sym: str):
        try:
            return sym, get_full_screener_data(sym) or {}
        except Exception:
            return sym, {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        scr_futs = {ex.submit(_safe_screener, row["Symbol"]): row["Symbol"] for row in filtered}
        for done_s, fut_s in enumerate(as_completed(scr_futs)):
            s_sym, s_data = fut_s.result()
            screener_map[s_sym] = s_data
            scr_prog.progress((done_s + 1) / len(filtered),
                              text=f"Fundamentals: {done_s+1}/{len(filtered)}…")
    scr_prog.empty()

    # Step 2: run AI with tv + screener (same inputs as Stock Analyzer)
    ai_prog = st.progress(0.0, text="Running AI analysis…")
    for i, row in enumerate(filtered):
        try:
            v: AIVerdict = analyze_stock(
                row["Symbol"],
                tv=row["_tv"],
                screener=screener_map.get(row["Symbol"], {}),
            )
            row["AI Verdict"]    = v.verdict
            row["AI Score"]      = v.score
            row["AI Tech"]       = v.tech_score
            row["AI Fund"]       = v.fund_score
            row["AI Confidence"] = v.confidence
        except Exception:
            pass
        if i % 3 == 0:
            ai_prog.progress((i + 1) / len(filtered), text=f"AI scored {i+1}/{len(filtered)}…")
    ai_prog.empty()
    audit_log.append(f"**AI Scoring:** TV + Screener data used for {len(filtered)} stocks")

# ── Sort results ───────────────────────────────────────────────────────────────
sort_key = "AI Score" if run_ai else "TV Score"
filtered.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=True)

# ── Results ────────────────────────────────────────────────────────────────────
st.success(f"✅ **{len(filtered)}** stocks matched from **{len(results_raw)}** scanned — {len(results_raw)-len(filtered)} skipped by filters.")

if not filtered:
    st.info("No stocks matched. Try relaxing the filter criteria or switching scan type.")
    with st.expander("🔎 Audit Log"):
        for line in audit_log:
            st.markdown(line)
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
pass_chgs  = [float(r.get("Change %") or 0) for r in filtered]
pass_rsis  = [float(r.get("RSI") or 0)      for r in filtered if r.get("RSI")]
pass_buys  = sum(1 for r in filtered if "BUY" in str(r.get("Signal", "")))

sm1, sm2, sm3, sm4, sm5 = st.columns(5)
sm1.metric("Matched",     len(filtered))
sm2.metric("Scanned",     len(results_raw))
sm3.metric("Avg Change",  f"{sum(pass_chgs)/max(len(pass_chgs),1):+.2f}%")
sm4.metric("Avg RSI",     f"{sum(pass_rsis)/max(len(pass_rsis),1):.1f}" if pass_rsis else "—")
sm5.metric("Buy Signals", pass_buys)

st.markdown("---")

# ── Signal distribution of matched stocks ────────────────────────────────────
ch1, ch2 = st.columns(2)
with ch1:
    sig_counts = pd.Series([r["Signal"] for r in filtered]).value_counts()
    sig_colors = {"STRONG_BUY": GREEN, "BUY": "#4caf50", "NEUTRAL": TEXT_DIM, "SELL": "#e57373", "STRONG_SELL": RED}
    fig_sig = go.Figure(go.Bar(
        x=list(sig_counts.index), y=list(sig_counts.values),
        marker_color=[sig_colors.get(s, BLUE) for s in sig_counts.index],
        text=list(sig_counts.values), textposition="outside",
    ))
    fig_sig.update_layout(
        title="Signal Distribution (Matched)", template="plotly_dark",
        paper_bgcolor=CARD, plot_bgcolor=CARD, height=240,
        margin=dict(l=0,r=0,t=36,b=0),
        xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
        showlegend=False,
    )
    st.plotly_chart(fig_sig, use_container_width=True)

with ch2:
    rsi_v_all = [float(r["RSI"]) for r in filtered if r.get("RSI") is not None]
    if rsi_v_all:
        fig_rsi = go.Figure(go.Histogram(x=rsi_v_all, nbinsx=20, marker_color=BLUE, opacity=0.8))
        fig_rsi.add_vline(x=30, line_dash="dot", line_color=GREEN)
        fig_rsi.add_vline(x=70, line_dash="dot", line_color=RED)
        fig_rsi.update_layout(
            title="RSI Distribution (Matched)", template="plotly_dark",
            paper_bgcolor=CARD, plot_bgcolor=CARD, height=240,
            margin=dict(l=0,r=0,t=36,b=0),
            xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
            showlegend=False,
        )
        st.plotly_chart(fig_rsi, use_container_width=True)

st.markdown("---")

# ── Full results table ────────────────────────────────────────────────────────
st.markdown(f'<div class="z-section">All Matched Stocks ({len(filtered)})</div>', unsafe_allow_html=True)

display_rows = []
for s in filtered:
    chg = s.get("Change %") or 0
    rsi = s.get("RSI")
    rec = s.get("Signal", "NEUTRAL")
    vs50 = "—"
    vs200 = "—"
    try:
        if s.get("Price") and s.get("SMA 50"):
            vs50 = f"{(float(s['Price'])-float(s['SMA 50']))/abs(float(s['SMA 50']))*100:+.1f}%"
    except Exception:
        pass
    try:
        if s.get("Price") and s.get("SMA 200"):
            vs200 = f"{(float(s['Price'])-float(s['SMA 200']))/abs(float(s['SMA 200']))*100:+.1f}%"
    except Exception:
        pass
    row_d = {
        "Symbol":     s["Symbol"],
        "Price (₹)":  f"{float(s['Price']):,.2f}" if s.get("Price") else "—",
        "Change %":   f"{float(chg):+.2f}%" if chg is not None else "—",
        "RSI":        f"{float(rsi):.1f}" if rsi is not None else "—",
        "ADX":        f"{float(s.get('ADX',0)):.1f}" if s.get("ADX") else "—",
        "MACD":       f"{float(s.get('MACD',0)):.2f}" if s.get("MACD") is not None else "—",
        "vs SMA50":   vs50,
        "vs SMA200":  vs200,
        "Signal":     rec,
        "TV Score":   s.get("TV Score", 0),
        "AI Verdict": s.get("AI Verdict", "—"),
        "AI Score":   s.get("AI Score", 0) if run_ai else "—",
        "AI Tech":    s.get("AI Tech", 0) if run_ai else "—",
        "AI Fund":    s.get("AI Fund", 0) if run_ai else "—",
        "AI Conf":    s.get("AI Confidence", "—") if run_ai else "—",
        "_chg":       float(chg) if chg is not None else 0,
        "_rsi":       float(rsi) if rsi is not None else 50,
        "_rec":       rec,
    }
    display_rows.append(row_d)

df_res = pd.DataFrame(display_rows)

def _style_scan(df: pd.DataFrame):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for i in range(len(df)):
        chg_v = df.iloc[i]["_chg"]
        rsi_v = df.iloc[i]["_rsi"]
        rec_v = str(df.iloc[i]["_rec"])
        styles.iloc[i, df.columns.get_loc("Change %")] = f"color:{GREEN if float(chg_v) >= 0 else RED};font-weight:700"
        if float(rsi_v) > 70:
            styles.iloc[i, df.columns.get_loc("RSI")] = f"color:{RED};font-weight:600"
        elif float(rsi_v) < 35:
            styles.iloc[i, df.columns.get_loc("RSI")] = f"color:{GREEN};font-weight:600"
        if "STRONG_BUY" in rec_v:
            styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{GREEN};font-weight:800"
        elif "BUY" in rec_v:
            styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{GREEN};font-weight:600"
        elif "STRONG_SELL" in rec_v:
            styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{RED};font-weight:800"
        elif "SELL" in rec_v:
            styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{RED};font-weight:600"
        else:
            styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{TEXT_DIM}"
        if run_ai:
            ai_v = str(df.iloc[i]["AI Verdict"])
            if "BUY" in ai_v:
                styles.iloc[i, df.columns.get_loc("AI Verdict")] = f"color:{GREEN};font-weight:700"
            elif "SELL" in ai_v:
                styles.iloc[i, df.columns.get_loc("AI Verdict")] = f"color:{RED};font-weight:700"
            else:
                styles.iloc[i, df.columns.get_loc("AI Verdict")] = f"color:{TEXT_DIM}"
            for _col, _fw in [("AI Score", "700"), ("AI Tech", "500"), ("AI Fund", "500")]:
                try:
                    val = float(df.iloc[i][_col])
                    c = GREEN if val >= 60 else RED if val < 40 else YELLOW
                    styles.iloc[i, df.columns.get_loc(_col)] = f"color:{c};font-weight:{_fw}"
                except Exception:
                    pass
    return styles

hide_cols = ["_chg", "_rsi", "_rec"]
if not run_ai:
    hide_cols += ["AI Verdict", "AI Score", "AI Tech", "AI Fund", "AI Conf"]

st.dataframe(
    df_res.style.apply(_style_scan, axis=None).hide(subset=hide_cols, axis="columns"),
    use_container_width=True, hide_index=True, height=480,
)

# ── Top 10 Cards ──────────────────────────────────────────────────────────────
st.markdown('<div class="z-section">Top 10 Results</div>', unsafe_allow_html=True)
for i, s in enumerate(filtered[:10], 1):
    rec   = s.get("Signal", "NEUTRAL")
    rec_c = GREEN if "BUY" in rec else RED if "SELL" in rec else TEXT_DIM
    chg   = s.get("Change %") or 0
    chg_c = GREEN if float(chg) >= 0 else RED
    rsi   = s.get("RSI")
    adx   = s.get("ADX")
    ai_v  = s.get("AI Verdict", "")
    ai_s  = s.get("AI Score", 0)
    ai_html = f'<span style="color:{GREEN if "BUY" in str(ai_v) else RED if "SELL" in str(ai_v) else TEXT_DIM};font-size:0.8rem">AI:{ai_v}({ai_s:.0f})</span>' if run_ai and ai_v != "—" else ""
    st.markdown(
        f'<div class="z-stock-row">'
        f'<span style="color:{TEXT_DIM};font-size:0.78rem;min-width:28px">#{i}</span>'
        f'<span style="color:{TEXT};font-weight:700;min-width:110px">{s["Symbol"]}</span>'
        f'<span style="color:{TEXT_DIM};font-size:0.83rem;min-width:90px">₹{float(s.get("Price",0)):,.2f}</span>'
        f'<span style="color:{chg_c};font-weight:600;min-width:70px">{float(chg):+.2f}%</span>'
        f'<span style="color:{TEXT_DIM};font-size:0.82rem;min-width:70px">RSI:{f"{float(rsi):.0f}" if rsi else "—"}</span>'
        f'<span style="color:{TEXT_DIM};font-size:0.82rem;min-width:65px">ADX:{f"{float(adx):.0f}" if adx else "—"}</span>'
        f'<span style="color:{rec_c};font-weight:700;min-width:100px">{rec}</span>'
        f'<span style="color:{YELLOW};font-size:0.83rem;min-width:60px">TV:{s.get("TV Score",0):.0f}</span>'
        f'{ai_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Download ───────────────────────────────────────────────────────────────────
st.markdown("---")
dl_df = df_res.drop(columns=["_chg","_rsi","_rec"], errors="ignore")
st.download_button(
    "⬇ Download CSV", dl_df.to_csv(index=False),
    f"scan_{sel_name.replace(' ','_')}_{scan_type.replace(' ','_')}.csv", "text/csv",
)

# ── Audit Trail ───────────────────────────────────────────────────────────────
with st.expander("🔎 Scan Audit Log — Filter & Rule Engine Trace", expanded=False):
    for line in audit_log:
        st.markdown(line)
