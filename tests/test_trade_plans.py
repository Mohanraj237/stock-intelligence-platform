"""
Trade-plan integrity (Group 3).

  3.2 range setups get an option plan when IV rank supports one, and a stated
      reason when they do not — never a silently failed gate
  3.3 no R:R gate that cannot fire; `rr` is labelled for what it is
  3.4 lot sizes come from one table, estimates are flagged, the delta
      approximation is declared
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.confluence_scorer import ConfluenceResult
from services.equity_advisor import RR_BASIS_FIXED, build_equity_plan
from services.lot_sizes import DEFAULT_LOT_SIZE, INDEX_SYMBOLS, LOT_SIZES, lot_size_for
import services.option_advisor as option_advisor
from services.option_advisor import (
    RR_BASIS_FIXED as OPT_RR_BASIS_FIXED,
    RR_BASIS_PREMIUM,
    build_plan,
    build_plan_with_reason,
)

ROOT = Path(__file__).resolve().parent.parent
GENERATED_TS = ROOT / "frontend" / "lib" / "lot-sizes.generated.ts"


def _result(direction: str = "bullish", symbol: str = "RELIANCE",
            spot: float = 1400.0, total: int = 78) -> ConfluenceResult:
    return ConfluenceResult(
        symbol=symbol, direction=direction, total=total,
        trend_score=24, momentum_score=25, volume_score=11,
        candle_score=16, structural_score=5,
        spot_price=spot, atr=20.0, rel_vol=1.8,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3.2 — IV rank drives the range path
# ─────────────────────────────────────────────────────────────────────────────

class TestRangeSetupPlans:
    def test_range_setup_gets_a_plan_when_iv_rank_is_rich(self):
        """
        The router never passed iv_rank and the default was hardcoded to 30,
        below the range path's floor of 40 — so this branch was unreachable.
        """
        plan, reason = build_plan_with_reason(_result("range"), iv_rank=65.0)
        assert plan is not None, reason
        assert plan.action == "SELL"
        assert plan.iv_rank == 65.0

    def test_low_iv_rank_declines_with_a_reason(self):
        plan, reason = build_plan_with_reason(_result("range"), iv_rank=20.0)
        assert plan is None
        assert "20" in reason and "below 40" in reason

    def test_missing_iv_rank_declines_with_a_reason(self):
        plan, reason = build_plan_with_reason(_result("range"), iv_rank=None)
        assert plan is None
        assert "IV history" in reason

    def test_directional_plan_is_unaffected_by_a_missing_iv_rank(self):
        plan, reason = build_plan_with_reason(_result("bullish"), iv_rank=None)
        assert plan is not None and reason == ""
        assert plan.iv_rank is None
        assert "IV rank unavailable" in plan.iv_note

    def test_iv_note_warnings_can_now_fire(self):
        """They needed iv_rank > 50, which the hardcoded 30 never reached."""
        high = build_plan(_result("bullish"), iv_rank=80.0)
        assert "expensive" in high.iv_note

        moderate = build_plan(_result("bullish", total=70), iv_rank=60.0)
        assert "Moderate IV rank" in moderate.iv_note

    def test_router_maps_insufficient_history_to_none(self, monkeypatch):
        import backend.routers.live_scanner as ls
        monkeypatch.setattr(
            "services.fno_data_service.get_iv_rank",
            lambda sym: {"sufficient_history": False, "iv_rank": None},
        )
        assert ls._iv_rank_for("NIFTY") is None

        monkeypatch.setattr(
            "services.fno_data_service.get_iv_rank",
            lambda sym: {"sufficient_history": True, "iv_rank": 61.5},
        )
        assert ls._iv_rank_for("NIFTY") == 61.5


# ─────────────────────────────────────────────────────────────────────────────
# 3.3 — R:R is labelled, not faked
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskReward:
    def test_directional_option_rr_is_declared_fixed(self):
        plan = build_plan(_result("bullish"))
        assert plan.rr == 1.5
        assert plan.rr_basis == OPT_RR_BASIS_FIXED
        assert "fixed" in plan.rr_basis

    def test_equity_rr_is_declared_fixed(self):
        plan = build_equity_plan(_result("bullish"))
        assert plan.rr == 1.5
        assert plan.rr_basis == RR_BASIS_FIXED

    def test_no_directional_setup_is_ever_rejected_by_the_dead_rr_gate(self):
        """A gate that cannot fire is worse than no gate — it reads as a check."""
        for direction in ("bullish", "bearish"):
            for spot in (50.0, 500.0, 25_000.0):
                assert build_plan(_result(direction, spot=spot)) is not None
                assert build_equity_plan(_result(direction, spot=spot)) is not None

    def test_no_rr_floor_survives_anywhere(self):
        """
        Both plans have an rr that is fixed by construction, so no floor can
        ever fire. The premium-sell floor was a *second*, independent reason the
        range path never produced a plan, on top of the iv_rank default.
        """
        assert not hasattr(option_advisor, "_RR_FLOOR")

    def test_premium_sell_rr_is_constant_and_labelled(self):
        """(1 − 0.5) / (2.5 − 1) = 0.33 — the premium cancels out entirely."""
        for spot in (50.0, 1_400.0, 25_000.0):
            plan = build_plan(_result("range", spot=spot), iv_rank=65.0)
            assert plan is not None
            assert plan.rr == pytest.approx(0.33, abs=0.01)
            assert plan.rr_basis == RR_BASIS_PREMIUM
            assert "credit strategy" in plan.rr_basis

    def test_risk_model_is_unchanged(self):
        r = _result("bullish", spot=1000.0)
        r.atr = 20.0
        plan = build_equity_plan(r)
        assert plan.risk_per_share == pytest.approx(max(20.0 * 1.5, 1000.0 * 0.003))


# ─────────────────────────────────────────────────────────────────────────────
# 3.4 — Option plan data integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestOptionPlanIntegrity:
    def test_known_symbol_lot_size_is_not_flagged(self):
        plan = build_plan(_result("bullish", symbol="RELIANCE"))
        assert plan.lot_size == LOT_SIZES["RELIANCE"]
        assert plan.lot_size_estimated is False

    def test_unknown_symbol_lot_size_is_flagged_not_silent(self):
        plan = build_plan(_result("bullish", symbol="NOTALISTEDSYMBOL"))
        assert plan.lot_size == DEFAULT_LOT_SIZE
        assert plan.lot_size_estimated is True
        assert "estimated" in plan.iv_note

    def test_delta_assumption_is_declared_on_the_plan(self):
        plan = build_plan(_result("bullish"))
        assert plan.delta_assumption == 0.5
        # premium targets follow directly from that assumption
        expected_t1 = round(plan.entry_premium + 0.5 * 1.5 * plan.raw_risk_pts, 1)
        assert plan.t1_premium == pytest.approx(expected_t1)

    def test_lot_size_helper_reports_estimation(self):
        assert lot_size_for("NIFTY") == (LOT_SIZES["NIFTY"], False)
        assert lot_size_for("nifty") == (LOT_SIZES["NIFTY"], False)
        assert lot_size_for("ZZZZ")  == (DEFAULT_LOT_SIZE, True)


# ─────────────────────────────────────────────────────────────────────────────
# 3.4 — Python ↔ TypeScript lot-size parity (CI guard)
# ─────────────────────────────────────────────────────────────────────────────

class TestLotSizeParity:
    def _parse_ts(self) -> dict[str, int]:
        src = GENERATED_TS.read_text(encoding="utf-8")
        body = re.search(r"LOT_SIZES:\s*Record<string,\s*number>\s*=\s*\{(.*?)\n\};",
                         src, re.S)
        assert body, "could not locate LOT_SIZES in the generated TS file"
        out: dict[str, int] = {}
        for key, val in re.findall(r'\s*"?([A-Za-z0-9&\-]+)"?:\s*(\d+),', body.group(1)):
            out[key] = int(val)
        return out

    def test_generated_file_exists(self):
        assert GENERATED_TS.exists(), "run: python scripts/gen_lot_sizes.py"

    def test_typescript_table_matches_python_exactly(self):
        """
        The two tables used to disagree on LT, MARUTI, POWERGRID, ONGC,
        NESTLEIND, TITAN and ADANIPORTS. A wrong lot size is a wrong position
        size, so this must fail the build rather than drift.
        """
        ts = self._parse_ts()
        assert ts == LOT_SIZES, {
            "only_in_python": {k: v for k, v in LOT_SIZES.items() if ts.get(k) != v},
            "only_in_ts":     {k: v for k, v in ts.items() if LOT_SIZES.get(k) != v},
        }

    def test_generator_output_is_byte_identical_to_the_checked_in_file(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.gen_lot_sizes import render
        assert render() == GENERATED_TS.read_text(encoding="utf-8"), \
            "regenerate with: python scripts/gen_lot_sizes.py"

    def test_default_and_index_symbols_are_exported(self):
        src = GENERATED_TS.read_text(encoding="utf-8")
        assert f"DEFAULT_LOT_SIZE = {DEFAULT_LOT_SIZE}" in src
        for sym in INDEX_SYMBOLS:
            assert f'"{sym}"' in src

    def test_fno_types_no_longer_defines_its_own_table(self):
        src = (ROOT / "frontend" / "lib" / "fno-types.ts").read_text(encoding="utf-8")
        assert "lot-sizes.generated" in src
        assert "NIFTY: 75" not in src, "fno-types.ts must not re-declare lot sizes"
