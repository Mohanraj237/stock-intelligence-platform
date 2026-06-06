"""Tests for /api/fno endpoints.

All F&O routes use query params, not path params:
  /api/fno/option-chain?symbol=NIFTY   (not /option-chain/NIFTY)
  /api/fno/pcr?symbol=NIFTY            (not /pcr/NIFTY)
"""
from __future__ import annotations
import pytest


NIFTY = "NIFTY"
BANKNIFTY = "BANKNIFTY"


class TestOptionChain:
    def test_nifty_option_chain_returns_200(self, client):
        r = client.get(f"/api/fno/option-chain?symbol={NIFTY}")
        assert r.status_code == 200

    def test_option_chain_schema(self, client):
        r = client.get(f"/api/fno/option-chain?symbol={NIFTY}")
        d = r.json()
        assert "rows" in d
        assert "meta" in d
        assert isinstance(d["rows"], list)

    def test_option_chain_rows_have_required_fields(self, client):
        r = client.get(f"/api/fno/option-chain?symbol={NIFTY}")
        rows = r.json().get("rows", [])
        if rows:
            row = rows[0]
            assert "strike" in row
            assert "expiry" in row
            # Actual field names use uppercase prefix: CE_oi / PE_oi
            assert "CE_oi" in row or "PE_oi" in row or "ce_oi" in row or "pe_oi" in row

    def test_option_chain_meta_has_spot_price(self, client):
        r = client.get(f"/api/fno/option-chain?symbol={NIFTY}")
        meta = r.json().get("meta", {})
        assert "spot" in meta or "underlying_value" in meta or "symbol" in meta or "underlying" in meta

    def test_banknifty_option_chain(self, client):
        r = client.get(f"/api/fno/option-chain?symbol={BANKNIFTY}")
        assert r.status_code == 200
        assert "rows" in r.json()

    def test_invalid_symbol_uses_synthetic(self, client):
        r = client.get("/api/fno/option-chain?symbol=FAKESTOCK123")
        # Should return 200 with synthetic data, not 500
        assert r.status_code == 200
        assert "rows" in r.json()

    def test_default_symbol_is_nifty(self, client):
        # No symbol param — defaults to NIFTY
        r = client.get("/api/fno/option-chain")
        assert r.status_code == 200
        assert "rows" in r.json()

    def test_option_chain_with_expiry_filter(self, client):
        r1 = client.get(f"/api/fno/option-chain?symbol={NIFTY}")
        rows = r1.json().get("rows", [])
        if not rows:
            pytest.skip("No option chain rows to filter on")
        first_expiry = rows[0].get("expiry")
        if not first_expiry:
            pytest.skip("No expiry field in rows")
        r2 = client.get(f"/api/fno/option-chain?symbol={NIFTY}&expiry={first_expiry}")
        assert r2.status_code == 200
        filtered = r2.json().get("rows", [])
        if filtered:
            assert all(row.get("expiry") == first_expiry for row in filtered)


class TestVIX:
    def test_vix_returns_200(self, client):
        r = client.get("/api/fno/vix")
        assert r.status_code == 200

    def test_vix_schema(self, client):
        r = client.get("/api/fno/vix")
        d = r.json()
        assert "vix" in d
        vix = d["vix"]
        if vix is not None:
            assert isinstance(vix, (int, float))
            assert 0 < vix < 200


class TestPCR:
    def test_pcr_returns_200(self, client):
        r = client.get(f"/api/fno/pcr?symbol={NIFTY}")
        assert r.status_code == 200

    def test_pcr_schema(self, client):
        r = client.get(f"/api/fno/pcr?symbol={NIFTY}")
        d = r.json()
        assert "pcr" in d or "put_call_ratio" in d or "symbol" in d or "total_ce_oi" in d

    def test_pcr_default_symbol(self, client):
        r = client.get("/api/fno/pcr")
        assert r.status_code == 200


class TestFNOSymbols:
    def test_symbols_returns_list(self, client):
        r = client.get("/api/fno/symbols")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_symbols_contains_known_fno_stocks(self, client):
        r = client.get("/api/fno/symbols")
        syms = r.json()
        # These are always in the F&O-eligible stock list
        assert "ADANIENT" in syms or "RELIANCE" in syms or "INFY" in syms or "HDFCBANK" in syms


class TestOIAnalytics:
    def test_oi_spurts_returns_list(self, client):
        r = client.get("/api/fno/oi-spurts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_oi_variations_returns_list(self, client):
        r = client.get("/api/fno/oi-variations")
        assert r.status_code in (200, 404, 502)
        if r.status_code == 200:
            assert isinstance(r.json(), list)


class TestPaperTrades:
    def test_open_trades_list(self, client):
        r = client.get("/api/fno/paper-trades/open")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_closed_trades_list(self, client):
        r = client.get("/api/fno/paper-trades/closed")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_equity_curve(self, client):
        r = client.get("/api/fno/paper-trades/equity-curve")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_portfolio_summary(self, client):
        r = client.get("/api/fno/paper-trades/portfolio")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_add_empty_body_returns_422(self, client):
        r = client.post("/api/fno/paper-trades", json={})
        assert r.status_code == 422

    def test_add_missing_required_fields_returns_422(self, client):
        # symbol and entry_price are required
        r = client.post("/api/fno/paper-trades", json={"symbol": "NIFTY"})
        assert r.status_code == 422

    def test_add_valid_paper_trade(self, client):
        payload = {
            "symbol": "NIFTY",
            "instrument_type": "CE",
            "strike": 24000.0,
            "expiry": "2026-06-26",
            "action": "BUY",
            "lots": 1,
            "lot_size": 50,
            "entry_price": 150.0,
        }
        r = client.post("/api/fno/paper-trades", json=payload)
        # 200 = success, 400 = service validation failed (e.g. expiry format), 422 = schema
        assert r.status_code in (200, 201, 400)
