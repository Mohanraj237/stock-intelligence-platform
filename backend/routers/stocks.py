"""Per-stock endpoints: quote, OHLCV, indicators, fundamentals, AI verdict, chart analysis."""
from __future__ import annotations
import logging
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.deps import run_sync
from backend.schemas import (
    Quote, OHLCVResponse, OHLCVBar, Indicators, Fundamentals, AIVerdict,
    StockSnapshot, ChartAnalysis, QuarterlyRow,
)
from backend.schemas.common import (
    Timeframe, TIMEFRAME_TO_YF_INTERVAL, TIMEFRAME_TO_YF_PERIOD, Verdict,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{symbol}/quote", response_model=Quote)
async def quote(symbol: str, region: str = Query("IN")) -> Quote:
    if region == "US":
        from services.us_market_service import get_quote as us_get_quote
        raw = await run_sync(us_get_quote, symbol)
        if not raw:
            raise HTTPException(status_code=404, detail=f"No quote for {symbol}")
        return Quote(
            symbol=symbol.upper(),
            company=raw.get("name"),
            last_price=float(raw.get("price") or 0),
            change=float(raw.get("change") or 0),
            change_pct=float(raw.get("change_pct") or 0),
            open=raw.get("open"),
            high=raw.get("high"),
            low=raw.get("low"),
            prev_close=raw.get("prev_close"),
            volume=raw.get("volume"),
            week52_high=raw.get("year_high"),
            week52_low=raw.get("year_low"),
            market_cap=raw.get("market_cap"),
            sector=raw.get("sector"),
            industry=raw.get("industry"),
        )
    from services.nse_service import get_quote
    raw = await run_sync(get_quote, symbol)
    if not raw:
        raise HTTPException(status_code=404, detail=f"No quote for {symbol}")
    return Quote(
        symbol=symbol.upper(),
        company=raw.get("companyName") or raw.get("company"),
        last_price=float(raw.get("lastPrice") or raw.get("last") or 0),
        change=float(raw.get("change") or 0),
        change_pct=float(raw.get("pChange") or raw.get("change_pct") or 0),
        open=raw.get("open"),
        high=raw.get("dayHigh"),
        low=raw.get("dayLow"),
        prev_close=raw.get("previousClose"),
        volume=raw.get("totalTradedVolume"),
        week52_high=raw.get("yearHigh"),
        week52_low=raw.get("yearLow"),
        market_cap=raw.get("marketCap"),
        sector=raw.get("sector"),
        industry=raw.get("industry"),
    )


@router.get("/{symbol}/ohlcv", response_model=OHLCVResponse)
async def ohlcv(
    symbol: str,
    region: str = Query("IN"),
    timeframe: Timeframe = Query(Timeframe.DAILY),
    period: Optional[str] = Query(None, description="Override default period (e.g. 6mo, 2y, max)"),
) -> OHLCVResponse:
    from services.market_data_service import get_ohlcv_history
    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    yf_period = period or TIMEFRAME_TO_YF_PERIOD[timeframe]
    df = await run_sync(get_ohlcv_history, symbol, yf_period, interval, region)
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"No OHLCV for {symbol} @ {timeframe.value}")
    bars: list[OHLCVBar] = []
    for ts, row in df.iterrows():
        try:
            bars.append(OHLCVBar(
                time=int(ts.timestamp()),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume") or 0) if "Volume" in row else None,
            ))
        except Exception:
            continue
    return OHLCVResponse(symbol=symbol.upper(), timeframe=timeframe, bars=bars)


@router.get("/{symbol}/indicators", response_model=Indicators)
async def indicators(symbol: str, region: str = Query("IN"), timeframe: Timeframe = Query(Timeframe.DAILY)) -> Indicators:
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    period = TIMEFRAME_TO_YF_PERIOD[timeframe]
    df = await run_sync(get_ohlcv_history, symbol, period, interval, region)
    if df is None or len(df) < 5:
        raise HTTPException(status_code=404, detail=f"Not enough data for {symbol}")
    ind = await run_sync(compute_indicators_from_ohlcv, df)
    return Indicators(**{k: ind.get(k) for k in Indicators.model_fields.keys() if k in ind})


