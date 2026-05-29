from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


from utils.theme import (
    apply_theme, signal_badge, fmt_cr,
    metric_card, verdict_card, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW
)
apply_theme()
from utils.advanced_chart import render_ohlcv_chart
from utils.tv_chart import render_tv_chart

from services.market_router import (
    get_region, get_universe_names as get_all_universe_names,
    get_universe_display_map as universe_display_map,
    get_universe_symbols, scan_symbols_bulk, get_ohlcv_history as get_tv_ohlcv_history,
    get_quote as nse_get_quote, get_fundamentals, fmt_currency, fmt_volume, fmt_market_cap,
    currency_symbol,
)
from services.ai_service import analyze_stock
from engines.pattern_engine import detect_patterns

region = get_region()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("## 🔍 Stock Analyzer")

# ── Index + Stock Selection ────────────────────────────────────────────────────
disp_map = universe_display_map()
all_names = get_all_universe_names()
labels = [disp_map.get(n, n) for n in all_names]

col_idx, col_stock, col_tf = st.columns([2, 2, 1])

with col_idx:
    sel_label = st.selectbox("Select Index / Universe", labels, key="sa_index")
    sel_universe = all_names[labels.index(sel_label)]

@st.cache_data(ttl=3600, show_spinner=False)
def load_index_stocks(universe: str):
    return get_universe_symbols(universe)

symbols = load_index_stocks(sel_universe)

with col_stock:
    if symbols:
        selected_symbol = st.selectbox("Select Stock", symbols, key="sa_stock")
    else:
        st.warning("No stocks found for this index.")
        st.stop()

with col_tf:
    timeframe = st.selectbox("History", ["1y", "2y", "6m", "3m", "5y"], key="sa_tf")

st.markdown("---")

sym = selected_symbol

# ── Cached fetchers ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_tv(symbol):
    bulk = scan_symbols_bulk([symbol])
    return bulk.get(symbol, {})

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_screener(symbol):
    return get_fundamentals(symbol)

@st.cache_data(ttl=600, show_spinner=False)
def fetch_ohlcv(symbol, period):
    return get_tv_ohlcv_history(symbol, period=period, interval="1d")

@st.cache_data(ttl=300, show_spinner=False)
def fetch_nse(symbol):
    try:
        return nse_get_quote(symbol) or {}
    except Exception:
        return {}

# ── Parallel fetch — all 4 sources simultaneously ─────────────────────────────
from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed, TimeoutError as _FutTimeout

# Per-source timeout budgets (seconds). Screener is treated as best-effort —
# we never let it block the page. Yahoo OHLCV is critical for charts/technicals.
_TIMEOUTS = {"ohlcv": 20, "tv": 12, "nse": 10, "screener": 12}

_cache_key = f"{sym}_{timeframe}"
if st.session_state.get("_sa_cache_key") != _cache_key:
    status_bar = st.empty()
    source_desc = "Yahoo Finance · Yahoo Finance (US)" if region == "US" else "Yahoo Finance · Screener · NSE"
    status_bar.info(f"⏳ Loading {sym} from {source_desc} simultaneously...")

    _results = {"tv": {}, "screener": {}, "nse": {}, "ohlcv": None}
    with ThreadPoolExecutor(max_workers=4) as _ex:
        _futs = {
            _ex.submit(fetch_tv, sym):               "tv",
            _ex.submit(fetch_screener, sym):          "screener",
            _ex.submit(fetch_nse, sym):               "nse",
            _ex.submit(fetch_ohlcv, sym, timeframe):  "ohlcv",
        }
        # Wait per-future with a hard cap so a hanging Screener never blocks UI
        for _fut in _as_completed(_futs, timeout=25):
            _key = _futs[_fut]
            try:
                _results[_key] = _fut.result(timeout=_TIMEOUTS.get(_key, 15))
            except _FutTimeout:
                _results[_key] = (
                    {"error": f"{_key} timed out"} if _key != "ohlcv" else None
                )
            except Exception as e:
                _results[_key] = (
                    {"error": str(e)[:120]} if _key != "ohlcv" else None
                )

    st.session_state["_sa_cache_key"] = _cache_key
    st.session_state["_sa_tv"]       = _results.get("tv") or {}
    st.session_state["_sa_screener"] = _results.get("screener") or {}
    st.session_state["_sa_nse"]      = _results.get("nse") or {}
    st.session_state["_sa_ohlcv"]    = _results.get("ohlcv")
    status_bar.empty()

tv       = st.session_state.get("_sa_tv", {})
screener = st.session_state.get("_sa_screener", {})
nse_q    = st.session_state.get("_sa_nse", {})
df_ohlcv = st.session_state.get("_sa_ohlcv")

# ── Fundamentals health banner ────────────────────────────────────────────────
if screener.get("error"):
    if region == "IN":
        try:
            from services.screener_service import is_screener_healthy, reset_circuit_breaker
            _hb1, _hb2 = st.columns([5, 1])
            with _hb1:
                st.warning(
                    "⚠️ **Screener.in is currently unreachable** — fundamentals, P&L, balance sheet, "
                    "shareholding, peers, and ratio history will be unavailable for this session. "
                    "**Charts, technical indicators, patterns, and AI Chart Analysis still work fine.**",
                    icon=None,
                )
            with _hb2:
                if not is_screener_healthy() and st.button("🔄 Retry Screener", key="sa_retry_screener"):
                    reset_circuit_breaker()
                    for k in ["_sa_cache_key", "_sa_screener"]:
                        st.session_state.pop(k, None)
                    st.rerun()
        except Exception:
            st.warning("⚠️ Fundamentals unavailable for this session.")
    else:
        st.warning("⚠️ Yahoo Finance fundamentals unavailable — charts and technicals still work.")

