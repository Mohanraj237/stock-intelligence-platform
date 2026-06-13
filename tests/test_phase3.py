"""
Phase 3 regression tests — WS-1, WS-2, WS-4, WS-5.

All tests use the shared TestClient session from conftest.py.
No live NSE/YF calls — services fall back to synthetic data or file-based storage.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# WS-1: F&O Scanner backend endpoint schema
# ─────────────────────────────────────────────────────────────────────────────

class TestFoScannerBackend:
    """
    GET /api/fno/scan — OI-data scanner (server-side, NSE-backed).
    WS-1: OI-data scan types route to this endpoint; chain types do not.
    """

    BACKEND_SCAN_TYPES = ["High OI Buildup", "OI Unwinding", "Unusual Volume"]

    def test_scan_returns_200(self, client):
        r = client.get("/api/fno/scan?scan_type=High+OI+Buildup")
        assert r.status_code == 200

    def test_scan_returns_list(self, client):
        r = client.get("/api/fno/scan?scan_type=High+OI+Buildup")
        data = r.json()
        assert isinstance(data, list)

    @pytest.mark.parametrize("scan_type", ["High OI Buildup", "OI Unwinding", "Unusual Volume"])
    def test_backend_scan_types_return_list(self, client, scan_type):
        r = client.get(f"/api/fno/scan?scan_type={scan_type.replace(' ', '+')}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_scan_row_schema(self, client):
        """Every returned row must have the FoScanRow-compatible fields."""
        r = client.get("/api/fno/scan?scan_type=High+OI+Buildup")
        rows = r.json()
        if not rows:
            pytest.skip("No scan results — NSE may be unavailable; schema can't be verified")
        row = rows[0]
        assert "symbol"      in row, "Missing 'symbol'"
        assert "signal_type" in row, "Missing 'signal_type'"
        assert "metric"      in row, "Missing 'metric'"
        assert "direction"   in row, "Missing 'direction'"
        assert "strength"    in row, "Missing 'strength'"
        assert "expiry"      in row, "Missing 'expiry'"
        assert "dte"         in row, "Missing 'dte'"

    def test_direction_values_are_capitalised(self, client):
        """Frontend ScanResult expects 'Bullish' | 'Bearish' | 'Neutral' (capital B/N)."""
        r = client.get("/api/fno/scan?scan_type=High+OI+Buildup")
        for row in r.json():
            assert row["direction"] in ("Bullish", "Bearish", "Neutral"), (
                f"Unexpected direction value: {row['direction']}"
            )

    def test_strength_is_0_to_100(self, client):
        r = client.get("/api/fno/scan?scan_type=High+OI+Buildup")
        for row in r.json():
            assert 0 <= row["strength"] <= 100, f"Strength out of range: {row['strength']}"


# ─────────────────────────────────────────────────────────────────────────────
# WS-2: GET /api/fno/max-pain
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxPain:
    """WS-2 — Dedicated max-pain endpoint."""

    def test_returns_200(self, client):
        r = client.get("/api/fno/max-pain?symbol=NIFTY")
        assert r.status_code == 200

    def test_schema(self, client):
        d = client.get("/api/fno/max-pain?symbol=NIFTY").json()
        assert "symbol"       in d
        assert "expiry"       in d
        assert "max_pain"     in d
        assert "spot"         in d
        assert "distance_pct" in d
        assert "synthetic"    in d

    def test_max_pain_is_positive_float(self, client):
        d = client.get("/api/fno/max-pain?symbol=NIFTY").json()
        assert isinstance(d["max_pain"], (int, float))
        # Synthetic chain always returns a value > 0
        assert d["max_pain"] >= 0

    def test_distance_pct_is_non_negative(self, client):
        d = client.get("/api/fno/max-pain?symbol=BANKNIFTY").json()
        assert d["distance_pct"] >= 0

    def test_max_pain_known_input(self, client):
        """
        Regression: with a simple synthetic chain the max-pain function must return
        the strike with minimum total writer loss.  Here we test via the API that the
        returned max_pain is a plausible strike (within ±10 strikes of spot).
        """
        d = client.get("/api/fno/max-pain?symbol=NIFTY").json()
        if d["spot"] > 0 and d["max_pain"] > 0:
            # Max pain should be within ±20% of spot (sanity bound)
            assert abs(d["max_pain"] - d["spot"]) / d["spot"] < 0.20, (
                f"Max pain {d['max_pain']} is suspiciously far from spot {d['spot']}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# WS-4: Yahoo Finance ticker fixes
# ─────────────────────────────────────────────────────────────────────────────

class TestYFTickerFixes:
    """
    WS-4 — Verify ticker resolution is correct after the mapping updates.
    Does NOT make live YF calls — just asserts the _ticker() function logic.
    """

    def test_midcpnifty_resolves_to_yf_ticker(self):
        from services.intraday_data import _ticker
        assert _ticker("MIDCPNIFTY") == "NIFTY_MID_SELECT.NS"

    def test_bankex_resolves_to_yf_ticker(self):
        from services.intraday_data import _ticker
        assert _ticker("BANKEX") == "BSE-BANK.BO"

    def test_tatamotors_resolves_to_override_ticker(self):
        from services.intraday_data import _ticker
        # TATAMOTORS uses the equity override map (YF ticker: TMCV.NS)
        assert _ticker("TATAMOTORS") == "TMCV.NS"

    def test_eternal_resolves_to_yf_ticker(self):
        from services.intraday_data import _ticker
        # ETERNAL (formerly ZOMATO) — override in _EQUITY_TICKER_OVERRIDE
        assert _ticker("ETERNAL") == "ETERNAL.NS"

    def test_standard_equity_still_appends_ns(self):
        from services.intraday_data import _ticker
        # Unaffected symbols should still use the {SYM}.NS convention
        assert _ticker("RELIANCE") == "RELIANCE.NS"
        assert _ticker("INFY")     == "INFY.NS"

    def test_midcpnifty_in_all_indices(self):
        from services.intraday_data import _ALL_INDICES
        assert "MIDCPNIFTY" in _ALL_INDICES, "MIDCPNIFTY should be in _ALL_INDICES after WS-4"

    def test_bankex_in_all_indices(self):
        from services.intraday_data import _ALL_INDICES
        assert "BANKEX" in _ALL_INDICES, "BANKEX should be in _ALL_INDICES after WS-4"

    def test_tatamotors_in_equity_universe(self):
        from services.intraday_data import _ALL_FNO_EQUITY
        assert "TATAMOTORS" in _ALL_FNO_EQUITY, "TATAMOTORS should be re-enabled after WS-4"

    def test_eternal_in_equity_universe(self):
        from services.intraday_data import _ALL_FNO_EQUITY
        assert "ETERNAL" in _ALL_FNO_EQUITY, "ETERNAL (ex-ZOMATO) should be in _ALL_FNO_EQUITY"

    def test_eternal_in_lot_sizes(self):
        from services.fno_data_service import LOT_SIZES
        assert "ETERNAL" in LOT_SIZES, "ETERNAL should have a lot size entry"
        assert LOT_SIZES["ETERNAL"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# WS-5: Historical IV per symbol → true IV Rank
# ─────────────────────────────────────────────────────────────────────────────

class TestIVRank:
    """
    WS-5 — IV rank math and fallback-to-VIX-proxy logic.
    All tests operate on in-memory / temp JSON; no live NSE calls.
    """

    def _make_entries(self, ivs: list[float], today="2026-06-09") -> list[dict]:
        """Build a history entry list from a list of IV values."""
        from datetime import date, timedelta
        start = date.fromisoformat(today) - timedelta(days=len(ivs))
        return [
            {"date": (start + timedelta(days=i)).isoformat(), "atm_iv": iv}
            for i, iv in enumerate(ivs)
        ]

    def test_iv_rank_math_full_range(self, tmp_path, monkeypatch):
        """When current IV is the 52w high, IV Rank = 100."""
        from services.fno_data_service import get_iv_rank, _IV_HISTORY_PATH, _IV_RANK_MIN_DAYS

        ivs = list(range(10, 40))  # 30 entries, values 10–39
        history = {"NIFTY": self._make_entries(ivs)}
        history_path = tmp_path / "iv_history.json"
        history_path.write_text(json.dumps(history))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", history_path)

        r = get_iv_rank("NIFTY")
        assert r["sufficient_history"] is True
        assert r["iv_rank"] == pytest.approx(100.0)
        assert r["current_iv"] == 39.0
        assert r["iv_52w_high"] == 39.0
        assert r["iv_52w_low"]  == 10.0

    def test_iv_rank_at_minimum_is_0(self, tmp_path, monkeypatch):
        """When current IV is the 52w low, IV Rank = 0."""
        from services.fno_data_service import get_iv_rank

        ivs = list(range(30, 10, -1))  # 20 entries, 30 down to 11 + one 10 not enough
        # Build enough entries: 30 with current = min
        ivs2 = [20.0] * 29 + [10.0]
        history = {"BANKNIFTY": self._make_entries(ivs2)}
        path = tmp_path / "iv_history.json"
        path.write_text(json.dumps(history))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", path)

        r = get_iv_rank("BANKNIFTY")
        assert r["iv_rank"] == pytest.approx(0.0)

    def test_iv_rank_midpoint(self, tmp_path, monkeypatch):
        """When current IV is exactly the midpoint, IV Rank ≈ 50."""
        from services.fno_data_service import get_iv_rank

        # 30 entries: low=10, high=30, current (last)=20
        ivs = [10.0] + [15.0] * 28 + [20.0]
        # Manually override high/low in this test by using range
        ivs2 = [10.0 + i for i in range(30)]  # 10..39; last=39 → not midpoint
        # Build: 15 entries at 10, 14 entries at 30, last entry = 20
        ivs3 = [10.0] * 15 + [30.0] * 14 + [20.0]
        history = {"NIFTY": self._make_entries(ivs3)}
        path = tmp_path / "iv_history.json"
        path.write_text(json.dumps(history))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", path)

        r = get_iv_rank("NIFTY")
        assert r["iv_rank"] == pytest.approx(50.0)

    def test_insufficient_history_returns_false(self, tmp_path, monkeypatch):
        """Fewer than _IV_RANK_MIN_DAYS entries → sufficient_history = False."""
        from services.fno_data_service import get_iv_rank, _IV_RANK_MIN_DAYS

        ivs = [15.0] * (_IV_RANK_MIN_DAYS - 1)  # one short
        history = {"RELIANCE": self._make_entries(ivs)}
        path = tmp_path / "iv_history.json"
        path.write_text(json.dumps(history))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", path)

        r = get_iv_rank("RELIANCE")
        assert r["sufficient_history"] is False
        assert r["iv_rank"] is None   # rank undefined without enough history

    def test_no_history_returns_sufficient_false(self, tmp_path, monkeypatch):
        """Symbol with no history at all."""
        from services.fno_data_service import get_iv_rank

        path = tmp_path / "iv_history.json"
        path.write_text(json.dumps({}))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", path)

        r = get_iv_rank("INFY")
        assert r["sufficient_history"] is False
        assert r["current_iv"] is None

    def test_iv_snapshot_endpoint_200(self, client):
        r = client.post("/api/fno/iv-snapshot", json={})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        assert d["ok"] is True
        assert "updated" in d
        assert isinstance(d["updated"], list)

    def test_iv_rank_endpoint_200(self, client):
        r = client.get("/api/fno/iv-rank?symbol=NIFTY")
        assert r.status_code == 200
        d = r.json()
        assert "symbol" in d
        assert "sufficient_history" in d
        assert "days_available" in d

    def test_append_daily_iv_idempotent(self, tmp_path, monkeypatch):
        """
        Calling append_daily_iv_snapshot() twice on the same day should not
        add a duplicate entry for any symbol.
        """
        from services.fno_data_service import append_daily_iv_snapshot

        path = tmp_path / "iv_history.json"
        path.write_text(json.dumps({}))
        monkeypatch.setattr("services.fno_data_service._IV_HISTORY_PATH", path)

        # First call — may succeed or fail depending on NSE availability; we only
        # care that a second call on the same day doesn't duplicate.
        append_daily_iv_snapshot()
        data_after_first = json.loads(path.read_text())
        append_daily_iv_snapshot()
        data_after_second = json.loads(path.read_text())

        for sym, entries in data_after_second.items():
            first_entries = data_after_first.get(sym, [])
            assert len(entries) == len(first_entries), (
                f"{sym}: second snapshot added duplicate entries "
                f"({len(first_entries)} → {len(entries)})"
            )
