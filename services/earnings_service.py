"""
Earnings calendar service for NSE/BSE.

Sources (all free, no API key):
  1. NSE corporate announcements / board meetings API  -> upcoming results
  2. Screener.in quarterly P&L                          -> historical earnings + sentiment

Public API:
  - get_upcoming_results(days_ahead=14) -> list of upcoming board meetings (results)
  - get_recent_earnings(symbol)         -> last 4-8 quarters with sentiment tag
  - classify_earnings(sales_growth_pct, profit_growth_pct) -> "POSITIVE"|"NEUTRAL"|"NEGATIVE"
  - get_earnings_calendar(universe_symbols) -> upcoming results + last quarter sentiment per stock
"""
from __future__ import annotations
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# NSE session (re-uses headers from nse_service via duplicate session here)
# ─────────────────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
    "Connection": "keep-alive",
}

_SESSION: Optional[requests.Session] = None
_SESSION_TS: float = 0
_SESSION_TTL = 300
_SESSION_LOCK = threading.Lock()


def _session() -> requests.Session:
    global _SESSION, _SESSION_TS
    with _SESSION_LOCK:
        if _SESSION is None or (time.time() - _SESSION_TS) > _SESSION_TTL:
            s = requests.Session()
            s.headers.update(_HEADERS)
            try:
                s.get("https://www.nseindia.com", timeout=8)
            except Exception:
                pass
            _SESSION = s
            _SESSION_TS = time.time()
        return _SESSION


