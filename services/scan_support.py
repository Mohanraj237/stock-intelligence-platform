"""
Shared plumbing for the equity and F&O scanners.

Everything here is about making a scan *explainable*:
  • inputs are validated and rejected loudly instead of silently substituted
  • pattern selection is matched by identity, then applied as a hard post-filter
  • symbols that could not be scanned are counted and reported
  • the pattern backtest runs the registry detector on the card's own timeframe
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from services.pattern_registry import (
    CATALOG_BY_ID,
    REGISTRY,
    UnknownPatternError,
    pattern_slug,
    resolve_pattern_selection,
)

log = logging.getLogger(__name__)

MAX_REPORTED_ERRORS = 50
PATTERN_MODES = ("filter", "shape")


class ScanInputError(ValueError):
    """A scan parameter was invalid. Surfaced to the client as HTTP 400."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"error": str(self), "field": self.field}


# ─────────────────────────────────────────────────────────────────────────────
# Input parsing — no silent fallbacks
# ─────────────────────────────────────────────────────────────────────────────

def parse_timeframes(raw: str | None, allowed: list[str]) -> list[str] | None:
    """
    Comma-separated timeframe subset → validated list.

    None (parameter absent) means "no filter — scan all". An **empty or
    whitespace-only** value means the caller deselected everything, which is a
    mistake, not a request to scan all eight. Unknown values are named in the
    error rather than dropped.
    """
    if raw is None:
        return None
    wanted = [t.strip() for t in raw.split(",") if t.strip()]
    if not wanted:
        raise ScanInputError("timeframes", "Select at least one timeframe.")
    invalid = [t for t in wanted if t not in allowed]
    if invalid:
        raise ScanInputError(
            "timeframes",
            f"Unknown timeframe(s): {', '.join(invalid)}. Allowed: {', '.join(allowed)}.",
        )
    # de-duplicate, preserve the scanner's canonical order
    return [tf for tf in allowed if tf in set(wanted)]


def parse_pattern_names(raw: str | None) -> set[str] | None:
    """Comma-separated pattern ids or display names → set of ids (or None)."""
    try:
        return resolve_pattern_selection(raw)
    except UnknownPatternError as exc:
        raise ScanInputError("pattern_names", str(exc)) from exc


def parse_pattern_mode(raw: str) -> str:
    mode = (raw or "filter").strip().lower()
    if mode not in PATTERN_MODES:
        raise ScanInputError(
            "pattern_mode",
            f"Unknown pattern_mode '{raw}'. Allowed: {', '.join(PATTERN_MODES)}.",
        )
    return mode


