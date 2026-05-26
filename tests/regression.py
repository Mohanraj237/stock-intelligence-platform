"""
End-to-end regression for the FastAPI backend.

Hits every router with realistic payloads, prints PASS/FAIL with timing.
Network-bound endpoints (Yahoo, NSE, Screener) are marked degradable -
a 502/timeout is reported but does not fail the run, since it reflects
upstream availability not our code.
"""
from __future__ import annotations
import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

import os
BASE = os.environ.get("SIP_REGRESSION_URL", "http://127.0.0.1:8000")
SYMBOL = "RELIANCE"
UNIVERSE = "NIFTY 50"


@dataclass
class Result:
    method: str
    path: str
    status: int = 0
    duration_ms: float = 0
    ok: bool = False
    note: str = ""
    body_kind: str = ""   # "list[N]" / "dict{keys}" / "scalar"
    error: str = ""


def fmt_body(body: Any) -> str:
    if isinstance(body, list):
        return f"list[{len(body)}]"
    if isinstance(body, dict):
        return f"dict{{{','.join(list(body.keys())[:4])}{'...' if len(body) > 4 else ''}}}"
    return str(type(body).__name__)


def call(client: httpx.Client, method: str, path: str, *,
         json_body: Optional[dict] = None, degradable: bool = False,
         timeout: float = 60.0) -> Result:
    r = Result(method=method, path=path)
    t0 = time.perf_counter()
    try:
        resp = client.request(method, path, json=json_body, timeout=timeout)
        r.status = resp.status_code
        r.duration_ms = (time.perf_counter() - t0) * 1000
        if 200 <= resp.status_code < 300:
            r.ok = True
            try:
                r.body_kind = fmt_body(resp.json())
            except Exception:
                r.body_kind = "non-json"
        elif degradable and resp.status_code in (404, 502, 503, 504):
            r.ok = True
            r.note = f"upstream degraded ({resp.status_code})"
        else:
            r.error = resp.text[:200]
    except httpx.HTTPError as e:
        r.duration_ms = (time.perf_counter() - t0) * 1000
        if degradable:
            r.ok = True
            r.note = f"upstream timeout/network ({type(e).__name__})"
        else:
            r.error = f"{type(e).__name__}: {e}"
    return r


