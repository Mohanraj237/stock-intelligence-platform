from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _pattern_color(direction: str) -> str:
    if direction == "Bullish":
        return "#31d0aa"
    if direction == "Bearish":
        return "#f87171"
    return "#f5c542"


def candlestick_chart(df, title: str, patterns: list[dict] | None = None):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.72, 0.28],
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
        ),
        row=1,
        col=1,
    )
    if "DMA_50" in df:
        fig.add_trace(go.Scatter(x=df.index, y=df["DMA_50"], name="50 DMA", line=dict(color="#f5c542", width=1.5)), row=1, col=1)
    if "DMA_200" in df:
        fig.add_trace(go.Scatter(x=df.index, y=df["DMA_200"], name="200 DMA", line=dict(color="#31d0aa", width=1.5)), row=1, col=1)
    for pattern in patterns or []:
        points = pattern.get("Points") or []
        color = _pattern_color(pattern.get("Direction", ""))
        if len(points) == 1:
            point = points[0]
            fig.add_trace(
                go.Scatter(
                    x=[pd.to_datetime(point["date"])],
                    y=[point["price"]],
                    mode="markers+text",
                    marker=dict(color=color, size=10),
                    text=[pattern.get("Pattern", "")],
                    textposition="top center",
                    name=pattern.get("Pattern", "Pattern"),
                ),
                row=1,
                col=1,
            )
        if len(points) >= 2:
            for idx in range(0, len(points) - 1, 2):
                first = points[idx]
                second = points[idx + 1]
                fig.add_trace(
                    go.Scatter(
                        x=[pd.to_datetime(first["date"]), pd.to_datetime(second["date"])],
                        y=[first["price"], second["price"]],
                        mode="lines+markers",
                        line=dict(color=color, width=2, dash="dash"),
                        marker=dict(color=color, size=6),
                        name=pattern.get("Pattern", "Pattern"),
                    ),
                    row=1,
                    col=1,
                )
            label_point = points[-1]
            fig.add_annotation(
                x=pd.to_datetime(label_point["date"]),
                y=label_point["price"],
                text=f"{pattern.get('Pattern')} ({pattern.get('Confidence')}%)",
                showarrow=True,
                arrowcolor=color,
                font=dict(color=color),
                bgcolor="#111827",
                bordercolor=color,
                row=1,
                col=1,
            )
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color="#5b6cff"), row=2, col=1)
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=680,
        paper_bgcolor="#0f172a",
        plot_bgcolor="#111827",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=70, b=20),
    )
    return fig
