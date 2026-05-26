from __future__ import annotations
import re
import time
import threading
import logging
from typing import Any, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_SESSION_ACTIVE = False

# ── Circuit breaker ──────────────────────────────────────────────────────────
# If Screener fails N times in a row, we mark it "down" for COOLOFF_SECONDS and
# every subsequent call returns an error immediately — the app never hangs.
_FAILURE_COUNT = 0
_CIRCUIT_OPEN_UNTIL = 0.0
_FAILURE_THRESHOLD = 3
_COOLOFF_SECONDS = 300        # 5-minute cool-off
_CB_LOCK = threading.Lock()

# Per-request budget. (connect_timeout, read_timeout) in seconds.
# Keep tight so the UI stays responsive even when Screener is slow.
_HTTP_TIMEOUT = (5, 8)


def _circuit_open() -> bool:
    return time.time() < _CIRCUIT_OPEN_UNTIL


def _record_failure(reason: str):
    global _FAILURE_COUNT, _CIRCUIT_OPEN_UNTIL
    with _CB_LOCK:
        _FAILURE_COUNT += 1
        if _FAILURE_COUNT >= _FAILURE_THRESHOLD and not _circuit_open():
            _CIRCUIT_OPEN_UNTIL = time.time() + _COOLOFF_SECONDS
            logger.warning(
                f"Screener.in circuit-breaker OPEN for {_COOLOFF_SECONDS}s "
                f"after {_FAILURE_COUNT} failures (last: {reason})"
            )


def _record_success():
    global _FAILURE_COUNT, _CIRCUIT_OPEN_UNTIL
    with _CB_LOCK:
        _FAILURE_COUNT = 0
        _CIRCUIT_OPEN_UNTIL = 0.0


def is_screener_healthy() -> bool:
    """Public health-check the UI can call to decide whether to show a banner."""
    return not _circuit_open()


def reset_circuit_breaker():
    """Force-reopen the circuit (used by 'Retry' button in the UI)."""
    global _FAILURE_COUNT, _CIRCUIT_OPEN_UNTIL
    with _CB_LOCK:
        _FAILURE_COUNT = 0
        _CIRCUIT_OPEN_UNTIL = 0.0
        logger.info("Screener circuit breaker manually reset.")


def get_circuit_status() -> dict:
    """Report current breaker state for debugging / status displays."""
    open_ = _circuit_open()
    return {
        "healthy":      not open_,
        "circuit_open": open_,
        "failure_count": _FAILURE_COUNT,
        "cooloff_remaining_seconds": max(0, int(_CIRCUIT_OPEN_UNTIL - time.time())),
    }


def configure_session(csrf_token: str, session_id: str) -> bool:
    """Inject Screener.in auth cookies into the shared session."""
    global _SESSION_ACTIVE
    for domain in [".screener.in", "www.screener.in"]:
        SESSION.cookies.set("csrftoken", csrf_token, domain=domain)
        SESSION.cookies.set("sessionid", session_id, domain=domain)
    SESSION.headers.update({
        "X-CSRFToken": csrf_token,
        "Referer": "https://www.screener.in/",
    })
    _SESSION_ACTIVE = True
    logger.info("Screener.in session configured.")
    return True


def _load_session_from_settings() -> bool:
    """Auto-load Screener credentials from settings.json on first use."""
    global _SESSION_ACTIVE
    if _SESSION_ACTIVE:
        return True
    try:
        from storage.file_store import get_settings
        s = get_settings()
        csrf = s.get("screener_csrf", "")
        sid = s.get("screener_session", "")
        if csrf and sid:
            configure_session(csrf, sid)
            return True
    except Exception as e:
        logger.debug(f"Could not auto-load Screener session: {e}")
    return False


def get_screener_status() -> dict:
    """Return current auth state."""
    _load_session_from_settings()
    return {
        "authenticated": _SESSION_ACTIVE,
        "cookies": {c.name: c.value[:8] + "..." for c in SESSION.cookies},
    }


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace(".NS", "").replace(".BO", "").replace("-EQ", "")


