"""
PDF report generator.

Produces a comprehensive multi-page PDF report for any stock containing:
  - Cover page with verdict / scores / target / SL
  - Price chart (candlesticks + EMAs + key levels) — rendered with matplotlib
  - Multi-timeframe breakout table
  - Technical indicators dashboard
  - Detected chart patterns
  - AI Chart Analysis (full 14-section narrative)
  - Fundamentals snapshot (P/E, ROE, ROCE, D/E, growth, promoter holding)
  - Quarterly results
  - Pros / Cons / Risk flags
"""
from __future__ import annotations
import io
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Force matplotlib to non-interactive backend (server-side image rendering)
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                 Image, Table, TableStyle, KeepTogether)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ─────────────────────────────────────────────────────────────────────────────
# Chart rendering — matplotlib → PNG bytes
# ─────────────────────────────────────────────────────────────────────────────
def _render_candlestick_png(df, symbol: str, timeframe: str = "Daily",
                             entry: Optional[float] = None,
                             target: Optional[float] = None,
                             stop: Optional[float] = None,
                             pattern_lines: Optional[list] = None) -> bytes:
    """Render an OHLCV candlestick chart with overlays as PNG bytes."""
    if df is None or df.empty:
        return b""

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(11, 6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    fig.patch.set_facecolor("#0f172a")
    for ax in (ax_price, ax_vol):
        ax.set_facecolor("#131722")
        ax.tick_params(colors="#94a3b8", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#1e293b")
        ax.grid(True, color="#1e293b", linewidth=0.4, alpha=0.8)

    # Candlesticks (manual)
    width  = 0.6
    width2 = 0.08
    for i, (idx, row) in enumerate(df.iterrows()):
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        color = "#26a69a" if c >= o else "#ef5350"
        ax_price.add_patch(Rectangle((i - width/2, min(o, c)), width, abs(c - o),
                                       facecolor=color, edgecolor=color))
        ax_price.add_line(plt.Line2D([i, i], [l, h], color=color, linewidth=0.7))

    # EMAs
    closes = df["Close"].astype(float)
    if len(closes) >= 20:
        ema20 = closes.ewm(span=20, adjust=False).mean()
        ax_price.plot(range(len(df)), ema20.values, color="#2962ff", linewidth=0.9, label="EMA20")
    if len(closes) >= 50:
        ema50 = closes.ewm(span=50, adjust=False).mean()
        ax_price.plot(range(len(df)), ema50.values, color="#ff9800", linewidth=0.9, label="EMA50")
    if len(closes) >= 200:
        ema200 = closes.ewm(span=200, adjust=False).mean()
        ax_price.plot(range(len(df)), ema200.values, color="#9c27b0", linewidth=0.9, label="EMA200")

    # Target / Stop / Entry
    n = len(df)
    if entry:
        ax_price.axhline(y=entry, color="#2962ff", linestyle="-", linewidth=1.0, alpha=0.85)
        ax_price.text(n - 1, entry, f" Entry {entry:.2f}", color="#2962ff", fontsize=7, va="center")
    if target:
        ax_price.axhline(y=target, color="#26a69a", linestyle="--", linewidth=1.0, alpha=0.85)
        ax_price.text(n - 1, target, f" Target {target:.2f}", color="#26a69a", fontsize=7, va="center")
    if stop:
        ax_price.axhline(y=stop, color="#ef5350", linestyle="--", linewidth=1.0, alpha=0.85)
        ax_price.text(n - 1, stop, f" Stop {stop:.2f}", color="#ef5350", fontsize=7, va="center")

    # Pattern trendlines (best-effort — convert dates to bar positions)
    if pattern_lines:
        idx_to_pos = {str(d.date() if hasattr(d, "date") else d)[:10]: i for i, d in enumerate(df.index)}
        for ln in pattern_lines:
            try:
                x0 = idx_to_pos.get(str(ln["x0"])[:10])
                x1 = idx_to_pos.get(str(ln["x1"])[:10])
                if x0 is None or x1 is None:
                    continue
                ax_price.plot([x0, x1], [float(ln["y0"]), float(ln["y1"])],
                              color=ln.get("color", "#f5c542"), linewidth=1.1,
                              linestyle=":" if ln.get("dash") == "dot" else "-",
                              alpha=0.8)
            except Exception:
                continue

    ax_price.set_title(f"{symbol} — {timeframe}",
                       color="#e2e8f0", fontsize=10, pad=8)
    ax_price.legend(loc="upper left", fontsize=7,
                    facecolor="#131722", edgecolor="#1e293b", labelcolor="#94a3b8")
    ax_price.set_ylabel("Price (Rs)", color="#94a3b8", fontsize=8)

    # Volume
    if "Volume" in df.columns:
        vols = df["Volume"].astype(float).values
        vcols = ["#26a69a" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#ef5350"
                 for i in range(len(df))]
        ax_vol.bar(range(len(df)), vols, color=vcols, width=0.6, alpha=0.7)
        ax_vol.set_ylabel("Volume", color="#94a3b8", fontsize=8)

    # X-tick labels (sparse)
    if n > 0:
        step = max(1, n // 10)
        ticks = list(range(0, n, step))
        ax_vol.set_xticks(ticks)
        labels = [str(df.index[i].date() if hasattr(df.index[i], "date") else df.index[i])[:10]
                  for i in ticks]
        ax_vol.set_xticklabels(labels, rotation=30, ha="right", fontsize=6)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, facecolor="#0f172a", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_score_bar_png(scores: dict) -> bytes:
    """Horizontal bar chart of AI scores."""
    fig, ax = plt.subplots(figsize=(8, 2.2))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#131722")
    labels = list(scores.keys())
    values = [float(v) if v is not None else 0 for v in scores.values()]
    bar_colors = ["#26a69a" if v >= 60 else "#ef5350" if v < 40 else "#f5c542" for v in values]
    ax.barh(labels, values, color=bar_colors)
    ax.set_xlim(0, 100)
    ax.axvline(x=50, color="#1e293b", linestyle="--", linewidth=0.7)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    for i, v in enumerate(values):
        ax.text(v + 1, i, f"{v:.0f}", color="#e2e8f0", fontsize=8, va="center")
    ax.set_xlabel("Score (0-100)", color="#94a3b8", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, facecolor="#0f172a", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────
_BG = colors.HexColor("#0f172a")
_CARD = colors.HexColor("#131722")
_TEXT = colors.HexColor("#e2e8f0")
_DIM = colors.HexColor("#94a3b8")
_GREEN = colors.HexColor("#26a69a")
_RED = colors.HexColor("#ef5350")
_BLUE = colors.HexColor("#2962ff")
_YELLOW = colors.HexColor("#f5c542")

_styles = getSampleStyleSheet()


def _para(text: str, size=10, color=_TEXT, bold=False, align=TA_LEFT) -> Paragraph:
    style = ParagraphStyle(
        "x", parent=_styles["BodyText"],
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, textColor=color, leading=size * 1.3, alignment=align,
    )
    return Paragraph(text, style)


def _section_header(title: str) -> Paragraph:
    style = ParagraphStyle(
        "h", parent=_styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=13, textColor=_BLUE,
        spaceBefore=12, spaceAfter=6, leading=16,
    )
    return Paragraph(title, style)


# ─────────────────────────────────────────────────────────────────────────────
# Builder helpers
# ─────────────────────────────────────────────────────────────────────────────
def _stat_table(rows: list, col_widths=None) -> Table:
    t = Table(rows, colWidths=col_widths or [4.5 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _CARD),
        ("TEXTCOLOR",  (0, 0), (0, -1), _DIM),
        ("TEXTCOLOR",  (1, 0), (-1, -1), _TEXT),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ALIGN",      (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#1e293b")),
    ]))
    return t


