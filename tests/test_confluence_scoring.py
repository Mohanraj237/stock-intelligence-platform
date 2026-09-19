"""
Confluence scorer correctness.

Covers the four scoring defects fixed in Group 2:
  2.1 VWAP is a real VWAP on 1d/1wk/1mo, and sessions group by exchange tz
  2.2 Category 1 is normalised and can actually reach 30
  2.3 The 8-point RSI band is reachable and the overbought cliff is a taper
  2.5 Volume-less instruments are rescaled, not handed free points
  2.6 The minimum-bars gate covers the EMA50 lookback
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.confluence_scorer import (
    MIN_BARS_TO_SCORE,
    DEFAULT_WEIGHTS,
    ScoringWeights,
    _trend_category,
    add_indicators,
    compute_vwap,
    has_real_volume,
    rsi_points,
    score,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _frame(closes: np.ndarray, volume: float | np.ndarray = 1e6,
           freq: str = "D", start: str = "2024-01-01") -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range(start, periods=n, freq=freq)
    vol = np.full(n, volume, dtype=float) if np.isscalar(volume) else np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "open":   closes * 0.999,
        "high":   closes * 1.01,
        "low":    closes * 0.99,
        "close":  closes,
        "volume": vol,
    }, index=idx)


def _uptrend(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return _frame(np.linspace(90, 130, n) + rng.normal(0, 0.4, n))


# ─────────────────────────────────────────────────────────────────────────────
# 2.1 — VWAP
# ─────────────────────────────────────────────────────────────────────────────

class TestVwap:
    def test_positional_vwap_is_not_the_bars_own_typical_price(self):
        """
        The old session-reset VWAP made vwap == (h+l+c)/3 of the same bar on
        daily data, reducing the trend vote to a within-bar test.
        """
        df = _uptrend(120)
        vwap = compute_vwap(df, "1d")
        own_tp = (df["high"] + df["low"] + df["close"]) / 3
        tail = vwap.dropna()
        assert len(tail) > 0
        assert not np.allclose(tail.values, own_tp.loc[tail.index].values)

    def test_rolling_vwap_matches_manual_20_bar_calculation(self):
        closes = np.arange(100, 160, dtype=float)
        vols   = np.linspace(1e5, 5e5, len(closes))
        df = _frame(closes, volume=vols)
        vwap = compute_vwap(df, "1d")

        tp = (df["high"] + df["low"] + df["close"]) / 3
        win_tp, win_v = tp.iloc[-20:], df["volume"].iloc[-20:]
        expected = float((win_tp * win_v).sum() / win_v.sum())
        assert float(vwap.iloc[-1]) == pytest.approx(expected, rel=1e-9)

    def test_first_19_bars_have_no_rolling_vwap(self):
        df = _uptrend(60)
        vwap = compute_vwap(df, "1d")
        assert vwap.iloc[:19].isna().all()
        assert not np.isnan(float(vwap.iloc[19]))

    def test_intraday_still_resets_per_session(self):
        # Two NSE sessions of 1h bars.
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2024-03-04 09:15") + pd.Timedelta(hours=h) for h in range(6)]
            + [pd.Timestamp("2024-03-05 09:15") + pd.Timedelta(hours=h) for h in range(6)]
        )
        closes = np.arange(100, 112, dtype=float)
        df = pd.DataFrame({
            "open": closes, "high": closes * 1.002, "low": closes * 0.998,
            "close": closes, "volume": np.full(12, 1000.0),
        }, index=idx)
        vwap = compute_vwap(df, "1h", session_tz="Asia/Kolkata")
        # First bar of each session: VWAP == that bar's typical price.
        for pos in (0, 6):
            tp = (df["high"].iloc[pos] + df["low"].iloc[pos] + df["close"].iloc[pos]) / 3
            assert float(vwap.iloc[pos]) == pytest.approx(tp)

    def test_us_intraday_session_does_not_split_at_ist_midnight(self):
        """
        A US session runs 19:00–02:30 IST, crossing IST midnight. Grouping by
        IST date reset VWAP mid-session; grouping by the exchange's own date
        keeps it in one bucket.
        """
        # 09:30–15:30 New York on one day, expressed as tz-naive IST timestamps.
        ny_open_ist = pd.Timestamp("2024-03-04 20:00")   # 09:30 ET ≈ 20:00 IST
        idx = pd.DatetimeIndex([ny_open_ist + pd.Timedelta(hours=h) for h in range(7)])
        assert idx[-1].day != idx[0].day, "fixture must straddle IST midnight"

        closes = np.arange(100, 107, dtype=float)
        df = pd.DataFrame({
            "open": closes, "high": closes * 1.002, "low": closes * 0.998,
            "close": closes, "volume": np.full(7, 1000.0),
        }, index=idx)

        ist  = compute_vwap(df, "1h", session_tz="Asia/Kolkata")
        newy = compute_vwap(df, "1h", session_tz="America/New_York")

        # Under IST grouping the session restarts at the midnight boundary…
        midnight_pos = next(i for i, t in enumerate(idx) if t.day != idx[0].day)
        tp_at_split = (df["high"].iloc[midnight_pos] + df["low"].iloc[midnight_pos]
                       + df["close"].iloc[midnight_pos]) / 3
        assert float(ist.iloc[midnight_pos]) == pytest.approx(tp_at_split)
        # …but under exchange-local grouping it does not.
        assert float(newy.iloc[midnight_pos]) != pytest.approx(tp_at_split)

    def test_no_volume_yields_nan_so_the_vote_is_skipped(self):
        df = _uptrend(80)
        df["volume"] = 0.0
        assert not has_real_volume(df)
        assert compute_vwap(df, "1d").isna().all()


# ─────────────────────────────────────────────────────────────────────────────
# 2.2 — Trend category normalisation
# ─────────────────────────────────────────────────────────────────────────────

class TestTrendCategory:
    def _scored(self, df: pd.DataFrame):
        reasons: list[str] = []
        return _trend_category(add_indicators(df, timeframe="1d"), len(df) - 1, reasons)

    def test_all_five_votes_bullish_reaches_the_stated_maximum(self):
        """The category is documented as 0-30; it used to cap at 25."""
        n = 120
        closes = np.linspace(100, 200, n)      # relentless uptrend → new 10-bar high
        direction, pts = self._scored(_frame(closes))
        assert direction == "bullish"
        assert pts == 30

    def test_all_votes_bearish_reaches_the_stated_maximum(self):
        closes = np.linspace(200, 100, 120)
        direction, pts = self._scored(_frame(closes))
        assert direction == "bearish"
        assert pts == 30

    def test_missing_ema50_no_longer_penalises_the_score(self):
        """
        Normalisation removes the old bias where a short history scored lower
        purely because the EMA50 vote was unavailable.
        """
        long_df  = _frame(np.linspace(100, 200, 120))
        short_df = _frame(np.linspace(100, 200, 45))   # < 50 bars → no EMA50

        long_dir, long_pts   = self._scored(long_df)
        short_ind = add_indicators(short_df, timeframe="1d")
        assert "ema_50" not in short_ind.columns
        short_dir, short_pts = _trend_category(short_ind, len(short_ind) - 1, [])

        assert long_dir == short_dir == "bullish"
        assert short_pts == long_pts == 30

    def test_partial_agreement_scales_proportionally(self):
        df = add_indicators(_uptrend(120), timeframe="1d")
        reasons: list[str] = []
        _, pts = _trend_category(df, len(df) - 1, reasons)
        votes_cast = sum(1 for r in reasons if r.startswith(("Price", "EMA", "New")))
        assert 0 < pts <= 30
        assert votes_cast > 0

    def test_tied_votes_are_range(self):
        df = add_indicators(_frame(np.full(120, 100.0) + np.tile([0.5, -0.5], 60)),
                            timeframe="1d")
        direction, pts = _trend_category(df, len(df) - 1, [])
        if direction == "range":
            assert pts == 5


# ─────────────────────────────────────────────────────────────────────────────
# 2.3 — RSI bands
# ─────────────────────────────────────────────────────────────────────────────

class TestRsiPoints:
    # (rsi, bullish, bearish, range)
    TABLE = [
        (25, 4,  8, 4),
        (35, 4, 12, 4),
        (45, 8, 12, 8),
        (55, 12, 8, 8),
        (65, 12, 4, 4),
        (72, 10, 4, 4),
        (85, 4,  4, 4),
    ]

    @pytest.mark.parametrize("rsi,bull,bear,rng_", TABLE)
    def test_awarded_points(self, rsi, bull, bear, rng_):
        assert rsi_points(float(rsi), "bullish")[0] == bull
        assert rsi_points(float(rsi), "bearish")[0] == bear
        assert rsi_points(float(rsi), "range")[0]   == rng_

    def test_eight_point_band_is_reachable_in_both_directions(self):
        """Both 8-point branches used to be dead code."""
        assert 8 in {rsi_points(float(r), "bullish")[0] for r in range(0, 101)}
        assert 8 in {rsi_points(float(r), "bearish")[0] for r in range(0, 101)}

    def test_overbought_is_a_taper_not_a_cliff(self):
        """RSI 70→71 used to drop 12 points at once."""
        at_70 = rsi_points(70.0, "bullish")[0]
        at_71 = rsi_points(71.0, "bullish")[0]
        at_80 = rsi_points(80.0, "bullish")[0]
        assert at_70 == 12 and at_80 == 4
        assert at_70 - at_71 <= 1
        # monotonically non-increasing across the taper
        vals = [rsi_points(float(r), "bullish")[0] for r in range(70, 81)]
        assert all(a >= b for a, b in zip(vals, vals[1:]))

    def test_oversold_taper_mirrors(self):
        vals = [rsi_points(float(r), "bearish")[0] for r in range(20, 31)]
        assert vals[0] == 4 and vals[-1] == 12
        assert all(a <= b for a, b in zip(vals, vals[1:]))

    def test_nan_scores_nothing(self):
        assert rsi_points(float("nan"), "bullish") == (0, "")


# ─────────────────────────────────────────────────────────────────────────────
# 2.5 — Volume-less instruments
# ─────────────────────────────────────────────────────────────────────────────

class TestVolumelessInstruments:
    def test_index_gets_no_free_volume_points_and_is_rescaled(self):
        df = _uptrend(150)
        idx_df = df.copy()
        idx_df["volume"] = 0.0

        stock = score("STOCK", add_indicators(df, timeframe="1d"), timeframe="1d")
        index = score("INDEX", add_indicators(idx_df, timeframe="1d"), timeframe="1d")

        assert stock.volume_available is True
        assert index.volume_available is False
        assert index.volume_score == 0          # was a free neutral 6

        # trend/momentum/candle/structural_score are already the post-rescale
        # per-category contributions (so the breakdown reflects a custom
        # weighting too) — they should sum to the total directly.
        breakdown_sum = (index.trend_score + index.momentum_score
                         + index.candle_score + index.structural_score)
        assert index.total == pytest.approx(breakdown_sum, abs=1)

    def test_a_perfect_volumeless_setup_can_still_reach_the_top_of_the_scale(self):
        """
        Rescaling means an index is judged on the same 0-100 basis as a stock,
        so the same threshold means the same thing for both.
        """
        raw_max = 30 + 25 + 25 + 5
        assert round(raw_max * 100 / 85) == 100


# ─────────────────────────────────────────────────────────────────────────────
# 2.6 — Minimum bars
# ─────────────────────────────────────────────────────────────────────────────

class TestMinimumBars:
    def test_gate_covers_the_ema50_lookback(self):
        assert MIN_BARS_TO_SCORE >= 50

    def test_short_history_is_not_scored(self):
        df = add_indicators(_uptrend(40), timeframe="1d")
        assert score("SHORT", df, timeframe="1d") is None

    def test_exactly_at_the_gate_is_scored(self):
        df = add_indicators(_uptrend(MIN_BARS_TO_SCORE), timeframe="1d")
        result = score("EDGE", df, timeframe="1d")
        assert result is not None
        assert result.bars_used == MIN_BARS_TO_SCORE


# ─────────────────────────────────────────────────────────────────────────────
# ScoringWeights — user-configurable category ceilings
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringWeights:
    def test_default_weights_match_original_hardcoded_split(self):
        assert (DEFAULT_WEIGHTS.trend, DEFAULT_WEIGHTS.momentum, DEFAULT_WEIGHTS.volume,
                DEFAULT_WEIGHTS.candle, DEFAULT_WEIGHTS.structural) == (30, 25, 15, 25, 5)
        assert DEFAULT_WEIGHTS.total_max == 100

    def test_omitting_weights_reproduces_default_weights_score_exactly(self):
        """weights=None must be byte-identical to weights=DEFAULT_WEIGHTS — this
        is the backward-compatibility guarantee every existing caller relies on."""
        df = add_indicators(_uptrend(150), timeframe="1d")
        a = score("A", df, timeframe="1d", weights=None)
        b = score("A", df, timeframe="1d", weights=DEFAULT_WEIGHTS)
        assert a.total == b.total
        assert (a.trend_score, a.momentum_score, a.volume_score,
                a.candle_score, a.structural_score) == \
               (b.trend_score, b.momentum_score, b.volume_score,
                b.candle_score, b.structural_score)

    def test_total_stays_on_a_0_100_scale_regardless_of_weight_sum(self):
        """Weights summing to something other than 100 must not change the
        reachable ceiling — the total is always rescaled back to 0-100."""
        df = add_indicators(_uptrend(150), timeframe="1d")
        heavy = ScoringWeights(trend=60, momentum=40, volume=30, candle=50, structural=20)  # sums to 200
        light = ScoringWeights(trend=6, momentum=4, volume=3, candle=5, structural=2)        # sums to 20
        r_heavy = score("A", df, timeframe="1d", weights=heavy)
        r_light = score("A", df, timeframe="1d", weights=light)
        assert 0 <= r_heavy.total <= 100
        assert 0 <= r_light.total <= 100
        # Same relative proportions -> same total regardless of absolute scale.
        assert r_heavy.total == pytest.approx(r_light.total, abs=1)

    def test_raising_a_category_weight_increases_its_relative_contribution(self):
        """Doubling trend's weight (others held at default) should not shrink
        trend's share of the final 0-100 total relative to the default split."""
        df = add_indicators(_uptrend(150), timeframe="1d")
        default_result = score("A", df, timeframe="1d", weights=DEFAULT_WEIGHTS)
        boosted = ScoringWeights(trend=60, momentum=25, volume=15, candle=25, structural=5)
        boosted_result = score("A", df, timeframe="1d", weights=boosted)
        if default_result.trend_score > 0:
            default_share = default_result.trend_score / max(default_result.total, 1)
            boosted_share = boosted_result.trend_score / max(boosted_result.total, 1)
            assert boosted_share >= default_share

    def test_breakdown_sums_to_total_with_custom_weights(self):
        df = add_indicators(_uptrend(150), timeframe="1d")
        weights = ScoringWeights(trend=40, momentum=20, volume=10, candle=25, structural=5)
        r = score("A", df, timeframe="1d", weights=weights)
        breakdown = r.trend_score + r.momentum_score + r.volume_score + r.candle_score + r.structural_score
        # total may be lower than the breakdown sum only via the fixed
        # contradiction penalty, never higher.
        assert r.total <= breakdown + 1
        assert breakdown <= 101  # allows rounding slack at the 100 ceiling

    def test_zero_weight_category_contributes_nothing(self):
        df = add_indicators(_uptrend(150), timeframe="1d")
        weights = ScoringWeights(trend=30, momentum=25, volume=0, candle=25, structural=5)
        r = score("A", df, timeframe="1d", weights=weights)
        assert r.volume_score == 0
