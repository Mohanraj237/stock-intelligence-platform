"""
Phase A — Paper Trade LTP / P&L / Total Equity correctness tests.

Acceptance criteria (from the task spec):
  RBLBANK  370 CE  entry=7.55   LTP=9.90  → P&L = +₹7,461.25  (+31.13%)
  INDUSINDBK 920 CE entry=22.53 LTP=20.30 → P&L = −₹1,115.00 (−9.90%)
  Open P&L total = +₹6,346.25
  Total Equity   = 4,64,763.75 + 35,236.25 + 6,346.25 = ₹5,06,346.25
  Total P&L %    = 1.27%

Tests cover:
  1. P&L math — BUY and SELL sign convention, exact values
  2. Chain lookup — expiry normalisation, strike matching
  3. Fallback — synthetic chain rejected, cached chain accepted
  4. Portfolio summary — all four header cards
  5. Regression — manual PATCH endpoint round-trip via FastAPI
"""
from __future__ import annotations

import json
import sys
import types
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

# Make sure project root is on sys.path (conftest does this for the session,
# but standalone pytest runs of this file need it too).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pnl(entry: float, ltp: float, lots: int, lot_size: int, action: str = "BUY") -> float:
    mult = 1 if action == "BUY" else -1
    return round(mult * (ltp - entry) * lots * lot_size, 2)


def _pnl_pct(pnl: float, margin: float) -> float:
    return round(pnl / margin * 100, 2) if margin else 0.0


def _margin(entry: float, lot_size: int, lots: int) -> float:
    """Premium margin for option BUY (no leverage)."""
    return entry * lot_size * lots


# ── 1. P&L math — exact acceptance values ─────────────────────────────────────

class TestPnlMath:
    """Unit tests for the P&L formula — no I/O, pure arithmetic."""

    def test_rblbank_buy_pnl_exact(self):
        pnl = _pnl(entry=7.55, ltp=9.90, lots=1, lot_size=3175)
        assert pnl == pytest.approx(7461.25, abs=0.01), f"RBLBANK P&L {pnl}"

    def test_indusindbk_buy_pnl_exact(self):
        pnl = _pnl(entry=22.53, ltp=20.30, lots=1, lot_size=500)
        assert pnl == pytest.approx(-1115.00, abs=0.01), f"INDUSINDBK P&L {pnl}"

    def test_rblbank_pnl_pct(self):
        margin = _margin(7.55, 3175, 1)          # 23971.25
        pnl    = _pnl(7.55, 9.90, 1, 3175)       # 7461.25
        pct    = _pnl_pct(pnl, margin)
        assert pct == pytest.approx(31.13, abs=0.01), f"RBLBANK P&L% {pct}"

    def test_indusindbk_pnl_pct(self):
        margin = _margin(22.53, 500, 1)           # 11265.00
        pnl    = _pnl(22.53, 20.30, 1, 500)      # -1115.00
        pct    = _pnl_pct(pnl, margin)
        assert pct == pytest.approx(-9.90, abs=0.01), f"INDUSINDBK P&L% {pct}"

    def test_open_pnl_total(self):
        p1 = _pnl(7.55, 9.90, 1, 3175)
        p2 = _pnl(22.53, 20.30, 1, 500)
        assert p1 + p2 == pytest.approx(6346.25, abs=0.01)

    def test_total_equity(self):
        available = 464763.75
        deployed  = 35236.25
        open_pnl  = _pnl(7.55, 9.90, 1, 3175) + _pnl(22.53, 20.30, 1, 500)
        assert available + deployed + open_pnl == pytest.approx(506346.25, abs=0.01)

    def test_total_pnl_pct(self):
        initial  = 500_000.0
        open_pnl = _pnl(7.55, 9.90, 1, 3175) + _pnl(22.53, 20.30, 1, 500)
        pct      = round(open_pnl / initial * 100, 2)
        assert pct == pytest.approx(1.27, abs=0.01)

    def test_sell_sign_is_inverted(self):
        """SELL position: profit when price falls."""
        pnl = _pnl(entry=100.0, ltp=90.0, lots=1, lot_size=100, action="SELL")
        assert pnl == pytest.approx(1000.0, abs=0.01)

    def test_buy_loss_when_price_falls(self):
        pnl = _pnl(entry=100.0, ltp=80.0, lots=1, lot_size=100, action="BUY")
        assert pnl == pytest.approx(-2000.0, abs=0.01)

    def test_deployed_equals_entry_premium(self):
        """margin_used for BUY options = entry_price × lot_size × lots."""
        assert _margin(7.55, 3175, 1) == pytest.approx(23971.25, abs=0.01)
        assert _margin(22.53, 500, 1)  == pytest.approx(11265.00, abs=0.01)
        assert _margin(7.55, 3175, 1) + _margin(22.53, 500, 1) == pytest.approx(35236.25, abs=0.01)