def main() -> int:
    print(f"\n{'-' * 70}\nRegression - backend at {BASE}\n{'-' * 70}\n")

    with httpx.Client(base_url=BASE) as c:
        results: list[Result] = []

        # Health
        results.append(call(c, "GET", "/api/health"))

        # Universe
        results.append(call(c, "GET", "/api/universe/list"))
        results.append(call(c, "GET", f"/api/universe/{UNIVERSE}/symbols?limit=5"))
        results.append(call(c, "GET", f"/api/universe/{UNIVERSE}", degradable=True))
        results.append(call(c, "GET", "/api/universe/_meta/status"))

        # Market
        results.append(call(c, "GET", "/api/market/status", degradable=True))
        results.append(call(c, "GET", "/api/market/indices", degradable=True))
        results.append(call(c, "GET", "/api/market/sectors", degradable=True))
        results.append(call(c, "GET", "/api/market/fii-dii", degradable=True))
        results.append(call(c, "GET", f"/api/market/universe/{UNIVERSE}/quotes", degradable=True))

        # Stocks (per-symbol)
        for tf in ["1D", "1W", "1M"]:
            results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/ohlcv?timeframe={tf}", degradable=True))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/quote", degradable=True))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/indicators?timeframe=1D", degradable=True))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/fundamentals", degradable=True, timeout=20))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/quarterly?n=4", degradable=True, timeout=20))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/verdict?timeframe=1D", degradable=True, timeout=45))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/chart-analysis?timeframe=1W", degradable=True, timeout=45))
        results.append(call(c, "GET", f"/api/stocks/{SYMBOL}/snapshot?timeframe=1D", degradable=True, timeout=45))

        # Patterns
        results.append(call(c, "GET", "/api/patterns/library"))
        results.append(call(c, "GET", "/api/patterns/library/Bull%20Flag/example"))
        results.append(call(c, "GET", f"/api/patterns/detect/{SYMBOL}?timeframe=1D", degradable=True))
        results.append(call(c, "GET", f"/api/patterns/multi-tf-breakout/{SYMBOL}", degradable=True, timeout=45))
        results.append(call(
            c, "POST", "/api/patterns/scan",
            json_body={
                "universe": UNIVERSE,
                "pattern_names": [],
                "direction": None,
                "timeframes": ["1D"],
                "min_confidence": 60,
                "breakout_states": [],
                "max_symbols": 5,
            },
            degradable=True, timeout=120,
        ))

        # Scans
        results.append(call(c, "GET", "/api/scans/types"))
        results.append(call(
            c, "POST", "/api/scans/run",
            json_body={
                "universe": UNIVERSE, "scan_type": "breakout_ready",
                "filters": {}, "enable_ai": False, "max_symbols": 5,
            },
            degradable=True, timeout=120,
        ))

        # News + earnings
        results.append(call(c, "GET", "/api/news/market?limit=10", degradable=True))
        results.append(call(c, "GET", f"/api/news/stock/{SYMBOL}?limit=5", degradable=True))
        results.append(call(c, "GET", f"/api/news/announcements?symbol={SYMBOL}", degradable=True))
        results.append(call(c, "GET", "/api/earnings/upcoming?days_ahead=7", degradable=True))
        results.append(call(c, "GET", f"/api/earnings/recent/{SYMBOL}?n=4", degradable=True, timeout=20))

        # Positions
        results.append(call(
            c, "POST", "/api/positions/calc",
            json_body={"capital": 500000, "risk_pct": 1, "entry": 1200, "stop": 1150, "target": 1320},
        ))
        results.append(call(
            c, "POST", "/api/positions/kelly",
            json_body={"capital": 500000, "win_rate": 55, "avg_win_pct": 8, "avg_loss_pct": 4, "fractional": 0.5},
        ))

        # Portfolio (read + roundtrip add/delete)
        results.append(call(c, "GET", "/api/portfolio", degradable=True))
        added = call(
            c, "POST", "/api/portfolio/add",
            json_body={"symbol": "ZREGRESSIONTEST", "qty": 1, "buy_price": 100, "buy_date": "2025-01-01"},
        )
        results.append(added)
        if added.ok:
            results.append(call(c, "DELETE", "/api/portfolio/ZREGRESSIONTEST"))

        # Watchlist
        results.append(call(c, "GET", "/api/watchlist", degradable=True, timeout=120))
        addw = call(c, "POST", "/api/watchlist/add", json_body={"symbol": "ZREGRESSIONTEST"})
        results.append(addw)
        if addw.ok:
            results.append(call(c, "DELETE", "/api/watchlist/ZREGRESSIONTEST"))

        # Rules
        results.append(call(c, "GET", "/api/rules"))
        rule_create = call(
            c, "POST", "/api/rules",
            json_body={
                "name": "regression-rsi-oversold",
                "conditions": [{"field": "rsi", "op": "<", "value": 30}],
                "logic": "AND",
            },
        )
        results.append(rule_create)
        rule_id = ""
        try:
            rule_id = rule_create and json.loads(httpx.get(f"{BASE}/api/rules").text)[-1].get("id", "")
        except Exception:
            pass
        if rule_id:
            results.append(call(c, "DELETE", f"/api/rules/{rule_id}"))

        # Settings (GET only - PATCH would mutate user's config)
        results.append(call(c, "GET", "/api/settings"))

        # Reports - generate is heavy (PDF), so just list
        results.append(call(c, "GET", "/api/reports/list"))

        # -- Print summary ---------------------------------------------
        passed = sum(1 for r in results if r.ok)
        failed = [r for r in results if not r.ok]
        print(f"{'METHOD':<6} {'STATUS':>6} {'TIME':>9}  PATH")
        print("-" * 90)
        for r in results:
            mark = "+" if r.ok else "x"
            note = f"  ({r.note})" if r.note else (f"  -> {r.body_kind}" if r.body_kind else "")
            print(f"{mark} {r.method:<6} {r.status:>6} {r.duration_ms:>8.0f}ms  {r.path}{note}")
            if r.error:
                print(f"     |- {r.error}")
        print("-" * 90)
        print(f"\n{passed} / {len(results)} OK ({len(failed)} failed)\n")

        if failed:
            print("FAILURES:")
            for r in failed:
                print(f"  {r.method} {r.path} -> {r.status}: {r.error}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
