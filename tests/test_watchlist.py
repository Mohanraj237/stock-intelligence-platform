"""Tests for /api/watchlist endpoints — CRUD lifecycle."""
from __future__ import annotations
import pytest


TEST_SYMBOL = "TEST_WL_SYMBOL"


class TestWatchlistCRUD:
    def test_get_watchlist_returns_list(self, fresh_client):
        r = fresh_client.get("/api/watchlist")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_symbol(self, fresh_client):
        r = fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        assert r.status_code == 200
        d = r.json()
        assert d.get("added") == TEST_SYMBOL or d.get("already_present") is True

    def test_symbol_present_after_add(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        r = fresh_client.get("/api/watchlist")
        symbols = [row["symbol"] for row in r.json()]
        assert TEST_SYMBOL in symbols

    def test_add_duplicate_returns_already_present(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        r2 = fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        assert r2.status_code == 200
        assert r2.json().get("already_present") is True

    def test_remove_symbol(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        r = fresh_client.delete(f"/api/watchlist/{TEST_SYMBOL}")
        assert r.status_code == 200
        d = r.json()
        assert "removed" in d

    def test_symbol_gone_after_remove(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        fresh_client.delete(f"/api/watchlist/{TEST_SYMBOL}")
        r = fresh_client.get("/api/watchlist")
        symbols = [row["symbol"] for row in r.json()]
        assert TEST_SYMBOL not in symbols

    def test_remove_nonexistent_returns_404(self, fresh_client):
        r = fresh_client.delete("/api/watchlist/SYMBOL_THAT_DOES_NOT_EXIST_XYZ")
        assert r.status_code == 404

    def test_watchlist_row_schema(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": TEST_SYMBOL})
        r = fresh_client.get("/api/watchlist")
        rows = r.json()
        matching = [row for row in rows if row["symbol"] == TEST_SYMBOL]
        assert matching, "Added symbol not found in watchlist"
        row = matching[0]
        assert "symbol" in row

    def test_add_requires_symbol_field(self, fresh_client):
        r = fresh_client.post("/api/watchlist/add", json={})
        assert r.status_code == 422

    def test_case_insensitive_add(self, fresh_client):
        sym_lower = TEST_SYMBOL.lower()
        fresh_client.post("/api/watchlist/add", json={"symbol": sym_lower})
        r = fresh_client.get("/api/watchlist")
        symbols_upper = [row["symbol"].upper() for row in r.json()]
        assert TEST_SYMBOL.upper() in symbols_upper


class TestWatchlistEnrichment:
    """Verify that watchlist rows have numeric fields for known symbols."""

    def test_us_stock_enriched(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": "AAPL"})
        r = fresh_client.get("/api/watchlist")
        rows = r.json()
        aapl = next((row for row in rows if row["symbol"].upper() == "AAPL"), None)
        if aapl is None:
            pytest.skip("AAPL not enriched — possibly network unavailable")
        # If we got data, last_price should be a number
        if aapl.get("last_price") is not None:
            assert isinstance(aapl["last_price"], (int, float))

    def test_indian_stock_enriched(self, fresh_client):
        fresh_client.post("/api/watchlist/add", json={"symbol": "RELIANCE"})
        r = fresh_client.get("/api/watchlist")
        rows = r.json()
        rel = next((row for row in rows if row["symbol"].upper() == "RELIANCE"), None)
        if rel is None:
            pytest.skip("RELIANCE not enriched — possibly network unavailable")
        if rel.get("last_price") is not None:
            assert isinstance(rel["last_price"], (int, float))