# If TV scanner blocked, compute indicators from OHLCV
_ind = tv.get("indicators") or {}
if (not _ind.get("close")) and df_ohlcv is not None and not df_ohlcv.empty:
    try:
        import ta as _ta
        _c = df_ohlcv["Close"]
        _h = df_ohlcv["High"]
        _l = df_ohlcv["Low"]
        _computed = {
            "close":    float(_c.iloc[-1]),
            "open":     float(df_ohlcv["Open"].iloc[-1]),
            "high":     float(_h.iloc[-1]),
            "low":      float(_l.iloc[-1]),
            "volume":   float(df_ohlcv["Volume"].iloc[-1]) if "Volume" in df_ohlcv.columns else None,
            "change":   float((_c.iloc[-1] - _c.iloc[-2]) / _c.iloc[-2] * 100) if len(_c) > 1 else 0,
            "rsi":      float(_ta.momentum.RSIIndicator(_c, window=14).rsi().iloc[-1]),
            "macd":     float(_ta.trend.MACD(_c).macd().iloc[-1]),
            "macd_signal": float(_ta.trend.MACD(_c).macd_signal().iloc[-1]),
            "macd_hist":   float(_ta.trend.MACD(_c).macd_diff().iloc[-1]),
            "sma20":    float(_ta.trend.SMAIndicator(_c, window=20).sma_indicator().iloc[-1]),
            "sma50":    float(_ta.trend.SMAIndicator(_c, window=50).sma_indicator().iloc[-1]) if len(_c) >= 50 else None,
            "sma100":   float(_ta.trend.SMAIndicator(_c, window=100).sma_indicator().iloc[-1]) if len(_c) >= 100 else None,
            "sma200":   float(_ta.trend.SMAIndicator(_c, window=200).sma_indicator().iloc[-1]) if len(_c) >= 200 else None,
            "ema20":    float(_ta.trend.EMAIndicator(_c, window=20).ema_indicator().iloc[-1]),
            "ema50":    float(_ta.trend.EMAIndicator(_c, window=50).ema_indicator().iloc[-1]) if len(_c) >= 50 else None,
            "ema200":   float(_ta.trend.EMAIndicator(_c, window=200).ema_indicator().iloc[-1]) if len(_c) >= 200 else None,
            "adx":      float(_ta.trend.ADXIndicator(_h, _l, _c).adx().iloc[-1]),
            "adx_pos":  float(_ta.trend.ADXIndicator(_h, _l, _c).adx_pos().iloc[-1]),
            "adx_neg":  float(_ta.trend.ADXIndicator(_h, _l, _c).adx_neg().iloc[-1]),
            "bb_upper": float(_ta.volatility.BollingerBands(_c).bollinger_hband().iloc[-1]),
            "bb_lower": float(_ta.volatility.BollingerBands(_c).bollinger_lband().iloc[-1]),
            "bb_mid":   float(_ta.volatility.BollingerBands(_c).bollinger_mavg().iloc[-1]),
            "stoch_k":  float(_ta.momentum.StochasticOscillator(_h, _l, _c).stoch().iloc[-1]),
            "stoch_d":  float(_ta.momentum.StochasticOscillator(_h, _l, _c).stoch_signal().iloc[-1]),
            "cci20":    float(_ta.trend.CCIIndicator(_h, _l, _c, window=20).cci().iloc[-1]),
        }
        # Remove NaN values
        _computed = {k: (None if (v is not None and v != v) else v) for k, v in _computed.items()}
        if not tv:
            tv = {"indicators": _computed, "recommendation": "NEUTRAL", "source": "Computed from OHLCV"}
        else:
            tv.setdefault("indicators", {}).update(_computed)
        st.session_state["_sa_tv"] = tv
    except Exception:
        pass  # silently fall back to empty indicators

patterns = []
if df_ohlcv is not None and not df_ohlcv.empty:
    try:
        patterns = detect_patterns(df_ohlcv)
    except Exception:
        pass

verdict = analyze_stock(sym, tv=tv, screener=screener, patterns=patterns)

# ── Key Metrics Row ────────────────────────────────────────────────────────────
ind = tv.get("indicators") or {}
ratios = screener.get("ratios") or {}

close = ind.get("close") or nse_q.get("price") or 0
change_pct = ind.get("change") or nse_q.get("change_pct") or 0
high_52 = nse_q.get("year_high") or ratios.get("high_52w")
low_52 = nse_q.get("year_low")
market_cap = ratios.get("market_cap")
pe = ratios.get("pe")
rsi = ind.get("rsi")

price_color = GREEN if change_pct >= 0 else RED
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

