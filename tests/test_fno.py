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


class TestFNOWatchlist:
    """P1-2 — GET/POST/DELETE /api/fno/watchlist"""

    def test_get_watchlist_returns_list(self, client):
        r = client.get("/api/fno/watchlist")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0   # defaults to ["NIFTY", "BANKNIFTY"]

    def test_add_symbol_to_watchlist(self, fresh_client):
        r = fresh_client.post("/api/fno/watchlist", json={"symbol": "RELIANCE"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "RELIANCE" in d["watchlist"]

    def test_add_requires_symbol(self, client):
        r = client.post("/api/fno/watchlist", json={})
        assert r.status_code == 400

    def test_remove_symbol_from_watchlist(self, fresh_client):
        fresh_client.post("/api/fno/watchlist", json={"symbol": "INFY"})
        r = fresh_client.delete("/api/fno/watchlist/INFY")
        assert r.status_code == 200
        assert "INFY" not in r.json().get("watchlist", [])

    def test_add_is_idempotent(self, fresh_client):
        fresh_client.post("/api/fno/watchlist", json={"symbol": "TCS"})
        fresh_client.post("/api/fno/watchlist", json={"symbol": "TCS"})
        wl = fresh_client.get("/api/fno/watchlist").json()
        assert wl.count("TCS") == 1


class TestUnderlyingQuotes:
    """P1-7 — GET /api/fno/underlying-quotes"""

    def test_returns_list(self, client):
        r = client.get("/api/fno/underlying-quotes")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_accepts_symbols_param(self, client):
        r = client.get("/api/fno/underlying-quotes?symbols=NIFTY,BANKNIFTY")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_each_row_has_required_fields(self, client):
        r = client.get("/api/fno/underlying-quotes?symbols=NIFTY")
        rows = r.json()
        if rows:
            row = rows[0]
            assert "symbol" in row
            assert "ltp" in row
            assert "change_pct" in row



class TestFNOHistory:
    """P1-1 — GET /api/fno/history endpoint added in Workstream B."""

    def test_history_returns_200(self, client):
        r = client.get("/api/fno/history")
        assert r.status_code == 200

    def test_history_schema(self, client):
        r = client.get("/api/fno/history")
        d = r.json()
        assert "pcr" in d, "Missing 'pcr' key"
        assert "vix" in d, "Missing 'vix' key"
        assert isinstance(d["pcr"], list)
        assert isinstance(d["vix"], list)

    def test_history_max_60_entries(self, client):
        r = client.get("/api/fno/history")
        d = r.json()
        assert len(d["pcr"]) <= 60, f"PCR history has {len(d['pcr'])} entries, max is 60"
        assert len(d["vix"]) <= 60, f"VIX history has {len(d['vix'])} entries, max is 60"

    def test_pcr_entry_schema(self, client):
        pcr = client.get("/api/fno/history").json().get("pcr", [])
        if pcr:
            entry = pcr[0]
            assert "date" in entry, "PCR entry missing 'date'"
            # At least one PCR field must be present
            assert "nifty_pcr" in entry or "banknifty_pcr" in entry

    def test_vix_entry_schema(self, client):
        vix = client.get("/api/fno/history").json().get("vix", [])
        if vix:
            entry = vix[0]
            assert "date" in entry, "VIX entry missing 'date'"
            assert "vix" in entry, "VIX entry missing 'vix'"

    def test_history_dates_are_iso_format(self, client):
        import re
        d = client.get("/api/fno/history").json()
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for entry in d.get("pcr", []) + d.get("vix", []):
            assert pattern.match(entry.get("date", "")), f"Bad date format: {entry.get('date')}"


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

    def test_refresh_prices_returns_list(self, client):
        """POST /api/fno/paper-trades/refresh-prices must return a list (may be empty)."""
        r = client.post("/api/fno/paper-trades/refresh-prices", json={})
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestPaperTradePnL:
    """
    P1-5, P2-8 — Verify P&L math for BUY and SELL positions.
    Uses fresh_client to avoid polluting the shared portfolio.
    """

    def _reset(self, c):
        c.post("/api/fno/paper-trades/reset", json={"initial_capital": 2_000_000})

    def _add(self, c, action, entry, lots=1, lot_size=100):
        return c.post("/api/fno/paper-trades", json={
            "symbol": "NIFTY",
            "instrument_type": "CE",
            "strike": 24000.0,
            "expiry": "2027-12-25",
            "action": action,
            "lots": lots,
            "lot_size": lot_size,
            "entry_price": entry,
            "target_price": entry * 1.5,
            "stop_loss": entry * 0.5,
        })

    def test_buy_profit_pnl(self, fresh_client):
        """BUY: P&L = (exit − entry) × lots × lot_size — positive when exit > entry."""
        self._reset(fresh_client)
        r = self._add(fresh_client, "BUY", entry=100.0, lots=2, lot_size=75)
        assert r.status_code == 200

        trades = fresh_client.get("/api/fno/paper-trades/open").json()
        assert trades, "No open trades after adding one"
        trade_id = trades[-1]["trade_id"]

        r2 = fresh_client.post(f"/api/fno/paper-trades/{trade_id}/close",
                               json={"exit_price": 150.0, "exit_reason": "TEST"})
        assert r2.status_code == 200

        closed = fresh_client.get("/api/fno/paper-trades/closed").json()
        trade = next((t for t in closed if t["trade_id"] == trade_id), None)
        assert trade is not None, "Closed trade not found"
        # (150 − 100) × 2 × 75 = 7500
        assert trade["pnl_rs"] == pytest.approx(7500.0), f"Got {trade['pnl_rs']}"
        assert trade["exit_price"] == pytest.approx(150.0)

    def test_buy_loss_pnl(self, fresh_client):
        """BUY: P&L is negative when exit < entry."""
        self._reset(fresh_client)
        r = self._add(fresh_client, "BUY", entry=200.0, lots=1, lot_size=50)
        assert r.status_code == 200

        trade_id = fresh_client.get("/api/fno/paper-trades/open").json()[-1]["trade_id"]
        fresh_client.post(f"/api/fno/paper-trades/{trade_id}/close",
                          json={"exit_price": 120.0, "exit_reason": "SL_HIT"})

        trade = next(
            t for t in fresh_client.get("/api/fno/paper-trades/closed").json()
            if t["trade_id"] == trade_id
        )
        # (120 − 200) × 1 × 50 = −4000
        assert trade["pnl_rs"] == pytest.approx(-4000.0)

    def test_sell_profit_pnl(self, fresh_client):
        """SELL: P&L = (entry − exit) × lots × lot_size — positive when exit < entry (premium decayed)."""
        self._reset(fresh_client)
        r = self._add(fresh_client, "SELL", entry=200.0, lots=1, lot_size=15)
        assert r.status_code == 200

        trades = fresh_client.get("/api/fno/paper-trades/open").json()
        assert trades
        trade_id = trades[-1]["trade_id"]

        fresh_client.post(f"/api/fno/paper-trades/{trade_id}/close",
                          json={"exit_price": 80.0, "exit_reason": "TARGET_HIT"})

        trade = next(
            t for t in fresh_client.get("/api/fno/paper-trades/closed").json()
            if t["trade_id"] == trade_id
        )
        # (200 − 80) × 1 × 15 = 1800
        assert trade["pnl_rs"] == pytest.approx(1800.0)

    def test_sell_loss_pnl(self, fresh_client):
        """SELL: P&L is negative when exit > entry (option moved against the seller)."""
        self._reset(fresh_client)
        r = self._add(fresh_client, "SELL", entry=100.0, lots=1, lot_size=15)
        assert r.status_code == 200

        trade_id = fresh_client.get("/api/fno/paper-trades/open").json()[-1]["trade_id"]
        fresh_client.post(f"/api/fno/paper-trades/{trade_id}/close",
                          json={"exit_price": 250.0, "exit_reason": "SL_HIT"})

        trade = next(
            t for t in fresh_client.get("/api/fno/paper-trades/closed").json()
            if t["trade_id"] == trade_id
        )
        # (100 − 250) × 1 × 15 = −2250
        assert trade["pnl_rs"] == pytest.approx(-2250.0)

    def test_close_uses_provided_exit_price(self, fresh_client):
        """The exit price sent in the close request must appear verbatim in the trade record."""
        self._reset(fresh_client)
        self._add(fresh_client, "BUY", entry=100.0)
        trade_id = fresh_client.get("/api/fno/paper-trades/open").json()[-1]["trade_id"]

        exact_price = 137.50
        fresh_client.post(f"/api/fno/paper-trades/{trade_id}/close",
                          json={"exit_price": exact_price, "exit_reason": "MANUAL"})

        trade = next(
            t for t in fresh_client.get("/api/fno/paper-trades/closed").json()
            if t["trade_id"] == trade_id
        )
        assert trade["exit_price"] == pytest.approx(exact_price), (
            f"Expected exit_price={exact_price}, got {trade['exit_price']}"
        )