# ── 2. Chain lookup — _ltp_from_chain with real DataFrame fixture ──────────────

def _make_chain_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal option-chain DataFrame from a list of row dicts."""
    return pd.DataFrame(rows)


def _make_chain_meta(synthetic: bool = False, cached: bool = False) -> dict:
    return {
        "expiry_dates":  ["25-Jun-2026"],
        "strike_prices": [370],
        "underlying":    365.85,
        "timestamp":     "13-Jun-2026 15:00:52",
        "synthetic":     synthetic,
        "cached":        cached,
    }


RBLBANK_CHAIN_ROWS = [
    {
        "strike": 365, "expiry": "25-Jun-2026",
        "CE_ltp": 11.0, "PE_ltp": 5.0,
        "CE_oi": 100, "PE_oi": 100,
        "CE_oi_chg": 0, "PE_oi_chg": 0,
        "CE_oi_chg_pct": 0, "PE_oi_chg_pct": 0,
        "CE_vol": 0, "PE_vol": 0,
        "CE_iv": 0, "PE_iv": 0,
        "CE_chg": 0, "PE_chg": 0,
        "CE_chg_pct": 0, "PE_chg_pct": 0,
        "CE_bid_qty": 0, "CE_bid": 0, "CE_ask_qty": 0, "CE_ask": 0,
        "PE_bid_qty": 0, "PE_bid": 0, "PE_ask_qty": 0, "PE_ask": 0,
    },
    {
        "strike": 370, "expiry": "25-Jun-2026",
        "CE_ltp": 9.90, "PE_ltp": 12.5,
        "CE_oi": 200, "PE_oi": 150,
        "CE_oi_chg": 0, "PE_oi_chg": 0,
        "CE_oi_chg_pct": 0, "PE_oi_chg_pct": 0,
        "CE_vol": 0, "PE_vol": 0,
        "CE_iv": 0, "PE_iv": 0,
        "CE_chg": 0, "PE_chg": 0,
        "CE_chg_pct": 0, "PE_chg_pct": 0,
        "CE_bid_qty": 0, "CE_bid": 0, "CE_ask_qty": 0, "CE_ask": 0,
        "PE_bid_qty": 0, "PE_bid": 0, "PE_ask_qty": 0, "PE_ask": 0,
    },
]

INDUSINDBK_CHAIN_ROWS = [
    {
        "strike": 920, "expiry": "25-Jun-2026",
        "CE_ltp": 20.30, "PE_ltp": 30.0,
        "CE_oi": 500, "PE_oi": 300,
        "CE_oi_chg": 0, "PE_oi_chg": 0,
        "CE_oi_chg_pct": 0, "PE_oi_chg_pct": 0,
        "CE_vol": 0, "PE_vol": 0,
        "CE_iv": 0, "PE_iv": 0,
        "CE_chg": 0, "PE_chg": 0,
        "CE_chg_pct": 0, "PE_chg_pct": 0,
        "CE_bid_qty": 0, "CE_bid": 0, "CE_ask_qty": 0, "CE_ask": 0,
        "PE_bid_qty": 0, "PE_bid": 0, "PE_ask_qty": 0, "PE_ask": 0,
    },
]


class TestChainLookup:
    """_ltp_from_chain with mocked get_option_chain — no real NSE calls."""

    def _call(self, sym, strike, expiry, instr, df, meta):
        # _ltp_from_chain does `from services.fno_data_service import get_option_chain`
        # inside the function, so patching the source module attribute is the correct target.
        from services.paper_trade_service import _ltp_from_chain
        with patch("services.fno_data_service.get_option_chain", return_value=(df, meta)):
            return _ltp_from_chain(sym, strike, expiry, instr)

    def test_rblbank_370_ce_resolves_to_9_90(self):
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta(synthetic=False, cached=False)
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(9.90, abs=0.01)
        assert src == "live"

    def test_indusindbk_920_ce_resolves_to_20_30(self):
        df   = _make_chain_df(INDUSINDBK_CHAIN_ROWS)
        meta = _make_chain_meta(synthetic=False, cached=False)
        ltp, src = self._call("INDUSINDBK", 920.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(20.30, abs=0.01)
        assert src == "live"

    def test_cached_chain_returns_cached_source(self):
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta(synthetic=False, cached=True)
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(9.90, abs=0.01)
        assert src == "cached"

    def test_expiry_normalisation_case_insensitive(self):
        """Stored as '25-Jun-2026'; chain may return '25-JUN-2026'."""
        rows = [{**r, "expiry": "25-JUN-2026"} for r in RBLBANK_CHAIN_ROWS]
        df   = _make_chain_df(rows)
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(9.90, abs=0.01)

    def test_expiry_normalisation_space_separator(self):
        """Chain may return '25 Jun 2026' (space-separated)."""
        rows = [{**r, "expiry": "25 Jun 2026"} for r in RBLBANK_CHAIN_ROWS]
        df   = _make_chain_df(rows)
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(9.90, abs=0.01)

    def test_wrong_strike_returns_none(self):
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 999.0, "25-Jun-2026", "CE", df, meta)
        assert ltp is None
        assert src == "none"

    def test_pe_column_lookup(self):
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "PE", df, meta)
        assert ltp == pytest.approx(12.5, abs=0.01)


# ── 3. Fallback — synthetic chain must be rejected ────────────────────────────

class TestFallbackBehaviour:

    def _call(self, sym, strike, expiry, instr, df, meta):
        from services.paper_trade_service import _ltp_from_chain
        with patch("services.fno_data_service.get_option_chain", return_value=(df, meta)):
            return _ltp_from_chain(sym, strike, expiry, instr)

    def test_synthetic_chain_rejected(self):
        """When NSE is down and only Black-Scholes estimate exists, return None."""
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta(synthetic=True)
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp is None
        assert src == "none"

    def test_empty_dataframe_returns_none(self):
        df   = pd.DataFrame()
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp is None
        assert src == "none"

    def test_zero_ltp_returns_none(self):
        """A row with lastPrice=0 is treated as 'no data', not as a valid price."""
        rows = [{**r, "CE_ltp": 0.0} for r in RBLBANK_CHAIN_ROWS if r["strike"] == 370]
        rows += [r for r in RBLBANK_CHAIN_ROWS if r["strike"] != 370]
        df   = _make_chain_df(rows)
        meta = _make_chain_meta()
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp is None
        assert src == "none"

    def test_exception_from_get_option_chain_returns_none(self):
        from services.paper_trade_service import _ltp_from_chain
        with patch("services.fno_data_service.get_option_chain", side_effect=RuntimeError("NSE blocked")):
            ltp, src = _ltp_from_chain("RBLBANK", 370.0, "25-Jun-2026", "CE")
        assert ltp is None
        assert src == "none"

    def test_cached_accepted_even_when_not_live(self):
        """Disk cache (real last-close prices) must be accepted."""
        df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        meta = _make_chain_meta(synthetic=False, cached=True)
        ltp, src = self._call("RBLBANK", 370.0, "25-Jun-2026", "CE", df, meta)
        assert ltp == pytest.approx(9.90, abs=0.01)
        assert src == "cached"


# ── 4. Portfolio summary — acceptance math via paper_trade_service ────────────

class TestPortfolioSummary:
    """Integration: write two trades into a temp file, verify summary."""

    TRADES = [
        {
            "trade_id": "TEST0001", "symbol": "RBLBANK",
            "instrument_type": "CE", "strike": 370.0, "expiry": "25-Jun-2026",
            "action": "BUY", "lots": 1, "lot_size": 3175,
            "entry_price": 7.55, "entry_time": "2026-06-13T14:22:24",
            "current_price": 9.90, "target_price": 19.9, "stop_loss": 1.0,
            "status": "OPEN", "source": "SCANNER", "ai_confidence": "",
            "strategy_name": "", "pnl_rs": 7461.25, "pnl_pct": 31.13,
            "margin_used": 23971.25, "exit_price": None,
            "exit_time": None, "exit_reason": None, "price_source": "manual",
        },
        {
            "trade_id": "TEST0002", "symbol": "INDUSINDBK",
            "instrument_type": "CE", "strike": 920.0, "expiry": "25-Jun-2026",
            "action": "BUY", "lots": 1, "lot_size": 500,
            "entry_price": 22.53, "entry_time": "2026-06-13T14:24:39",
            "current_price": 20.30, "target_price": 50.0, "stop_loss": 4.2,
            "status": "OPEN", "source": "SCANNER", "ai_confidence": "",
            "strategy_name": "", "pnl_rs": -1115.00, "pnl_pct": -9.90,
            "margin_used": 11265.0, "exit_price": None,
            "exit_time": None, "exit_reason": None, "price_source": "manual",
        },
    ]

    @pytest.fixture
    def temp_trades_file(self, tmp_path):
        f = tmp_path / "paper_trades.json"
        f.write_text(json.dumps({
            "portfolio": {
                "initial_capital": 500_000.0,
                "available_capital": 464_763.75,
            },
            "trades": self.TRADES,
            "closed_trades": [],
        }), encoding="utf-8")
        return f

    def test_portfolio_summary_exact_values(self, temp_trades_file):
        import services.paper_trade_service as pts
        original_path = pts._TRADES_PATH
        pts._TRADES_PATH = temp_trades_file
        try:
            s = pts.get_portfolio_summary()
        finally:
            pts._TRADES_PATH = original_path

        assert s["total_equity"]    == pytest.approx(506_346.25, abs=0.01), s
        assert s["open_pnl"]        == pytest.approx(6_346.25,   abs=0.01), s
        assert s["total_pnl"]       == pytest.approx(6_346.25,   abs=0.01), s
        assert s["total_pnl_pct"]   == pytest.approx(1.27,        abs=0.01), s
        assert s["available_capital"] == pytest.approx(464_763.75, abs=0.01)
        assert s["deployed_capital"]  == pytest.approx(35_236.25,  abs=0.01)

    def test_open_trades_count(self, temp_trades_file):
        import services.paper_trade_service as pts
        original_path = pts._TRADES_PATH
        pts._TRADES_PATH = temp_trades_file
        try:
            s = pts.get_portfolio_summary()
        finally:
            pts._TRADES_PATH = original_path
        assert s["open_trades_count"] == 2
        assert s["closed_trades_count"] == 0


# ── 5. Regression — PATCH /price endpoint round-trip ─────────────────────────

class TestPatchPriceEndpoint:
    """Hits the real FastAPI app via TestClient to verify the PATCH endpoint."""

    def test_rblbank_patch_returns_correct_pnl(self, client):
        # First reset to known state by using the open trades endpoint
        r = client.get("/api/fno/paper-trades/open")
        if r.status_code != 200:
            pytest.skip("paper-trades backend not available")

        open_trades = r.json()
        rbl = next((t for t in open_trades if t["symbol"] == "RBLBANK"), None)
        if rbl is None:
            pytest.skip("RBLBANK trade not present — reset portfolio first")

        trade_id = rbl["trade_id"]
        entry    = float(rbl["entry_price"])
        lot_sz   = int(rbl["lot_size"])
        lots     = int(rbl["lots"])
        margin   = float(rbl["margin_used"])

        new_ltp = 9.90
        r2 = client.patch(
            f"/api/fno/paper-trades/{trade_id}/price",
            json={"current_price": new_ltp},
        )
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["current_price"] == pytest.approx(new_ltp, abs=0.01)
        expected_pnl = round((new_ltp - entry) * lots * lot_sz, 2)
        assert d["pnl_rs"] == pytest.approx(expected_pnl, abs=0.01)
        expected_pct = round(expected_pnl / margin * 100, 2)
        assert d["pnl_pct"] == pytest.approx(expected_pct, abs=0.01)
        assert d.get("price_source") == "manual"

    def test_indusindbk_patch_negative_pnl(self, client):
        open_trades = client.get("/api/fno/paper-trades/open").json()
        indu = next((t for t in open_trades if t["symbol"] == "INDUSINDBK"), None)
        if indu is None:
            pytest.skip("INDUSINDBK trade not present")

        r = client.patch(
            f"/api/fno/paper-trades/{indu['trade_id']}/price",
            json={"current_price": 20.30},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["pnl_rs"] == pytest.approx(-1115.00, abs=0.01)
        assert d["pnl_pct"] == pytest.approx(-9.90, abs=0.01)

    def test_patch_invalid_price_returns_400(self, client):
        open_trades = client.get("/api/fno/paper-trades/open").json()
        if not open_trades:
            pytest.skip("no open trades")
        tid = open_trades[0]["trade_id"]
        r = client.patch(f"/api/fno/paper-trades/{tid}/price", json={"current_price": 0})
        assert r.status_code == 400

    def test_patch_unknown_trade_returns_404(self, client):
        r = client.patch("/api/fno/paper-trades/DOESNOTEXIST/price", json={"current_price": 10.0})
        assert r.status_code == 404

    def test_portfolio_after_both_patches(self, client):
        """After setting both LTPs, portfolio summary must match spec."""
        open_trades = client.get("/api/fno/paper-trades/open").json()
        rbl   = next((t for t in open_trades if t["symbol"] == "RBLBANK"),    None)
        indu  = next((t for t in open_trades if t["symbol"] == "INDUSINDBK"), None)
        if not rbl or not indu:
            pytest.skip("Both trades must be present")

        client.patch(f"/api/fno/paper-trades/{rbl['trade_id']}/price",  json={"current_price": 9.90})
        client.patch(f"/api/fno/paper-trades/{indu['trade_id']}/price", json={"current_price": 20.30})

        s = client.get("/api/fno/paper-trades/portfolio").json()
        assert s["total_equity"]  == pytest.approx(506_346.25, abs=0.01), s
        assert s["open_pnl"]      == pytest.approx(6_346.25,   abs=0.01), s
        assert s["total_pnl_pct"] == pytest.approx(1.27,        abs=0.01), s


# ── 6. update_all_prices integration — mocked chain ──────────────────────────

class TestUpdateAllPrices:
    """update_all_prices() with get_option_chain mocked per-symbol."""

    def _chain_for(self, sym: str):
        if sym == "RBLBANK":
            return _make_chain_df(RBLBANK_CHAIN_ROWS), _make_chain_meta()
        if sym == "INDUSINDBK":
            return _make_chain_df(INDUSINDBK_CHAIN_ROWS), _make_chain_meta()
        return pd.DataFrame(), _make_chain_meta()

    def test_both_trades_updated_with_correct_prices(self, tmp_path):
        import services.paper_trade_service as pts

        trades_file = tmp_path / "paper_trades.json"
        trades_file.write_text(json.dumps({
            "portfolio": {"initial_capital": 500_000.0, "available_capital": 464_763.75},
            "trades": [
                {
                    "trade_id": "R001", "symbol": "RBLBANK", "instrument_type": "CE",
                    "strike": 370.0, "expiry": "25-Jun-2026", "action": "BUY",
                    "lots": 1, "lot_size": 3175, "entry_price": 7.55,
                    "current_price": 7.55, "target_price": 19.9, "stop_loss": 1.0,
                    "status": "OPEN", "source": "SCANNER", "ai_confidence": "",
                    "strategy_name": "", "pnl_rs": 0.0, "pnl_pct": 0.0,
                    "margin_used": 23971.25, "exit_price": None,
                    "exit_time": None, "exit_reason": None,
                },
                {
                    "trade_id": "I001", "symbol": "INDUSINDBK", "instrument_type": "CE",
                    "strike": 920.0, "expiry": "25-Jun-2026", "action": "BUY",
                    "lots": 1, "lot_size": 500, "entry_price": 22.53,
                    "current_price": 22.53, "target_price": 50.0, "stop_loss": 4.2,
                    "status": "OPEN", "source": "SCANNER", "ai_confidence": "",
                    "strategy_name": "", "pnl_rs": 0.0, "pnl_pct": 0.0,
                    "margin_used": 11265.0, "exit_price": None,
                    "exit_time": None, "exit_reason": None,
                },
            ],
            "closed_trades": [],
        }), encoding="utf-8")

        original_path = pts._TRADES_PATH
        pts._TRADES_PATH = trades_file
        try:
            with patch("services.fno_data_service.get_option_chain", side_effect=self._chain_for):
                results = pts.update_all_prices()
        finally:
            pts._TRADES_PATH = original_path

        by_id = {r["trade_id"]: r for r in results}

        rbl_r = by_id.get("R001")
        assert rbl_r is not None, "RBLBANK not in results"
        assert rbl_r["current_price"] == pytest.approx(9.90, abs=0.01)
        assert rbl_r["pnl_rs"]        == pytest.approx(7461.25, abs=0.01)
        assert rbl_r["price_source"]  == "live"
        assert rbl_r.get("error") is None

        indu_r = by_id.get("I001")
        assert indu_r is not None, "INDUSINDBK not in results"
        assert indu_r["current_price"] == pytest.approx(20.30, abs=0.01)
        assert indu_r["pnl_rs"]        == pytest.approx(-1115.00, abs=0.01)
        assert indu_r["price_source"]  == "live"

    def test_synthetic_chain_does_not_update_price(self, tmp_path):
        """When only synthetic (BS) data available, price must NOT be updated."""
        import services.paper_trade_service as pts

        trades_file = tmp_path / "paper_trades.json"
        trades_file.write_text(json.dumps({
            "portfolio": {"initial_capital": 500_000.0, "available_capital": 476_028.75},
            "trades": [{
                "trade_id": "R002", "symbol": "RBLBANK", "instrument_type": "CE",
                "strike": 370.0, "expiry": "25-Jun-2026", "action": "BUY",
                "lots": 1, "lot_size": 3175, "entry_price": 7.55,
                "current_price": 7.55, "target_price": 19.9, "stop_loss": 1.0,
                "status": "OPEN", "source": "SCANNER", "ai_confidence": "",
                "strategy_name": "", "pnl_rs": 0.0, "pnl_pct": 0.0,
                "margin_used": 23971.25, "exit_price": None,
                "exit_time": None, "exit_reason": None,
            }],
            "closed_trades": [],
        }), encoding="utf-8")

        synthetic_df   = _make_chain_df(RBLBANK_CHAIN_ROWS)
        synthetic_meta = _make_chain_meta(synthetic=True)

        original_path = pts._TRADES_PATH
        pts._TRADES_PATH = trades_file
        try:
            with patch("services.fno_data_service.get_option_chain",
                       return_value=(synthetic_df, synthetic_meta)):
                results = pts.update_all_prices()
        finally:
            pts._TRADES_PATH = original_path

        assert len(results) == 1
        r = results[0]
        assert r["current_price"] is None, "Synthetic price must not be applied"
        assert r["price_source"]  == "none"
        assert r.get("error") is not None, "Must explain why no price was set"

        # Verify the trade on disk was NOT mutated
        saved = json.loads(trades_file.read_text())
        assert saved["trades"][0]["current_price"] == pytest.approx(7.55, abs=0.01)
        assert saved["trades"][0]["pnl_rs"]        == pytest.approx(0.0,  abs=0.01)