with c1:
    st.markdown(f"""<div class="z-card">
      <div class="z-card-title">Price</div>
      <div class="z-val" style="color:{price_color}">{fmt_currency(close)}</div>
      <div style="font-size:0.8rem;color:{price_color}">{change_pct:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(metric_card("52W High", fmt_currency(high_52, decimals=0) if high_52 else "—"), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card("52W Low", fmt_currency(low_52, decimals=0) if low_52 else "—"), unsafe_allow_html=True)
with c4:
    st.markdown(metric_card("Market Cap", fmt_market_cap(market_cap) if market_cap else "—"), unsafe_allow_html=True)
with c5:
    st.markdown(metric_card("P/E", f"{pe:.1f}x" if pe else "—"), unsafe_allow_html=True)
with c6:
    rsi_color = RED if rsi and rsi > 70 else GREEN if rsi and rsi < 35 else TEXT
    st.markdown(f"""<div class="z-card">
      <div class="z-card-title">RSI (14)</div>
      <div class="z-val" style="color:{rsi_color}">{f"{rsi:.1f}" if rsi else "—"}</div>
    </div>""", unsafe_allow_html=True)
with c7:
    st.markdown(f"""<div class="z-card">
      <div class="z-card-title">TV Signal</div>
      <div style="margin-top:4px">{signal_badge(tv.get("recommendation", "—"))}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("---")

# ── AI Verdict Row ─────────────────────────────────────────────────────────────
vc1, vc2, vc3, vc4, vc5 = st.columns([2, 1, 1, 1, 1])
with vc1:
    st.markdown(verdict_card(verdict.verdict, verdict.score, f"{verdict.confidence} confidence"), unsafe_allow_html=True)
with vc2:
    tgt_str = fmt_currency(verdict.price_target) if verdict.price_target else "—"
    upsid_str = f"{verdict.upside_pct:+.1f}%" if verdict.upside_pct is not None else ""
    up_color = GREEN if (verdict.upside_pct or 0) >= 0 else RED
    st.markdown(metric_card("Price Target", tgt_str, upsid_str, up_color), unsafe_allow_html=True)
with vc3:
    sl_str = fmt_currency(verdict.stop_loss) if verdict.stop_loss else "—"
    st.markdown(metric_card("Stop Loss", sl_str, "", RED), unsafe_allow_html=True)
with vc4:
    st.markdown(f"""<div class="z-card">
      <div class="z-card-title">Tech Score</div>
      <div class="z-val">{verdict.tech_score:.0f}</div>
      <div style="font-size:0.75rem;color:{TEXT_DIM}">/100</div>
    </div>""", unsafe_allow_html=True)
with vc5:
    st.markdown(f"""<div class="z-card">
      <div class="z-card-title">Fund Score</div>
      <div class="z-val">{verdict.fund_score:.0f}</div>
      <div style="font-size:0.75rem;color:{TEXT_DIM}">/100</div>
    </div>""", unsafe_allow_html=True)

# ── Chart analysis display helper ─────────────────────────────────────────────
def _display_chart_analysis(analysis_text: str, symbol: str):
    """Render AI chart analysis with section-level formatting."""
    # Split into numbered sections and render each with a subtle separator
    import re
    sections = re.split(r'(?=\*\*\d+\.)', analysis_text)
    for section in sections:
        if not section.strip():
            continue
        # Detect verdict line for highlight box
        if "FINAL VERDICT" in section.upper() or "Strong Buy" in section or "Breakdown Risk" in section:
            verdict_color = GREEN
            if "SELL" in section.upper() or "AVOID" in section.upper() or "BREAKDOWN" in section.upper():
                verdict_color = RED
            elif "WATCHLIST" in section.upper():
                verdict_color = YELLOW
            st.markdown(
                f'<div style="background:rgba(49,208,170,0.08);border:1px solid {verdict_color};'
                f'border-radius:8px;padding:12px 16px;margin:8px 0">{section}</div>',
                unsafe_allow_html=True,
            )
        elif "RISK MANAGEMENT" in section.upper() or "ENTRY" in section.upper():
            st.markdown(
                f'<div style="background:rgba(33,150,243,0.08);border-left:3px solid {BLUE};'
                f'padding:10px 14px;margin:6px 0;border-radius:0 6px 6px 0">{section}</div>',
                unsafe_allow_html=True,
            )
        elif "RED FLAGS" in section.upper() or "WARNING" in section.upper():
            st.markdown(
                f'<div style="background:rgba(239,83,80,0.08);border-left:3px solid {RED};'
                f'padding:10px 14px;margin:6px 0;border-radius:0 6px 6px 0">{section}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(section)

    # Download button
    st.download_button(
        "⬇ Download Analysis",
        analysis_text,
        file_name=f"{symbol}_chart_analysis.md",
        mime="text/markdown",
        key=f"dl_ca_{symbol}",
    )


# ── Main Tabs ──────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📈 Chart", "🤖 AI Analysis", "🧬 Patterns", "📊 Technicals",
    "💰 Fundamentals", "📋 Quarterly", "🏦 Balance Sheet",
    "📉 Ratio Trends", "👥 Shareholding", "🔗 Peers", "🎯 AI Chart Analysis"
])

