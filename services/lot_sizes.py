"""
Single source of truth for NSE F&O lot sizes.

Python owns this table. `frontend/lib/lot-sizes.generated.ts` is generated from
it by `scripts/gen_lot_sizes.py`, and `tests/test_lot_sizes.py` fails the build
if the two ever drift. A wrong lot size means a wrong position size, so the two
runtimes must never disagree.

The values below are the ones the option advisor has been building plans with.
They are NOT independently reconciled against the live NSE contract master —
NSE revises lot sizes periodically, so treat this table as needing a periodic
refresh from the exchange, not as authoritative forever.
"""
from __future__ import annotations

# Symbols with no entry here get DEFAULT_LOT_SIZE and are flagged
# `lot_size_estimated: true` on the plan.
DEFAULT_LOT_SIZE = 500

LOT_SIZES: dict[str, int] = {
    # ── Indices ──────────────────────────────────────────────────────────────
    "NIFTY": 75, "BANKNIFTY": 15, "FINNIFTY": 40,
    "MIDCPNIFTY": 75, "SENSEX": 10, "BANKEX": 15,
    # ── Equities ─────────────────────────────────────────────────────────────
    "RELIANCE": 250, "TCS": 150, "INFY": 400,
    "HDFCBANK": 550, "ICICIBANK": 700, "AXISBANK": 1200,
    "KOTAKBANK": 400, "SBIN": 1500, "WIPRO": 1500, "LT": 150,
    "BAJFINANCE": 125, "BAJAJFINSV": 500,
    "TATAMOTORS": 1425, "MARUTI": 75, "TATASTEEL": 5500,
    "SUNPHARMA": 700, "DRREDDY": 125, "CIPLA": 650, "DIVISLAB": 200,
    "HCLTECH": 700, "TECHM": 600,
    "ADANIPORTS": 1250, "ADANIENT": 625,
    "ONGC": 1925, "POWERGRID": 4700,
    "NTPC": 2250, "BPCL": 1800, "COALINDIA": 2100,
    "HINDUNILVR": 300, "NESTLEIND": 40, "ASIANPAINT": 200, "TITAN": 175,
    "ULTRACEMCO": 100, "GRASIM": 375, "HEROMOTOCO": 150, "EICHERMOT": 175,
    "APOLLOHOSP": 250, "JSWSTEEL": 600,
    "M&M": 700, "BHARTIARTL": 950, "INDUSINDBK": 500, "HINDPETRO": 1000,
    "IOC": 5250, "VEDL": 2000, "SAIL": 6700, "PNB": 8000, "BANKBARODA": 3350,
    "CANBK": 3250, "IDFCFIRSTB": 5500, "FEDERALBNK": 5000,
    "HAL": 150, "BEL": 3700, "BHEL": 4350, "HDFCLIFE": 1100, "SBILIFE": 750,
    "ITC": 3200, "IRCTC": 1375, "LICI": 700, "DMART": 450, "TATACONSUM": 1100,
    "BRITANNIA": 200, "UPL": 1300, "BAJAJ-AUTO": 250,
    "ETERNAL": 4500,  # formerly ZOMATO — renamed Feb 2025
    "ZOMATO": 4500,   # legacy alias, kept so old paper trades still price
    "NAUKRI": 200,
    "RBLBANK": 3175,
    "AUBANK": 1000,
    "ABCAPITAL": 6000,
    "MFSL": 4000,
    "PERSISTENT": 125,
    "360ONE": 1000,
    "POLICYBZR": 2000,
    "PIIND": 500,
    "DEEPAKNTR": 500,
    "AARTIIND": 1500,
    "ASTRAL": 700,
    "TATAPOWER": 4000,
    "NHPC": 8000,
    "RECLTD": 2250,
    "PFC": 2700,
    "RVNL": 3000,
    "IRFC": 6000,
    "APLAPOLLO": 500,
}

INDEX_SYMBOLS: list[str] = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX",
]


def lot_size_for(symbol: str) -> tuple[int, bool]:
    """
    (lot_size, estimated). `estimated` is True when the symbol is not in the
    table and DEFAULT_LOT_SIZE was substituted — a silently wrong position size
    is worse than a flagged one.
    """
    sym = symbol.upper()
    if sym in LOT_SIZES:
        return LOT_SIZES[sym], False
    return DEFAULT_LOT_SIZE, True
