from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

from backend.config import get_settings
from backend.stock_universe import SYMBOL_ALIASES


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
}

PERIOD_TO_DAYS = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
}

YAHOO_EQUIVALENTS = {
    "TATAMOTORS": ["TATAMOTORS.NS", "TMPV.NS", "TMCV.NS", "TATAMOTORS.BO"],
    "LTM": ["LTM.NS", "LTIM.NS", "LTM.BO", "LTIM.BO"],
    "LTIM": ["LTIM.NS", "LTM.NS", "LTIM.BO", "LTM.BO"],
}


@dataclass(frozen=True)
class QuoteResult:
    symbol: str
    yahoo_symbol: str
    company_name: str
    current_price: float | None
    day_change_pct: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    volume: int | None
    market_cap: int | None
    exchange: str
    source: str = "Unknown"


def normalize_symbol(query: str) -> str:
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")
    clean = clean.replace("NSE:", "").replace("BSE:", "").replace("&", "")
    return SYMBOL_ALIASES.get(clean, clean.replace(" ", ""))


def yahoo_candidates(symbol: str) -> list[str]:
    normalized = normalize_symbol(symbol)
    if normalized in YAHOO_EQUIVALENTS:
        return YAHOO_EQUIVALENTS[normalized]
    return [f"{normalized}.NS", f"{normalized}.BO"]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    expected = ["Open", "High", "Low", "Close", "Volume"]
    for column in expected:
        if column not in df.columns:
            df[column] = 0
    df = df[expected].copy()
    for column in expected:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[df["Close"] > 0]
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _stored_setting(key: str, default: str = "") -> str:
    try:
        from backend.watchlist import get_app_setting

        return get_app_setting(key, default)
    except Exception:
        return default


