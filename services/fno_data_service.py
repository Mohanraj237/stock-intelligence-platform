"""
F&O Data Service — NSE India public endpoints only.
Reuses the existing NSE session/cookie mechanism from nse_service.
All monetary values in ₹.  Cache TTL = 60 s (live data).
"""
from __future__ import annotations

import time
import logging
import threading
from datetime import datetime, date
from typing import Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Shared session (same cookie pool as nse_service) ─────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}

_SESSION: Optional[requests.Session] = None
_SESSION_TS: float = 0
_SESSION_TTL = 300
_SESSION_LOCK = threading.Lock()


_SEED_PAGES = [
    "https://www.nseindia.com",
    "https://www.nseindia.com/market-data/equity-derivatives-watch",
]

def _get_session() -> requests.Session:
    global _SESSION, _SESSION_TS
    with _SESSION_LOCK:
        if _SESSION is None or (time.time() - _SESSION_TS) > _SESSION_TTL:
            sess = requests.Session()
            sess.headers.update(_HEADERS)
            html_headers = {**_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"}
            for page in _SEED_PAGES:
                try:
                    sess.get(page, timeout=10, headers=html_headers)
                    time.sleep(0.3)
                except Exception:
                    pass
            _SESSION = sess
            _SESSION_TS = time.time()
        return _SESSION


def _api_get(path: str, params: dict | None = None, timeout: int = 15) -> Optional[Any]:
    sess = _get_session()
    url = f"https://www.nseindia.com{path}"
    try:
        resp = sess.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        # 403 / 401 → force session refresh on next call
        if resp.status_code in (401, 403):
            global _SESSION_TS
            _SESSION_TS = 0
        logger.warning("FNO NSE API %s → %s", path, resp.status_code)
    except Exception as exc:
        logger.warning("FNO NSE API %s failed: %s", path, exc)
    return None


# ── Lot sizes (NSE F&O, as of 2024-25 revision) ──────────────────────────────
LOT_SIZES: dict[str, int] = {
    # Indices
    "NIFTY":      75,
    "BANKNIFTY":  15,
    "FINNIFTY":   40,
    "MIDCPNIFTY": 75,
    "SENSEX":     10,
    "BANKEX":     15,
    # Large-caps
    "RELIANCE":   250,
    "TCS":        150,
    "INFY":       400,
    "HDFCBANK":   550,
    "ICICIBANK":  700,
    "AXISBANK":   1200,
    "KOTAKBANK":  400,
    "SBIN":       1500,
    "BAJFINANCE": 125,
    "BAJAJFINSV": 500,
    "WIPRO":      1500,
    "LT":         175,
    "MARUTI":     100,
    "TATAMOTORS": 1425,
    "TATASTEEL":  5500,
    "SUNPHARMA":  700,
    "DRREDDY":    125,
    "CIPLA":      650,
    "DIVISLAB":   200,
    "HCLTECH":    700,
    "TECHM":      600,
    "NTPC":       2250,
    "POWERGRID":  2700,
    "ONGC":       1975,
    "BPCL":       1800,
    "COALINDIA":  2100,
    "NESTLEIND":  50,
    "ASIANPAINT": 200,
    "HINDUNILVR": 300,
    "TITAN":      375,
    "ULTRACEMCO": 100,
    "GRASIM":     375,
    "HEROMOTOCO": 150,
    "EICHERMOT":  175,
    "APOLLOHOSP": 250,
    "ADANIENT":   625,
    "ADANIPORTS": 625,
    "JSWSTEEL":   600,
    "M&M":        700,
    "BHARTIARTL": 950,
    "INDUSINDBK": 500,
    "HINDPETRO":  1000,
    "IOC":        5250,
    "VEDL":       2000,
    "SAIL":       6700,
    "PNB":        8000,
    "BANKBARODA": 3350,
    "CANBK":      3250,
    "IDFCFIRSTB": 5500,
    "FEDERALBNK": 5000,
    "ZOMATO":     4500,
    "HAL":        150,
    "BEL":        3700,
    "BHEL":       4350,
    "HDFCLIFE":   1100,
    "SBILIFE":    750,
    "ITC":        3200,
    "IRCTC":      1375,
    "LICI":       700,
    "DMART":      450,
    "TATACONSUM": 1100,
    "BRITANNIA":  200,
    "UPL":        1300,
    "BAJAJ-AUTO": 250,
}

# ── Index → symbol map for option chain ──────────────────────────────────────
INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]

