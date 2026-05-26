"""Zerodha-inspired dark theme CSS and helper renderers for Streamlit."""
from __future__ import annotations

# ── Color Palette ──────────────────────────────────────────────────────────────
BG = "#131722"
CARD = "#1e222d"
BORDER = "#2a2e39"
TEXT = "#d1d4dc"
TEXT_DIM = "#787b86"
GREEN = "#26a69a"
RED = "#ef5350"
BLUE = "#2962ff"
ORANGE = "#ff9800"
YELLOW = "#f59e0b"
PURPLE = "#9c27b0"
TEAL = "#00bcd4"

# ── Global CSS ─────────────────────────────────────────────────────────────────
ZERODHA_CSS = f"""
<style>
/* Root background */
.stApp, .main, [data-testid="stAppViewContainer"],
[data-testid="stMain"], section.main {{
    background-color: {BG} !important;
    color: {TEXT} !important;
    font-family: 'Inter', 'Segoe UI', sans-serif;
}}

/* Sidebar */
[data-testid="stSidebar"], section[data-testid="stSidebar"] {{
    background-color: #0d1117 !important;
    border-right: 1px solid {BORDER} !important;
}}
[data-testid="stSidebar"] * {{ color: {TEXT} !important; }}

/* Headers */
h1, h2, h3, h4, h5, h6 {{ color: {TEXT} !important; font-weight: 600; }}
h1 {{ font-size: 1.6rem; border-bottom: 2px solid {BLUE}; padding-bottom: 6px; }}
h2 {{ font-size: 1.3rem; }}
h3 {{ font-size: 1.1rem; color: #c8cbd4 !important; }}

/* Metric cards */
[data-testid="stMetricValue"] {{ font-size: 1.4rem; font-weight: 700; color: {TEXT} !important; }}
[data-testid="stMetricLabel"] {{ font-size: 0.75rem; color: {TEXT_DIM} !important; text-transform: uppercase; letter-spacing: 0.04em; }}
[data-testid="stMetricDelta"] {{ font-size: 0.85rem; font-weight: 600; }}
[data-testid="metric-container"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
    padding: 12px 16px !important;
}}

/* Buttons */
.stButton > button {{
    background: {BLUE} !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 20px !important;
    transition: opacity 0.15s ease;
}}
.stButton > button:hover {{ opacity: 0.88 !important; }}
.stButton > button[kind="secondary"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
}}

/* Select boxes & dropdowns */
[data-testid="stSelectbox"] > div > div,
.stSelectbox > div > div {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 6px !important;
    color: {TEXT} !important;
}}
[data-testid="stSelectbox"] label, .stSelectbox label {{ color: {TEXT_DIM} !important; font-size: 0.8rem; text-transform: uppercase; }}

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {{
    background: {CARD} !important;
    border-bottom: 1px solid {BORDER} !important;
    gap: 0 !important;
}}
[data-testid="stTabs"] [role="tab"] {{
    background: transparent !important;
    color: {TEXT_DIM} !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 8px 16px !important;
    border-radius: 0 !important;
    border: none !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: {BLUE} !important;
    border-bottom: 2px solid {BLUE} !important;
    font-weight: 700 !important;
}}
[data-testid="stTabs"] [role="tab"]:hover {{ color: {TEXT} !important; }}

/* DataFrames / Tables */
[data-testid="stDataFrame"], .stDataFrame {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
}}

/* Expander */
[data-testid="stExpander"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
}}
[data-testid="stExpander"] summary {{ color: {TEXT} !important; }}

/* Input fields */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 6px !important;
    color: {TEXT} !important;
}}

/* Divider */
hr {{ border-color: {BORDER} !important; margin: 12px 0 !important; }}

/* Info/Success/Warning/Error boxes */
[data-testid="stInfo"] {{ background: rgba(41,98,255,0.12) !important; border-left: 3px solid {BLUE} !important; color: {TEXT} !important; border-radius: 6px; }}
[data-testid="stSuccess"] {{ background: rgba(38,166,154,0.12) !important; border-left: 3px solid {GREEN} !important; color: {TEXT} !important; border-radius: 6px; }}
[data-testid="stWarning"] {{ background: rgba(245,158,11,0.12) !important; border-left: 3px solid {YELLOW} !important; color: {TEXT} !important; border-radius: 6px; }}
[data-testid="stError"] {{ background: rgba(239,83,80,0.12) !important; border-left: 3px solid {RED} !important; color: {TEXT} !important; border-radius: 6px; }}

/* Progress bar */
.stProgress > div > div > div {{ background: {BLUE} !important; }}

/* Scrollbar */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {BG}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: #3d4455; }}

/* Card component class */
.z-card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
}}
.z-card-title {{
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {TEXT_DIM};
    margin-bottom: 6px;
}}
.z-val {{ font-size: 1.5rem; font-weight: 700; color: {TEXT}; }}
.z-pos {{ color: {GREEN} !important; }}
.z-neg {{ color: {RED} !important; }}
.z-neu {{ color: {TEXT_DIM} !important; }}
.z-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}}
.z-badge-buy {{ background: rgba(38,166,154,0.18); color: {GREEN}; border: 1px solid {GREEN}; }}
.z-badge-sell {{ background: rgba(239,83,80,0.18); color: {RED}; border: 1px solid {RED}; }}
.z-badge-hold {{ background: rgba(120,123,134,0.18); color: {TEXT_DIM}; border: 1px solid {BORDER}; }}
.z-badge-strong-buy {{ background: rgba(38,166,154,0.28); color: #00e5d0; border: 1px solid #00e5d0; }}
.z-badge-strong-sell {{ background: rgba(239,83,80,0.28); color: #ff6060; border: 1px solid #ff6060; }}

/* Section header */
.z-section {{
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {TEXT_DIM};
    padding: 6px 0;
    border-bottom: 1px solid {BORDER};
    margin: 16px 0 10px 0;
}}
/* Stock row */
.z-stock-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid {BORDER};
    background: {CARD};
    margin-bottom: 4px;
    transition: border-color 0.15s;
}}
.z-stock-row:hover {{ border-color: {BLUE}; }}
</style>
"""