@router.get("/{symbol}/fundamentals", response_model=Fundamentals)
async def fundamentals(symbol: str, region: str = Query("IN")) -> Fundamentals:
    if region == "US":
        from services.us_market_service import get_us_fundamentals
        data = await run_sync(get_us_fundamentals, symbol)
        data = data or {}
        if data.get("error"):
            return Fundamentals(error=data.get("error"))
        # get_us_fundamentals returns ratios nested under "ratios" key
        r = data.get("ratios") or {}
        # Also fetch live quote for market cap and current price
        try:
            from services.us_market_service import get_quote as us_get_quote
            q_raw = await run_sync(us_get_quote, symbol)
        except Exception:
            q_raw = {}
        q_raw = q_raw or {}
        return Fundamentals(
            symbol=symbol.upper(),
            name=q_raw.get("name") or symbol.upper(),
            sector=data.get("sector"),
            industry=data.get("industry"),
            market_cap=q_raw.get("market_cap"),
            pe=r.get("pe"),
            pb=r.get("pb"),
            book_value=r.get("book_value"),
            dividend_yield=r.get("div_yield"),
            eps=r.get("eps"),
            roe=r.get("roe"),
            opm=r.get("operating_margin"),
            npm=r.get("profit_margin"),
            sales_growth=r.get("revenue_growth"),
            profit_growth=r.get("earnings_growth"),
            debt_to_equity=r.get("debt_equity"),
            about=data.get("description"),
            pros=[],
            cons=[],
            insights=[],
            peers=[],
        )
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol)
    data = data or {}
    if data.get("error"):
        return Fundamentals(error=data.get("error"))
    ratios = data.get("ratios", {}) or {}
    sh = data.get("shareholding", {}) or {}
    return Fundamentals(
        symbol=symbol.upper(),
        name=data.get("name"),
        sector=data.get("sector"),
        industry=data.get("industry"),
        market_cap=ratios.get("market_cap"),
        pe=ratios.get("pe"),
        pb=ratios.get("pb"),
        book_value=ratios.get("book_value"),
        dividend_yield=ratios.get("dividend_yield"),
        eps=ratios.get("eps"),
        roe=ratios.get("roe"),
        roce=ratios.get("roce"),
        opm=ratios.get("opm"),
        npm=ratios.get("npm"),
        sales_growth=ratios.get("sales_growth"),
        profit_growth=ratios.get("profit_growth"),
        debt_to_equity=ratios.get("debt_equity"),
        interest_coverage=ratios.get("interest_coverage"),
        promoter_holding=ratios.get("promoter_holding"),
        fii_holding=sh.get("fii"),
        dii_holding=sh.get("dii"),
        public_holding=sh.get("public"),
        pledge_pct=sh.get("pledge"),
        about=data.get("about"),
        pros=data.get("pros") or [],
        cons=data.get("cons") or [],
        insights=data.get("insights") or [],
        peers=data.get("peers") or [],
    )


def _pick(d: dict, *candidates: str) -> dict:
    """Return d[k] for the first matching key in `candidates`."""
    for c in candidates:
        v = d.get(c)
        if isinstance(v, dict):
            return v
    return {}


@router.get("/{symbol}/quarterly", response_model=list[QuarterlyRow])
async def quarterly(symbol: str, region: str = Query("IN"), n: int = Query(8, ge=1, le=20)) -> list[QuarterlyRow]:
    if region == "US":
        # US quarterly data not available via Screener; return empty list gracefully
        return []
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol)
    pq = ((data or {}).get("pl") or {}).get("quarterly") or (data or {}).get("quarterly") or {}
    sales      = _pick(pq, "Sales +", "Sales", "Revenue +", "Revenue")
    net_profit = _pick(pq, "Net Profit +", "Net Profit", "Financing Profit")
    opm        = _pick(pq, "OPM %", "Financing Margin %")
    periods = list(sales.keys())[-n:]
    out: list[QuarterlyRow] = []
    for period in periods:
        out.append(QuarterlyRow(
            period=period,
            sales=sales.get(period),
            net_profit=net_profit.get(period),
            opm_pct=opm.get(period),
        ))
    for i, row in enumerate(out):
        prior = out[i - 4] if i >= 4 else None
        if prior:
            if row.sales and prior.sales:
                row.sales_yoy_pct = (row.sales - prior.sales) / abs(prior.sales) * 100
            if row.net_profit and prior.net_profit:
                row.profit_yoy_pct = (row.net_profit - prior.net_profit) / abs(prior.net_profit) * 100
    return out


def _coerce_verdict(v: str | None) -> Verdict:
    """The AI service emits 'STRONG BUY' (with space); our enum uses STRONG_BUY."""
    if not v:
        return Verdict.NEUTRAL
    normalized = v.strip().upper().replace(" ", "_")
    try:
        return Verdict(normalized)
    except ValueError:
        return Verdict.NEUTRAL