# ─── Tab 0: Chart ──────────────────────────────────────────────────────────────
with tabs[0]:
    if df_ohlcv is not None and not df_ohlcv.empty:
        # Pull lines from the strongest detected pattern for overlay
        pat_lines = []
        if patterns:
            best_pat = max(patterns, key=lambda p: (p.get("confidence", 0) or 0))
            pat_lines = best_pat.get("lines", []) or []
        render_tv_chart(
            df=df_ohlcv, symbol=sym, height=720,
            show_volume=True, show_emas=(20, 50, 200),
            entry=close or None,
            target=verdict.price_target,
            stop=verdict.stop_loss,
            pattern_lines=pat_lines,
            title=f"{sym} — Daily",
            key_suffix=f"sa_{sym}",
        )
    else:
        st.warning("OHLCV data unavailable. Check ticker symbol or try a different timeframe.")

# ─── Tab 1: AI Analysis ────────────────────────────────────────────────────────
with tabs[1]:
    ai1, ai2 = st.columns([1, 1])
    with ai1:
        st.markdown(f'<div class="z-section">Summary</div>', unsafe_allow_html=True)
        st.markdown(verdict.summary)
        st.markdown(f'<div class="z-section">Bull Case</div>', unsafe_allow_html=True)
        st.markdown(f'<p style="color:{GREEN};font-size:0.88rem">{verdict.bull_case}</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="z-section">Bear Case</div>', unsafe_allow_html=True)
        st.markdown(f'<p style="color:{RED};font-size:0.88rem">{verdict.bear_case}</p>', unsafe_allow_html=True)
        if verdict.risk_flags:
            st.markdown(f'<div class="z-section">Risk Flags</div>', unsafe_allow_html=True)
            for flag in verdict.risk_flags:
                st.markdown(f'<div style="background:rgba(239,83,80,0.1);border-left:3px solid {RED};padding:6px 10px;margin-bottom:4px;border-radius:0 6px 6px 0;font-size:0.83rem">⚠ {flag}</div>', unsafe_allow_html=True)

    with ai2:
        st.markdown(f'<div class="z-section">Score Breakdown</div>', unsafe_allow_html=True)
        scores = {"Technical": verdict.tech_score, "Fundamental": verdict.fund_score,
                  "Pattern": verdict.pattern_score, "Momentum": verdict.momentum_score}
        bar_colors = [GREEN if v >= 60 else RED if v < 40 else YELLOW for v in scores.values()]
        fig_sc = go.Figure(go.Bar(
            x=list(scores.keys()), y=list(scores.values()),
            marker_color=bar_colors,
            text=[f"{v:.0f}" for v in scores.values()], textposition="outside",
        ))
        fig_sc.add_hline(y=50, line_dash="dash", line_color=BORDER)
        fig_sc.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=250, showlegend=False, yaxis_range=[0, 115],
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_sc, use_container_width=True)

        st.markdown(f'<div class="z-section">Key Signals</div>', unsafe_allow_html=True)
        for sig in verdict.signals:
            pos = any(w in sig.lower() for w in ["bullish", "strong", "good", "above", "growth", "oversold", "golden", "attractive", "high retur"])
            neg = any(w in sig.lower() for w in ["bearish", "weak", "poor", "below", "declining", "overbought", "death", "high debt", "pledge"])
            col = GREEN if pos else RED if neg else TEXT_DIM
            ico = "↑" if pos else "↓" if neg else "→"
            st.markdown(f'<div style="font-size:0.82rem;color:{col};padding:2px 0">{ico} {sig}</div>', unsafe_allow_html=True)

# ─── Tab 2: Patterns ───────────────────────────────────────────────────────────
with tabs[2]:
    if df_ohlcv is None or df_ohlcv.empty:
        st.warning("No OHLCV data available for pattern detection.")
    elif not patterns:
        st.info("No patterns detected in current timeframe.")
    else:
        st.markdown(f"**{len(patterns)} pattern(s) detected**")
        fig_p = go.Figure()
        fig_p.add_trace(go.Candlestick(
            x=df_ohlcv.index, open=df_ohlcv["Open"], high=df_ohlcv["High"],
            low=df_ohlcv["Low"], close=df_ohlcv["Close"],
            increasing_line_color=GREEN, decreasing_line_color=RED, name=sym
        ))
        n = len(df_ohlcv)
        for pat in patterns:
            d = pat.get("direction", "neutral") if isinstance(pat, dict) else "neutral"
            lc = GREEN if d == "bullish" else RED if d == "bearish" else YELLOW
            for ln in (pat.get("lines", []) if isinstance(pat, dict) else []):
                if not isinstance(ln, dict):
                    continue
                try:
                    fig_p.add_shape(type="line",
                        x0=str(ln["x0"]), y0=float(ln["y0"]),
                        x1=str(ln["x1"]), y1=float(ln["y1"]),
                        line=dict(color=ln.get("color", lc), width=1.5, dash=ln.get("dash","dot")),
                        xref="x", yref="y")
                except Exception:
                    pass
        fig_p.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            xaxis_rangeslider_visible=False, height=500,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_p, use_container_width=True)
        for pat in patterns:
            name = pat.get("name", "Unknown") if isinstance(pat, dict) else "Unknown"
            conf = pat.get("confidence", 0) if isinstance(pat, dict) else 0
            d    = pat.get("direction", "neutral") if isinstance(pat, dict) else "neutral"
            desc = pat.get("description", "") if isinstance(pat, dict) else ""
            kl   = pat.get("key_levels", {}) if isinstance(pat, dict) else {}
            dc = GREEN if d == "bullish" else RED if d == "bearish" else YELLOW
            with st.expander(f"{name} — {conf:.0f}% confidence"):
                st.markdown(f'<span style="color:{dc}">Direction: {d.title()}</span>', unsafe_allow_html=True)
                if kl.get("target"):
                    _cs = currency_symbol()
                    st.markdown(f'Target: {_cs}{kl["target"]:,.2f} | Stop: {_cs}{kl.get("stop",0):,.2f}')
                if desc:
                    st.markdown(desc)