def apply_theme() -> None:
    """Inject Zerodha CSS into the current Streamlit page."""
    import streamlit as st
    st.markdown(ZERODHA_CSS, unsafe_allow_html=True)


def hex_to_rgba(hex_color: str, alpha: float = 0.2) -> str:
    """Convert '#rrggbb' to 'rgba(r,g,b,alpha)' — Plotly doesn't support 8-digit hex."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# Pre-built rgba versions of palette colors (alpha=0.2)
GREEN_A  = hex_to_rgba(GREEN, 0.2)
RED_A    = hex_to_rgba(RED, 0.2)
BLUE_A   = hex_to_rgba(BLUE, 0.2)
YELLOW_A = hex_to_rgba(YELLOW, 0.2)

SYM_COLORS  = [BLUE, GREEN, YELLOW, RED, "#a855f7", "#06b6d4"]
SYM_COLORS_A = [hex_to_rgba(c, 0.2) for c in SYM_COLORS]


def color_val(v, pos_green: bool = True) -> str:
    """Return HTML-colored span for a value (green=positive, red=negative)."""
    if v is None:
        return f'<span style="color:{TEXT_DIM}">—</span>'
    try:
        f = float(v)
        c = GREEN if (f >= 0 if pos_green else f <= 0) else RED
        return f'<span style="color:{c}">{v}</span>'
    except Exception:
        return f'<span style="color:{TEXT}">{v}</span>'


def pct_color(v) -> str:
    if v is None:
        return f'<span style="color:{TEXT_DIM}">—</span>'
    try:
        f = float(v)
        c = GREEN if f >= 0 else RED
        sign = "+" if f > 0 else ""
        return f'<span style="color:{c};font-weight:600">{sign}{f:.2f}%</span>'
    except Exception:
        return f'<span style="color:{TEXT}">—</span>'


def signal_badge(signal: str) -> str:
    lbl = str(signal).upper().replace("_", " ")
    if "STRONG BUY" in lbl or "STRONG_BUY" in lbl:
        cls = "z-badge z-badge-strong-buy"
    elif "BUY" in lbl:
        cls = "z-badge z-badge-buy"
    elif "STRONG SELL" in lbl or "STRONG_SELL" in lbl:
        cls = "z-badge z-badge-strong-sell"
    elif "SELL" in lbl:
        cls = "z-badge z-badge-sell"
    else:
        cls = "z-badge z-badge-hold"
    return f'<span class="{cls}">{lbl}</span>'


def fmt_num(v, decimals: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if abs(f) >= 1e7:
            return f"₹{f/1e7:.2f}Cr"
        if abs(f) >= 1e5:
            return f"₹{f/1e5:.2f}L"
        return f"{f:.{decimals}f}{suffix}"
    except Exception:
        return str(v)


def fmt_cr(v) -> str:
    if v is None:
        return "—"
    try:
        return f"₹{float(v):,.0f} Cr"
    except Exception:
        return str(v)


def metric_card(label: str, value: str, delta: str = "", color: str = TEXT) -> str:
    delta_html = f'<div style="font-size:0.8rem;color:{color};margin-top:2px">{delta}</div>' if delta else ""
    return f"""
<div class="z-card" style="min-width:120px">
  <div class="z-card-title">{label}</div>
  <div class="z-val" style="color:{color}">{value}</div>
  {delta_html}
</div>"""


def verdict_card(verdict: str, score: float, confidence: str = "") -> str:
    if "STRONG BUY" in verdict:
        bg, fg = "rgba(38,166,154,0.15)", GREEN
    elif "BUY" in verdict:
        bg, fg = "rgba(38,166,154,0.08)", GREEN
    elif "STRONG SELL" in verdict:
        bg, fg = "rgba(239,83,80,0.20)", RED
    elif "SELL" in verdict:
        bg, fg = "rgba(239,83,80,0.10)", RED
    else:
        bg, fg = "rgba(120,123,134,0.10)", TEXT_DIM
    conf_html = f'<div style="font-size:0.8rem;color:{TEXT_DIM};margin-top:4px">{confidence}</div>' if confidence else ""
    return f"""
<div style="background:{bg};border:2px solid {fg};border-radius:10px;padding:16px 20px;text-align:center">
  <div style="font-size:0.75rem;text-transform:uppercase;color:{TEXT_DIM};letter-spacing:0.05em">AI Verdict</div>
  <div style="font-size:1.8rem;font-weight:800;color:{fg};margin:4px 0">{verdict}</div>
  <div style="font-size:1rem;color:{TEXT_DIM}">Score: <span style="color:{fg};font-weight:700">{score:.0f}/100</span></div>
  {conf_html}
</div>"""
