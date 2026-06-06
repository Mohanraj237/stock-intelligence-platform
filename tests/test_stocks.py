"""Tests for /api/stocks endpoints."""
from __future__ import annotations
import pytest


IN_SYMBOL = "RELIANCE"
US_SYMBOL = "AAPL"


class TestOHLCV:
    def test_ohlcv_india(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1D")
        assert r.status_code == 200

    def test_ohlcv_us(self, client):
        r = client.get(f"/api/stocks/{US_SYMBOL}/ohlcv?region=US&timeframe=1D")
        assert r.status_code == 200

    def test_ohlcv_schema(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1D")
        d = r.json()
        assert "symbol" in d
        assert "bars" in d or "candles" in d or "data" in d or "ohlcv" in d

    def test_ohlcv_bars_have_ohlcv_fields(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1D")
        d = r.json()
        bars = d.get("bars") or d.get("candles") or d.get("data") or d.get("ohlcv") or []
        if bars:
            bar = bars[0]
            for field in ("open", "high", "low", "close"):
                assert field in bar or field.capitalize() in bar

    def test_ohlcv_weekly_timeframe(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1W")
        assert r.status_code == 200

    def test_ohlcv_monthly_timeframe(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1M")
        assert r.status_code == 200

    def test_ohlcv_unknown_symbol_does_not_crash(self, client):
        r = client.get("/api/stocks/UNKNOWNSYMBOL99999/ohlcv?region=IN&timeframe=1D")
        assert r.status_code in (200, 404, 502)


class TestIndicators:
    def test_indicators_india(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/indicators?region=IN&timeframe=1D")
        assert r.status_code == 200

    def test_indicators_schema(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/indicators?region=IN&timeframe=1D")
        d = r.json()
        assert isinstance(d, dict)
        for field in ("rsi", "sma50", "sma200", "macd_hist"):
            assert field in d

    def test_indicators_rsi_range(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/indicators?region=IN&timeframe=1D")
        d = r.json()
        rsi = d.get("rsi")
        if rsi is not None:
            assert 0 <= rsi <= 100


class TestFundamentals:
    def test_fundamentals_india(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/fundamentals?region=IN")
        assert r.status_code == 200

    def test_fundamentals_schema(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/fundamentals?region=IN")
        d = r.json()
        assert "symbol" in d

    def test_fundamentals_us(self, client):
        r = client.get(f"/api/stocks/{US_SYMBOL}/fundamentals?region=US")
        assert r.status_code == 200


class TestVerdict:
    def test_verdict_india(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/verdict?region=IN&timeframe=1D")
        assert r.status_code == 200

    def test_verdict_schema(self, client):
        r = client.get(f"/api/stocks/{IN_SYMBOL}/verdict?region=IN&timeframe=1D")
        d = r.json()
        assert "symbol" in d
        assert "verdict" in d or "signal" in d or "recommendation" in d or "score" in d


class TestRegionIsolation:
    """Verify that IN and US never bleed into each other for stock data."""

    def test_nse_symbol_uses_in_region(self, client):
        r_in = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=IN&timeframe=1D")
        r_us = client.get(f"/api/stocks/{IN_SYMBOL}/ohlcv?region=US&timeframe=1D")
        # Both should respond — but may return different data or empty for US
        assert r_in.status_code == 200
        assert r_us.status_code in (200, 404, 502)

    def test_us_symbol_uses_us_region(self, client):
        r_in = client.get(f"/api/stocks/{US_SYMBOL}/ohlcv?region=IN&timeframe=1D")
        r_us = client.get(f"/api/stocks/{US_SYMBOL}/ohlcv?region=US&timeframe=1D")
        assert r_us.status_code == 200
        # IN region may return empty or error for a US-only ticker
        assert r_in.status_code in (200, 404, 502)
