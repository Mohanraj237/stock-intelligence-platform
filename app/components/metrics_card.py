from __future__ import annotations
import streamlit as st
from typing import Optional

def _fmt(v, suffix="", decimals=2, prefix="") -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if abs(f) >= 1e4:
            return f"{prefix}{f:,.0f}{suffix}"
        return f"{prefix}{f:.{decimals}f}{suffix}"
    except Exception:
        return str(v)

def render_kpi_row(metrics: list[dict], cols: int = 4):
    """Render a row of KPI metric tiles.
    Each metric dict: {label, value, delta=None, help=None, color=None}
    """
    grid = st.columns(cols)
    for i, m in enumerate(metrics):
        with grid[i % cols]:
            label = m.get("label", "")
            value = m.get("value")
            delta = m.get("delta")
            help_text = m.get("help")
            color = m.get("color")

            val_str = _fmt(value, suffix=m.get("suffix", ""), prefix=m.get("prefix", ""))
            delta_str = None
            if delta is not None:
                try:
                    d = float(delta)
                    delta_str = f"{d:+.2f}{'%' if m.get('delta_pct') else ''}"
                except Exception:
                    delta_str = str(delta)

            st.metric(
                label=label,
                value=val_str,
                delta=delta_str,
                help=help_text,
                delta_color="normal" if not m.get("inverse_delta") else "inverse",
            )

def render_score_bar(label: str, score: float, max_score: float = 100, color: str = "#31d0aa"):
    pct = min(score / max_score * 100, 100)
    bar_color = "#ef4444" if pct < 30 else "#f59e0b" if pct < 60 else color
    st.markdown(f"""
<div style="margin-bottom:10px">
  <div style="display:flex;justify-content:space-between;margin-bottom:3px">
    <span style="font-size:0.85rem;color:#94a3b8">{label}</span>
    <span style="font-size:0.85rem;font-weight:600;color:{bar_color}">{score:.0f}/100</span>
  </div>
  <div style="background:#1e293b;border-radius:4px;height:8px">
    <div style="background:{bar_color};width:{pct:.0f}%;height:100%;border-radius:4px;transition:width 0.3s"></div>
  </div>
</div>""", unsafe_allow_html=True)

def render_check_cards(checks: list[dict], cols: int = 2):
    """Show pass/fail check cards in a grid."""
    if not checks:
        st.info("No checks available.")
        return
    grid = st.columns(cols)
    for i, c in enumerate(checks):
        with grid[i % cols]:
            passed = c.get("passed", False)
            icon = "✅" if passed else "❌"
            color = "#22c55e" if passed else "#ef4444"
            pts = c.get("points", 0)
            mx  = c.get("max", "—")
            st.markdown(f"""
<div style="background:#1e293b;border-radius:8px;padding:10px 14px;margin-bottom:8px;border-left:3px solid {color}">
  <div style="font-size:0.8rem;font-weight:600;color:{color}">{icon} {c.get('check','')}</div>
  <div style="font-size:0.75rem;color:#94a3b8;margin-top:3px">{c.get('actual','')}</div>
  <div style="font-size:0.7rem;color:#64748b;margin-top:2px">Points: {pts}/{mx}</div>
</div>""", unsafe_allow_html=True)

def render_verdict_banner(score: float, recommendation: str = ""):
    if score >= 75:
        color, bg, label = "#22c55e", "#052e16", "STRONG BUY"
    elif score >= 60:
        color, bg, label = "#86efac", "#14532d", "BUY"
    elif score >= 45:
        color, bg, label = "#fbbf24", "#292524", "NEUTRAL / WATCH"
    elif score >= 30:
        color, bg, label = "#fb923c", "#431407", "CAUTION"
    else:
        color, bg, label = "#ef4444", "#450a0a", "AVOID"
    st.markdown(f"""
<div style="background:{bg};border:1px solid {color};border-radius:10px;padding:18px 24px;text-align:center;margin-bottom:16px">
  <div style="font-size:1.8rem;font-weight:800;color:{color}">{label}</div>
  <div style="font-size:1rem;color:#94a3b8;margin-top:4px">Composite Score: {score}/100</div>
  {f'<div style="font-size:0.85rem;color:#94a3b8;margin-top:6px">{recommendation}</div>' if recommendation else ''}
</div>""", unsafe_allow_html=True)

def render_pattern_badge(pattern_name: str, direction: str, confidence: int):
    color = "#22c55e" if direction == "Bullish" else "#ef4444" if direction == "Bearish" else "#f59e0b"
    st.markdown(f"""
<span style="background:{color}22;border:1px solid {color};color:{color};
  border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:600;margin-right:6px">
  {pattern_name} ({confidence}%)
</span>""", unsafe_allow_html=True)

def render_shareholding_chart(sh_data: dict):
    import plotly.graph_objects as go
    keys = ["promoter", "fii", "dii", "public"]
    labels = ["Promoter", "FII", "DII", "Public"]
    values = [sh_data.get(k) for k in keys]
    valid = [(l, v) for l, v in zip(labels, values) if v is not None]
    if not valid:
        st.info("Shareholding data unavailable.")
        return
    fig = go.Figure(go.Pie(
        labels=[x[0] for x in valid],
        values=[x[1] for x in valid],
        hole=0.45,
        marker_colors=["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6"],
    ))
    fig.update_layout(
        paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
        font=dict(color="#f8fafc"),
        margin=dict(t=20, b=20, l=0, r=0),
        showlegend=True,
        legend=dict(orientation="h", y=-0.1),
        height=280,
    )
    st.plotly_chart(fig, use_container_width=True)

def render_pl_chart(pl_data: dict):
    import plotly.graph_objects as go
    annual = pl_data.get("annual", {})
    if not annual:
        st.info("P&L data unavailable.")
        return
    rev_row  = next((v for k, v in annual.items() if "sales" in k.lower() or "revenue" in k.lower()), {})
    pat_row  = next((v for k, v in annual.items() if "net profit" in k.lower() or "pat" in k.lower() or "profit after" in k.lower()), {})
    if not rev_row:
        st.info("Revenue data not found in P&L.")
        return
    years  = list(rev_row.keys())
    rev    = [rev_row.get(y) for y in years]
    profit = [pat_row.get(y) for y in years] if pat_row else []
    fig = go.Figure()
    fig.add_bar(x=years, y=rev, name="Revenue", marker_color="#3b82f6")
    if profit:
        fig.add_bar(x=years, y=profit, name="Net Profit", marker_color="#22c55e")
    fig.update_layout(
        barmode="group", paper_bgcolor="#0f172a", plot_bgcolor="#111827",
        font=dict(color="#f8fafc"), height=300,
        margin=dict(t=20, b=30, l=40, r=10),
        xaxis=dict(gridcolor="#1e293b"), yaxis=dict(gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)
