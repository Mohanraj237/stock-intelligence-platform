from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import json


from utils.theme import apply_theme
apply_theme()

from engines.rule_engine import (Rule, RuleCondition, evaluate_rules, apply_rules_to_universe,
    PRESET_RULES, AVAILABLE_FIELDS, OPERATORS)
from storage.file_store import get_rules, save_rules, add_rule, delete_rule
from services.universe_sync import get_universe_symbols, universe_display_map, get_all_universe_names
from services.tradingview_service import get_tv_analysis, tv_score
from engines.scoring_engine import build_stock_snapshot

st.markdown("## ⚙️ Rule Engine")
st.markdown("Create custom stock filters using visual rules. Combine technical and fundamental conditions.")

tab1, tab2, tab3 = st.tabs(["🔧 Build Rules", "📋 Saved Rules", "🚀 Apply to Universe"])

# ── Tab 1: Build Rules ─────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Create New Rule")

    with st.form("new_rule_form"):
        rule_name = st.text_input("Rule Name", placeholder="e.g., My Breakout Filter")
        rule_desc = st.text_area("Description", placeholder="Describe what this rule does...", height=70)
        logic = st.radio("Condition Logic", ["AND", "OR"], horizontal=True,
                         help="AND: all conditions must pass. OR: any condition can pass.")

        st.markdown("#### Conditions")
        num_conditions = st.number_input("Number of conditions", min_value=1, max_value=10, value=3)

        conditions = []
        field_labels = [f[0] for f in AVAILABLE_FIELDS]
        field_keys   = [f[1] for f in AVAILABLE_FIELDS]

        for i in range(int(num_conditions)):
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            with c1:
                fi = st.selectbox(f"Field {i+1}", field_labels, key=f"field_{i}")
                fk = field_keys[field_labels.index(fi)]
            with c2:
                op = st.selectbox(f"Operator {i+1}", [">", ">=", "<", "<=", "==", "between"], key=f"op_{i}")
            with c3:
                val = st.number_input(f"Value {i+1}", value=0.0, key=f"val_{i}", format="%.2f")
            with c4:
                val2 = st.number_input(f"Value2 (between) {i+1}", value=100.0, key=f"val2_{i}", format="%.2f") if op == "between" else None
            with c5:
                st.markdown(f"<br>", unsafe_allow_html=True)

            conditions.append({
                "field": fk, "op": op,
                "value": val,
                "value2": val2 if op == "between" else None,
            })

        submitted = st.form_submit_button("💾 Save Rule", type="primary")
        if submitted:
            if not rule_name:
                st.error("Rule name is required.")
            else:
                new_rule = {"name": rule_name, "description": rule_desc, "logic": logic, "conditions": conditions}
                rule_id = add_rule(new_rule)
                st.success(f"Rule '{rule_name}' saved with ID: {rule_id}")

    # Load presets
    st.markdown("### Load a Preset Rule")
    preset_names = [r["name"] for r in PRESET_RULES]
    sel_preset = st.selectbox("Preset Rules", preset_names)
    if st.button("Load Preset"):
        pr = next((r for r in PRESET_RULES if r["name"] == sel_preset), None)
        if pr:
            add_rule(pr)
            st.success(f"Loaded preset: {sel_preset}")
            st.rerun()

# ── Tab 2: Saved Rules ─────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Saved Rules")
    saved = get_rules()
    if not saved:
        st.info("No rules saved yet. Create one in the 'Build Rules' tab.")
    else:
        for rule in saved:
            with st.expander(f"📋 {rule.get('name', 'Unnamed')} — {rule.get('logic', 'AND')} · {len(rule.get('conditions', []))} conditions"):
                st.markdown(f"**Description:** {rule.get('description', '')}")
                st.markdown(f"**Logic:** {rule.get('logic', 'AND')}")
                conds = rule.get("conditions", [])
                if conds:
                    df_c = pd.DataFrame(conds)
                    st.dataframe(df_c, use_container_width=True)
                col_del, col_export = st.columns(2)
                with col_del:
                    if st.button(f"🗑️ Delete", key=f"del_{rule.get('id','')}"):
                        delete_rule(rule.get("id", ""))
                        st.rerun()
                with col_export:
                    st.download_button("📥 Export JSON", json.dumps(rule, indent=2),
                                       f"{rule.get('name','rule')}.json", "application/json",
                                       key=f"exp_{rule.get('id','')}")

# ── Tab 3: Apply Rules ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Apply Rules to Universe")
    saved_rules = get_rules()
    if not saved_rules:
        st.warning("No saved rules. Create rules in the 'Build Rules' tab first.")
        st.stop()

    rule_names = [r.get("name", f"Rule {i}") for i, r in enumerate(saved_rules)]
    selected_rule_names = st.multiselect("Select Rules to Apply", rule_names, default=rule_names[:1] if rule_names else [])
    rules_to_apply = [r for r in saved_rules if r.get("name") in selected_rule_names]

    multi_logic = st.radio("Cross-rule logic", ["ALL rules must pass", "ANY rule must pass"], horizontal=True)
    logic_mode = "ALL" if "ALL" in multi_logic else "ANY"

    disp_map = universe_display_map()
    names = get_all_universe_names()
    labels = [disp_map.get(n, n) for n in names]
    sel_label = st.selectbox("Universe", labels, key="rule_universe")
    sel_name = names[labels.index(sel_label)]
    max_stocks = st.number_input("Max Stocks to Scan", min_value=10, max_value=300, value=50, step=10, key="rule_max")

    if st.button("🚀 Apply Rules", type="primary") and rules_to_apply:
        symbols = get_universe_symbols(sel_name, limit=max_stocks)
        progress = st.progress(0, "Scanning...")
        stocks = []
        for i, sym in enumerate(symbols):
            try:
                tv = get_tv_analysis(sym, "1d") or {}
                ind = tv.get("indicators") or {}
                snap = {
                    "Symbol": sym, "Signal": tv.get("recommendation", "NEUTRAL"),
                    "tv_analysis": tv,
                    "RSI": ind.get("rsi"), "MACD": ind.get("macd"),
                    "Price": ind.get("close"), "Change %": ind.get("change"),
                    "SMA 50": ind.get("sma50"), "SMA 200": ind.get("sma200"),
                }
                stocks.append(snap)
            except Exception:
                pass
            progress.progress((i+1)/len(symbols))
        progress.empty()

        matched = apply_rules_to_universe(rules_to_apply, stocks, logic=logic_mode)
        st.success(f"**{len(matched)} stocks** matched your rules out of {len(stocks)} scanned.")
        if matched:
            display_df = pd.DataFrame([{
                "Symbol": s.get("Symbol"), "Price": s.get("Price"),
                "RSI": s.get("RSI"), "Signal": s.get("Signal"),
                "Rules Passed": sum(1 for e in s.get("_rule_results", []) if e.get("passed")),
                "Total Rules": len(s.get("_rule_results", [])),
            } for s in matched])
            st.dataframe(display_df, use_container_width=True)
            st.download_button("📥 Export Results", display_df.to_csv(index=False), "rule_results.csv", "text/csv")