# ─────────────────────────────────────────────────────────────────────────────
# Upcoming results (NSE board meetings = result-announcement meetings)
# ─────────────────────────────────────────────────────────────────────────────
def get_upcoming_results(days_ahead: int = 14) -> List[Dict]:
    """
    Fetch upcoming board meetings where the agenda includes 'Financial Results'.
    Returns a list of {symbol, company, date, purpose} sorted by date.
    """
    sess = _session()
    today = datetime.now().date()
    upto  = today + timedelta(days=days_ahead)
    url = "https://www.nseindia.com/api/corporate-board-meetings"
    params = {"index": "equities",
              "from_date": today.strftime("%d-%m-%Y"),
              "to_date":   upto.strftime("%d-%m-%Y")}
    try:
        resp = sess.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"NSE board meetings → {resp.status_code}")
            return []
        data = resp.json()
    except Exception as e:
        logger.warning(f"NSE board meetings failed: {e}")
        return []

    rows = data if isinstance(data, list) else data.get("data", [])
    out: List[Dict] = []
    for r in rows:
        purpose = (r.get("bm_purpose") or r.get("purpose") or "").strip()
        # Only result-related meetings
        if not any(kw in purpose.lower() for kw in ["financial result", "quarterly result",
                                                     "audited", "unaudited", "results"]):
            continue
        sym = r.get("bm_symbol") or r.get("symbol") or ""
        date_str = r.get("bm_date") or r.get("meetingdate") or ""
        out.append({
            "symbol":  sym.strip(),
            "company": (r.get("sm_name") or r.get("companyname") or sym).strip(),
            "date":    date_str.strip(),
            "purpose": purpose[:120],
        })
    out.sort(key=lambda x: x["date"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment classification
# ─────────────────────────────────────────────────────────────────────────────
def classify_earnings(sales_growth_pct: Optional[float],
                      profit_growth_pct: Optional[float]) -> Dict:
    """
    Classify a quarter's earnings:
      POSITIVE  — both growth > thresholds
      NEUTRAL   — mixed
      NEGATIVE  — declining sales or profit
    """
    sg = sales_growth_pct
    pg = profit_growth_pct

    if sg is None and pg is None:
        return {"label": "UNKNOWN", "color": "neutral", "score": 0,
                "reason": "Growth data unavailable"}

    score = 0
    reasons = []
    if pg is not None:
        if pg >= 25:    score += 3; reasons.append(f"Profit grew {pg:.1f}%")
        elif pg >= 15:  score += 2; reasons.append(f"Profit grew {pg:.1f}%")
        elif pg >= 5:   score += 1; reasons.append(f"Modest profit growth {pg:.1f}%")
        elif pg >= -5:  reasons.append(f"Flat profit ({pg:+.1f}%)")
        elif pg >= -20: score -= 2; reasons.append(f"Profit declined {pg:.1f}%")
        else:           score -= 3; reasons.append(f"Profit collapsed {pg:.1f}%")

    if sg is not None:
        if sg >= 20:    score += 2; reasons.append(f"Sales grew {sg:.1f}%")
        elif sg >= 10:  score += 1; reasons.append(f"Sales grew {sg:.1f}%")
        elif sg >= 0:   reasons.append(f"Sales flat ({sg:+.1f}%)")
        else:           score -= 2; reasons.append(f"Sales declined {sg:.1f}%")

    if score >= 3:    label, color = "POSITIVE", "bullish"
    elif score >= 1:  label, color = "MILDLY POSITIVE", "bullish"
    elif score <= -3: label, color = "NEGATIVE", "bearish"
    elif score <= -1: label, color = "MILDLY NEGATIVE", "bearish"
    else:             label, color = "NEUTRAL", "neutral"

    return {"label": label, "color": color, "score": score,
            "reason": "; ".join(reasons[:3])}


# ─────────────────────────────────────────────────────────────────────────────
# Recent earnings from Screener.in quarterly P&L
# ─────────────────────────────────────────────────────────────────────────────
def get_recent_earnings(symbol: str, n_quarters: int = 4) -> List[Dict]:
    """
    Fetch last `n_quarters` of quarterly earnings for a symbol from Screener,
    classify each one as positive/neutral/negative.
    Returns list ordered newest → oldest.
    """
    try:
        from services.screener_service import get_full_screener_data
        data = get_full_screener_data(symbol)
    except Exception as e:
        logger.debug(f"Screener fetch failed for {symbol}: {e}")
        return []

    pl = (data or {}).get("pl") or {}
    quarterly = pl.get("quarterly") or {}
    if not quarterly:
        return []

    # Quarterly is dict-of-dicts: row_label -> {quarter_label: value}
    sales_row = quarterly.get("Sales +") or quarterly.get("Sales") or {}
    np_row    = quarterly.get("Net Profit +") or quarterly.get("Net Profit") or {}
    opm_row   = quarterly.get("OPM %") or {}

    quarters = list(sales_row.keys())[-n_quarters:]  # most recent N
    results: List[Dict] = []
    sales_vals = list(sales_row.values())
    np_vals = list(np_row.values())

    for i, q in enumerate(quarters):
        idx = list(sales_row.keys()).index(q)
        sales_now = _to_float(sales_row.get(q))
        np_now    = _to_float(np_row.get(q))
        # YoY comparison if available
        sg_yoy = None
        pg_yoy = None
        if idx >= 4:
            sales_yoy = _to_float(sales_vals[idx - 4])
            np_yoy = _to_float(np_vals[idx - 4])
            if sales_yoy and sales_now is not None:
                sg_yoy = (sales_now - sales_yoy) / abs(sales_yoy) * 100
            if np_yoy and np_now is not None:
                pg_yoy = (np_now - np_yoy) / abs(np_yoy) * 100

        cls = classify_earnings(sg_yoy, pg_yoy)
        results.append({
            "symbol":  symbol,
            "quarter": q,
            "sales":   sales_now,
            "net_profit": np_now,
            "opm":     _to_float(opm_row.get(q)),
            "sales_growth_yoy":  sg_yoy,
            "profit_growth_yoy": pg_yoy,
            "sentiment": cls["label"],
            "sentiment_color": cls["color"],
            "sentiment_reason": cls["reason"],
            "score": cls["score"],
        })
    results.reverse()  # newest first
    return results


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        # Strip commas / % / + from Screener strings
        s = str(v).replace(",", "").replace("%", "").replace("+", "").strip()
        if s in ("", "-", "—"):
            return None
        return float(s)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Combined earnings calendar for a list of symbols
# ─────────────────────────────────────────────────────────────────────────────
def get_earnings_calendar(symbols: List[str],
                          days_ahead: int = 14,
                          fetch_recent: bool = True,
                          max_workers: int = 6) -> Dict:
    """
    For a universe of symbols return:
      - upcoming: list of upcoming result announcements that match those symbols
      - recent: per-symbol last quarter snapshot with sentiment

    Setting fetch_recent=False skips the slow Screener fetches and only returns upcoming.
    """
    upcoming_all = get_upcoming_results(days_ahead=days_ahead)
    sym_set = {s.upper().strip() for s in symbols}
    upcoming = [u for u in upcoming_all if u["symbol"].upper().strip() in sym_set]

    recent: Dict[str, List[Dict]] = {}
    if fetch_recent:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(get_recent_earnings, s, 1): s for s in symbols}
            for f in as_completed(futs):
                sym = futs[f]
                try:
                    recent[sym] = f.result() or []
                except Exception:
                    recent[sym] = []
    return {"upcoming": upcoming, "recent": recent}