def _fetch_yahoo_chart_history(candidate: str, period: str, interval: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(candidate)}"
    response = _session().get(
        url,
        params={
            "range": period,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("Yahoo chart returned no result.")
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    if not timestamps or not quotes:
        raise RuntimeError("Yahoo chart returned no candles.")
    df = pd.DataFrame(
        {
            "Open": quotes.get("open"),
            "High": quotes.get("high"),
            "Low": quotes.get("low"),
            "Close": quotes.get("close"),
            "Volume": quotes.get("volume"),
        },
        index=pd.to_datetime(timestamps, unit="s"),
    )
    return _clean_ohlcv(df)


def _nse_date(value: datetime) -> str:
    return value.strftime("%d-%m-%Y")


def _fetch_nse_history(symbol: str, period: str) -> pd.DataFrame:
    session = _session()
    session.get("https://www.nseindia.com", timeout=15)
    days = PERIOD_TO_DAYS.get(period, 365)
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    url = "https://www.nseindia.com/api/historical/cm/equity"
    response = session.get(
        url,
        params={
            "symbol": normalize_symbol(symbol),
            "series": '["EQ"]',
            "from": _nse_date(from_date),
            "to": _nse_date(to_date),
        },
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json().get("data") or []
    if not rows:
        raise RuntimeError("NSE historical API returned no rows.")
    df = pd.DataFrame(rows)
    column_map = {
        "CH_TIMESTAMP": "Date",
        "CH_OPENING_PRICE": "Open",
        "CH_TRADE_HIGH_PRICE": "High",
        "CH_TRADE_LOW_PRICE": "Low",
        "CH_CLOSING_PRICE": "Close",
        "CH_TOT_TRADED_QTY": "Volume",
    }
    df = df.rename(columns=column_map)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return _clean_ohlcv(df)


def _fetch_twelve_data_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    settings = get_settings()
    api_key = _stored_setting("TWELVE_DATA_API_KEY", settings.twelve_data_api_key)
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")
    tv_interval = "1day" if interval == "1d" else interval
    outputsize = min(5000, PERIOD_TO_DAYS.get(period, 365) + 20)
    response = _session().get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": f"{normalize_symbol(symbol)}:NSE",
            "interval": tv_interval,
            "outputsize": outputsize,
            "apikey": api_key,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("values") or []
    if not rows:
        raise RuntimeError(payload.get("message") or "Twelve Data returned no candles.")
    df = pd.DataFrame(rows)
    df = df.rename(
        columns={
            "datetime": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    df["Date"] = pd.to_datetime(df["Date"])
    return _clean_ohlcv(df.set_index("Date"))


def _fetch_alpha_vantage_history(symbol: str) -> pd.DataFrame:
    settings = get_settings()
    api_key = _stored_setting("ALPHA_VANTAGE_API_KEY", settings.alpha_vantage_api_key)
    if not api_key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured.")
    response = _session().get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": f"{normalize_symbol(symbol)}.BSE",
            "outputsize": "full",
            "apikey": api_key,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    series = payload.get("Time Series (Daily)") or {}
    if not series:
        raise RuntimeError(payload.get("Note") or payload.get("Error Message") or "Alpha Vantage returned no candles.")
    rows = []
    for date_value, candle in series.items():
        rows.append(
            {
                "Date": date_value,
                "Open": candle.get("1. open"),
                "High": candle.get("2. high"),
                "Low": candle.get("3. low"),
                "Close": candle.get("4. close"),
                "Volume": candle.get("6. volume"),
            }
        )
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return _clean_ohlcv(df.set_index("Date")).tail(400)


@lru_cache(maxsize=256)
def _cached_price_history(symbol: str, period: str, interval: str) -> tuple[str, str, pd.DataFrame]:
    normalized = normalize_symbol(symbol)
    errors: list[str] = []
    for provider_name, provider_symbol, fetcher in _history_providers(normalized, period, interval):
        try:
            data = fetcher()
            if not data.empty and len(data) >= 30:
                return provider_symbol, provider_name, data
            errors.append(f"{provider_name}: not enough candles")
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")

    raise RuntimeError(
        "No market data found from Yahoo chart, NSE, Twelve Data, or Alpha Vantage. "
        f"Provider errors: {' | '.join(errors[-8:])}"
    )


def _history_providers(symbol: str, period: str, interval: str):
    normalized = normalize_symbol(symbol)
    candidates = yahoo_candidates(normalized)
    providers = []
    for candidate in candidates:
        providers.append((f"Yahoo chart {candidate}", candidate, lambda c=candidate: _fetch_yahoo_chart_history(c, period, interval)))
    providers.extend(
        [
            ("NSE historical", f"{normalized}.NS", lambda: _fetch_nse_history(normalized, period)),
            ("Twelve Data", f"{normalized}.NS", lambda: _fetch_twelve_data_history(normalized, period, interval)),
            ("Alpha Vantage", f"{normalized}.BO", lambda: _fetch_alpha_vantage_history(normalized)),
        ]
    )
    return providers


def get_price_history(symbol: str, period: str = "1y", interval: str = "1d") -> tuple[str, pd.DataFrame]:
    provider_symbol, _source, data = _cached_price_history(symbol, period, interval)
    return provider_symbol, data.copy()


def get_price_history_with_source(symbol: str, period: str = "1y", interval: str = "1d") -> tuple[str, str, pd.DataFrame]:
    provider_symbol, source, data = _cached_price_history(symbol, period, interval)
    return provider_symbol, source, data.copy()


def collect_price_histories(symbol: str, period: str = "1y", interval: str = "1d") -> dict[str, Any]:
    histories: list[dict[str, Any]] = []
    status: list[dict[str, str]] = []
    for provider_name, provider_symbol, fetcher in _history_providers(symbol, period, interval):
        try:
            data = fetcher()
            if data.empty or len(data) < 30:
                raise RuntimeError("not enough candles")
            histories.append(
                {
                    "source": provider_name,
                    "symbol": provider_symbol,
                    "status": "ok",
                    "rows": len(data),
                    "start": str(data.index.min().date()),
                    "end": str(data.index.max().date()),
                    "data": data,
                }
            )
            status.append({"source": provider_name, "status": "ok", "message": f"{len(data)} candles"})
        except Exception as exc:
            status.append({"source": provider_name, "status": "error", "message": str(exc)[:220]})
    return {"symbol": normalize_symbol(symbol), "histories": histories, "status": status}


def _fetch_yahoo_quote(candidate: str) -> dict[str, Any]:
    response = _session().get(
        "https://query1.finance.yahoo.com/v7/finance/quote",
        params={"symbols": candidate},
        timeout=15,
    )
    response.raise_for_status()
    return ((response.json().get("quoteResponse") or {}).get("result") or [{}])[0]


def _fetch_nse_quote(symbol: str) -> dict[str, Any]:
    session = _session()
    session.get("https://www.nseindia.com", timeout=15)
    response = session.get(
        "https://www.nseindia.com/api/quote-equity",
        params={"symbol": normalize_symbol(symbol)},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_quote(symbol: str) -> QuoteResult:
    normalized = normalize_symbol(symbol)
    provider_symbol, source, history = get_price_history_with_source(normalized, period="1y", interval="1d")
    last = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else last
    current_price = _safe_float(last.get("Close"))
    previous_close = _safe_float(previous.get("Close"))
    day_change_pct = None
    if current_price and previous_close:
        day_change_pct = ((current_price - previous_close) / previous_close) * 100

    company_name = normalized
    market_cap = None
    high_52 = _safe_float(history["High"].tail(252).max())
    low_52 = _safe_float(history["Low"].tail(252).min())

    try:
        quote_data = _fetch_yahoo_quote(provider_symbol)
        company_name = quote_data.get("longName") or quote_data.get("shortName") or company_name
        current_price = _safe_float(quote_data.get("regularMarketPrice")) or current_price
        day_change_pct = _safe_float(quote_data.get("regularMarketChangePercent")) or day_change_pct
        high_52 = _safe_float(quote_data.get("fiftyTwoWeekHigh")) or high_52
        low_52 = _safe_float(quote_data.get("fiftyTwoWeekLow")) or low_52
        market_cap = _safe_int(quote_data.get("marketCap"))
    except Exception:
        pass

    if provider_symbol.endswith(".NS"):
        try:
            nse_quote = _fetch_nse_quote(normalized)
            info = nse_quote.get("info", {})
            price_info = nse_quote.get("priceInfo", {})
            metadata = nse_quote.get("metadata", {})
            company_name = info.get("companyName") or company_name
            current_price = _safe_float(price_info.get("lastPrice")) or current_price
            day_change_pct = _safe_float(price_info.get("pChange")) or day_change_pct
            high_52 = _safe_float(price_info.get("weekHighLow", {}).get("max")) or high_52
            low_52 = _safe_float(price_info.get("weekHighLow", {}).get("min")) or low_52
            market_cap = _safe_int(metadata.get("marketCap")) or market_cap
        except Exception:
            pass

    return QuoteResult(
        symbol=normalized,
        yahoo_symbol=provider_symbol,
        company_name=company_name,
        current_price=current_price,
        day_change_pct=day_change_pct,
        fifty_two_week_high=high_52,
        fifty_two_week_low=low_52,
        volume=_safe_int(last.get("Volume")),
        market_cap=market_cap,
        exchange="NSE" if provider_symbol.endswith(".NS") else "BSE",
        source=source,
    )
