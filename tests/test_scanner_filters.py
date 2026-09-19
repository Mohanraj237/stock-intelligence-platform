"""
Pattern identity, hard pattern filtering, and loud input validation.

Covers Group 1:
  1.1 pattern_names no longer shapes the score; it is a hard post-filter
  1.2 patterns are matched by identity, and GET /patterns is complete
  1.3 bad inputs return HTTP 400 instead of silently scanning something else
  1.4 the scan summary reports what was skipped
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.confluence_scorer import add_indicators, score
from services.pattern_registry import (
    CATALOG_BY_ID,
    PATTERN_CATALOG,
    REGISTRY,
    UnknownPatternError,
    pattern_slug,
    patterns_grouped_by_family,
    resolve_pattern_selection,
)
from services.scan_support import (
    ScanDiagnostics,
    ScanInputError,
    apply_pattern_filters,
    parse_pattern_mode,
    parse_pattern_names,
    parse_timeframes,
    resolve_universe,
)

REGISTRY_SRC = Path(__file__).resolve().parent.parent / "services" / "pattern_registry.py"
EQUITY_TFS = ["1d", "1wk", "1mo"]
FNO_TFS    = ["5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]


def _frame(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open":   closes * 0.999,
        "high":   closes * 1.01,
        "low":    closes * 0.99,
        "close":  closes,
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="D"))


def _uptrend(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return _frame(np.linspace(90, 130, n) + rng.normal(0, 0.4, n))


# ─────────────────────────────────────────────────────────────────────────────
# 1.2 — Identity and catalog completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternCatalog:
    def test_catalog_covers_every_name_a_detector_can_emit(self):
        """
        Acceptance: GET /patterns must list the complete emitted set. Six
        directional variants and three legacy-only names used to be missing.
        """
        src = REGISTRY_SRC.read_text(encoding="utf-8")
        emitted = set(re.findall(r'PatternResult\(\s*"([^"]+)"', src))
        legacy = {"Hammer / Pin Bar", "Bullish Marubozu", "Bearish Marubozu"}
        catalog_names = {c.name for c in PATTERN_CATALOG}
        assert emitted <= catalog_names, f"missing from catalog: {emitted - catalog_names}"
        assert legacy <= catalog_names
        assert catalog_names == emitted | legacy

    def test_grouped_endpoint_count_equals_catalog_count(self):
        groups = patterns_grouped_by_family()
        total = sum(len(v) for v in groups.values())
        total += sum(len(p["variants"]) for v in groups.values() for p in v)
        assert total == len(PATTERN_CATALOG)

    def test_previously_unselectable_names_are_now_present(self):
        for name in ("Inside Bar Breakout", "Inside Bar Breakdown", "Breakdown Retest",
                     "Rectangle Breakdown", "Channel Breakdown", "Trendline Breakdown",
                     "Hammer / Pin Bar", "Bullish Marubozu", "Bearish Marubozu"):
            assert pattern_slug(name) in CATALOG_BY_ID, name

    def test_variants_are_nested_under_their_parent(self):
        groups = patterns_grouped_by_family()
        flat = {p["name"]: p for v in groups.values() for p in v}
        assert {v["name"] for v in flat["Inside Bar"]["variants"]} == {
            "Inside Bar Breakdown", "Inside Bar Breakout"}
        assert {v["name"] for v in flat["Trendline Breakout"]["variants"]} == {
            "Trendline Breakdown"}

    def test_registry_entry_ids_are_unique(self):
        ids = [e.pattern_id for e in REGISTRY]
        assert len(ids) == len(set(ids))


class TestPatternSelection:
    def test_selecting_a_parent_selects_its_variants(self):
        """Acceptance: selecting 'Inside Bar' must not discard breakout hits."""
        assert resolve_pattern_selection("Inside Bar") == {
            "inside_bar", "inside_bar_breakout", "inside_bar_breakdown"}

    def test_matching_is_case_insensitive_and_accepts_ids(self):
        by_name = resolve_pattern_selection("BULLISH ENGULFING")
        by_id   = resolve_pattern_selection("bullish_engulfing")
        assert by_name == by_id == {"bullish_engulfing"}

    def test_selecting_a_variant_selects_only_that_variant(self):
        assert resolve_pattern_selection("Inside Bar Breakout") == {"inside_bar_breakout"}

    def test_legacy_only_name_resolves_through_its_parent(self):
        assert resolve_pattern_selection("Hammer") == {"hammer", "hammer_pin_bar"}

    def test_empty_selection_means_no_filter(self):
        assert resolve_pattern_selection("") is None
        assert resolve_pattern_selection(None) is None
        assert resolve_pattern_selection("  ,  ") is None

    def test_unknown_name_raises_instead_of_returning_nothing(self):
        with pytest.raises(UnknownPatternError) as exc:
            resolve_pattern_selection("Bullish Engulfing,Not A Pattern")
        assert "Not A Pattern" in str(exc.value)

    def test_router_layer_converts_it_to_a_400(self):
        with pytest.raises(ScanInputError) as exc:
            parse_pattern_names("Nope")
        assert exc.value.field == "pattern_names"


# ─────────────────────────────────────────────────────────────────────────────
# 1.1 — Filtering does not shape the score
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternModeScoreComparability:
    def _score(self, ids, mode):
        df = add_indicators(_uptrend(220), timeframe="1d")
        return score("TEST", df, timeframe="1d",
                     enabled_pattern_ids=ids, pattern_mode=mode)

    def test_filter_mode_scores_identically_to_an_unfiltered_scan(self):
        """
        Acceptance: a card's confluence_score with a pattern filter must equal
        the score the same symbol/TF receives with no filter.
        """
        unfiltered = self._score(None, "filter")
        filtered   = self._score({"bullish_engulfing"}, "filter")
        assert filtered.total == unfiltered.total
        assert filtered.candle_score == unfiltered.candle_score
        assert filtered.structural_score == unfiltered.structural_score
        assert [p["name"] for p in filtered.patterns] == [p["name"] for p in unfiltered.patterns]

    def test_shape_mode_still_lowers_the_score(self):
        unfiltered = self._score(None, "filter")
        shaped     = self._score({"bullish_engulfing"}, "shape")
        assert shaped.total <= unfiltered.total

    def test_shape_mode_strips_non_selected_patterns(self):
        shaped = self._score({"bullish_engulfing"}, "shape")
        assert all(p["pattern_id"] == "bullish_engulfing" for p in shaped.patterns)

    def test_legacy_fallback_runs_under_filter_mode(self):
        """
        The legacy detector was disabled whenever a filter was set, because it
        ignored the filter. Under "filter" mode the selection is applied after
        scoring, so the fallback is safe again.
        """
        # A frame where the registry finds nothing but a legacy hammer exists.
        closes = np.full(80, 100.0)
        df = _frame(closes)
        i = df.index[-1]
        df.loc[i, ["open", "close", "high", "low"]] = [99.8, 100.0, 100.1, 95.0]
        scored = score("LEG", add_indicators(df, timeframe="1d"), timeframe="1d",
                       enabled_pattern_ids={"hammer"}, pattern_mode="filter")
        assert scored is not None
        assert scored.pattern.name != "None"


class TestHardPostFilter:
    def _card(self, primary: str, pattern_rows: list[dict]) -> dict:
        return {"symbol": "X", "pattern": primary, "patterns": pattern_rows}

    def _row(self, name: str, conf: float = 0.8, family: str = "price_action") -> dict:
        pid = pattern_slug(name)
        entry = CATALOG_BY_ID.get(pid)
        return {
            "name": name, "pattern_id": pid,
            "parent_id": entry.parent_id if entry else pid,
            "family": family, "confidence": conf,
        }

    def test_cards_without_a_selected_pattern_are_dropped(self):
        cards = [
            self._card("Bull Flag", [self._row("Bull Flag", family="chart")]),
            self._card("Bullish Engulfing", [self._row("Bullish Engulfing", family="candlestick")]),
        ]
        out = apply_pattern_filters(cards, None, 0.0, {"bullish_engulfing"})
        assert [c["pattern"] for c in out] == ["Bullish Engulfing"]

    def test_selecting_a_parent_keeps_variant_hits(self):
        cards = [self._card("NR7", [self._row("NR7"), self._row("Inside Bar Breakout")])]
        out = apply_pattern_filters(cards, None, 0.0, resolve_pattern_selection("Inside Bar"))
        assert len(out) == 1
        # displayed pattern is rewritten to the matched one
        assert out[0]["pattern"] == "Inside Bar Breakout"

    def test_legacy_primary_pattern_alone_can_carry_a_card(self):
        card = self._card("Hammer / Pin Bar", [])
        out = apply_pattern_filters([card], None, 0.0, resolve_pattern_selection("Hammer"))
        assert len(out) == 1

    def test_no_filter_returns_everything(self):
        cards = [self._card("Bull Flag", [self._row("Bull Flag", family="chart")])]
        assert apply_pattern_filters(cards, None, 0.0, None) == cards

    def test_family_filter_still_works(self):
        cards = [
            self._card("Bull Flag", [self._row("Bull Flag", family="chart")]),
            self._card("NR7", [self._row("NR7", family="price_action")]),
        ]
        out = apply_pattern_filters(cards, "chart", 0.0, None)
        assert [c["pattern"] for c in out] == ["Bull Flag"]

    def test_confidence_floor_still_works(self):
        cards = [self._card("NR7", [self._row("NR7", conf=0.4)])]
        assert apply_pattern_filters(cards, None, 0.6, None) == []


# ─────────────────────────────────────────────────────────────────────────────
# 1.3 — No silent fallbacks
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_absent_timeframes_means_all(self):
        assert parse_timeframes(None, EQUITY_TFS) is None

    def test_empty_timeframes_is_an_error_not_all(self):
        """Deselecting every timeframe used to scan all of them."""
        with pytest.raises(ScanInputError) as exc:
            parse_timeframes("", EQUITY_TFS)
        assert "at least one timeframe" in str(exc.value)
        with pytest.raises(ScanInputError):
            parse_timeframes("  , ", FNO_TFS)

    def test_unknown_timeframe_is_named_not_dropped(self):
        with pytest.raises(ScanInputError) as exc:
            parse_timeframes("1d,3h", EQUITY_TFS)
        assert "3h" in str(exc.value)

    def test_valid_timeframes_are_deduped_and_canonically_ordered(self):
        assert parse_timeframes("1mo,1d,1d", EQUITY_TFS) == ["1d", "1mo"]

    def test_unknown_universe_names_the_key(self):
        with pytest.raises(ScanInputError) as exc:
            resolve_universe("top30", {"indices", "stocks", "dynamic"})
        assert "top30" in str(exc.value)
        assert exc.value.field == "universe"

    def test_unknown_pattern_mode_is_rejected(self):
        assert parse_pattern_mode("") == "filter"
        assert parse_pattern_mode("SHAPE") == "shape"
        with pytest.raises(ScanInputError):
            parse_pattern_mode("strict")


# ─────────────────────────────────────────────────────────────────────────────
# 1.4 — Skipped-symbol reporting
# ─────────────────────────────────────────────────────────────────────────────

class TestScanDiagnostics:
    def test_counts_each_outcome(self):
        d = ScanDiagnostics()
        d.record("A", "ok")
        d.record("B", "no_data", "no data returned")
        d.record("C", "insufficient_bars", "only 12 bars")
        out = d.as_dict()
        assert out["scanned"] == 3
        assert out["skipped_no_data"] == 1
        assert out["skipped_insufficient_bars"] == 1
        assert {e["symbol"] for e in out["errors"]} == {"B", "C"}

    def test_error_list_is_capped_and_reports_the_overflow(self):
        d = ScanDiagnostics()
        for i in range(70):
            d.record(f"S{i}", "no_data", "boom")
        out = d.as_dict()
        assert len(out["errors"]) == 50
        assert out["errors_truncated"] == 20
        assert out["skipped_no_data"] == 70


# ─────────────────────────────────────────────────────────────────────────────
# Router-level integration
# ─────────────────────────────────────────────────────────────────────────────

class TestScannerEndpoints:
    def test_equity_patterns_endpoint_is_complete(self, client):
        r = client.get("/api/equity-scanner/patterns")
        assert r.status_code == 200
        data = r.json()
        total = sum(len(v) for v in data.values())
        total += sum(len(p["variants"]) for v in data.values() for p in v)
        assert total == len(PATTERN_CATALOG)

    def test_fno_patterns_endpoint_matches_equity(self, client):
        assert (client.get("/api/live-scanner/patterns").json()
                == client.get("/api/equity-scanner/patterns").json())

    def test_pattern_rows_carry_stable_ids(self, client):
        data = client.get("/api/equity-scanner/patterns").json()
        for fam in data.values():
            for p in fam:
                assert p["pattern_id"] in CATALOG_BY_ID
                for v in p["variants"]:
                    assert CATALOG_BY_ID[v["pattern_id"]].parent_id == p["pattern_id"]

    @pytest.mark.parametrize("qs,field", [
        ("universe=not_a_universe", "universe"),
        ("universe=india_nifty50&timeframes=", "timeframes"),
        ("universe=india_nifty50&timeframes=4h", "timeframes"),
        ("universe=india_nifty50&pattern_names=Nope", "pattern_names"),
        ("universe=india_nifty50&pattern_mode=strict", "pattern_mode"),
    ])
    def test_equity_scan_rejects_bad_input(self, client, qs, field):
        r = client.get(f"/api/equity-scanner/scan/stream?{qs}")
        assert r.status_code == 400
        assert r.json()["field"] == field

    @pytest.mark.parametrize("qs,field", [
        ("universe=top30", "universe"),
        ("universe=indices&timeframes=", "timeframes"),
        ("universe=indices&timeframes=2h", "timeframes"),
        ("universe=indices&pattern_names=Nope", "pattern_names"),
    ])
    def test_fno_scan_rejects_bad_input(self, client, qs, field):
        r = client.get(f"/api/live-scanner/scan?{qs}")
        assert r.status_code == 400
        assert r.json()["field"] == field

    def test_fno_default_universe_is_stocks(self):
        """`top30` was the default and was never registered — it fell back to indices."""
        from backend.routers.live_scanner import DEFAULT_FNO_UNIVERSE, FNO_UNIVERSE_KEYS
        assert DEFAULT_FNO_UNIVERSE == "stocks"
        assert "top30" not in FNO_UNIVERSE_KEYS

    def test_unknown_equity_universe_count_is_400(self, client):
        r = client.get("/api/equity-scanner/universe-count/nope")
        assert r.status_code == 400
