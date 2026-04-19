from __future__ import annotations

import re
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup

from backend.stock_data import normalize_symbol, yahoo_candidates


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

TRENDLYNE_IDS = {
    "RELIANCE": ("1127", "reliance-industries-ltd"),
    "TCS": ("1372", "tata-consultancy-services-ltd"),
    "INFY": ("630", "infosys-ltd"),
    "HDFCBANK": ("533", "hdfc-bank-ltd"),
    "TATAMOTORS": ("1362", "tata-motors-ltd"),
}


def _clean_number(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("%", "").replace("x", "").strip()
    match = re.search(r"-?\d+(\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def _parse_screener_ratio(soup: BeautifulSoup, label: str) -> float | None:
    for li in soup.select("li.flex.flex-space-between"):
        name = li.select_one(".name")
        value = li.select_one(".number")
        if name and value and label.lower() in name.get_text(" ", strip=True).lower():
            return _clean_number(value.get_text(" ", strip=True))
    text = soup.get_text(" ", strip=True)
    pattern = rf"{re.escape(label)}\s+(-?\d+(\.\d+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def fetch_screener_fundamentals(symbol: str) -> dict[str, Any]:
    clean = normalize_symbol(symbol)
    urls = [
        f"https://www.screener.in/company/{clean}/consolidated/",
        f"https://www.screener.in/company/{clean}/",
    ]
    last_error = ""
    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=12)
            if response.status_code != 200:
                last_error = f"Screener returned HTTP {response.status_code}"
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            return {
                "PE Ratio": _parse_screener_ratio(soup, "Stock P/E"),
                "PB Ratio": _parse_screener_ratio(soup, "Price to book value"),
                "ROE": _parse_screener_ratio(soup, "ROE"),
                "ROCE": _parse_screener_ratio(soup, "ROCE"),
                "Debt to Equity": _parse_screener_ratio(soup, "Debt to equity"),
                "Revenue Growth": _parse_screener_ratio(soup, "Sales growth"),
                "Profit Growth": _parse_screener_ratio(soup, "Profit growth"),
                "Promoter Holding": _parse_screener_ratio(soup, "Promoter holding"),
                "Dividend Yield": _parse_screener_ratio(soup, "Dividend Yield"),
                "Source": "Screener.in",
            }
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "Screener data unavailable.")


def fetch_yahoo_direct_fundamentals(symbol: str) -> dict[str, Any]:
    for candidate in yahoo_candidates(symbol):
        try:
            response = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": candidate},
                headers=HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            info = ((response.json().get("quoteResponse") or {}).get("result") or [{}])[0]
            if info:
                return {
                    "PE Ratio": info.get("trailingPE") or info.get("forwardPE"),
                    "PB Ratio": info.get("priceToBook"),
                    "ROE": None,
                    "ROCE": None,
                    "Debt to Equity": info.get("debtToEquity"),
                    "Revenue Growth": None,
                    "Profit Growth": None,
                    "Promoter Holding": None,
                    "Dividend Yield": (info.get("dividendYield") * 100) if info.get("dividendYield") else None,
                    "Source": "Yahoo Finance direct quote",
                }
        except Exception:
            continue
    return {
        "PE Ratio": None,
        "PB Ratio": None,
        "ROE": None,
        "ROCE": None,
        "Debt to Equity": None,
        "Revenue Growth": None,
        "Profit Growth": None,
        "Promoter Holding": None,
        "Dividend Yield": None,
        "Source": "Fallback mock parser structure",
    }


def fetch_trendlyne_snapshot(symbol: str) -> dict[str, Any]:
    clean = normalize_symbol(symbol)
    if clean in TRENDLYNE_IDS:
        stock_id, slug = TRENDLYNE_IDS[clean]
        search_url = f"https://trendlyne.com/equity/{stock_id}/{clean}/{slug}/"
    else:
        search_url = f"https://trendlyne.com/equity/{clean}/"
    response = requests.get(search_url, headers=HEADERS, timeout=12, allow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(f"Trendlyne returned HTTP {response.status_code}")
    soup = BeautifulSoup(response.text, "html.parser")
    raw_text = unescape(response.text)
    text = soup.get_text(" ", strip=True)
    if clean not in text.upper():
        raise RuntimeError("Trendlyne symbol page did not match the requested stock.")

    def find_after(label: str) -> float | None:
        json_match = re.search(
            rf'"title"\s*:\s*"{re.escape(label)}"\s*,\s*"value"\s*:\s*(-?[\d,.]+)',
            raw_text,
            flags=re.IGNORECASE,
        )
        if json_match:
            return _clean_number(json_match.group(1))
        raw_match = re.search(rf"{re.escape(label)}\s*:?\s*(-?[\d,.]+)", raw_text, flags=re.IGNORECASE)
        if raw_match:
            return _clean_number(raw_match.group(1))
        match = re.search(rf"{re.escape(label)}\s*:?\s*(-?[\d,.]+)", text, flags=re.IGNORECASE)
        return _clean_number(match.group(1)) if match else None

    return {
        "Trendlyne Market Cap Cr": find_after("Market Capitalization"),
        "Trendlyne PE TTM": find_after("PE TTM"),
        "Trendlyne PB": find_after("Price to Book") or find_after("Price to Book Value Adjusted"),
        "Trendlyne Momentum Score": find_after("Momentum Score"),
        "Trendlyne Valuation Score": find_after("Valuation Score"),
        "Trendlyne RSI": find_after("RSI"),
        "Trendlyne SMA 50": find_after("SMA 50"),
        "Trendlyne SMA 200": find_after("SMA 200"),
        "Trendlyne Source": response.url,
    }


def get_fundamentals(symbol: str) -> dict[str, Any]:
    trendlyne = {}
    try:
        trendlyne = fetch_trendlyne_snapshot(symbol)
    except Exception:
        trendlyne = {"Trendlyne Source": "Unavailable or blocked"}

    try:
        data = fetch_screener_fundamentals(symbol)
        if any(value is not None for key, value in data.items() if key != "Source"):
            return {**data, **trendlyne}
    except Exception:
        pass
    return {**fetch_yahoo_direct_fundamentals(symbol), **trendlyne}
