"""Tests for /api/market endpoints."""
from __future__ import annotations
import pytest


class TestMarketStatus:
    def test_status_india(self, client):
        r = client.get("/api/market/status?region=IN")
        assert r.status_code == 200
        d = r.json()
        assert "status" in d
        assert "is_open" in d

    def test_status_us(self, client):
        r = client.get("/api/market/status?region=US")
        assert r.status_code == 200
        d = r.json()
        assert "status" in d
        assert "is_open" in d

    def test_status_default_is_india(self, client):
        r = client.get("/api/market/status")
        assert r.status_code == 200

    def test_status_invalid_region_still_responds(self, client):
        # Unknown region should not crash the server
        r = client.get("/api/market/status?region=EU")
        assert r.status_code in (200, 422)


class TestIndices:
    def test_indices_india_returns_list(self, client):
        r = client.get("/api/market/indices?region=IN")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_indices_us_returns_list(self, client):
        r = client.get("/api/market/indices?region=US")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_indices_schema(self, client):
        r = client.get("/api/market/indices?region=IN")
        assert r.status_code == 200
        items = r.json()
        if items:
            item = items[0]
            assert "name" in item or "symbol" in item
            assert "last_price" in item
            assert "change_pct" in item


class TestSectors:
    def test_sectors_india_returns_list(self, client):
        r = client.get("/api/market/sectors?region=IN")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sectors_us_returns_list(self, client):
        r = client.get("/api/market/sectors?region=US")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sectors_india_schema(self, client):
        r = client.get("/api/market/sectors?region=IN")
        items = r.json()
        if items:
            item = items[0]
            assert "name" in item
            assert "change_pct" in item
            assert "advances" in item
            assert "declines" in item

    def test_sectors_us_schema(self, client):
        r = client.get("/api/market/sectors?region=US")
        items = r.json()
        if items:
            item = items[0]
            assert "name" in item
            assert "change_pct" in item


class TestUniverseQuotes:
    def test_nifty50_quotes_returns_list(self, client):
        r = client.get("/api/market/universe/NIFTY%2050/quotes?region=IN")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_nifty50_quotes_schema(self, client):
        r = client.get("/api/market/universe/NIFTY%2050/quotes?region=IN")
        items = r.json()
        if items:
            item = items[0]
            assert "symbol" in item
            assert "last_price" in item
            assert "change_pct" in item

    def test_dow30_us_quotes_returns_list(self, client):
        r = client.get("/api/market/universe/DOW%2030/quotes?region=US")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unknown_universe_returns_empty_or_error(self, client):
        r = client.get("/api/market/universe/NONEXISTENT_INDEX/quotes?region=IN")
        # Should return 200 with empty list, or 502 if NSE fails — not 500
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            assert isinstance(r.json(), list)


class TestFIIDII:
    def test_fii_dii_returns_list(self, client):
        r = client.get("/api/market/fii-dii")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_fii_dii_schema(self, client):
        r = client.get("/api/market/fii-dii")
        items = r.json()
        if items:
            item = items[0]
            assert "date" in item
            assert "fii_buy" in item
            assert "fii_net" in item
            assert "dii_net" in item