def _split_case(case: str | list, prefix: str) -> list[str]:
    """analyze_stock returns 'Bull case: A; B; C' as a single string.
    Convert to a list of bullets the UI can render. Tolerate both shapes."""
    if isinstance(case, list):
        return [str(x).strip() for x in case if str(x).strip()]
    if not isinstance(case, str) or not case.strip():
        return []
    body = case.strip()
    # Strip leading "Bull case: " / "Bear case: " label
    for p in (f"{prefix} case:", f"{prefix.lower()} case:", f"{prefix.upper()} CASE:"):
        if body.startswith(p):
            body = body[len(p):].strip()
            break
    parts = [s.strip().rstrip(".") for s in body.split(";") if s.strip()]
    return parts or ([body] if body else [])


@router.get("/{symbol}/verdict", response_model=AIVerdict)
async def verdict(symbol: str, region: str = Query("IN"), timeframe: Timeframe = Query(Timeframe.DAILY)) -> AIVerdict:
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    from services.ai_service import analyze_stock
    from engines.pattern_engine import detect_patterns

    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    period = TIMEFRAME_TO_YF_PERIOD[timeframe]
    df = await run_sync(get_ohlcv_history, symbol, period, interval, region)
    indicators = await run_sync(compute_indicators_from_ohlcv, df) if df is not None else {}
    tv = {"indicators": indicators, "recommendation": "NEUTRAL", "close": indicators.get("close")}
    if region == "US":
        try:
            from services.us_market_service import get_us_fundamentals
            screener = await run_sync(get_us_fundamentals, symbol)
        except Exception:
            screener = {}
    else:
        from services.screener_service import get_full_screener_data
        screener = await run_sync(get_full_screener_data, symbol)
    patterns = await run_sync(detect_patterns, df) if df is not None else []
    raw = await run_sync(analyze_stock, symbol, tv, screener, patterns)

    # ai_service.AIVerdict uses different field names than our schema:
    # - score           → composite_score
    # - bull_case (str) → bull_case (list[str])
    # - bear_case (str) → bear_case (list[str])
    # - signals         → signal_chain
    return AIVerdict(
        symbol=symbol.upper(),
        verdict=_coerce_verdict(getattr(raw, "verdict", None)),
        composite_score=float(getattr(raw, "score", getattr(raw, "composite_score", 50))),
        tech_score=float(getattr(raw, "tech_score", 50)),
        fund_score=float(getattr(raw, "fund_score", 50)),
        pattern_score=float(getattr(raw, "pattern_score", 50)),
        momentum_score=float(getattr(raw, "momentum_score", 50)),
        confidence=str(getattr(raw, "confidence", "Medium")),
        price_target=getattr(raw, "price_target", None),
        stop_loss=getattr(raw, "stop_loss", None),
        bull_case=_split_case(getattr(raw, "bull_case", ""), "Bull"),
        bear_case=_split_case(getattr(raw, "bear_case", ""), "Bear"),
        risk_flags=list(getattr(raw, "risk_flags", []) or []),
        signal_chain=list(getattr(raw, "signals", getattr(raw, "signal_chain", [])) or []),
    )


_SECTION_RE = re.compile(r"\*\*(\d+\.?\s*[A-Z][A-Z\s&—:\-]+?)\*\*\s*(.*?)(?=\n\*\*\d+\.|\n\*\*CONFIDENCE LEVEL|\Z)", re.DOTALL)
_PROB_RE = re.compile(r"([A-Z][A-Za-z\-\s]+?)\s*[:?]\s*\*\*([\d.]+)/10\*\*")
_VERDICT_RE = re.compile(r"FINAL VERDICT[:\s]+([A-Z_/\s]+?)\*\*", re.IGNORECASE)
_CONF_RE = re.compile(r"CONFIDENCE LEVEL[:\s]+([A-Za-z]+)", re.IGNORECASE)
_PRICE_RE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")


