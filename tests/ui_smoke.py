"""
UI smoke test: crawl every sidebar route, assert HTTP 200 + expected page-title
text. Catches 404s, build errors, missing routes.
"""
from __future__ import annotations
import os
import sys
import time
from dataclasses import dataclass

import httpx

BASE = os.environ.get("SIP_UI_URL", "http://127.0.0.1:3001")

ROUTES: list[tuple[str, str]] = [
    ("/",                "Dashboard"),    # redirects to dashboard
    ("/dashboard",       "Dashboard"),
    ("/universe",        "Universe Explorer"),
    ("/news",            "News"),
    ("/earnings",        "Earnings Calendar"),
    ("/analyzer",        "Stock Analyzer"),
    ("/scanner",         "Scanner"),
    ("/patterns",        "Pattern Lab"),
    ("/compare",         "Compare"),
    ("/backtest",        "Backtest"),
    ("/position-sizing", "Position Sizing"),
    ("/rules",           "Rule Engine"),
    ("/portfolio",       "Portfolio"),
    ("/watchlist",       "Watchlist"),
    ("/reports",         "Reports"),
    ("/settings",        "Settings"),
    ("/learn",           "Learn"),
]


@dataclass
class R:
    path: str
    status: int = 0
    duration_ms: float = 0
    ok: bool = False
    has_title: bool = False
    error: str = ""


def main() -> int:
    print(f"\n{'-' * 70}\nUI smoke - {BASE}\n{'-' * 70}\n")
    out: list[R] = []
    with httpx.Client(base_url=BASE, follow_redirects=True, timeout=30.0) as c:
        for path, title in ROUTES:
            r = R(path=path)
            t0 = time.perf_counter()
            try:
                resp = c.get(path)
                r.status = resp.status_code
                r.duration_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    r.ok = True
                    body = resp.text
                    r.has_title = title.lower() in body.lower()
                    if not r.has_title:
                        r.error = f"missing title '{title}' in HTML"
                        r.ok = False
                else:
                    r.error = f"HTTP {resp.status_code}"
            except Exception as e:
                r.error = f"{type(e).__name__}: {e}"
                r.duration_ms = (time.perf_counter() - t0) * 1000
            out.append(r)

    print(f"{'STATUS':>6} {'TIME':>9}  PATH")
    print("-" * 90)
    for r in out:
        mark = "+" if r.ok else "x"
        ttl  = "" if r.ok else f"  ({r.error})"
        print(f"{mark} {r.status:>6} {r.duration_ms:>8.0f}ms  {r.path}{ttl}")
    print("-" * 90)
    passed = sum(1 for r in out if r.ok)
    print(f"\n{passed} / {len(out)} OK\n")
    if passed != len(out):
        for r in out:
            if not r.ok:
                print(f"FAIL {r.path}: {r.error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