def _clean_num(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[,%\s₹]", "", str(text).strip())
    cleaned = cleaned.replace("Cr", "").replace("cr", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", cleaned)
    return float(m.group(0)) if m else None


def _parse_ratio(soup: BeautifulSoup, label: str) -> Optional[float]:
    for li in soup.select("li.flex.flex-space-between, li.flex, #top-ratios li"):
        name_el = li.select_one(".name, span:first-child")
        val_el = li.select_one(".number, span.number, .value")
        if name_el and val_el:
            if label.lower() in name_el.get_text(" ", strip=True).lower():
                return _clean_num(val_el.get_text(" ", strip=True))
    text = soup.get_text(" ", strip=True)
    m = re.search(rf"{re.escape(label)}\s+(-?\d[\d,\.]*)", text, re.IGNORECASE)
    return _clean_num(m.group(1)) if m else None


def _parse_table(section) -> dict:
    """Parse a data-table in a screener section into {row_label: {period: value}}."""
    if section is None:
        return {}
    result = {}
    table = section.find("table", class_="data-table")
    if not table:
        return {}
    thead = table.find("thead")
    headers = []
    if thead:
        for th in thead.find_all("th"):
            headers.append(th.get_text(" ", strip=True))
    tbody = table.find("tbody")
    if not tbody:
        return {}
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        row_label = cells[0].get_text(" ", strip=True)
        row_data = {}
        for i, cell in enumerate(cells[1:], 1):
            col = headers[i] if i < len(headers) else f"col_{i}"
            row_data[col] = _clean_num(cell.get_text(" ", strip=True))
        result[row_label] = row_data
    return result


def _get_page(symbol: str, suffix: str = "") -> Optional[BeautifulSoup]:
    # Short-circuit when the breaker is open — never let a Screener outage
    # block the calling page.
    if _circuit_open():
        logger.debug("Screener circuit open — skipping fetch")
        return None

    _load_session_from_settings()
    clean = normalize_symbol(symbol)
    urls = [
        f"https://www.screener.in/company/{clean}/consolidated/{suffix}",
        f"https://www.screener.in/company/{clean}/{suffix}",
    ]
    last_error: Optional[str] = None
    for url in urls:
        try:
            resp = SESSION.get(url, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 200:
                _record_success()
                return BeautifulSoup(resp.text, "html.parser")
            elif resp.status_code == 404:
                # 404 = the URL variant is wrong, not a Screener outage — try next
                continue
            else:
                last_error = f"HTTP {resp.status_code}"
                logger.warning(f"Screener {url} → {resp.status_code}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = f"{type(e).__name__}"
            logger.warning(f"Screener fetch failed {url}: {e}")
        except Exception as e:
            last_error = str(e)[:80]
            logger.warning(f"Screener fetch failed {url}: {e}")

    if last_error:
        _record_failure(last_error)
    return None


def search_company(query: str) -> list[dict]:
    """Search Screener.in for a company by name or symbol."""
    if _circuit_open():
        return []
    _load_session_from_settings()
    try:
        url = f"https://www.screener.in/api/company/search/?q={query}&v=3&fts=1"
        resp = SESSION.get(url, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200:
            _record_success()
            data = resp.json()
            return [{"name": r.get("name", ""), "url": r.get("url", ""), "symbol": r.get("name", "")} for r in data]
    except (requests.Timeout, requests.ConnectionError) as e:
        _record_failure(type(e).__name__)
        logger.warning(f"Screener search failed: {e}")
    except Exception as e:
        logger.warning(f"Screener search failed: {e}")
    return []


def _parse_shareholding(soup: BeautifulSoup) -> dict:
    """Parse shareholding section including full history table."""
    section = soup.find("section", id="shareholding")
    sh_table = _parse_table(section)

    promoter = fii = dii = public = pledge = None
    for key, vals in sh_table.items():
        kl = key.lower()
        last_val = list(vals.values())[-1] if vals else None
        if "promoter" in kl and "pledge" not in kl:
            promoter = last_val
        elif "fii" in kl or "foreign" in kl:
            fii = last_val
        elif "dii" in kl or "domestic" in kl:
            dii = last_val
        elif "public" in kl or "retail" in kl:
            public = last_val
        elif "pledge" in kl:
            pledge = last_val

    return {
        "promoter": promoter,
        "fii": fii,
        "dii": dii,
        "public": public,
        "pledge": pledge,
        "history": sh_table,
    }


_INDEX_NAME_PATTERNS = re.compile(
    r"^(BSE|Nifty|S&P|CNX|NSE|Sensex|Dollex)", re.IGNORECASE
)


_UI_NOISE_NAMES = {"editcolumns", "edit columns", "compare", "addtowatchlist", "add to watchlist"}


def _looks_like_index(name: str, symbol: str) -> bool:
    """Filter out index/benchmark/UI entries that Screener mixes into the peers section."""
    if not name:
        return True
    n = name.lower().replace(" ", "")
    if n in _UI_NOISE_NAMES:
        return True
    if _INDEX_NAME_PATTERNS.search(name):
        return True
    if symbol and symbol.isdigit():
        return True
    s = (symbol or "").upper()
    if s in {"NIFTY", "CNX500", "SENSEX"}:
        return True
    if s.startswith(("CNX", "NIFTY", "NIFT", "BSE", "NSE", "NI", "NF", "NY", "ENHANCE")):
        return True
    return False


def _parse_peers(soup: BeautifulSoup) -> list[dict]:
    """Parse the peer-comparison table from Screener.

    Returns rows with rich columns (PE, ROCE, Market Cap, etc.) when the
    table is available. Filters out index entries (BSE Sensex, Nifty 50…)
    that Screener mixes into the peers section.
    """
    peers_section = soup.find("section", id="peers")
    if not peers_section:
        return []

    table = peers_section.find("table", class_="data-table")
    if table:
        hdrs = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        rows = []
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            row = {hdrs[i] if i < len(hdrs) else f"c{i}": c.get_text(" ", strip=True) for i, c in enumerate(cells)}
            link = cells[0].find("a") if cells else None
            sym = ""
            if link and link.get("href"):
                m = re.search(r"/company/([^/]+)/", link["href"])
                if m:
                    sym = m.group(1)
                    row["_symbol"] = sym
            name = row.get(hdrs[0]) if hdrs else (link.get_text(strip=True) if link else "")
            row["name"] = name
            if _looks_like_index(name, sym):
                continue
            rows.append(row)
        if rows:
            return rows[:20]

    # Drop the "benchmarks" paragraph — Screener lists indices the company
    # belongs to (BSE Sensex, Nifty 50…), which are not peer companies.
    bench = peers_section.find(id="benchmarks")
    if bench:
        bench.decompose()

    # Fallback: extract company links from peers section, filter indices
    peers = []
    seen = set()
    for a in peers_section.find_all("a", href=re.compile(r"/company/")):
        m = re.search(r"/company/([^/]+)/", a["href"])
        if not m:
            continue
        sym = m.group(1)
        name = a.get_text(strip=True)
        if not name or sym in seen or _looks_like_index(name, sym):
            continue
        seen.add(sym)
        peers.append({"name": name, "_symbol": sym})
    return peers[:20]


def _parse_insights(soup: BeautifulSoup) -> list[str]:
    """Parse auth-only insights section."""
    insights = []
    section = soup.find("section", id="insights")
    if section:
        for li in section.find_all("li"):
            text = li.get_text(" ", strip=True)
            if text:
                insights.append(text)
    return insights[:15]


def _parse_historical_ratios(soup: BeautifulSoup) -> dict:
    """Parse 10-year historical ratios table (section id='ratios')."""
    section = soup.find("section", id="ratios")
    return _parse_table(section)


def _parse_documents(soup: BeautifulSoup) -> list[dict]:
    """Parse annual reports / concall links if available."""
    docs = []
    section = soup.find("section", id="documents")
    if not section:
        return docs
    for a in section.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text:
            docs.append({"title": text, "url": a["href"]})
    return docs[:20]


def get_full_screener_data(symbol: str) -> dict[str, Any]:
    """Fetch all available Screener.in data for a symbol in one HTTP call.

    Returns a dict with 'error' set (and otherwise empty) when:
      - Screener is unreachable
      - The circuit breaker is open after repeated failures
    Callers MUST check `data.get("error")` and degrade gracefully.
    """
    clean = normalize_symbol(symbol)
    if _circuit_open():
        return {
            "symbol": clean,
            "error": "Screener.in temporarily unavailable (circuit-breaker open)",
            "circuit_open": True,
            "cooloff_remaining": max(0, int(_CIRCUIT_OPEN_UNTIL - time.time())),
            "source": "Screener.in (skipped)",
        }
    soup = _get_page(clean)
    if not soup:
        return {
            "symbol": clean,
            "error": "Screener.in unavailable (timeout or no data)",
            "circuit_open": _circuit_open(),
            "source": "Screener.in (failed)",
        }

    # Overview
    name = ""
    h1 = soup.find("h1", class_=re.compile(r"h\d|shrink"))
    if not h1:
        h1 = soup.find("h1")
    if h1:
        name = h1.get_text(" ", strip=True)

    sector, industry = "", ""
    # New Screener layout: sector links live in <a href="/market/IN.../">
    # with title attributes "Broad Sector" / "Sector" / "Industry".
    for a in soup.select("a[href*='/market/'][title]"):
        title = (a.get("title") or "").strip().lower()
        text = a.get_text(strip=True)
        if not text:
            continue
        if title in ("broad sector", "sector") and not sector:
            sector = text
        elif title == "industry" and not industry:
            industry = text
    if not sector:
        # Old breadcrumb fallback
        crumbs = soup.select("ol.breadcrumb a, .breadcrumb a, a[href*='/industry/'], a[href*='/sector/']")
        if crumbs:
            sector = crumbs[-2].get_text(strip=True) if len(crumbs) >= 2 else ""
            industry = industry or crumbs[-1].get_text(strip=True)

    about_el = soup.select_one(".about p, #about p, .company-description p")
    about = about_el.get_text(" ", strip=True)[:600] if about_el else ""

    # NSE/BSE codes
    nse_code = bse_code = ""
    for a in soup.select("a[href*='nseindia'], a[href*='bseindia']"):
        href = a.get("href", "")
        if "nse" in href.lower():
            nse_code = a.get_text(strip=True)
        elif "bse" in href.lower():
            bse_code = a.get_text(strip=True)

    # Key ratios from top-ratios section
    def r(label):
        return _parse_ratio(soup, label)

    market_cap = r("Market Cap")
    current_price = r("Current Price")
    book_value_ps = r("Book Value")  # per share

    # Financial statements (needed for derived ratios)
    pl_annual = _parse_table(soup.find("section", id="profit-loss"))
    pl_quarterly = _parse_table(soup.find("section", id="quarters"))
    bs_data = _parse_table(soup.find("section", id="balance-sheet"))
    cf_data = _parse_table(soup.find("section", id="cash-flow"))
    historical_ratios = _parse_historical_ratios(soup)

    def _latest(table: dict, row: str) -> Optional[float]:
        row_data = table.get(row, {})
        vals = [v for v in row_data.values() if v is not None]
        return vals[-1] if vals else None

    # Derive ratios from tables where not in top-ratios
    opm = _latest(pl_annual, "OPM %")
    eps = _latest(pl_annual, "EPS in Rs")
    net_profit = _latest(pl_annual, "Net Profit +")
    sales = _latest(pl_annual, "Sales +")
    interest = _latest(pl_annual, "Interest")
    op_profit = _latest(pl_annual, "Operating Profit")
    borrowings = _latest(bs_data, "Borrowings +")
    equity_cap = _latest(bs_data, "Equity Capital")
    reserves = _latest(bs_data, "Reserves")

    npm = round(net_profit / sales * 100, 2) if net_profit and sales and sales > 0 else None
    equity_total = (equity_cap or 0) + (reserves or 0)
    debt_equity = round(borrowings / equity_total, 2) if borrowings and equity_total and equity_total > 0 else None
    interest_coverage = round(op_profit / interest, 1) if op_profit and interest and interest > 0 else None
    pb = round(current_price / book_value_ps, 2) if current_price and book_value_ps and book_value_ps > 0 else None

    # Shareholding (promoter from latest quarter)
    shareholding = _parse_shareholding(soup)
    promoter_holding = shareholding.get("promoter")

    ratios = {
        "market_cap": market_cap,
        "current_price": current_price,
        "high_52w": r("High / Low"),
        "pe": r("Stock P/E"),
        "pb": pb,
        "book_value": book_value_ps,
        "dividend_yield": r("Dividend Yield"),
        "roce": r("ROCE"),
        "roe": r("ROE"),
        "face_value": r("Face Value"),
        "eps": eps,
        "opm": opm,
        "npm": npm,
        "debt_equity": debt_equity,
        "interest_coverage": interest_coverage,
        "sales_growth": r("Sales growth"),
        "profit_growth": r("Profit growth"),
        "promoter_holding": promoter_holding,
    }

    # Peers
    peers = _parse_peers(soup)

    # Pros/cons
    pros = [li.get_text(" ", strip=True) for li in soup.select(".pros li, .strengths li, #pros li")][:10]
    cons = [li.get_text(" ", strip=True) for li in soup.select(".cons li, .weaknesses li, #cons li")][:10]

    # Auth-only sections
    insights = _parse_insights(soup)
    documents = _parse_documents(soup)

    return {
        "symbol": clean,
        "name": name,
        "sector": sector,
        "industry": industry,
        "nse_code": nse_code,
        "bse_code": bse_code,
        "about": about,
        "ratios": ratios,
        "pl": {"annual": pl_annual, "quarterly": pl_quarterly},
        "balance_sheet": bs_data,
        "cash_flow": cf_data,
        "historical_ratios": historical_ratios,
        "shareholding": shareholding,
        "peers": peers,
        "pros": pros,
        "cons": cons,
        "insights": insights,
        "documents": documents,
        "authenticated": _SESSION_ACTIVE,
        "source": "Screener.in",
        "fetched_at": time.time(),
    }