def _parse_chart_analysis_markdown(md: str) -> dict:
    """Split the analyze_chart_data markdown into a structured dict that
    survives the wire and renders well in the UI."""
    if not md:
        return {"sections": {}, "final_verdict": "", "confidence": "Medium",
                "probability_scores": {}, "pro_explanation": "", "targets": [],
                "entry": None, "stop_loss": None, "red_flags": []}

    sections: dict[str, str] = {}
    for m in _SECTION_RE.finditer(md):
        title = re.sub(r"^\d+\.?\s*", "", m.group(1).strip()).strip(": ").title()
        body  = m.group(2).strip()
        if title:
            sections[title] = body

    prob_scores: dict[str, float] = {}
    if "Probability Scores" in sections:
        for pm in _PROB_RE.finditer(sections["Probability Scores"]):
            prob_scores[pm.group(1).strip().rstrip(":")] = float(pm.group(2))

    verdict_m = _VERDICT_RE.search(md)
    conf_m    = _CONF_RE.search(md)

    # Pull entry/stop/targets out of "Risk Management" section
    entry = stop = None
    targets: list[float] = []
    rm_text = sections.get("Risk Management — Trade Setup") or sections.get("Risk Management") or ""
    if rm_text:
        for line in rm_text.splitlines():
            ll = line.lower()
            prices = [float(x.replace(",", "")) for x in _PRICE_RE.findall(line)]
            if not prices:
                continue
            if "stop" in ll and stop is None:
                stop = prices[-1]
            elif "safe entry" in ll and entry is None:
                entry = prices[-1]
            elif "target" in ll or "positional" in ll:
                targets.extend(prices)

    red_flags_text = sections.get("Red Flags & Warnings") or sections.get("Red Flags") or ""
    red_flags = [
        re.sub(r"^[-•\s]+", "", line).strip()
        for line in red_flags_text.splitlines()
        if line.strip().startswith(("-", "•"))
    ]

    pro = sections.get("Pro Trader Explanation") or ""

    return {
        "sections": sections,
        "final_verdict": (verdict_m.group(1).strip() if verdict_m else "").rstrip(":"),
        "confidence": (conf_m.group(1).strip() if conf_m else "Medium").title(),
        "probability_scores": prob_scores,
        "pro_explanation": pro,
        "entry": entry,
        "stop_loss": stop,
        "targets": targets[:3],
        "red_flags": red_flags,
    }


@router.get("/{symbol}/chart-analysis", response_model=ChartAnalysis)
async def chart_analysis(symbol: str, region: str = Query("IN"), timeframe: Timeframe = Query(Timeframe.DAILY)) -> ChartAnalysis:
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import (
        compute_indicators_from_ohlcv, analyze_chart_data,
    )
    from engines.pattern_engine import detect_patterns

    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    period = TIMEFRAME_TO_YF_PERIOD[timeframe]
    df = await run_sync(get_ohlcv_history, symbol, period, interval, region)
    if df is None or len(df) < 30:
        raise HTTPException(status_code=404, detail="Not enough data for chart analysis")
    ind = await run_sync(compute_indicators_from_ohlcv, df)
    patterns = await run_sync(detect_patterns, df)
    if region == "US":
        try:
            from services.us_market_service import get_us_fundamentals
            funda = await run_sync(get_us_fundamentals, symbol)
        except Exception:
            funda = {}
    else:
        from services.screener_service import get_full_screener_data
        funda = await run_sync(get_full_screener_data, symbol)

    raw = await run_sync(
        analyze_chart_data, symbol, timeframe.value, df, ind, patterns, funda,
    )
    md = (raw or {}).get("analysis") or ""
    parsed = _parse_chart_analysis_markdown(md)
    return ChartAnalysis(symbol=symbol.upper(), timeframe=timeframe, **parsed)


def _periodic_table(d: dict | None) -> list[dict]:
    """Convert {metric: {period: value}} into [{period, metric_a, metric_b, ...}]."""
    d = d or {}
    if not d:
        return []
    periods: list[str] = []
    for v in d.values():
        if isinstance(v, dict):
            for p in v.keys():
                if p not in periods:
                    periods.append(p)
    rows = []
    for p in periods:
        row: dict = {"period": p}
        for metric, by_period in d.items():
            if isinstance(by_period, dict):
                row[metric] = by_period.get(p)
        rows.append(row)
    return rows


@router.get("/{symbol}/balance-sheet")
async def balance_sheet(symbol: str, region: str = Query("IN")) -> dict:
    if region == "US":
        return {"symbol": symbol.upper(), "rows": []}
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol)
    return {"symbol": symbol.upper(), "rows": _periodic_table((data or {}).get("balance_sheet"))}


