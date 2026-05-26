"""
Pattern Lab — pattern-driven multi-timeframe scanner.

User flow:
  1. Pick a universe (NIFTY 50/100/500/sector index)
  2. Pick one or more chart patterns from the Learn library
  3. Pick breakout state filter (verge / fresh / confirmed / any)
  4. Engine scans every stock at 1d · 1w · 1mo, finds matching patterns,
     tags each match with its breakout state, ranks by confluence
  5. Click any stock → see chart with the pattern drawn, target/SL/entry overlays,
     inline timeframe switcher, plotly drawing tools enabled
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW, ORANGE
apply_theme()
from utils.tv_chart import render_tv_chart

from engines.pattern_engine import detect_patterns
from services.universe_sync import (
    get_universe_symbols, get_all_universe_names, universe_display_map,
)
from services.market_data_service import get_ohlcv_history
from services.ai_service import analyze_stock
from services.pattern_examples import all_pattern_names, get_pattern_by_name
from services.breakout_service import (
    classify_breakout, classify_multi_timeframe,
    BULLISH_STATES, BEARISH_STATES, STATE_COLOR, STATE_LABEL,
    VERGE_BREAKOUT, FRESH_BREAKOUT, CONFIRMED_BREAKOUT, EXTENDED, NO_BREAKOUT,
    VERGE_BREAKDOWN, FRESH_BREAKDOWN, CONFIRMED_BREAKDOWN,
)

DIRECTION_COLOR = {"bullish": GREEN, "bearish": RED, "neutral": YELLOW}

TIMEFRAMES = [
    ("1d",  "1y",  "1d",  1.0),
    ("1w",  "5y",  "1W",  1.3),
    ("1mo", "max", "1M",  1.5),
]


def _norm_dir(d: str) -> str:
    return (d or "neutral").strip().lower()


def _breakout_priority(state: str) -> int:
    return {
        FRESH_BREAKOUT: 5, CONFIRMED_BREAKOUT: 4, VERGE_BREAKOUT: 3,
        EXTENDED: 1, NO_BREAKOUT: 0,
        FRESH_BREAKDOWN: 5, CONFIRMED_BREAKDOWN: 4, VERGE_BREAKDOWN: 3,
    }.get(state, 0)


def _render_studio_chart(symbol, df, patterns, timeframe, row_meta, key_suffix=""):
    """Render a TradingView-style chart with candles, EMAs, pattern lines, target/SL/entry."""
    if df is None or df.empty:
        st.warning(f"No {timeframe} data.")
        return

    # Pull pattern trendlines + the strongest pattern's key-levels
    pat_lines = []
    key_levels = {}
    for pat in patterns:
        for ln in pat.get("lines", []) or []:
            if not isinstance(ln, dict):
                continue
            ln_copy = dict(ln)
            ln_copy.setdefault("color",
                               DIRECTION_COLOR.get(_norm_dir(pat.get("direction")), YELLOW))
            pat_lines.append(ln_copy)
        kl = pat.get("key_levels") or {}
        if kl.get("support") and not key_levels.get("support"):
            key_levels["support"] = kl["support"]
        if kl.get("resistance") and not key_levels.get("resistance"):
            key_levels["resistance"] = kl["resistance"]

    render_tv_chart(
        df=df, symbol=symbol, height=520, show_volume=True,
        show_emas=(20, 50, 200),
        entry=row_meta.get("Entry ₹"),
        target=row_meta.get("Target ₹"),
        stop=row_meta.get("Stop ₹"),
        key_levels=key_levels or None,
        pattern_lines=pat_lines,
        title=f"{symbol} — {timeframe}",
        key_suffix=f"studio_{key_suffix}",
    )


def _render_pattern_card(p: dict, container):
    pdir = _norm_dir(p.get("direction"))
    pc   = DIRECTION_COLOR.get(pdir, YELLOW)
    conf = p.get("confidence", 0) or 0
    name = p.get("name", "—")
    desc = (p.get("description") or "")[:140]
    kl   = p.get("key_levels") or {}
    tgt  = f"₹{kl['target']:,.0f}" if kl.get("target") else "—"
    stp  = f"₹{kl['stop']:,.0f}" if kl.get("stop") else "—"
    bk   = p.get("breakout") or {}
    bk_label = bk.get("label", "—")
    bk_color = bk.get("color", TEXT_DIM)
    bk_dist  = bk.get("distance_pct")
    bk_vol   = "Y" if bk.get("volume_confirmed") else "—"

    bg = ("rgba(38,166,154,0.08)" if pdir == "bullish"
          else "rgba(239,83,80,0.08)" if pdir == "bearish"
          else "rgba(245,158,11,0.08)")

    lib = get_pattern_by_name(name)
    when = lib.get("when_to_trade", "") if lib else ""

    with container:
        st.markdown(
            f'<div style="background:{bg};border:1px solid {pc};border-radius:8px;'
            f'padding:10px 12px;margin-bottom:8px">'
            f'<div style="color:{pc};font-weight:700;font-size:0.92rem">{name}</div>'
            f'<div style="color:{TEXT_DIM};font-size:0.72rem;margin:2px 0">'
            f'Confidence <b style="color:{pc}">{conf}%</b> · '
            f'<span style="color:{bk_color};font-weight:600">{bk_label}</span>'
            f'{f" · {bk_dist:+.2f}%" if bk_dist is not None else ""} · vol✓ {bk_vol}'
            f'</div>'
            f'<div style="color:{TEXT_DIM};font-size:0.74rem;margin-top:4px">{desc}</div>'
            f'<div style="margin-top:6px;font-size:0.78rem">'
            f'<span style="color:{GREEN}">▲ T: {tgt}</span> &nbsp; '
            f'<span style="color:{RED}">▼ S: {stp}</span></div>'
            f'{f"<div style='color:{TEXT};font-size:0.74rem;margin-top:6px;border-top:1px solid {BORDER};padding-top:6px'><b>Entry rule:</b> {when}</div>" if when else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Page ─────────────────────────────────────────────────────────────────────
st.markdown("## 🧬 Pattern Lab")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:12px">'
    f'Filter the universe by chart pattern + breakout state. '
    f'Every stock scanned across <b>1d · 1w · 1mo</b>. '
    f'Click any match to see the chart with the pattern drawn, target/SL overlays, '
    f'inline timeframe switching, and Plotly drawing tools.'
    f'</div>',
    unsafe_allow_html=True,
)

tab_scan, tab_single = st.tabs(["📡 Pattern Scan", "🔍 Single-Stock Studio"])


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_syms(u: str):
    return get_universe_symbols(u)


disp_map  = universe_display_map()
all_names = get_all_universe_names()
uni_labels = [disp_map.get(n, n) for n in all_names]


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PATTERN SCAN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_scan:
    pattern_lib_names = all_pattern_names()

    bc1, bc2 = st.columns([1, 2])
    with bc1:
        sel_label = st.selectbox("Index / Universe", uni_labels, key="pl_universe")
        sel_universe = all_names[uni_labels.index(sel_label)]
        all_syms = _cached_syms(sel_universe)
        st.caption(f"{len(all_syms)} stocks in {sel_universe}")
    with bc2:
        sel_patterns = st.multiselect(
            "Chart patterns to scan for (multi-select)",
            options=pattern_lib_names,
            default=[],
            key="pl_patterns",
            help="Pulled from the Learn library. Empty = all patterns.",
        )
        if not sel_patterns:
            st.caption(f"No filter — will list **all** detected patterns.")

    bc3, bc4, bc5 = st.columns([1, 2, 1])
    with bc3:
        bulk_max = st.number_input("Max stocks (0 = all)", min_value=0,
                                    max_value=len(all_syms), value=0, step=10,
                                    key="pl_max")
    with bc4:
        breakout_filter = st.multiselect(
            "Breakout state filter (multi-select; empty = any)",
            options=[
                "Verge of breakout", "Fresh breakout (1 candle)", "Confirmed breakout",
                "Extended (late entry)", "Verge of breakdown",
                "Fresh breakdown", "Confirmed breakdown",
            ],
            default=[],
            key="pl_break_filter",
            help="Filter results by where price is relative to the breakout level.",
        )
    with bc5:
        bulk_min_conf = st.slider("Min pattern confidence %", 30, 90, 50, step=5,
                                   key="pl_conf")

    direction_filter = st.radio("Direction filter", ["All", "Bullish", "Bearish"],
                                  horizontal=True, key="pl_dir")

    # ── worker ──────────────────────────────────────────────────────────────
    def _scan_one_mtf(sym: str):
        per_tf = {}
        all_patterns = []
        df_d = None
        for tf_label, period, interval, weight in TIMEFRAMES:
            try:
                df = get_ohlcv_history(sym, period=period, interval=interval)
                if df is None or len(df) < 30:
                    continue
                pats = detect_patterns(df) or []
                # Tag each pattern with timeframe + breakout state
                for p in pats:
                    p["timeframe"] = tf_label
                    p["weighted_conf"] = (p.get("confidence", 0) or 0) * weight
                    # Classify breakout against pattern's resistance level if available
                    kl = p.get("key_levels") or {}
                    res_level = kl.get("resistance") or kl.get("target")
                    p["breakout"] = classify_breakout(df, level_override=res_level)
                per_tf[tf_label] = {"patterns": pats, "df": df}
                all_patterns.extend(pats)
                if tf_label == "1d":
                    df_d = df
            except Exception:
                continue
        return sym, all_patterns, per_tf, df_d

    if st.button("▶ Run Pattern Scan", type="primary", key="pl_scan_btn"):
        bulk_syms = all_syms if bulk_max == 0 else all_syms[: int(bulk_max)]
        st.info(f"Scanning **{len(bulk_syms)}** stocks across **3 timeframes** (1d · 1w · 1mo)…")
        prog = st.progress(0.0)
        raw, done = [], 0
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_scan_one_mtf, s): s for s in bulk_syms}
            for fut in as_completed(futs):
                done += 1
                cur = futs[fut]
                prog.progress(done / len(bulk_syms),
                              text=f"{cur} ({done}/{len(bulk_syms)})")
                try:
                    raw.append(fut.result())
                except Exception:
                    pass
        prog.empty()

        # ── Aggregate per stock ────────────────────────────────────────────
        rows, details = [], {}
        for sym, all_pats, per_tf, df_d in raw:
            # Apply pattern-name filter
            filtered = [p for p in all_pats if (p.get("confidence", 0) or 0) >= bulk_min_conf]
            if sel_patterns:
                pat_set = {n.lower() for n in sel_patterns}
                filtered = [p for p in filtered if (p.get("name", "") or "").lower() in pat_set]
            if direction_filter == "Bullish":
                filtered = [p for p in filtered if _norm_dir(p.get("direction")) == "bullish"]
            elif direction_filter == "Bearish":
                filtered = [p for p in filtered if _norm_dir(p.get("direction")) == "bearish"]
            if breakout_filter:
                bk_set = set(breakout_filter)
                filtered = [p for p in filtered
                            if (p.get("breakout") or {}).get("label", "") in bk_set]
            if not filtered:
                continue

            tfs_present = {p.get("timeframe") for p in filtered}
            bull_count = sum(1 for p in filtered if _norm_dir(p.get("direction")) == "bullish")
            bear_count = sum(1 for p in filtered if _norm_dir(p.get("direction")) == "bearish")
            avg_conf   = sum((p.get("confidence", 0) or 0) for p in filtered) / len(filtered)

            # Score breakout bonus
            best_break = max(filtered,
                             key=lambda p: _breakout_priority((p.get("breakout") or {}).get("state")))
            break_state = (best_break.get("breakout") or {}).get("state", NO_BREAKOUT)

            confluence = (
                len(tfs_present) * 22
                + min(34, len(filtered) * 5)
                + (avg_conf - 50) * 0.4
                + _breakout_priority(break_state) * 6
            )
            confluence = max(0, min(100, confluence))

            net_dir = "bullish" if bull_count > bear_count else "bearish" if bear_count > bull_count else "neutral"
            best = max(filtered, key=lambda p: p.get("weighted_conf", 0))
            kl = best.get("key_levels") or {}
            best_break_obj = best_break.get("breakout") or {}

            rows.append({
                "Symbol":        sym,
                "Confluence":    round(confluence, 0),
                "Bias":          net_dir.title(),
                "Breakout":      best_break_obj.get("label", "—"),
                "TF (best)":     best_break.get("timeframe", "—"),
                "TFs Hit":       ", ".join(sorted(tfs_present, key=lambda t: ["1d","1w","1mo"].index(t) if t in ["1d","1w","1mo"] else 9)),
                "# Patterns":    len(filtered),
                "Best Pattern":  best.get("name", "—"),
                "Conf %":        best.get("confidence", 0),
                "Entry ₹":       best_break_obj.get("current_price"),
                "Target ₹":      round(kl["target"], 2) if kl.get("target") else None,
                "Stop ₹":        round(kl["stop"],   2) if kl.get("stop")   else None,
                "Vol✓":          "Y" if best_break_obj.get("volume_confirmed") else "—",
            })
            details[sym] = {
                "patterns": filtered, "per_tf": per_tf, "df_d": df_d,
                "best_pattern": best, "best_break": best_break,
            }

        rows.sort(key=lambda r: r["Confluence"], reverse=True)

        st.session_state.update({
            "pl_table": rows,
            "pl_details": details,
            "pl_stats":   {"scanned": len(raw), "found": len(rows),
                           "raw": sum(len(r[1]) for r in raw)},
        })

    # ── Render ───────────────────────────────────────────────────────────────
    rows    = st.session_state.get("pl_table", [])
    details = st.session_state.get("pl_details", {})
    stats   = st.session_state.get("pl_stats", {})

    if stats:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Stocks Scanned", stats.get("scanned", 0))
        s2.metric("With Patterns",  stats.get("found", 0))
        s3.metric("Raw Detections", stats.get("raw", 0))
        s4.metric("Timeframes",     "1d · 1w · 1mo")
        st.markdown("---")

    if rows:
        df_tbl = pd.DataFrame(rows)

        def _bias_style(v):
            if isinstance(v, str) and "ullish" in v: return f"color:{GREEN};font-weight:700"
            if isinstance(v, str) and "earish" in v: return f"color:{RED};font-weight:700"
            return f"color:{YELLOW}"

        def _conf_style(v):
            try:
                f = float(v)
                if f >= 75: return f"color:{GREEN};font-weight:700"
                if f >= 50: return f"color:{YELLOW};font-weight:600"
                return f"color:{TEXT_DIM}"
            except Exception: return ""

        def _breakout_style(v):
            sv = str(v)
            if "Fresh breakout" in sv:       return f"color:{GREEN};font-weight:700"
            if "Confirmed breakout" in sv:   return f"color:#1ec48a;font-weight:700"
            if "Verge of breakout" in sv:    return f"color:{YELLOW};font-weight:600"
            if "Verge of breakdown" in sv:   return f"color:{YELLOW};font-weight:600"
            if "Fresh breakdown" in sv:      return f"color:{RED};font-weight:700"
            if "Confirmed breakdown" in sv:  return f"color:#d32f2f;font-weight:700"
            if "Extended" in sv:             return f"color:{TEXT_DIM};font-style:italic"
            return ""

        st.dataframe(
            df_tbl.style
                  .map(_bias_style, subset=["Bias"])
                  .map(_conf_style, subset=["Confluence"])
                  .map(_breakout_style, subset=["Breakout"]),
            use_container_width=True, hide_index=True, height=420,
        )

        # ── Per-stock studio ────────────────────────────────────────────────
        st.markdown('<div style="color:#e2e8f0;font-weight:600;margin:14px 0 4px">Click a stock for chart studio</div>',
                    unsafe_allow_html=True)
        for row in rows[:25]:
            sym = row["Symbol"]
            d = details.get(sym, {})
            pats = d.get("patterns", [])
            per_tf = d.get("per_tf", {})

            with st.expander(
                f"**{sym}**  ·  Confluence **{row['Confluence']:.0f}**  ·  "
                f"{row['Bias']}  ·  **{row['Breakout']}** on {row['TF (best)']}  ·  "
                f"{row['# Patterns']} patterns"
            ):
                # Inline timeframe switcher
                tf_options = [k for k in ["1d", "1w", "1mo"] if k in per_tf]
                if not tf_options:
                    st.warning("No timeframe data available.")
                    continue
                _tk = f"pl_tf_{sym}"
                # default to 1d if available
                default_idx = tf_options.index("1d") if "1d" in tf_options else 0
                chosen_tf = st.radio(f"Timeframe — {sym}", tf_options,
                                       index=default_idx, horizontal=True, key=_tk)
                tf_data = per_tf.get(chosen_tf, {})
                tf_df = tf_data.get("df")
                tf_pats = [p for p in pats if p.get("timeframe") == chosen_tf]
                _render_studio_chart(sym, tf_df, tf_pats, chosen_tf, row, key_suffix=f"scan_{sym}")

                # Per-pattern analysis cards under the chart
                if tf_pats:
                    st.markdown(
                        f'<div style="color:{TEXT_DIM};font-size:0.78rem;margin-top:8px">'
                        f'<b>{len(tf_pats)} pattern(s) on {chosen_tf} timeframe:</b></div>',
                        unsafe_allow_html=True,
                    )
                    cols = st.columns(min(len(tf_pats), 3))
                    for j, p in enumerate(tf_pats[:6]):
                        _render_pattern_card(p, cols[j % 3])
                else:
                    st.caption(f"No patterns on {chosen_tf}. Switch timeframe above to see other matches.")

        st.download_button(
            "⬇ Download CSV",
            df_tbl.to_csv(index=False),
            f"pattern_scan_{sel_universe.replace(' ','_')}.csv", "text/csv",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — SINGLE STOCK STUDIO (deep multi-timeframe analysis)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_single:
    ss1, ss2 = st.columns([2, 2])
    with ss1:
        ss_label    = st.selectbox("Index", uni_labels, key="pl_ss_idx")
        ss_universe = all_names[uni_labels.index(ss_label)]
        ss_syms     = _cached_syms(ss_universe)
    with ss2:
        ss_symbol  = st.selectbox("Stock", ss_syms, key="pl_ss_stock")
    run_ai = st.checkbox("Add AI verdict (combines all timeframes)", value=True, key="pl_ai")

    if st.button("▶ Deep Multi-Timeframe Analyze", type="primary", key="pl_ss_btn"):
        with st.spinner(f"Scanning {ss_symbol} on 1d · 1w · 1mo…"):
            all_pats, per_tf_data, df_daily = [], {}, None
            for tf_label, period, interval, weight in TIMEFRAMES:
                try:
                    df = get_ohlcv_history(ss_symbol, period=period, interval=interval)
                    if df is None or len(df) < 30:
                        continue
                    pats = detect_patterns(df) or []
                    for p in pats:
                        p["timeframe"] = tf_label
                        kl = p.get("key_levels") or {}
                        p["breakout"] = classify_breakout(df,
                                                          level_override=kl.get("resistance") or kl.get("target"))
                    per_tf_data[tf_label] = {"patterns": pats, "df": df}
                    all_pats.extend(pats)
                    if tf_label == "1d":
                        df_daily = df
                except Exception:
                    continue

            mtf_classification = classify_multi_timeframe(
                ss_symbol,
                lambda s, p, i: get_ohlcv_history(s, period=p, interval=i),
            )

        ai_v = None
        if run_ai and df_daily is not None:
            with st.spinner("AI verdict…"):
                ai_v = analyze_stock(ss_symbol, tv={}, screener={}, patterns=all_pats)

        st.session_state["pl_ss"] = {
            "symbol":   ss_symbol,
            "all_pats": all_pats,
            "per_tf":   per_tf_data,
            "df_daily": df_daily,
            "ai":       ai_v,
            "mtf":      mtf_classification,
        }

    res = st.session_state.get("pl_ss")
    if not res:
        st.info("Pick a stock and click **Deep Multi-Timeframe Analyze**.")
    else:
        sym_r   = res["symbol"]
        pats_r  = res["all_pats"]
        per_tf  = res["per_tf"]
        ai_v    = res.get("ai")
        mtf     = res.get("mtf", {})

        # ── Multi-timeframe breakout summary banner ──────────────────────────
        overall = mtf.get("_overall", "—")
        st.markdown(
            f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;'
            f'padding:12px 16px;margin:10px 0;color:{TEXT}"><b>Multi-timeframe state:</b> {overall}</div>',
            unsafe_allow_html=True,
        )
        mtcols = st.columns(4)
        for i, tf in enumerate(["1d", "1w", "1mo"]):
            d_ = mtf.get(tf, {})
            color = d_.get("color", TEXT_DIM)
            with mtcols[i]:
                st.markdown(
                    f'<div style="background:{CARD};border:1px solid {color};border-radius:6px;'
                    f'padding:8px 12px"><div style="color:{TEXT_DIM};font-size:0.72rem">{tf}</div>'
                    f'<div style="color:{color};font-weight:700;font-size:0.85rem">{d_.get("label","—")}</div>'
                    f'<div style="color:{TEXT_DIM};font-size:0.7rem">'
                    f'lvl ₹{d_.get("level") or "—"} · '
                    f'{d_.get("distance_pct") or 0:+.2f}% · '
                    f'vol✓ {"Y" if d_.get("volume_confirmed") else "—"}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        # ── AI verdict ────────────────────────────────────────────────────────
        if ai_v:
            vc = GREEN if "BUY" in ai_v.verdict else RED if "SELL" in ai_v.verdict else YELLOW
            bg = ("rgba(38,166,154,0.1)" if "BUY" in ai_v.verdict
                  else "rgba(239,83,80,0.1)" if "SELL" in ai_v.verdict
                  else "rgba(245,158,11,0.1)")
            st.markdown(
                f'<div style="background:{bg};border:1px solid {vc};border-radius:8px;'
                f'padding:14px 18px;margin:12px 0;display:flex;justify-content:space-between">'
                f'<div><div style="color:{TEXT_DIM};font-size:0.78rem">AI VERDICT</div>'
                f'<div style="color:{vc};font-size:1.4rem;font-weight:700">{ai_v.verdict}</div></div>'
                f'<div style="text-align:right"><div style="color:{TEXT_DIM};font-size:0.78rem">SCORE</div>'
                f'<div style="color:{vc};font-size:1.4rem;font-weight:700">{ai_v.score:.0f}/100</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Inline timeframe switcher for the studio chart ───────────────────
        tf_avail = [k for k in ["1d", "1w", "1mo"] if k in per_tf]
        if tf_avail:
            _stk = f"pl_ss_tf_{sym_r}"
            chosen = st.radio(f"Studio timeframe", tf_avail,
                                index=tf_avail.index("1d") if "1d" in tf_avail else 0,
                                horizontal=True, key=_stk)
            tf_pats = [p for p in pats_r if p.get("timeframe") == chosen]
            tf_df   = per_tf.get(chosen, {}).get("df")
            best_kl = (max(tf_pats, key=lambda p: p.get("confidence", 0)) if tf_pats else {}).get("key_levels", {}) or {}
            row_meta = {
                "Entry ₹":  ai_v.price_target and ((ai_v.price_target + ai_v.stop_loss) / 2) if ai_v else None,
                "Target ₹": (ai_v.price_target if ai_v else None) or best_kl.get("target"),
                "Stop ₹":   (ai_v.stop_loss   if ai_v else None) or best_kl.get("stop"),
            }
            _render_studio_chart(sym_r, tf_df, tf_pats, chosen, row_meta, key_suffix=f"single_{sym_r}")

            # Per-pattern cards
            if tf_pats:
                st.markdown(
                    f'<div style="color:{BLUE};font-weight:700;font-size:0.9rem;margin:12px 0 4px">'
                    f'⏱ {chosen} timeframe — {len(tf_pats)} patterns</div>',
                    unsafe_allow_html=True,
                )
                cols = st.columns(min(len(tf_pats), 3))
                for j, p in enumerate(tf_pats[:6]):
                    _render_pattern_card(p, cols[j % 3])

        # AI signal chain
        if ai_v and ai_v.signals:
            st.markdown('<div style="color:#e2e8f0;font-weight:600;margin:12px 0 4px">AI Signal Chain</div>',
                        unsafe_allow_html=True)
            sc = st.columns(2)
            for i, sig in enumerate(ai_v.signals):
                c = (GREEN if any(w in sig.lower() for w in ["bull", "buy", "above", "strong"])
                     else RED if any(w in sig.lower() for w in ["bear", "sell", "below", "weak"])
                     else TEXT_DIM)
                with sc[i % 2]:
                    st.markdown(f'<div style="font-size:0.83rem;color:{c};padding:3px 0">→ {sig}</div>',
                                unsafe_allow_html=True)