# ─── Tab 3: Technicals ─────────────────────────────────────────────────────────
with tabs[3]:
    t1, t2, t3 = st.columns(3)

    def _row(lbl, val, suffix=""):
        if val is None:
            return f'<tr><td style="color:{TEXT_DIM};padding:3px 6px">{lbl}</td><td style="color:{TEXT_DIM}">—</td></tr>'
        try:
            fv = float(val)
            return f'<tr><td style="color:{TEXT_DIM};padding:3px 6px">{lbl}</td><td style="color:{TEXT};font-weight:600">{fv:,.2f}{suffix}</td></tr>'
        except Exception:
            return f'<tr><td style="color:{TEXT_DIM};padding:3px 6px">{lbl}</td><td style="color:{TEXT}">{val}</td></tr>'

    tbl_style = 'style="width:100%;font-size:0.83rem;border-collapse:collapse"'

    with t1:
        st.markdown(f'<div class="z-section">Price & Momentum</div>', unsafe_allow_html=True)
        tbl = f'<table {tbl_style}>'
        for lbl, key, suf in [("Close","close",""), ("Open","open",""), ("High","high",""),
                               ("Low","low",""), ("Change %","change","%"), ("Volume","volume",""),
                               ("RSI (14)","rsi",""), ("AO","ao",""), ("Momentum","mom","")]:
            tbl += _row(lbl, ind.get(key), suf)
        tbl += "</table>"
        st.markdown(tbl, unsafe_allow_html=True)

    with t2:
        st.markdown(f'<div class="z-section">Moving Averages</div>', unsafe_allow_html=True)
        close_v = ind.get("close") or 0
        tbl2 = f'<table {tbl_style}>'
        for lbl, key in [("EMA 20","ema20"),("EMA 50","ema50"),("EMA 100","ema100"),("EMA 200","ema200"),
                          ("SMA 20","sma20"),("SMA 50","sma50"),("SMA 100","sma100"),("SMA 200","sma200"),
                          ("BB Upper","bb_upper"),("BB Mid","bb_mid"),("BB Lower","bb_lower")]:
            val = ind.get(key)
            if val is None:
                tbl2 += f'<tr><td style="color:{TEXT_DIM};padding:3px 6px">{lbl}</td><td style="color:{TEXT_DIM}">—</td></tr>'
            else:
                c = GREEN if close_v > val else RED
                arr = "↑" if close_v > val else "↓"
                tbl2 += f'<tr><td style="color:{TEXT_DIM};padding:3px 6px">{lbl}</td><td style="color:{c};font-weight:600">{currency_symbol()}{val:,.2f} {arr}</td></tr>'
        tbl2 += "</table>"
        st.markdown(tbl2, unsafe_allow_html=True)

    with t3:
        st.markdown(f'<div class="z-section">Oscillators</div>', unsafe_allow_html=True)
        tbl3 = f'<table {tbl_style}>'
        for lbl, key in [("MACD","macd"),("MACD Signal","macd_signal"),("MACD Hist","macd_hist"),
                          ("ADX","adx"),("ADX +DI","adx_pos"),("ADX -DI","adx_neg"),
                          ("Stoch K","stoch_k"),("Stoch D","stoch_d"),("CCI 20","cci20")]:
            tbl3 += _row(lbl, ind.get(key))
        tbl3 += "</table>"
        st.markdown(tbl3, unsafe_allow_html=True)