@router.get("/{symbol}/cash-flow")
async def cash_flow(symbol: str, region: str = Query("IN")) -> dict:
    if region == "US":
        return {"symbol": symbol.upper(), "rows": []}
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol)
    return {"symbol": symbol.upper(), "rows": _periodic_table((data or {}).get("cash_flow"))}


@router.get("/{symbol}/ratios-history")
async def ratios_history(symbol: str, region: str = Query("IN")) -> dict:
    if region == "US":
        return {"symbol": symbol.upper(), "rows": []}
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol)
    return {"symbol": symbol.upper(), "rows": _periodic_table((data or {}).get("historical_ratios"))}


@router.get("/{symbol}/shareholding")
async def shareholding(symbol: str, region: str = Query("IN")) -> dict:
    if region == "US":
        return {"symbol": symbol.upper(), "latest": {}, "history": []}
    from services.screener_service import get_full_screener_data
    data = await run_sync(get_full_screener_data, symbol) or {}
    sh = data.get("shareholding") or {}
    return {
        "symbol": symbol.upper(),
        "latest": {
            "promoter": sh.get("promoter"),
            "fii":      sh.get("fii"),
            "dii":      sh.get("dii"),
            "public":   sh.get("public"),
            "pledge":   sh.get("pledge"),
        },
        "history": _periodic_table(sh.get("history")),
    }


SECTOR_TO_NSE_INDEX = {
    "energy": "NIFTY ENERGY",
    "oil": "NIFTY ENERGY",
    "petroleum": "NIFTY ENERGY",
    "information technology": "NIFTY IT",
    "it services": "NIFTY IT",
    "technology": "NIFTY IT",
    "banks": "NIFTY BANK",
    "banking": "NIFTY BANK",
    "financial": "NIFTY BANK",
    "private bank": "NIFTY BANK",
    "psu bank": "NIFTY PSU BANK",
    "pharmaceuticals": "NIFTY PHARMA",
    "pharma": "NIFTY PHARMA",
    "healthcare": "NIFTY PHARMA",
    "automobile": "NIFTY AUTO",
    "auto": "NIFTY AUTO",
    "fmcg": "NIFTY FMCG",
    "consumer": "NIFTY FMCG",
    "metals": "NIFTY METAL",
    "metal": "NIFTY METAL",
    "mining": "NIFTY METAL",
    "realty": "NIFTY REALTY",
    "real estate": "NIFTY REALTY",
    "media": "NIFTY MEDIA",
    "infrastructure": "NIFTY INFRA",
    "infra": "NIFTY INFRA",
}


def _resolve_sector_index(sector: str) -> Optional[str]:
    if not sector:
        return None
    s = sector.lower()
    for key, idx in SECTOR_TO_NSE_INDEX.items():
        if key in s:
            return idx
    return None


@router.get("/{symbol}/peers")
async def peers(symbol: str, region: str = Query("IN")) -> dict:
    """Return peers — first try Screener's curated list, then fall back to
    same-sector mates from the corresponding NSE sector index, enriched with
    live price + change %."""
    if region == "US":
        try:
            from services.us_market_service import get_us_peers
            return await run_sync(get_us_peers, symbol)
        except Exception:
            return {"symbol": symbol.upper(), "sector": None, "industry": None, "source": "us", "peers": []}

    from backend.deps import gather_bounded
    from services.screener_service import get_full_screener_data
    from services.universe_sync import get_universe_symbols
    from services.market_data_service import get_ohlcv_history

    data = await run_sync(get_full_screener_data, symbol) or {}
    sym_upper = symbol.upper()
    raw_peers = [
        p for p in (data.get("peers") or [])
        if isinstance(p, dict)
        and (p.get("_symbol") or "").upper() != sym_upper  # drop self-references
    ]

    # Fallback: derive sector mates from NSE sector index
    sector = (data.get("sector") or "").strip()
    industry = (data.get("industry") or "").strip()
    fallback_source = None
    if not raw_peers:
        sector_index = _resolve_sector_index(sector) or _resolve_sector_index(industry)
        if sector_index:
            try:
                sym_list = await run_sync(get_universe_symbols, sector_index, 25)
                # Exclude self; prefer alphabetic order, cap at 12
                fallback = [s for s in (sym_list or []) if s.upper() != symbol.upper()][:12]
                raw_peers = [{"name": s, "_symbol": s} for s in fallback]
                fallback_source = sector_index
            except Exception:
                pass

    # Enrich with price + change_pct from Yahoo OHLCV (more reliable than NSE
    # at concurrency, no rate-limiting).
    async def _enrich(p: dict) -> dict:
        sym = (p.get("_symbol") or p.get("name") or "").upper()
        out = dict(p)
        out["symbol"] = sym
        if not sym:
            return out
        try:
            df = await run_sync(get_ohlcv_history, sym, "3mo", "1d")
            if df is not None and len(df) >= 2:
                last = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2])
                hi = float(df["High"].max())
                lo = float(df["Low"].min())
                out["last_price"]  = last
                out["change_pct"]  = (last - prev) / prev * 100 if prev else None
                out["week52_high"] = hi
                out["week52_low"]  = lo
                out["company"]     = p.get("name")
        except Exception:
            pass
        return out

    enriched_or_err = await gather_bounded(*[_enrich(p) for p in raw_peers[:15]], limit=8)
    enriched = [e for e in enriched_or_err if isinstance(e, dict)]
    return {
        "symbol": symbol.upper(),
        "sector": sector or None,
        "industry": industry or None,
        "source": fallback_source or "screener",
        "peers": enriched,
    }