def _verdict_box(verdict: str, score: float, target: Optional[float],
                  stop: Optional[float], confidence: str) -> Table:
    color = _GREEN if "BUY" in verdict else _RED if "SELL" in verdict else _YELLOW
    rows = [
        [_para("VERDICT", 7, _DIM, bold=True),  _para(verdict, 14, color, bold=True)],
        [_para("SCORE", 7, _DIM, bold=True),    _para(f"{score:.0f}/100", 14, color, bold=True)],
        [_para("TARGET", 7, _DIM, bold=True),   _para(f"Rs {target:,.2f}" if target else "-", 11, _GREEN)],
        [_para("STOP",   7, _DIM, bold=True),   _para(f"Rs {stop:,.2f}"   if stop   else "-", 11, _RED)],
        [_para("CONFIDENCE", 7, _DIM, bold=True), _para(confidence, 11, _TEXT)],
    ]
    t = Table(rows, colWidths=[3.5 * cm, 7 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _CARD),
        ("BOX",        (0, 0), (-1, -1), 1.0, color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#1e293b")),
    ]))
    return t


def _multi_tf_table(mtf: dict) -> Table:
    rows = [["Timeframe", "Breakout state", "Level", "Distance %", "Volume confirmed"]]
    for tf in ["1d", "1w", "1mo"]:
        d = mtf.get(tf, {}) or {}
        rows.append([
            tf,
            d.get("label", "-"),
            f"Rs {d['level']:,.2f}" if d.get("level") else "-",
            f"{d.get('distance_pct', 0):+.2f}%" if d.get("distance_pct") is not None else "-",
            "Yes" if d.get("volume_confirmed") else "No",
        ])
    t = Table(rows, colWidths=[2 * cm, 5 * cm, 3 * cm, 2.5 * cm, 3 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), _CARD),
        ("TEXTCOLOR",  (0, 1), (-1, -1), _TEXT),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ALIGN",      (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#1e293b")),
    ]))
    return t


