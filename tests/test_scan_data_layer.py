"""
Data-layer correctness for the scanners.

Covers:
  2.4 4h bars are session-aligned buckets, not calendar buckets
  3.1 the backtest runs the registry detector on the card's own timeframe,
      honours `period`, and is always self-describing
  4.1 the bar cache is keyed, TTL'd, and reports a hit rate
  4.2 ALL_US_LISTED.json is read, and no US symbol resolves to a .NS ticker
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import services.intraday_data as idata
from services.confluence_scorer import add_indicators
from services.scan_support import BACKTEST_MAX_BARS, backtest_pattern

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "storage" / "universe"


# ─────────────────────────────────────────────────────────────────────────────
# 2.4 — Session-aligned 4h resample
# ─────────────────────────────────────────────────────────────────────────────

def _nse_1h_session(days: int = 2) -> pd.DataFrame:
    """NSE 1h bars as Yahoo delivers them: 09:15 … 15:15 IST, tz-naive."""
    stamps: list[pd.Timestamp] = []
    for d in range(days):
        day = pd.Timestamp("2024-03-04") + pd.Timedelta(days=d)
        stamps += [day + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=h)
                   for h in range(7)]
    idx = pd.DatetimeIndex(stamps)
    n = len(idx)
    closes = np.arange(100, 100 + n, dtype=float)
    return pd.DataFrame({
        "open": closes, "high": closes + 1, "low": closes - 1,
        "close": closes, "volume": np.full(n, 1000.0),
    }, index=idx)


class TestFourHourBuckets:
    def test_buckets_start_at_the_session_open(self):
        """
        Plain resample("4h") produced 08:00/12:00/16:00 buckets that straddle
        the 09:15 open and the 15:30 close, so every 4h pattern was detected on
        a bar that never existed.
        """
        out = idata.resample_to_4h(_nse_1h_session(1))
        times = [t.strftime("%H:%M") for t in out.index]
        assert times == ["09:15", "13:15"]

    def test_first_bucket_holds_0915_to_1315_and_second_holds_the_rest(self):
        src = _nse_1h_session(1)
        out = idata.resample_to_4h(src)

        first, second = out.iloc[0], out.iloc[1]
        # 09:15, 10:15, 11:15, 12:15 → 4 bars
        assert first["volume"] == 4 * 1000.0
        # 13:15, 14:15, 15:15 → 3 bars (short final bucket, session ends 15:30)
        assert second["volume"] == 3 * 1000.0
        assert first["open"] == src["open"].iloc[0]
        assert second["close"] == src["close"].iloc[-1]

    def test_boundaries_repeat_daily(self):
        out = idata.resample_to_4h(_nse_1h_session(2))
        times = sorted({t.strftime("%H:%M") for t in out.index})
        assert times == ["09:15", "13:15"]
        assert len(out) == 4          # two buckets per session, two sessions

    def test_no_bucket_spans_two_sessions(self):
        out = idata.resample_to_4h(_nse_1h_session(2))
        assert len({t.date() for t in out.index}) == 2

    def test_empty_input_is_passed_through(self):
        assert idata.resample_to_4h(pd.DataFrame()).empty


# ─────────────────────────────────────────────────────────────────────────────
# 4.2 — US ticker resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestUsTickerResolution:
    def test_all_us_listed_json_is_read(self):
        """
        _build_us_symbols globbed only US_*.json, which ALL_US_LISTED.json does
        not match — a symbol living only in that file became {SYMBOL}.NS.
        """
        path = UNIVERSE_DIR / "ALL_US_LISTED.json"
        if not path.exists():
            pytest.skip("ALL_US_LISTED.json not populated in this checkout")
        symbols = json.loads(path.read_text(encoding="utf-8")).get("symbols", [])
        if not symbols:
            pytest.skip("ALL_US_LISTED.json is empty")
        assert all(idata.is_us_symbol(s) for s in symbols[:50])

    def test_no_us_symbol_resolves_to_an_ns_ticker(self):
        offenders = idata.assert_no_us_symbol_maps_to_ns(idata.get_all_us_listed())
        assert offenders == [], f"US symbols resolving to .NS: {offenders[:20]}"

    def test_indian_symbols_still_get_the_ns_suffix(self):
        assert idata._ticker("RELIANCE") == "RELIANCE.NS"
        assert idata._ticker("AAPL") == "AAPL"

    def test_exchange_tz_follows_the_listing(self):
        assert idata.exchange_tz("AAPL") == "America/New_York"
        assert idata.exchange_tz("RELIANCE") == "Asia/Kolkata"


# ─────────────────────────────────────────────────────────────────────────────
# 4.1 — Bar cache
# ─────────────────────────────────────────────────────────────────────────────

class TestBarCache:
    @pytest.fixture(autouse=True)
    def _clean(self):
        idata.clear_bar_cache()
        idata.reset_cache_stats()
        yield
        idata.clear_bar_cache()
        idata.reset_cache_stats()

    def _stub_response(self, monkeypatch, counter: list[int]):
        class _Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"chart": {"result": [{
                    "timestamp": [1_700_000_000 + i * 86_400 for i in range(60)],
                    "indicators": {"quote": [{
                        "open":   [100.0 + i for i in range(60)],
                        "high":   [101.0 + i for i in range(60)],
                        "low":    [99.0 + i for i in range(60)],
                        "close":  [100.5 + i for i in range(60)],
                        "volume": [1000 + i for i in range(60)],
                    }]},
                }]}}

        class _Sess:
            headers: dict = {}
            def update(self, *_a, **_k): pass
            def get(self, *_a, **_k):
                counter[0] += 1
                return _Resp()

        def _session():
            s = _Sess()
            s.headers = type("H", (), {"update": lambda *a, **k: None})()
            return s

        monkeypatch.setattr(idata._req, "Session", _session)

    def test_second_fetch_within_ttl_is_served_from_cache(self, monkeypatch):
        calls = [0]
        self._stub_response(monkeypatch, calls)

        first  = idata.get_ohlcv("TESTSYM", "1d")
        second = idata.get_ohlcv("TESTSYM", "1d")

        assert calls[0] == 1, "second call should not hit the network"
        pd.testing.assert_frame_equal(first, second)
        assert idata.cache_stats()["hit_rate"] == 0.5

    def test_cache_is_keyed_on_symbol_interval_and_range(self, monkeypatch):
        calls = [0]
        self._stub_response(monkeypatch, calls)

        idata.get_ohlcv("TESTSYM", "1d")
        idata.get_ohlcv("TESTSYM", "1wk")          # different interval
        idata.get_ohlcv("TESTSYM", "1d", period="6mo")   # different range
        idata.get_ohlcv("OTHERSYM", "1d")          # different symbol
        assert calls[0] == 4

    def test_callers_cannot_mutate_the_cached_frame(self, monkeypatch):
        calls = [0]
        self._stub_response(monkeypatch, calls)

        first = idata.get_ohlcv("TESTSYM", "1d")
        first.loc[first.index[0], "close"] = -1.0
        second = idata.get_ohlcv("TESTSYM", "1d")
        assert float(second["close"].iloc[0]) != -1.0

    def test_expired_entries_are_refetched(self, monkeypatch):
        calls = [0]
        self._stub_response(monkeypatch, calls)
        monkeypatch.setattr(idata, "_ttl_for", lambda interval: 0.0)

        idata.get_ohlcv("TESTSYM", "1d")
        idata.get_ohlcv("TESTSYM", "1d")
        assert calls[0] == 2

    def test_daily_ttl_extends_to_the_next_open_when_the_market_is_shut(self, monkeypatch):
        monkeypatch.setattr(idata, "_market_is_open_ist", lambda now=None: False)
        assert idata._ttl_for("1d") > idata._CACHE_TTL["1d"]
        monkeypatch.setattr(idata, "_market_is_open_ist", lambda now=None: True)
        assert idata._ttl_for("1d") == idata._CACHE_TTL["1d"]

    def test_ttls_are_ordered_by_timeframe_speed(self):
        ttls = [idata._CACHE_TTL[tf] for tf in ("5m", "30m", "4h", "1wk")]
        assert ttls == sorted(ttls)

    def test_period_is_honoured_by_get_daily(self, monkeypatch):
        seen: list[dict] = []

        def _fake(symbol, interval="1d", period=None):
            seen.append({"interval": interval, "period": period})
            return pd.DataFrame()

        monkeypatch.setattr(idata, "get_ohlcv", _fake)
        idata.get_daily("X", period="6mo")
        assert seen == [{"interval": "1d", "period": "6mo"}]


# ─────────────────────────────────────────────────────────────────────────────
# 3.1 — Backtest
# ─────────────────────────────────────────────────────────────────────────────

def _daily(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    closes = np.linspace(90, 130, n) + rng.normal(0, 1.2, n)
    df = pd.DataFrame({
        "open":   closes * 0.998,
        "high":   closes * 1.012,
        "low":    closes * 0.988,
        "close":  closes,
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2023-01-02", periods=n, freq="B"))
    return add_indicators(df, timeframe="1d")


class TestBacktest:
    def test_result_is_always_self_describing(self):
        bt = backtest_pattern(_daily(), "1wk", "Hammer", "bullish")
        for key in ("hit_rate", "sample_size", "timeframe", "window_bars", "detector", "reason"):
            assert key in bt
        assert bt["timeframe"] == "1wk"      # echoes the card's own timeframe
        assert bt["detector"] == "Hammer"

    def test_registry_patterns_beyond_the_legacy_seven_are_coverable(self):
        """
        The old backtest walked the legacy 10-pattern detector against registry
        names, so a Bull Flag card could never show a hit rate at all.
        """
        for name in ("Bull Flag", "NR7", "Doji", "Inside Bar", "Volume Surge on Breakout"):
            bt = backtest_pattern(_daily(), "1d", name, "bullish")
            assert bt["detector"] is not None, name
            assert "no registry detector" not in (bt["reason"] or "")

    def test_variants_backtest_through_their_parent_detector(self):
        bt = backtest_pattern(_daily(), "1d", "Inside Bar Breakout", "bullish")
        assert bt["detector"] == "Inside Bar"

    def test_legacy_only_name_maps_onto_its_registry_equivalent(self):
        bt = backtest_pattern(_daily(), "1d", "Hammer / Pin Bar", "bullish")
        assert bt["detector"] == "Hammer"

    def test_pattern_with_no_registry_detector_says_so(self):
        bt = backtest_pattern(_daily(), "1d", "Bullish Marubozu", "bullish")
        assert bt["hit_rate"] is None
        assert "no registry detector" in bt["reason"]

    def test_no_pattern_states_a_reason_rather_than_a_blank(self):
        bt = backtest_pattern(_daily(), "1d", "None", "bullish")
        assert bt["hit_rate"] is None and bt["reason"]

    def test_missing_history_states_a_reason(self):
        bt = backtest_pattern(None, "1d", "Hammer", "bullish")
        assert bt["hit_rate"] is None and "No price history" in bt["reason"]

    def test_sample_floor_of_five_is_kept(self):
        bt = backtest_pattern(_daily(), "1d", "Cup & Handle", "bullish")
        if bt["sample_size"] < 5:
            assert bt["hit_rate"] is None
            assert bt["reason"]

    def test_window_is_bounded(self):
        bt = backtest_pattern(_daily(400), "1d", "Hammer", "bullish")
        assert bt["window_bars"] <= BACKTEST_MAX_BARS

    def test_hit_rate_is_a_probability_when_produced(self):
        for name in ("Hammer", "Doji", "NR7", "Inside Bar", "Spinning Top"):
            bt = backtest_pattern(_daily(), "1d", name, "bullish")
            if bt["hit_rate"] is not None:
                assert 0.0 <= bt["hit_rate"] <= 1.0
                assert bt["sample_size"] >= 5