# ─── Tab 4: Fundamentals ───────────────────────────────────────────────────────
with tabs[4]:
    if screener.get("error"):
        st.error(f"Screener unavailable: {screener.get('error')}")
    else:
        r = screener.get("ratios") or {}
        f1, f2, f3 = st.columns(3)

        def _frow(lbl, val):
            return f'<tr><td style="color:{TEXT_DIM};padding:4px 6px">{lbl}</td><td style="color:{TEXT};font-weight:600;padding:4px 6px">{val}</td></tr>'

        ftbl = f'<table {tbl_style}>'
        with f1:
            st.markdown(f'<div class="z-section">Valuation</div>', unsafe_allow_html=True)
            ftbl1 = f'<table {tbl_style}>'
            for lbl, val in [
                ("Market Cap", fmt_cr(r.get("market_cap"))),
                ("Current Price", fmt_currency(r.get("current_price")) if r.get("current_price") else "—"),
                ("P/E Ratio", f"{r.get('pe'):.1f}x" if r.get("pe") else "—"),
                ("P/B Ratio", f"{r.get('pb'):.2f}x" if r.get("pb") else "—"),
                ("Book Value/Share", fmt_currency(r.get("book_value")) if r.get("book_value") else "—"),
                ("Dividend Yield", f"{r.get('dividend_yield'):.2f}%" if r.get("dividend_yield") else "—"),
                ("EPS", fmt_currency(r.get("eps")) if r.get("eps") else "—"),
            ]:
                ftbl1 += _frow(lbl, val)
            ftbl1 += "</table>"
            st.markdown(ftbl1, unsafe_allow_html=True)
        with f2:
            st.markdown(f'<div class="z-section">Profitability</div>', unsafe_allow_html=True)
            ftbl2 = f'<table {tbl_style}>'
            for lbl, val in [
                ("ROE", f"{r.get('roe'):.1f}%" if r.get("roe") else "—"),
                ("ROCE", f"{r.get('roce'):.1f}%" if r.get("roce") else "—"),
                ("OPM %", f"{r.get('opm'):.1f}%" if r.get("opm") else "—"),
                ("NPM %", f"{r.get('npm'):.1f}%" if r.get("npm") else "—"),
                ("Sales Growth", f"{r.get('sales_growth'):.1f}%" if r.get("sales_growth") else "—"),
                ("Profit Growth", f"{r.get('profit_growth'):.1f}%" if r.get("profit_growth") else "—"),
            ]:
                ftbl2 += _frow(lbl, val)
            ftbl2 += "</table>"
            st.markdown(ftbl2, unsafe_allow_html=True)
        with f3:
            st.markdown(f'<div class="z-section">Health</div>', unsafe_allow_html=True)
            ftbl3 = f'<table {tbl_style}>'
            for lbl, val in [
                ("Debt/Equity", f"{r.get('debt_equity'):.2f}x" if r.get("debt_equity") is not None else "—"),
                ("Interest Coverage", f"{r.get('interest_coverage'):.1f}x" if r.get("interest_coverage") else "—"),
                ("Promoter %", f"{r.get('promoter_holding'):.1f}%" if r.get("promoter_holding") else "—"),
            ]:
                ftbl3 += _frow(lbl, val)
            ftbl3 += "</table>"
            st.markdown(ftbl3, unsafe_allow_html=True)

        about = screener.get("about", "")
        if about:
            st.markdown(f'<div class="z-section">About</div>', unsafe_allow_html=True)
            st.markdown(f'<p style="font-size:0.85rem;color:{TEXT_DIM}">{about}</p>', unsafe_allow_html=True)

        pros = screener.get("pros", [])
        cons = screener.get("cons", [])
        if pros or cons:
            pc1, pc2 = st.columns(2)
            with pc1:
                if pros:
                    st.markdown(f'<div class="z-section">Strengths</div>', unsafe_allow_html=True)
                    for p in pros:
                        st.markdown(f'<div style="color:{GREEN};font-size:0.83rem;padding:2px 0">✓ {p}</div>', unsafe_allow_html=True)
            with pc2:
                if cons:
                    st.markdown(f'<div class="z-section">Weaknesses</div>', unsafe_allow_html=True)
                    for c in cons:
                        st.markdown(f'<div style="color:{RED};font-size:0.83rem;padding:2px 0">✗ {c}</div>', unsafe_allow_html=True)

# ─── Tab 5: Quarterly ──────────────────────────────────────────────────────────
with tabs[5]:
    pl_q = (screener.get("pl") or {}).get("quarterly") or {}
    if pl_q:
        chart_rows = ["Sales +", "Net Profit +", "OPM %"]
        periods_q = list(next(iter(pl_q.values()), {}).keys())[:8]
        fig_q = go.Figure()
        for row_label in chart_rows:
            row_d = pl_q.get(row_label, {})
            vals_q = [row_d.get(p) for p in periods_q]
            if any(v is not None for v in vals_q):
                fig_q.add_trace(go.Bar(name=row_label, x=periods_q, y=vals_q))
        fig_q.update_layout(
            barmode="group", template="plotly_dark",
            paper_bgcolor=CARD, plot_bgcolor=CARD, height=350,
            legend=dict(orientation="h"), margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_q, use_container_width=True)
        data_rows_q = []
        for rl, dd in pl_q.items():
            row = {"Metric": rl}
            row.update({k: v for k, v in list(dd.items())[:8]})
            data_rows_q.append(row)
        if data_rows_q:
            df_qt = pd.DataFrame(data_rows_q).set_index("Metric")
            st.dataframe(df_qt, use_container_width=True, height=300)
    else:
        st.info("Quarterly data not available.")

# ─── Tab 6: Balance Sheet ──────────────────────────────────────────────────────
with tabs[6]:
    bs_data = screener.get("balance_sheet") or {}
    cf_data = screener.get("cash_flow") or {}
    bs1, bs2 = st.columns(2)
    with bs1:
        st.markdown(f'<div class="z-section">Balance Sheet</div>', unsafe_allow_html=True)
        if bs_data:
            bs_rows = [{"Item": k, "Latest": list(v.values())[-1] if v else None} for k, v in bs_data.items()]
            st.dataframe(pd.DataFrame(bs_rows), use_container_width=True, height=350, hide_index=True)
        else:
            st.info("Balance sheet data not available.")
    with bs2:
        st.markdown(f'<div class="z-section">Cash Flow</div>', unsafe_allow_html=True)
        if cf_data:
            cf_rows = [{"Item": k, "Latest": list(v.values())[-1] if v else None} for k, v in cf_data.items()]
            st.dataframe(pd.DataFrame(cf_rows), use_container_width=True, height=350, hide_index=True)
        else:
            st.info("Cash flow data not available.")