def resolve_universe(universe: str, registered: dict | set | list) -> str:
    """Validate a universe key against the scanner's registry."""
    if universe in registered:
        return universe
    keys = sorted(registered)
    raise ScanInputError(
        "universe",
        f"Unknown universe '{universe}'. Registered universes: {', '.join(keys)}.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scan diagnostics — what was skipped, and why
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScanDiagnostics:
    """Per-scan counters so 'no setups' is distinguishable from 'nothing loaded'."""
    scanned: int = 0
    skipped_no_data: int = 0
    skipped_insufficient_bars: int = 0
    errors: list[dict] = field(default_factory=list)
    _errors_seen: int = 0

    def record(self, symbol: str, outcome: str, reason: str = "") -> None:
        self.scanned += 1
        if outcome == "no_data":
            self.skipped_no_data += 1
        elif outcome == "insufficient_bars":
            self.skipped_insufficient_bars += 1
        if reason:
            self.add_error(symbol, reason)

    def add_error(self, symbol: str, reason: str) -> None:
        self._errors_seen += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append({"symbol": symbol, "reason": reason})

    def as_dict(self) -> dict:
        out = {
            "scanned":                   self.scanned,
            "skipped_no_data":           self.skipped_no_data,
            "skipped_insufficient_bars": self.skipped_insufficient_bars,
            "errors":                    list(self.errors),
        }
        if self._errors_seen > len(self.errors):
            out["errors_truncated"] = self._errors_seen - len(self.errors)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Pattern post-filter — hard, by identity
# ─────────────────────────────────────────────────────────────────────────────

def _card_pattern_ids(card: dict) -> set[str]:
    """Every pattern identity a card can be matched on."""
    ids: set[str] = set()
    for p in card.get("patterns") or []:
        pid = p.get("pattern_id") or pattern_slug(p.get("name", ""))
        if not pid:
            continue
        ids.add(pid)
        entry = CATALOG_BY_ID.get(pid)
        ids.add(p.get("parent_id") or (entry.parent_id if entry else pid))
    primary = card.get("pattern") or ""
    if primary and primary != "None":
        pid = pattern_slug(primary)
        ids.add(pid)
        entry = CATALOG_BY_ID.get(pid)
        if entry:
            ids.add(entry.parent_id)
    return ids


def apply_pattern_filters(
    cards: list[dict],
    pattern_families: str | None = None,
    min_pattern_conf: float = 0.0,
    pattern_ids: set[str] | None = None,
) -> list[dict]:
    """
    Drop cards that do not match the requested pattern identities, families or
    confidence floor.

    `pattern_ids` is a **hard** filter: a card survives only when at least one
    detected pattern (or its displayed primary pattern) is in the selection.
    When a card survives on a non-primary pattern, its displayed `pattern` is
    rewritten to the highest-confidence matched pattern.
    """
    if not pattern_families and not pattern_ids and min_pattern_conf <= 0.0:
        return cards

    families = {f.strip().lower() for f in pattern_families.split(",")} if pattern_families else set()
    out: list[dict] = []

    for card in cards:
        if pattern_ids is not None and not (_card_pattern_ids(card) & pattern_ids):
            continue

        pats = card.get("patterns") or []
        matched = [
            p for p in pats
            if p.get("confidence", 0.0) >= min_pattern_conf
            and (not families or p.get("family", "").lower() in families)
            and (
                pattern_ids is None
                or (p.get("pattern_id") or pattern_slug(p.get("name", ""))) in pattern_ids
                or (p.get("parent_id") or "") in pattern_ids
            )
        ]

        if not matched:
            # A card can still qualify on its displayed primary pattern alone —
            # the legacy fallback detector emits names that never appear in
            # patterns[]. Family / confidence filters need real pattern rows.
            if families or min_pattern_conf > 0.0 or pattern_ids is None:
                continue
            out.append(card)
            continue

        matched_names = {p.get("name", "").lower() for p in matched}
        if card.get("pattern", "").lower() not in matched_names:
            best = max(matched, key=lambda p: p.get("confidence", 0.0))
            card = {**card, "pattern": best["name"]}
        out.append(card)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pattern backtest — registry detector, on the card's own timeframe
# ─────────────────────────────────────────────────────────────────────────────

_DETECTOR_BY_ID = {e.pattern_id: e for e in REGISTRY}

# Enough history to produce a usable sample without making the scan quadratic.
BACKTEST_MAX_BARS = 260
BACKTEST_HORIZON  = 5       # bars allowed for T1 to be reached
MIN_SAMPLE        = 5


def _resolve_detector(pattern_name: str):
    """
    Registry entry able to emit `pattern_name`, plus the exact id to match on.

    Directional variants ("Inside Bar Breakout") are emitted by their parent's
    detector, so the parent entry is used and the *variant* id is matched.
    """
    pid = pattern_slug(pattern_name)
    entry = _DETECTOR_BY_ID.get(pid)
    if entry is not None:
        return entry, pid

    catalog = CATALOG_BY_ID.get(pid)
    if catalog is not None:
        parent = _DETECTOR_BY_ID.get(catalog.parent_id)
        if parent is not None:
            # Legacy-only names (e.g. "Hammer / Pin Bar") have no detector of
            # their own — backtest the registry pattern they map onto.
            match_id = pid if catalog.source == "variant" else catalog.parent_id
            return parent, match_id
    return None, pid


def backtest_pattern(
    df: pd.DataFrame | None,
    timeframe: str,
    pattern_name: str,
    direction: str,
) -> dict:
    """
    Historical hit rate for `pattern_name` on **this card's own timeframe**.

    A "hit" is T1 (1.5 × risk) being touched within the next 5 bars before the
    stop. Always returns a self-describing dict — never a bare blank:
      {"hit_rate": float|None, "sample_size": int, "timeframe": str,
       "window_bars": int, "detector": str, "reason": str|None}
    """
    base: dict[str, Any] = {
        "hit_rate":    None,
        "sample_size": 0,
        "timeframe":   timeframe,
        "window_bars": 0,
        "detector":    None,
        "reason":      None,
    }

    if not pattern_name or pattern_name == "None":
        base["reason"] = "No pattern on this setup."
        return base
    if df is None or df.empty:
        base["reason"] = "No price history available for this timeframe."
        return base

    entry, match_id = _resolve_detector(pattern_name)
    if entry is None:
        base["reason"] = (
            f"'{pattern_name}' has no registry detector, so it cannot be backtested."
        )
        return base
    base["detector"] = entry.name

    window = df.tail(BACKTEST_MAX_BARS)
    n = len(window)
    base["window_bars"] = n

    start = max(entry.min_bars, 2)
    if n < start + BACKTEST_HORIZON + 1:
        base["reason"] = (
            f"Only {n} {timeframe} bars — needs at least "
            f"{start + BACKTEST_HORIZON + 1} to test '{entry.name}'."
        )
        return base

    has_atr = "atr" in window.columns
    hits = total = 0

    try:
        for i in range(start, n - BACKTEST_HORIZON - 1):
            sub = window.iloc[: i + 1]
            r = entry.detector_fn(sub)
            if r is None or r.pattern_id != match_id or r.direction != direction:
                continue

            entry_px = float(window.iloc[i]["close"])
            atr = float(window["atr"].iloc[i]) if has_atr else entry_px * 0.005
            if atr != atr or atr <= 0:                     # NaN guard
                atr = entry_px * 0.005
            risk = max(atr * 1.5, entry_px * 0.003)
            total += 1

            hi_target = entry_px + 1.5 * risk
            lo_target = entry_px - 1.5 * risk
            first_hit = next(
                (j for j in range(i + 1, min(i + 1 + BACKTEST_HORIZON, n))
                 if (direction == "bullish" and float(window.iloc[j]["high"]) >= hi_target)
                 or (direction == "bearish" and float(window.iloc[j]["low"]) <= lo_target)),
                None)
            first_stop = next(
                (j for j in range(i + 1, min(i + 1 + BACKTEST_HORIZON, n))
                 if (direction == "bullish" and float(window.iloc[j]["low"]) <= entry_px - risk)
                 or (direction == "bearish" and float(window.iloc[j]["high"]) >= entry_px + risk)),
                None)
            if first_hit is not None and (first_stop is None or first_hit <= first_stop):
                hits += 1
    except Exception as exc:
        log.debug("Backtest error %s/%s: %s", pattern_name, timeframe, exc)
        base["reason"] = f"Backtest failed: {exc}"
        return base

    base["sample_size"] = total
    if total < MIN_SAMPLE:
        base["reason"] = (
            f"Only {total} prior occurrence(s) in {n} {timeframe} bars — "
            f"needs {MIN_SAMPLE} for a hit rate."
        )
        return base

    base["hit_rate"] = round(hits / total, 2)
    return base