@router.get("/{symbol}/snapshot", response_model=StockSnapshot)
async def snapshot(symbol: str, region: str = Query("IN"), timeframe: Timeframe = Query(Timeframe.DAILY)) -> StockSnapshot:
    """Single-shot for the Stock Analyzer page header — quote + indicators + fundamentals + verdict, in parallel."""
    import asyncio
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    from services.ai_service import analyze_stock
    from engines.pattern_engine import detect_patterns

    interval = TIMEFRAME_TO_YF_INTERVAL[timeframe]
    period = TIMEFRAME_TO_YF_PERIOD[timeframe]

    if region == "US":
        from services.us_market_service import get_quote as us_get_quote, get_us_fundamentals
        quote_t = run_sync(us_get_quote, symbol)
        funda_t = run_sync(get_us_fundamentals, symbol)
    else:
        from services.nse_service import get_quote as nse_get_quote
        from services.screener_service import get_full_screener_data
        quote_t = run_sync(nse_get_quote, symbol)
        funda_t = run_sync(get_full_screener_data, symbol)

    df_t = run_sync(get_ohlcv_history, symbol, period, interval, region)
    quote_raw, df, funda_raw = await asyncio.gather(quote_t, df_t, funda_t, return_exceptions=True)

    if isinstance(df, Exception) or df is None:
        df = None
    ind = await run_sync(compute_indicators_from_ohlcv, df) if df is not None else {}
    patterns = await run_sync(detect_patterns, df) if df is not None else []

    funda_raw = {} if isinstance(funda_raw, Exception) or not funda_raw else funda_raw

    tv = {"indicators": ind, "recommendation": "NEUTRAL", "close": ind.get("close")}
    try:
        ai_raw = await run_sync(analyze_stock, symbol, tv, funda_raw, patterns)
        ai = AIVerdict(
            symbol=symbol.upper(),
            verdict=_coerce_verdict(getattr(ai_raw, "verdict", None)),
            composite_score=float(getattr(ai_raw, "score", getattr(ai_raw, "composite_score", 50))),
            tech_score=float(getattr(ai_raw, "tech_score", 50)),
            fund_score=float(getattr(ai_raw, "fund_score", 50)),
            pattern_score=float(getattr(ai_raw, "pattern_score", 50)),
            momentum_score=float(getattr(ai_raw, "momentum_score", 50)),
            confidence=str(getattr(ai_raw, "confidence", "Medium")),
            price_target=getattr(ai_raw, "price_target", None),
            stop_loss=getattr(ai_raw, "stop_loss", None),
            bull_case=_split_case(getattr(ai_raw, "bull_case", ""), "Bull"),
            bear_case=_split_case(getattr(ai_raw, "bear_case", ""), "Bear"),
            risk_flags=list(getattr(ai_raw, "risk_flags", []) or []),
            signal_chain=list(getattr(ai_raw, "signals", getattr(ai_raw, "signal_chain", [])) or []),
        )
    except Exception as e:
        log.warning("AI analyze failed for %s: %s", symbol, e)
        ai = None

    quote_d = quote_raw if not isinstance(quote_raw, Exception) else None

    return StockSnapshot(
        symbol=symbol.upper(),
        quote=quote_d,
        indicators=Indicators(**{k: ind.get(k) for k in Indicators.model_fields.keys() if k in ind}),
        fundamentals=None,  # Caller can hit /fundamentals separately for details
        ai=ai,
    )