# ─── Tab 7: Ratio Trends ───────────────────────────────────────────────────────
with tabs[7]:
    hist_ratios = screener.get("historical_ratios") or {}
    if hist_ratios:
        sel_metrics = st.multiselect("Select metrics", list(hist_ratios.keys()),
                                      default=list(hist_ratios.keys())[:4])
        if sel_metrics:
            fig_rt = go.Figure()
            for metric in sel_metrics:
                vd = hist_ratios[metric]
                fig_rt.add_trace(go.Scatter(x=list(vd.keys()), y=list(vd.values()),
                                             name=metric, mode="lines+markers"))
            fig_rt.update_layout(
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=400, margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig_rt, use_container_width=True)
    else:
        st.info("Historical ratio data not available.")

# ─── Tab 8: Shareholding ───────────────────────────────────────────────────────
with tabs[8]:
    sh = screener.get("shareholding") or {}
    sh1, sh2 = st.columns([1, 2])
    with sh1:
        st.markdown(f'<div class="z-section">Latest Holding</div>', unsafe_allow_html=True)
        for lbl, key in [("Promoter","promoter"),("FII","fii"),("DII","dii"),("Public","public"),("Pledge","pledge")]:
            val = sh.get(key)
            if val is not None:
                c = GREEN if (lbl == "Promoter" and val > 50) else RED if (lbl == "Pledge" and val > 10) else TEXT
                st.markdown(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid {BORDER}">'
                            f'<span style="color:{TEXT_DIM}">{lbl}</span>'
                            f'<span style="color:{c};font-weight:700">{val:.1f}%</span></div>', unsafe_allow_html=True)
    with sh2:
        history = sh.get("history") or {}
        if history:
            fig_sh = go.Figure()
            for holder, dd in history.items():
                if dd:
                    fig_sh.add_trace(go.Scatter(x=list(dd.keys()), y=list(dd.values()),
                                                  name=holder, mode="lines+markers"))
            fig_sh.update_layout(
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=350, margin=dict(l=0, r=0, t=10, b=0), title="Shareholding History",
            )
            st.plotly_chart(fig_sh, use_container_width=True)

# ─── Tab 9: Peers ──────────────────────────────────────────────────────────────
with tabs[9]:
    peers = screener.get("peers") or []
    if peers:
        peer_df = pd.DataFrame(peers)
        display_cols = [c for c in peer_df.columns if not c.startswith("_")]
        st.dataframe(peer_df[display_cols] if display_cols else peer_df,
                     use_container_width=True, hide_index=True)
    else:
        st.info("Peers data not available from Screener.in.")

