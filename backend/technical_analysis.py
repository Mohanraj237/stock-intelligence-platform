from __future__ import annotations

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volatility import BollingerBands


def add_indicators(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    close = df["Close"].astype(float)
    df["RSI_14"] = RSIIndicator(close=close, window=14).rsi()
    macd = MACD(close=close)
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["EMA_20"] = EMAIndicator(close=close, window=20).ema_indicator()
    df["DMA_50"] = SMAIndicator(close=close, window=50).sma_indicator()
    df["DMA_200"] = SMAIndicator(close=close, window=200).sma_indicator()
    bands = BollingerBands(close=close, window=20, window_dev=2)
    df["BB_HIGH"] = bands.bollinger_hband()
    df["BB_LOW"] = bands.bollinger_lband()
    df["BB_MID"] = bands.bollinger_mavg()
    df["AVG_VOLUME_20"] = df["Volume"].rolling(20).mean()
    return df


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> tuple[float | None, float | None]:
    recent = df.tail(lookback)
    if recent.empty:
        return None, None
    support = float(recent["Low"].quantile(0.15))
    resistance = float(recent["High"].quantile(0.85))
    return support, resistance


def trend_direction(row: pd.Series) -> str:
    close = row.get("Close")
    dma50 = row.get("DMA_50")
    dma200 = row.get("DMA_200")
    ema20 = row.get("EMA_20")
    if pd.isna(close) or pd.isna(dma50) or pd.isna(dma200):
        return "Insufficient data"
    if close > ema20 > dma50 > dma200:
        return "Strong uptrend"
    if close > dma50 > dma200:
        return "Uptrend"
    if close < dma50 < dma200:
        return "Downtrend"
    return "Sideways / consolidating"


def breakout_probability(df: pd.DataFrame, resistance: float | None) -> int:
    if df.empty or resistance is None:
        return 0
    latest = df.iloc[-1]
    close = float(latest["Close"])
    rsi = latest.get("RSI_14", np.nan)
    avg_volume = latest.get("AVG_VOLUME_20", np.nan)
    volume = latest.get("Volume", np.nan)
    distance_score = max(0, 35 - min(35, abs(resistance - close) / close * 700))
    momentum_score = 25 if rsi >= 65 else 18 if rsi >= 60 else 10 if rsi >= 50 else 2
    volume_score = 25 if avg_volume and volume > avg_volume * 1.5 else 15 if avg_volume and volume > avg_volume else 5
    trend_score = 15 if close > latest.get("DMA_50", close) else 5
    return int(min(100, round(distance_score + momentum_score + volume_score + trend_score)))


def technical_summary(history: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = add_indicators(history)
    latest = df.iloc[-1]
    support, resistance = support_resistance(df)
    macd_value = latest.get("MACD")
    signal_value = latest.get("MACD_SIGNAL")
    macd_state = "Bullish" if macd_value > signal_value else "Bearish"
    summary = {
        "RSI (14)": latest.get("RSI_14"),
        "MACD": macd_value,
        "MACD Signal": signal_value,
        "MACD State": macd_state,
        "20 EMA": latest.get("EMA_20"),
        "50 DMA": latest.get("DMA_50"),
        "200 DMA": latest.get("DMA_200"),
        "Bollinger Upper": latest.get("BB_HIGH"),
        "Bollinger Lower": latest.get("BB_LOW"),
        "Trend": trend_direction(latest),
        "Support": support,
        "Resistance": resistance,
        "Breakout Probability": breakout_probability(df, resistance),
    }
    return df, summary