_FNO_STOCKS_CACHE: list[dict] = []
_FNO_STOCKS_TS: float = 0
_FNO_STOCKS_TTL = 3600


def get_fno_stocks() -> list[dict]:
    """All F&O-eligible equities with lot sizes from NSE (1-hour cache)."""
    global _FNO_STOCKS_CACHE, _FNO_STOCKS_TS
    if _FNO_STOCKS_CACHE and (time.time() - _FNO_STOCKS_TS) < _FNO_STOCKS_TTL:
        return _FNO_STOCKS_CACHE

    data = _api_get("/api/equity-stockIndices", {"index": "SECURITIES IN F&O"})
    if not data:
        # Return cached data if available, else build minimal list from LOT_SIZES
        if _FNO_STOCKS_CACHE:
            return _FNO_STOCKS_CACHE
        return [{"symbol": s, "ltp": 0, "change": 0, "pChange": 0, "lot_size": l}
                for s, l in LOT_SIZES.items() if s not in INDEX_SYMBOLS]

    rows = []
    for item in data.get("data", []):
        sym = item.get("symbol", "")
        if not sym or sym in ("", "SECURITIES IN F&O"):
            continue
        # NSE returns lotSize in the F&O securities list; fall back to LOT_SIZES
        lot = (
            int(item["lotSize"]) if item.get("lotSize") and str(item["lotSize"]).isdigit()
            else LOT_SIZES.get(sym, 1)
        )
        rows.append({
            "symbol":   sym,
            "ltp":      item.get("lastPrice", 0),
            "change":   item.get("change", 0),
            "pChange":  item.get("pChange", 0),
            "lot_size": lot,
        })

    if rows:
        _FNO_STOCKS_CACHE = rows
        _FNO_STOCKS_TS = time.time()
    return rows or _FNO_STOCKS_CACHE or []


def get_fno_symbols() -> list[str]:
    """Sorted list of all F&O equity symbols."""
    stocks = get_fno_stocks()
    return sorted(s["symbol"] for s in stocks)


# ── Option chain ──────────────────────────────────────────────────────────────

def _parse_option_chain(raw: dict) -> tuple[pd.DataFrame, dict]:
    """
    Parse NSE option chain JSON into a flat DataFrame.

    Returns (df, meta) where meta contains:
        expiry_dates, strike_prices, underlying_value, timestamp,
        total_ce_oi, total_pe_oi
    """
    records = raw.get("records", {})
    filtered = raw.get("filtered", {})

    all_data      = records.get("data", [])
    expiry_dates  = records.get("expiryDates", [])
    strike_prices = records.get("strikePrices", [])
    underlying    = records.get("underlyingValue", 0)
    timestamp     = records.get("timestamp", "")

    rows = []
    for entry in all_data:
        strike  = entry.get("strikePrice", 0)
        expiry  = entry.get("expiryDate", "")

        def _side(d: dict, side: str) -> dict:
            return {
                f"{side}_oi":          d.get("openInterest", 0),
                f"{side}_oi_chg":      d.get("changeinOpenInterest", 0),
                f"{side}_oi_chg_pct":  d.get("pchangeinOpenInterest", 0),
                f"{side}_vol":         d.get("totalTradedVolume", 0),
                f"{side}_iv":          d.get("impliedVolatility", 0),
                f"{side}_ltp":         d.get("lastPrice", 0),
                f"{side}_chg":         d.get("change", 0),
                f"{side}_chg_pct":     d.get("pChange", 0),
                f"{side}_bid_qty":     d.get("bidQty", 0),
                f"{side}_bid":         d.get("bidprice", 0),
                f"{side}_ask_qty":     d.get("askQty", 0),
                f"{side}_ask":         d.get("askPrice", 0),
            }

        row = {"strike": strike, "expiry": expiry}
        row.update(_side(entry.get("CE", {}), "CE"))
        row.update(_side(entry.get("PE", {}), "PE"))
        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    ce_info = filtered.get("CE", {})
    pe_info = filtered.get("PE", {})
    meta = {
        "expiry_dates":    expiry_dates,
        "strike_prices":   strike_prices,
        "underlying":      underlying,
        "timestamp":       timestamp,
        "total_ce_oi":     ce_info.get("totOI", 0),
        "total_pe_oi":     pe_info.get("totOI", 0),
        "total_ce_vol":    ce_info.get("totVol", 0),
        "total_pe_vol":    pe_info.get("totVol", 0),
    }
    return df, meta


