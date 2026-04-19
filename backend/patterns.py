from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ChartPattern:
    name: str
    direction: str
    confidence: int
    status: str
    description: str
    points: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "Pattern": self.name,
            "Direction": self.direction,
            "Confidence": self.confidence,
            "Status": self.status,
            "Description": self.description,
            "Points": self.points,
        }


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _point(index_value, price: float) -> dict[str, Any]:
    return {"date": pd.to_datetime(index_value), "price": float(price)}


def _swing_points(df: pd.DataFrame, column: str, mode: str, window: int = 3) -> list[tuple[Any, float]]:
    values = df[column].to_numpy(dtype=float)
    points: list[tuple[Any, float]] = []
    for idx in range(window, len(df) - window):
        slice_values = values[idx - window : idx + window + 1]
        value = values[idx]
        if mode == "high" and value == np.nanmax(slice_values):
            points.append((df.index[idx], value))
        if mode == "low" and value == np.nanmin(slice_values):
            points.append((df.index[idx], value))
    return points


def detect_chart_patterns(history: pd.DataFrame) -> list[dict[str, Any]]:
    df = history.dropna(subset=["Open", "High", "Low", "Close"]).tail(180).copy()
    if len(df) < 60:
        return []

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float) if "Volume" in df else pd.Series(0, index=df.index)
    latest_close = float(close.iloc[-1])
    avg_volume = float(volume.tail(20).mean()) if volume.tail(20).mean() else 0
    latest_volume = float(volume.iloc[-1]) if len(volume) else 0

    patterns: list[ChartPattern] = []
    recent_60 = df.tail(60)
    prior_high = float(recent_60["High"].iloc[:-1].max())
    prior_low = float(recent_60["Low"].iloc[:-1].min())
    resistance_idx = recent_60["High"].iloc[:-1].idxmax()
    support_idx = recent_60["Low"].iloc[:-1].idxmin()

    if latest_close > prior_high:
        volume_bonus = 15 if avg_volume and latest_volume > avg_volume * 1.25 else 0
        breakout_pct = ((latest_close - prior_high) / prior_high) * 100
        patterns.append(
            ChartPattern(
                name="Breakout Above Resistance",
                direction="Bullish",
                confidence=min(95, int(70 + volume_bonus + min(10, breakout_pct * 2))),
                status="Confirmed",
                description=f"Close broke above the recent resistance near {prior_high:.2f}.",
                points=[_point(resistance_idx, prior_high), _point(df.index[-1], latest_close)],
            )
        )
    elif abs(latest_close - prior_high) / prior_high <= 0.025:
        patterns.append(
            ChartPattern(
                name="Resistance Breakout Watch",
                direction="Bullish",
                confidence=62,
                status="Forming",
                description=f"Price is within 2.5% of resistance near {prior_high:.2f}.",
                points=[_point(resistance_idx, prior_high), _point(df.index[-1], latest_close)],
            )
        )

    swing_highs = _swing_points(df, "High", "high")[-6:]
    swing_lows = _swing_points(df, "Low", "low")[-6:]

    if len(swing_highs) >= 3 and len(swing_lows) >= 3:
        high_prices = np.array([item[1] for item in swing_highs[-4:]])
        low_prices = np.array([item[1] for item in swing_lows[-4:]])
        high_range_pct = (high_prices.max() - high_prices.min()) / max(high_prices.mean(), 1)
        low_slope = np.polyfit(np.arange(len(low_prices)), low_prices, 1)[0]
        high_slope = np.polyfit(np.arange(len(high_prices)), high_prices, 1)[0]

        if high_range_pct < 0.04 and low_slope > 0:
            patterns.append(
                ChartPattern(
                    name="Ascending Triangle",
                    direction="Bullish",
                    confidence=76 if latest_close > high_prices.mean() * 0.98 else 66,
                    status="Breakout" if latest_close > high_prices.max() else "Forming",
                    description="Resistance is mostly flat while swing lows are rising.",
                    points=[_point(swing_lows[-3][0], swing_lows[-3][1]), _point(swing_lows[-1][0], swing_lows[-1][1]), _point(swing_highs[-3][0], swing_highs[-3][1]), _point(swing_highs[-1][0], swing_highs[-1][1])],
                )
            )

        if abs(high_slope) > 0 and high_slope < 0 and low_slope > 0:
            patterns.append(
                ChartPattern(
                    name="Symmetrical Triangle",
                    direction="Neutral",
                    confidence=64,
                    status="Forming",
                    description="Swing highs are falling and swing lows are rising, showing compression.",
                    points=[_point(swing_highs[-3][0], swing_highs[-3][1]), _point(swing_highs[-1][0], swing_highs[-1][1]), _point(swing_lows[-3][0], swing_lows[-3][1]), _point(swing_lows[-1][0], swing_lows[-1][1])],
                )
            )

        if len(swing_lows) >= 2:
            low_a, low_b = swing_lows[-2], swing_lows[-1]
            if abs(low_a[1] - low_b[1]) / max((low_a[1] + low_b[1]) / 2, 1) < 0.035 and latest_close > close.tail(30).mean():
                patterns.append(
                    ChartPattern(
                        name="Double Bottom",
                        direction="Bullish",
                        confidence=70,
                        status="Forming",
                        description="Two recent swing lows formed near the same price zone.",
                        points=[_point(low_a[0], low_a[1]), _point(low_b[0], low_b[1])],
                    )
                )

        if len(swing_highs) >= 2:
            high_a, high_b = swing_highs[-2], swing_highs[-1]
            if abs(high_a[1] - high_b[1]) / max((high_a[1] + high_b[1]) / 2, 1) < 0.035 and latest_close < close.tail(30).mean():
                patterns.append(
                    ChartPattern(
                        name="Double Top",
                        direction="Bearish",
                        confidence=68,
                        status="Forming",
                        description="Two recent swing highs formed near the same price zone.",
                        points=[_point(high_a[0], high_a[1]), _point(high_b[0], high_b[1])],
                    )
                )

    if latest_close < prior_low:
        patterns.append(
            ChartPattern(
                name="Breakdown Below Support",
                direction="Bearish",
                confidence=74,
                status="Confirmed",
                description=f"Close broke below recent support near {prior_low:.2f}.",
                points=[_point(support_idx, prior_low), _point(df.index[-1], latest_close)],
            )
        )

    return sorted([pattern.as_dict() for pattern in patterns], key=lambda item: item["Confidence"], reverse=True)