# ─── Tab 10: AI Chart Analysis ─────────────────────────────────────────────────
with tabs[10]:
    from services.chart_analysis_service import (
        analyze_chart_data, resample_ohlcv, compute_indicators_from_ohlcv,
    )

    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;'
        f'padding:12px 16px;margin-bottom:16px">'
        f'<span style="font-size:1rem;font-weight:700;color:{TEXT}">🎯 AI Chart Analysis</span><br>'
        f'<span style="font-size:0.82rem;color:{TEXT_DIM}">'
        f'Our rule-based engine analyzes the live chart data (OHLCV, indicators, patterns, fundamentals) '
        f'for <b>{sym}</b> on the selected timeframe and delivers a complete institutional-grade '
        f'breakdown — trend, S/R, entry/SL/targets, smart money read, and final verdict. '
        f'<b>100% local</b> — no API key required.'
        f'</span></div>',
        unsafe_allow_html=True,
    )

    ca1, ca2, ca3 = st.columns([1, 1, 2])

    with ca1:
        ca_timeframe = st.selectbox(
            "Chart Timeframe",
            ["Daily", "Weekly", "Monthly"],
            index=0,
            key="ca_tf_sel",
            help="Daily = intraday swings · Weekly = positional · Monthly = long-term trend",
        )
    with ca2:
        ca_lookback = st.selectbox(
            "Lookback Period",
            ["6 months", "1 year", "2 years", "5 years"],
            index=1,
            key="ca_lb_sel",
        )
    with ca3:
        ca_extra = st.text_input(
            "Additional context (optional)",
            placeholder="e.g. 'Just broke out of 6-month base', 'Budget-related rally'...",
            key="ca_extra",
        )

    st.markdown("---")

    # ── Resolve OHLCV for the chosen timeframe ─────────────────────────────────
    # Map lookback to fetch period
    lb_map = {"6 months": "6m", "1 year": "1y", "2 years": "2y", "5 years": "5y"}
    fetch_period = lb_map.get(ca_lookback, "1y")

    # Re-fetch if needed (different from the default timeframe fetched for the page)
    need_refetch = (fetch_period != timeframe)
    if need_refetch:
        @st.cache_data(ttl=600, show_spinner=False)
        def _fetch_ohlcv_ca(symbol, period):
            return get_tv_ohlcv_history(symbol, period=period, interval="1d")
        df_ca = _fetch_ohlcv_ca(sym, fetch_period)
    else:
        df_ca = df_ohlcv

    if df_ca is None or df_ca.empty:
        st.error("OHLCV data unavailable — cannot run chart analysis for this stock.")
    else:
        # Resample to target timeframe
        df_tf = resample_ohlcv(df_ca, ca_timeframe)

        # Compute indicators on the target timeframe's candles
        ca_indicators = compute_indicators_from_ohlcv(df_tf)

        # Detect patterns on target timeframe
        ca_patterns = []
        if df_tf is not None and not df_tf.empty:
            try:
                ca_patterns = detect_patterns(df_tf)
            except Exception:
                ca_patterns = []

        # Preview summary (so user sees what's about to be sent)
        prev1, prev2, prev3, prev4 = st.columns(4)
        _last_close = float(df_tf["Close"].iloc[-1]) if df_tf is not None and not df_tf.empty else 0
        _rsi_v = ca_indicators.get("rsi")
        _adx_v = ca_indicators.get("adx")
        prev1.metric("Candles", f"{len(df_tf) if df_tf is not None else 0}")
        prev2.metric(f"Close ({ca_timeframe})", fmt_currency(_last_close))
        prev3.metric("RSI", f"{_rsi_v:.1f}" if _rsi_v else "—")
        prev4.metric("Patterns", f"{len(ca_patterns)}")

        # Show preview of recent candles (condensed)
        with st.expander(f"🔍 Data being sent to AI ({ca_timeframe} · {len(df_tf) if df_tf is not None else 0} candles)", expanded=False):
            if df_tf is not None and not df_tf.empty:
                st.dataframe(df_tf.tail(20), use_container_width=True, height=300)
            if ca_indicators:
                st.markdown("**Computed indicators on this timeframe:**")
                ind_rows = [{"Indicator": k, "Value": f"{v:,.2f}" if isinstance(v, (int, float)) else str(v)}
                            for k, v in ca_indicators.items() if v is not None]
                st.dataframe(pd.DataFrame(ind_rows), use_container_width=True, hide_index=True, height=260)
            if ca_patterns:
                st.markdown("**Engine-detected patterns:**")
                for p in ca_patterns:
                    name = p.get("name", "?") if isinstance(p, dict) else "?"
                    conf = p.get("confidence", 0) if isinstance(p, dict) else 0
                    d = p.get("direction", "neutral") if isinstance(p, dict) else "neutral"
                    st.markdown(f"- **{name}** — {d}, {conf}% confidence")

        st.markdown("")
        analyze_btn = st.button(
            f"🔬 Run Rule-Based Chart Analysis on {sym} ({ca_timeframe})",
            type="primary",
            key="ca_run",
            use_container_width=True,
        )

        _cache_key_ca = f"_ca_result_{sym}_{ca_timeframe}"

        if analyze_btn:
            ratios_for_ai = screener.get("ratios") or {}
            company_nm   = screener.get("name", "")
            sector_nm    = screener.get("sector", "")
            with st.spinner(f"Analyzing {sym} on {ca_timeframe} timeframe..."):
                result = analyze_chart_data(
                    symbol=sym,
                    timeframe=ca_timeframe,
                    ohlcv_df=df_tf,
                    indicators=ca_indicators,
                    patterns=ca_patterns,
                    fundamentals=ratios_for_ai,
                    extra_context=ca_extra,
                    company_name=company_nm,
                    sector=sector_nm,
                )
            if result["success"]:
                st.session_state[_cache_key_ca] = result["analysis"]
                st.success("✅ Analysis complete!")
                st.markdown("---")
                _display_chart_analysis(result["analysis"], f"{sym}_{ca_timeframe}")
            else:
                st.error(f"Analysis failed: {result['error']}")

        elif _cache_key_ca in st.session_state:
            st.markdown("---")
            st.info(f"Showing previous {ca_timeframe} analysis for {sym}. Click **Run AI Analysis** to refresh.")
            _display_chart_analysis(st.session_state[_cache_key_ca], f"{sym}_{ca_timeframe}")

    # ── Info ───────────────────────────────────────────────────────────────────
    with st.expander("ℹ️ How this works", expanded=False):
        st.markdown(f"""
<div style="font-size:0.85rem;color:{TEXT_DIM}">

This tab does <b>not</b> need a chart image. Instead it sends Claude the actual numerical data
that would be visible on your chart:

<ul>
<li><b>OHLCV candles</b> — last 60 bars on the selected timeframe</li>
<li><b>Technical indicators</b> — RSI, MACD, ADX, EMAs, SMAs, Bollinger Bands, Stochastic, CCI (all recomputed for the timeframe)</li>
<li><b>Detected patterns</b> — from the pattern engine</li>
<li><b>Price statistics</b> — 52-week high/low, recent pivots, returns across timeframes, volatility</li>
<li><b>Fundamentals</b> — PE, ROE, ROCE, D/E, promoter holding, growth rates</li>
</ul>

Claude then delivers a structured <b>14-point institutional-grade analysis</b> with exact ₹ entry/SL/target levels,
probability scores, red flags, and a final verdict.

<b>No API key required.</b> Analysis runs entirely on your machine.
</div>
""", unsafe_allow_html=True)
