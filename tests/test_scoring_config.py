"""
Tests for GET/PATCH/POST /api/scoring-config and the underlying storage helpers.

Uses fresh_client (see conftest.py) since these tests mutate persisted state,
and reset the config back to factory defaults at the end of each mutating test
so later test runs (and a real user's Settings page) start from a clean slate.
"""
from __future__ import annotations

import pytest

from storage.file_store import get_scoring_config, save_scoring_config, reset_scoring_config


DEFAULTS = {
    "trend_weight": 30, "momentum_weight": 25, "volume_weight": 15,
    "candle_weight": 25, "structural_weight": 5, "default_threshold": 65,
}


class TestStorageHelpers:
    def test_defaults_when_nothing_saved(self):
        reset_scoring_config()
        assert get_scoring_config() == DEFAULTS

    def test_save_and_reload_round_trips(self):
        save_scoring_config({**DEFAULTS, "trend_weight": 40, "momentum_weight": 15})
        cfg = get_scoring_config()
        assert cfg["trend_weight"] == 40
        assert cfg["momentum_weight"] == 15
        assert cfg["volume_weight"] == 15  # untouched fields keep their value
        reset_scoring_config()

    def test_unknown_keys_are_dropped_on_save(self):
        save_scoring_config({**DEFAULTS, "not_a_real_field": 999})
        assert "not_a_real_field" not in get_scoring_config()
        reset_scoring_config()

    def test_reset_restores_defaults(self):
        save_scoring_config({**DEFAULTS, "trend_weight": 99})
        assert get_scoring_config()["trend_weight"] == 99
        reset_scoring_config()
        assert get_scoring_config() == DEFAULTS


class TestScoringConfigEndpoint:
    def test_get_returns_defaults_after_reset(self, fresh_client):
        fresh_client.post("/api/scoring-config/reset")
        r = fresh_client.get("/api/scoring-config")
        assert r.status_code == 200
        assert r.json() == DEFAULTS

    def test_patch_updates_only_sent_fields(self, fresh_client):
        fresh_client.post("/api/scoring-config/reset")
        r = fresh_client.patch("/api/scoring-config", json={"trend_weight": 45})
        assert r.status_code == 200
        body = r.json()
        assert body["trend_weight"] == 45
        assert body["momentum_weight"] == 25  # unchanged
        fresh_client.post("/api/scoring-config/reset")

    def test_patch_persists_across_requests(self, fresh_client):
        fresh_client.patch("/api/scoring-config", json={"default_threshold": 75})
        r = fresh_client.get("/api/scoring-config")
        assert r.json()["default_threshold"] == 75
        fresh_client.post("/api/scoring-config/reset")

    def test_reset_endpoint_restores_defaults(self, fresh_client):
        fresh_client.patch("/api/scoring-config", json={"trend_weight": 10, "candle_weight": 60})
        r = fresh_client.post("/api/scoring-config/reset")
        assert r.status_code == 200
        assert r.json() == DEFAULTS

    def test_patch_rejects_non_integer_weight(self, fresh_client):
        r = fresh_client.patch("/api/scoring-config", json={"trend_weight": "not-a-number"})
        assert r.status_code == 422
        fresh_client.post("/api/scoring-config/reset")


class TestScannerHonoursConfiguredDefaultThreshold:
    def test_equity_scan_stream_echoes_configured_default_threshold(self, fresh_client):
        """When ?threshold= is omitted, the scan should resolve to the
        persisted default_threshold, not a hardcoded 65."""
        fresh_client.patch("/api/scoring-config", json={"default_threshold": 77})
        with fresh_client.stream(
            "GET", "/api/equity-scanner/scan/stream?universe=india_indices"
        ) as r:
            first_line = None
            for line in r.iter_lines():
                if line.startswith("data:"):
                    first_line = line
                    break
        assert first_line is not None
        assert '"threshold": 77' in first_line or '"threshold":77' in first_line
        fresh_client.post("/api/scoring-config/reset")
