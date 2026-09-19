"""Tests for /api/universe endpoints."""
from __future__ import annotations
import pytest

from services import universe_sync


class TestUniverseList:
    def test_list_india(self, client):
        r = client.get("/api/universe/list?region=IN")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)

    def test_list_india_has_nifty50(self, client):
        r = client.get("/api/universe/list?region=IN")
        d = r.json()
        keys = list(d.keys())
        assert any("NIFTY" in k or "nifty" in k.lower() for k in keys)

    def test_list_us(self, client):
        r = client.get("/api/universe/list?region=US")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)

    def test_list_us_has_dow(self, client):
        r = client.get("/api/universe/list?region=US")
        d = r.json()
        keys = list(d.keys())
        assert any("DOW" in k.upper() or "NASDAQ" in k.upper() or "S&P" in k.upper() for k in keys)


class TestUniverseSymbols:
    def test_nifty50_symbols(self, client):
        r = client.get("/api/universe/NIFTY%2050/symbols?region=IN")
        assert r.status_code == 200
        syms = r.json()
        assert isinstance(syms, list)
        assert len(syms) > 0

    def test_nifty50_has_expected_symbols(self, client):
        r = client.get("/api/universe/NIFTY%2050/symbols?region=IN")
        syms = r.json()
        assert "RELIANCE" in syms or "HDFCBANK" in syms or "INFY" in syms

    def test_symbols_limit_param(self, client):
        r = client.get("/api/universe/NIFTY%2050/symbols?region=IN&limit=10")
        assert r.status_code == 200
        syms = r.json()
        assert len(syms) <= 10

    def test_us_universe_symbols(self, client):
        r = client.get("/api/universe/DOW%2030/symbols?region=US")
        assert r.status_code == 200
        syms = r.json()
        assert isinstance(syms, list)

    def test_unknown_universe_does_not_crash(self, client):
        r = client.get("/api/universe/TOTALLY_UNKNOWN/symbols?region=IN")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert isinstance(r.json(), list)


class TestUniverseSync:
    def test_sync_nifty50_returns_something(self, client):
        r = client.post("/api/universe/NIFTY%2050/sync?region=IN", json={})
        # Sync may succeed or fail on network issues — should not be 500
        assert r.status_code in (200, 202, 502, 503)


class TestUniverseSyncUrls:
    """NSE retired archives.nseindia.com for bulk CSV downloads (it now returns a
    hard 403 from Akamai's WAF regardless of headers/cookies/session — verified
    live) and moved the same files to nsearchives.nseindia.com. Guard against
    silently drifting back to the dead host."""

    def test_index_urls_use_live_archive_host(self):
        for name, url in universe_sync.INDEX_URLS.items():
            assert url.startswith("https://nsearchives.nseindia.com/"), (name, url)

    def test_equity_master_url_uses_live_archive_host(self):
        assert universe_sync.EQUITY_MASTER_URL.startswith(
            "https://nsearchives.nseindia.com/"
        )