def _patterns_table(patterns: list) -> Optional[Table]:
    if not patterns:
        return None
    rows = [["Pattern", "Direction", "Confidence", "Status", "Target", "Stop"]]
    for p in patterns[:12]:
        kl = p.get("key_levels") or {}
        rows.append([
            p.get("name", "-"),
            p.get("direction", "-"),
            f"{p.get('confidence', 0)}%",
            p.get("status", "-"),
            f"Rs {kl['target']:,.0f}" if kl.get("target") else "-",
            f"Rs {kl['stop']:,.0f}"   if kl.get("stop")   else "-",
        ])
    t = Table(rows, colWidths=[5 * cm, 2.2 * cm, 2.2 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), _CARD),
        ("TEXTCOLOR",  (0, 1), (-1, -1), _TEXT),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ALIGN",      (1, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#1e293b")),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────
def build_pdf_report(
    symbol: str,
    df_daily,
    indicators: dict,
    patterns: list,
    fundamentals: dict,
    ai_verdict,                 # AIVerdict dataclass
    chart_analysis: str = "",
    multi_tf_breakout: Optional[dict] = None,
    quarterly: Optional[dict] = None,
    pros: Optional[list] = None,
    cons: Optional[list] = None,
    company_name: str = "",
    sector: str = "",
) -> bytes:
    """Build a complete PDF report and return its bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"{symbol} — Stock Intelligence Report",
        author="Stock Intelligence Platform",
    )

    story = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(_para(f"{symbol}", 28, _BLUE, bold=True, align=TA_CENTER))
    if company_name:
        story.append(_para(company_name, 13, _TEXT, align=TA_CENTER))
    if sector:
        story.append(_para(sector, 9, _DIM, align=TA_CENTER))
    story.append(Spacer(1, 6 * mm))
    story.append(_para(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"Stock Intelligence Platform",
        8, _DIM, align=TA_CENTER,
    ))
    story.append(Spacer(1, 6 * mm))

    # ── Verdict ───────────────────────────────────────────────────────────────
    if ai_verdict:
        story.append(_verdict_box(
            ai_verdict.verdict, ai_verdict.score,
            ai_verdict.price_target, ai_verdict.stop_loss,
            ai_verdict.confidence,
        ))
        story.append(Spacer(1, 4 * mm))
        # Score breakdown chart
        scores_dict = {
            "Technical":   ai_verdict.tech_score,
            "Fundamental": ai_verdict.fund_score,
            "Pattern":     ai_verdict.pattern_score,
            "Momentum":    ai_verdict.momentum_score,
        }
        try:
            png = _render_score_bar_png(scores_dict)
            if png:
                story.append(Image(io.BytesIO(png), width=16 * cm, height=4 * cm))
        except Exception as e:
            logger.debug(f"score bar failed: {e}")

    # ── Price chart ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_header("📈 Price Chart (Daily)"))
    try:
        # Pull pattern lines from the strongest pattern
        pat_lines = []
        if patterns:
            best = max(patterns, key=lambda p: p.get("confidence", 0))
            pat_lines = best.get("lines", [])
        png = _render_candlestick_png(
            df_daily, symbol, "Daily",
            entry=indicators.get("close"),
            target=ai_verdict.price_target if ai_verdict else None,
            stop=ai_verdict.stop_loss   if ai_verdict else None,
            pattern_lines=pat_lines,
        )
        if png:
            story.append(Image(io.BytesIO(png), width=18 * cm, height=10 * cm))
    except Exception as e:
        logger.warning(f"Chart render failed: {e}")
        story.append(_para(f"(Chart render failed: {e})", 9, _RED))

    # ── Multi-timeframe breakout ──────────────────────────────────────────────
    if multi_tf_breakout:
        story.append(Spacer(1, 4 * mm))
        story.append(_section_header("📐 Multi-Timeframe Breakout State"))
        story.append(_multi_tf_table(multi_tf_breakout))
        if multi_tf_breakout.get("_overall"):
            story.append(Spacer(1, 2 * mm))
            story.append(_para(f"<b>Overall:</b> {multi_tf_breakout['_overall']}",
                                10, _TEXT))

    # ── Indicators ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5 * mm))
    story.append(_section_header("📊 Technical Indicators (latest)"))
    ind_pairs = [
        ("Close", f"Rs {indicators.get('close', 0):,.2f}" if indicators.get('close') else "-"),
        ("Day change %", f"{indicators.get('change', 0):+.2f}%" if indicators.get('change') is not None else "-"),
        ("RSI (14)", f"{indicators.get('rsi'):.1f}" if indicators.get('rsi') is not None else "-"),
        ("MACD", f"{indicators.get('macd'):.2f}" if indicators.get('macd') is not None else "-"),
        ("MACD Signal", f"{indicators.get('macd_signal'):.2f}" if indicators.get('macd_signal') is not None else "-"),
        ("ADX", f"{indicators.get('adx'):.1f}" if indicators.get('adx') is not None else "-"),
        ("EMA 20", f"Rs {indicators.get('ema20'):,.2f}" if indicators.get('ema20') else "-"),
        ("EMA 50", f"Rs {indicators.get('ema50'):,.2f}" if indicators.get('ema50') else "-"),
        ("SMA 200", f"Rs {indicators.get('sma200'):,.2f}" if indicators.get('sma200') else "-"),
        ("Bollinger upper", f"Rs {indicators.get('bb_upper'):,.2f}" if indicators.get('bb_upper') else "-"),
        ("Bollinger lower", f"Rs {indicators.get('bb_lower'):,.2f}" if indicators.get('bb_lower') else "-"),
        ("Stochastic %K", f"{indicators.get('stoch_k'):.1f}" if indicators.get('stoch_k') is not None else "-"),
    ]
    # Two-column layout
    half = (len(ind_pairs) + 1) // 2
    left  = [[_para(k, 9, _DIM), _para(v, 9, _TEXT, bold=True)] for k, v in ind_pairs[:half]]
    right = [[_para(k, 9, _DIM), _para(v, 9, _TEXT, bold=True)] for k, v in ind_pairs[half:]]
    while len(right) < len(left):
        right.append(["", ""])
    combined = [[*l, *r] for l, r in zip(left, right)]
    t = Table(combined, colWidths=[3.8 * cm, 3.2 * cm, 3.8 * cm, 3.2 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _CARD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#1e293b")),
    ]))
    story.append(t)

    # ── Detected patterns ─────────────────────────────────────────────────────
    if patterns:
        story.append(Spacer(1, 5 * mm))
        story.append(_section_header(f"🧬 Detected Chart Patterns ({len(patterns)})"))
        ptbl = _patterns_table(patterns)
        if ptbl:
            story.append(ptbl)

    # ── AI Chart Analysis (full narrative) ────────────────────────────────────
    if chart_analysis:
        story.append(PageBreak())
        story.append(_section_header("🎯 AI Chart Analysis"))
        # Render markdown as wrapped paragraphs (basic rendering)
        for line in chart_analysis.split("\n"):
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 2 * mm))
                continue
            if stripped.startswith("**") and stripped.endswith("**"):
                story.append(_para(stripped.strip("*"), 10, _BLUE, bold=True))
            elif stripped.startswith("# ") or stripped.startswith("## "):
                story.append(_para(stripped.lstrip("# "), 12, _BLUE, bold=True))
            elif stripped.startswith("- "):
                story.append(_para("• " + stripped[2:].replace("**", ""), 9, _TEXT))
            else:
                story.append(_para(stripped.replace("**", ""), 9, _TEXT))

    # ── Fundamentals ──────────────────────────────────────────────────────────
    if fundamentals:
        story.append(PageBreak())
        story.append(_section_header("💰 Fundamentals Snapshot"))
        fund_pairs = [
            ("Market Cap (Cr)", fundamentals.get("market_cap")),
            ("P/E", fundamentals.get("pe")),
            ("P/B", fundamentals.get("pb")),
            ("ROE %", fundamentals.get("roe")),
            ("ROCE %", fundamentals.get("roce")),
            ("OPM %", fundamentals.get("opm")),
            ("NPM %", fundamentals.get("npm")),
            ("Debt / Equity", fundamentals.get("debt_equity")),
            ("Promoter Holding %", fundamentals.get("promoter_holding")),
            ("Sales Growth %", fundamentals.get("sales_growth")),
            ("Profit Growth %", fundamentals.get("profit_growth")),
            ("Dividend Yield %", fundamentals.get("dividend_yield")),
        ]
        rows = []
        for k, v in fund_pairs:
            if v is None: continue
            try:
                rows.append([_para(k, 9, _DIM), _para(f"{float(v):,.2f}", 9, _TEXT, bold=True)])
            except Exception:
                rows.append([_para(k, 9, _DIM), _para(str(v), 9, _TEXT, bold=True)])
        if rows:
            story.append(_stat_table(rows))

    # ── Quarterly results ─────────────────────────────────────────────────────
    if quarterly:
        story.append(Spacer(1, 5 * mm))
        story.append(_section_header("📋 Recent Quarterly Results"))
        # Build a small table from quarterly P&L
        q_rows = quarterly.get("annual") or quarterly.get("quarterly") or {}
        if q_rows:
            sales = q_rows.get("Sales +") or q_rows.get("Sales") or {}
            np_   = q_rows.get("Net Profit +") or q_rows.get("Net Profit") or {}
            opm_  = q_rows.get("OPM %") or {}
            periods = list(sales.keys())[-6:]
            if periods:
                trows = [["Period"] + periods]
                trows.append(["Sales (Cr)"] + [f"{sales.get(p, 0):,.0f}" if sales.get(p) is not None else "-"
                                                  for p in periods])
                trows.append(["Net Profit (Cr)"] + [f"{np_.get(p, 0):,.0f}" if np_.get(p) is not None else "-"
                                                       for p in periods])
                trows.append(["OPM %"] + [f"{opm_.get(p, 0):.1f}" if opm_.get(p) is not None else "-"
                                              for p in periods])
                cw = [3 * cm] + [(15 / len(periods)) * cm] * len(periods)
                qt = Table(trows, colWidths=cw)
                qt.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), _CARD),
                    ("TEXTCOLOR",  (0, 1), (-1, -1), _TEXT),
                    ("FONTSIZE",   (0, 0), (-1, -1), 8),
                    ("ALIGN",      (1, 0), (-1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#1e293b")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(qt)

    # ── Pros / Cons / Risk flags ──────────────────────────────────────────────
    if pros or cons or (ai_verdict and ai_verdict.risk_flags):
        story.append(Spacer(1, 5 * mm))
        story.append(_section_header("✅ Strengths / ⚠ Risks"))
        if pros:
            story.append(_para("Strengths:", 10, _GREEN, bold=True))
            for p in pros[:8]:
                story.append(_para(f"✓  {p}", 9, _TEXT))
        if cons:
            story.append(Spacer(1, 2 * mm))
            story.append(_para("Weaknesses:", 10, _RED, bold=True))
            for c in cons[:8]:
                story.append(_para(f"✗  {c}", 9, _TEXT))
        if ai_verdict and ai_verdict.risk_flags:
            story.append(Spacer(1, 2 * mm))
            story.append(_para("AI-detected risk flags:", 10, _YELLOW, bold=True))
            for r in ai_verdict.risk_flags[:8]:
                story.append(_para(f"⚠  {r}", 9, _TEXT))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(_para(
        "Disclaimer: This report is generated automatically from public market "
        "data sources (Yahoo Finance, NSE India, Screener.in). It is for "
        "informational purposes only and does not constitute investment advice. "
        "Verify all data independently before making any trading decision.",
        7, _DIM, align=TA_CENTER,
    ))

    # ── Build PDF (with dark page background) ────────────────────────────────
    def _bg(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(_BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_bg, onLaterPages=_bg)
    buf.seek(0)
    return buf.read()