def get_option_chain(symbol: str, expiry: str | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Fetch and parse the full option chain for a symbol.
    Indices → /api/option-chain-indices
    Stocks  → /api/option-chain-equities
    Falls back to synthetic chain if NSE API is unavailable.

    Returns (df, meta) where meta["synthetic"]=True when synthetic fallback is used.
    """
    sym = symbol.upper()
    path = "/api/option-chain-indices" if sym in INDEX_SYMBOLS else "/api/option-chain-equities"

    raw = _api_get(path, {"symbol": sym})
    if raw is None:
        logger.info("NSE option chain unavailable for %s — using synthetic fallback", sym)
        return get_synthetic_option_chain(sym, expiry)

    df, meta = _parse_option_chain(raw)

    if df.empty:
        logger.info("Empty NSE chain for %s — using synthetic fallback", sym)
        return get_synthetic_option_chain(sym, expiry)

    # Sort expiry dates chronologically
    if meta.get("expiry_dates"):
        meta["expiry_dates"] = sorted(
            meta["expiry_dates"],
            key=lambda s: parse_expiry_date(s) or date.max,
        )

    if expiry and not df.empty:
        df = df[df["expiry"] == expiry].reset_index(drop=True)
    return df, meta


# ── Synthetic option chain (Black-Scholes fallback) ──────────────────────────

def _strike_interval(spot: float, sym: str) -> int:
    """Appropriate strike interval for a given spot price / symbol."""
    index_intervals = {
        "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50,
        "MIDCPNIFTY": 25, "SENSEX": 100, "BANKEX": 100,
    }
    if sym in index_intervals:
        return index_intervals[sym]
    if spot < 100:    return 2
    if spot < 500:    return 5
    if spot < 1000:   return 10
    if spot < 2000:   return 20
    if spot < 5000:   return 50
    if spot < 10000:  return 100
    return 200


def get_synthetic_option_chain(symbol: str, expiry: str | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Generate a synthetic option chain using real spot + India VIX + Black-Scholes.
    Works for BOTH indices and individual F&O stocks.
    Meta includes {"synthetic": True} to let the frontend show a disclaimer.
    """
    import math
    from datetime import timedelta

    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _bs_price(S: float, K: float, T: float, r: float, sigma: float, opt: str) -> float:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return max(0.0, S - K) if opt == "CE" else max(0.0, K - S)
        try:
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            if opt == "CE":
                return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
            else:
                return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        except Exception:
            return max(0.0, S - K) if opt == "CE" else max(0.0, K - S)

    sym = symbol.upper()
    all_indices_data = _api_get("/api/allIndices")

    index_name_map = {
        "NIFTY":      "NIFTY 50",
        "BANKNIFTY":  "NIFTY BANK",
        "FINNIFTY":   "NIFTY FINANCIAL SERVICES",
        "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
        "SENSEX":     "SENSEX",
        "BANKEX":     "BSE BANKEX",
    }

    spot = 0.0
    vix_val = 15.0
    if all_indices_data:
        for item in all_indices_data.get("data", []):
            idx_name = item.get("index", "")
            if sym in INDEX_SYMBOLS and idx_name == index_name_map.get(sym):
                spot = float(item.get("last") or 0)
            if "VIX" in idx_name.upper() and "INDIA" in idx_name.upper():
                vix_val = float(item.get("last") or 15.0)

    # For equity stocks: fetch spot from quote-derivative
    if sym not in INDEX_SYMBOLS and spot <= 0:
        quote = get_fno_quote(sym)
        spot = float(quote.get("spot") or quote.get("ltp") or 0)

    if spot <= 0:
        fallback = {"NIFTY": 25000, "BANKNIFTY": 54000, "FINNIFTY": 23000,
                    "MIDCPNIFTY": 13000, "SENSEX": 82000, "BANKEX": 60000}
        spot = fallback.get(sym, 1000.0)

    # ── Strike configuration ──────────────────────────────────────────────────────
    interval = _strike_interval(spot, sym)
    atm_strike = round(spot / interval) * interval
    n_wings = 20
    strikes = [atm_strike + (i - n_wings) * interval for i in range(2 * n_wings + 1)]

    # ── Generate upcoming expiry dates ────────────────────────────────────────────
    # Indices: weekly expiries on specific days; stocks: monthly (last Thursday)
    expiry_dow = {"NIFTY": 3, "BANKNIFTY": 2, "FINNIFTY": 1, "MIDCPNIFTY": 3}.get(sym, 3)
    today_d = date.today()
    expiry_date_objs: list[date] = []
    d = today_d
    if sym in INDEX_SYMBOLS:
        # Weekly expiries
        while len(expiry_date_objs) < 5:
            days_ahead = expiry_dow - d.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            d = d + timedelta(days=days_ahead)
            expiry_date_objs.append(d)
    else:
        # Monthly expiries — last Thursday of each month
        for m_offset in range(4):
            m = (today_d.month - 1 + m_offset) % 12 + 1
            y = today_d.year + ((today_d.month - 1 + m_offset) // 12)
            # Find last Thursday of month
            import calendar
            last_day = calendar.monthrange(y, m)[1]
            last_thu = date(y, m, last_day)
            while last_thu.weekday() != 3:  # 3 = Thursday
                last_thu -= timedelta(days=1)
            if last_thu > today_d:
                expiry_date_objs.append(last_thu)
        if not expiry_date_objs:
            # Fallback: 30 days from now
            expiry_date_objs.append(today_d + timedelta(days=30))

    expiry_dates_str = [dd.strftime("%d-%b-%Y") for dd in expiry_date_objs]

    # Determine which expiries to generate rows for.
    # When no expiry is specified (heatmap / full chain), generate all expiries
    # so pages like the heatmap can show the full strike × expiry grid.
    r = 0.065  # RBI-aligned risk-free rate
    atm_iv = vix_val / 100.0
    oi_base = 600_000
    oi_width = interval * 10

    if expiry and expiry in expiry_dates_str:
        expiries_to_build = [(expiry, expiry_date_objs[expiry_dates_str.index(expiry)], 1.0)]
    else:
        # OI decays for farther expiries (near-term carries most open interest)
        oi_decay = [1.0, 0.55, 0.35, 0.22, 0.14]
        expiries_to_build = [
            (exp_str, exp_obj, oi_decay[i] if i < len(oi_decay) else 0.10)
            for i, (exp_str, exp_obj) in enumerate(zip(expiry_dates_str, expiry_date_objs))
        ]

    # ── Build rows using Black-Scholes + realistic OI distribution ───────────────
    rows = []
    total_ce_oi = 0
    total_pe_oi = 0

    for current_expiry, current_expiry_obj, oi_factor in expiries_to_build:
        dte = max((current_expiry_obj - today_d).days, 1)
        T = dte / 365.0
        scaled_oi_base = int(oi_base * oi_factor)

        for K in strikes:
            moneyness = math.log(K / spot) if spot > 0 else 0
            iv_skewed = atm_iv * math.exp(-0.4 * moneyness)
            iv_skewed = max(0.05, min(iv_skewed, 1.5))

            ce_ltp = _bs_price(spot, K, T, r, iv_skewed, "CE")
            pe_ltp = _bs_price(spot, K, T, r, iv_skewed, "PE")

            ce_oi_center = atm_strike + interval
            pe_oi_center = atm_strike - interval
            ce_oi = int(scaled_oi_base * math.exp(-0.5 * ((K - ce_oi_center) / (oi_width * 1.2)) ** 2))
            pe_oi = int(scaled_oi_base * math.exp(-0.5 * ((K - pe_oi_center) / (oi_width * 1.2)) ** 2))

            major_round = interval * 10
            if K % major_round == 0:
                ce_oi = int(ce_oi * 1.9)
                pe_oi = int(pe_oi * 1.9)
            elif K % (interval * 5) == 0:
                ce_oi = int(ce_oi * 1.4)
                pe_oi = int(pe_oi * 1.4)

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            rows.append({
                "strike":        K,
                "expiry":        current_expiry,
                "CE_oi":         ce_oi,
                "CE_oi_chg":     0,
                "CE_oi_chg_pct": 0.0,
                "CE_vol":        int(ce_oi * 0.35),
                "CE_iv":         round(iv_skewed * 100, 2),
                "CE_ltp":        round(max(0.05, ce_ltp), 2),
                "CE_chg":        0.0,
                "CE_chg_pct":    0.0,
                "CE_bid_qty":    0,
                "CE_bid":        0.0,
                "CE_ask_qty":    0,
                "CE_ask":        0.0,
                "PE_oi":         pe_oi,
                "PE_oi_chg":     0,
                "PE_oi_chg_pct": 0.0,
                "PE_vol":        int(pe_oi * 0.35),
                "PE_iv":         round(iv_skewed * 100, 2),
                "PE_ltp":        round(max(0.05, pe_ltp), 2),
                "PE_chg":        0.0,
                "PE_chg_pct":    0.0,
                "PE_bid_qty":    0,
                "PE_bid":        0.0,
                "PE_ask_qty":    0,
                "PE_ask":        0.0,
            })

    df = pd.DataFrame(rows)
    meta = {
        "expiry_dates":   expiry_dates_str,
        "strike_prices":  strikes,
        "underlying":     round(spot, 2),
        "timestamp":      datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
        "total_ce_oi":    total_ce_oi,
        "total_pe_oi":    total_pe_oi,
        "total_ce_vol":   int(total_ce_oi * 0.35),
        "total_pe_vol":   int(total_pe_oi * 0.35),
        "synthetic":      True,
        "vix":            round(vix_val, 2),
    }
    return df, meta


# ── OI Analytics ─────────────────────────────────────────────────────────────

def get_oi_spurts() -> pd.DataFrame:
    """Top underlyings with unusual OI build-up (from NSE live-analysis endpoint)."""
    data = _api_get("/api/live-analysis-oi-spurts-underlyings")
    if not data:
        return pd.DataFrame()
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # NSE API field → our canonical field (handle both old and new NSE field names)
    rename = {
        # new NSE field names (as of 2025)
        "latestOI":            "oi_current",
        "changeInOI":          "oi_change",
        "underlyingValue":     "ltp",
        # old/alternate NSE field names
        "currentOI":           "oi_current",
        "prevOI":              "oi_prev",
        "change":              "oi_change",
        "pChange":             "oi_change_pct",
        "last":                "ltp",
        "previousClose":       "prev_close",
        "pricePChange":        "price_chg_pct",
        "volume":              "vol",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    # Compute oi_change_pct if not present
    if "oi_change_pct" not in df.columns and "oi_current" in df.columns and "oi_prev" in df.columns:
        df["oi_prev"] = df["prevOI"] if "prevOI" in df.columns else df.get("oi_prev", 0)
        df["oi_change_pct"] = df.apply(
            lambda r: round((r["oi_change"] / r["oi_prev"]) * 100, 2) if r.get("oi_prev", 0) > 0 else 0,
            axis=1,
        )
    # price_chg_pct — not directly available in new format, default to 0
    if "price_chg_pct" not in df.columns:
        df["price_chg_pct"] = 0.0
    return df


def get_oi_variations() -> pd.DataFrame:
    """OI variation data — long/short buildup/unwinding classification."""
    data = _api_get("/api/live-analysis-variations")

    if not data:
        return pd.DataFrame()

    all_rows = []
    for category, label in [
        ("allSec",       "All"),
        ("oi_spurts",    "OI Spurt"),
        ("price_spurts", "Price Spurt"),
    ]:
        for item in data.get(category, {}).get("data", []):
            item["_category"] = label
            all_rows.append(item)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    return df


# ── Index Futures ─────────────────────────────────────────────────────────────

def get_index_futures() -> list[dict]:
    """
    Live futures data for NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY.
    Fetches from NSE futures quote endpoints.
    """
    results = []
    futures_symbols = [
        ("NIFTY",      "NIFTY 50",     "/api/quote-derivative?symbol=NIFTY"),
        ("BANKNIFTY",  "NIFTY BANK",   "/api/quote-derivative?symbol=BANKNIFTY"),
        ("FINNIFTY",   "NIFTY FIN SERVICE", "/api/quote-derivative?symbol=FINNIFTY"),
        ("MIDCPNIFTY", "NIFTY MIDCAP SELECT", "/api/quote-derivative?symbol=MIDCPNIFTY"),
    ]

    def _fetch_one(sym, index_name, path):
        raw = _api_get(path)
        if not raw:
            return None
        fut_data = raw.get("stocks", [])
        # Find the near-month futures contract
        fut_row = None
        for s in fut_data:
            md = s.get("metadata", {})
            if md.get("instrumentType") == "Index Futures":
                fut_row = s
                break
        if fut_row is None:
            return None

        md   = fut_row.get("metadata", {})
        mkt  = fut_row.get("marketDeptOrderBook", {})
        spot = raw.get("underlyingValue", 0)
        ltp  = md.get("lastPrice", 0)
        return {
            "symbol":        sym,
            "index_name":    index_name,
            "spot":          spot,
            "futures_ltp":   ltp,
            "basis":         round(ltp - spot, 2) if spot else 0,
            "basis_pct":     round((ltp - spot) / spot * 100, 3) if spot else 0,
            "change":        md.get("change", 0),
            "change_pct":    md.get("pChange", 0),
            "oi":            md.get("openInterest", 0),
            "vol":           md.get("numberOfContractsTraded", 0),
            "expiry":        md.get("expiryDate", ""),
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_fetch_one, sym, idx, pth): sym
                for sym, idx, pth in futures_symbols}
        for f in as_completed(futs):
            try:
                res = f.result()
                if res:
                    results.append(res)
            except Exception:
                pass

    # Sort by canonical order
    order = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
    results.sort(key=lambda x: order.index(x["symbol"]) if x["symbol"] in order else 99)
    return results


# ── VIX ───────────────────────────────────────────────────────────────────────

def get_vix() -> dict:
    """India VIX current value and change."""
    data = _api_get("/api/allIndices")
    if not data:
        return {"vix": None, "change": None, "change_pct": None}
    for idx in data.get("data", []):
        if "VIX" in idx.get("index", "").upper():
            return {
                "vix":        idx.get("last"),
                "change":     idx.get("variation"),
                "change_pct": idx.get("percentChange"),
                "open":       idx.get("open"),
                "high":       idx.get("high"),
                "low":        idx.get("low"),
                "prev_close": idx.get("previousClose"),
            }
    return {"vix": None, "change": None, "change_pct": None}


# ── PCR ───────────────────────────────────────────────────────────────────────

def get_pcr(symbol: str) -> dict:
    """
    Calculate Put-Call Ratio for a symbol from live option chain OI.
    Returns {pcr_oi, pcr_vol, total_ce_oi, total_pe_oi, total_ce_vol, total_pe_vol}
    """
    _, meta = get_option_chain(symbol)
    if not meta:
        _, meta = get_synthetic_option_chain(symbol)
    if not meta:
        return {}

    total_ce_oi  = meta.get("total_ce_oi", 0)
    total_pe_oi  = meta.get("total_pe_oi", 0)
    total_ce_vol = meta.get("total_ce_vol", 0)
    total_pe_vol = meta.get("total_pe_vol", 0)

    pcr_oi  = round(total_pe_oi  / total_ce_oi,  3) if total_ce_oi  else 0
    pcr_vol = round(total_pe_vol / total_ce_vol, 3) if total_ce_vol else 0

    return {
        "symbol":       symbol,
        "pcr_oi":       pcr_oi,
        "pcr_vol":      pcr_vol,
        "total_ce_oi":  total_ce_oi,
        "total_pe_oi":  total_pe_oi,
        "total_ce_vol": total_ce_vol,
        "total_pe_vol": total_pe_vol,
    }


# ── Futures quote (single symbol) ─────────────────────────────────────────────

def get_fno_quote(symbol: str) -> dict:
    """
    Near-month futures quote for any F&O symbol.
    Returns {ltp, change, change_pct, oi, vol, expiry, spot, basis}
    """
    raw = _api_get("/api/quote-derivative", {"symbol": symbol.upper()})
    if not raw:
        return {}

    spot = raw.get("underlyingValue", 0)
    stocks = raw.get("stocks", [])
    instr_type = "Index Futures" if symbol.upper() in INDEX_SYMBOLS else "Stock Futures"

    near = None
    for s in stocks:
        md = s.get("metadata", {})
        if md.get("instrumentType") == instr_type:
            near = s
            break

    if not near:
        return {"spot": spot}

    md  = near.get("metadata", {})
    ltp = md.get("lastPrice", 0)
    return {
        "symbol":     symbol,
        "spot":       spot,
        "ltp":        ltp,
        "change":     md.get("change", 0),
        "change_pct": md.get("pChange", 0),
        "oi":         md.get("openInterest", 0),
        "vol":        md.get("numberOfContractsTraded", 0),
        "expiry":     md.get("expiryDate", ""),
        "basis":      round(ltp - spot, 2) if spot else 0,
        "basis_pct":  round((ltp - spot) / spot * 100, 3) if spot else 0,
    }


# ── Expiry utilities ──────────────────────────────────────────────────────────

def parse_expiry_date(expiry_str: str) -> date | None:
    """Parse 'DD-Mon-YYYY' → datetime.date.  Returns None on failure."""
    try:
        return datetime.strptime(expiry_str, "%d-%b-%Y").date()
    except Exception:
        try:
            return datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except Exception:
            return None


def days_to_expiry(expiry_str: str) -> int:
    """Calendar days from today to the given expiry string."""
    d = parse_expiry_date(expiry_str)
    if d is None:
        return 0
    return max(0, (d - date.today()).days)


def get_lot_size(symbol: str) -> int:
    """Return lot size for symbol; fallback to NSE F&O list, then 1."""
    sym = symbol.upper()
    if sym in LOT_SIZES:
        return LOT_SIZES[sym]
    stocks = get_fno_stocks()
    for s in stocks:
        if s["symbol"] == sym:
            return s.get("lot_size", 1)
    return 1


# ── Historical F&O data (local JSON store) ────────────────────────────────────

from pathlib import Path
import json

_BASE = Path(__file__).resolve().parents[1]
_FNO_HISTORY_PATH = _BASE / "storage" / "data" / "fno_history.json"
_FNO_WATCHLIST_PATH = _BASE / "storage" / "config" / "fno_watchlist.json"
_SAVED_STRATEGIES_PATH = _BASE / "storage" / "data" / "saved_strategies.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, data: Any):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to save %s: %s", path, exc)


# PCR / VIX history (append one entry per day on first load)

def _today_str() -> str:
    return date.today().isoformat()


def append_daily_fno_snapshot():
    """Append today's PCR + VIX to fno_history.json (called once per session)."""
    history = _load_json(_FNO_HISTORY_PATH, {"pcr": [], "vix": []})

    today = _today_str()
    # Don't double-write same day
    if history["pcr"] and history["pcr"][-1].get("date") == today:
        return

    nifty_pcr  = get_pcr("NIFTY")
    bn_pcr     = get_pcr("BANKNIFTY")
    vix_data   = get_vix()

    history["pcr"].append({
        "date":         today,
        "nifty_pcr":    nifty_pcr.get("pcr_oi", 0),
        "banknifty_pcr": bn_pcr.get("pcr_oi", 0),
    })
    history["vix"].append({
        "date": today,
        "vix":  vix_data.get("vix", 0),
    })

    # Keep last 60 trading days
    history["pcr"] = history["pcr"][-60:]
    history["vix"] = history["vix"][-60:]
    _save_json(_FNO_HISTORY_PATH, history)


def get_fno_history() -> dict:
    return _load_json(_FNO_HISTORY_PATH, {"pcr": [], "vix": []})


# F&O watchlist

def get_fno_watchlist() -> list[str]:
    data = _load_json(_FNO_WATCHLIST_PATH, {"symbols": ["NIFTY", "BANKNIFTY"]})
    return data.get("symbols", [])


def save_fno_watchlist(symbols: list[str]):
    _save_json(_FNO_WATCHLIST_PATH, {
        "symbols":    list(dict.fromkeys(s.upper().strip() for s in symbols if s.strip())),
        "updated_at": datetime.now().isoformat(),
    })


# Saved strategies

def get_saved_strategies() -> list[dict]:
    return _load_json(_SAVED_STRATEGIES_PATH, [])


def save_strategy(name: str, legs: list[dict]):
    strategies = get_saved_strategies()
    strategies = [s for s in strategies if s.get("name") != name]  # replace if exists
    strategies.append({"name": name, "legs": legs, "saved_at": datetime.now().isoformat()})
    _save_json(_SAVED_STRATEGIES_PATH, strategies)


def delete_strategy(name: str):
    strategies = [s for s in get_saved_strategies() if s.get("name") != name]
    _save_json(_SAVED_STRATEGIES_PATH, strategies)
