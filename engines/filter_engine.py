from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _num(v, default=None) -> Optional[float]:
    try:
        return float(v) if v is not None else default
    except Exception:
        return default

@dataclass
class FilterCriteria:
    # Market
    market_cap_min: Optional[float] = None
    market_cap_max: Optional[float] = None
    # Sector
    sectors: list[str] = field(default_factory=list)
    # Valuation
    pe_min: Optional[float] = None
    pe_max: Optional[float] = None
    pb_min: Optional[float] = None
    pb_max: Optional[float] = None
    # Quality
    roe_min: Optional[float] = None
    roce_min: Optional[float] = None
    debt_max: Optional[float] = None
    promoter_min: Optional[float] = None
    # Growth
    sales_growth_min: Optional[float] = None
    profit_growth_min: Optional[float] = None
    # Technical
    rsi_min: Optional[float] = None
    rsi_max: Optional[float] = None
    macd_bullish: bool = False
    price_above_sma50: bool = False
    price_above_sma200: bool = False
    adx_min: Optional[float] = None
    # Pattern
    pattern_types: list[str] = field(default_factory=list)
    min_pattern_confidence: Optional[float] = None
    # TradingView
    tv_ratings: list[str] = field(default_factory=list)
    # Score
    min_final_score: Optional[float] = None
    min_tech_score: Optional[float] = None
    min_funda_score: Optional[float] = None

def _get(d: dict, key: str) -> Optional[float]:
    v = d.get(key)
    return _num(v)

def apply_filters(stocks: list[dict], criteria: FilterCriteria) -> list[dict]:
    results = []
    for s in stocks:
        if not _passes(s, criteria):
            continue
        results.append(s)
    return results

def _passes(s: dict, c: FilterCriteria) -> bool:
    ratios = (s.get("screener_data") or {}).get("ratios") or s
    ind    = ((s.get("tv_analysis") or {}).get("indicators")) or s

    def r(k):
        return _num(ratios.get(k)) if k in ratios else _num(s.get(k))
    def i(k):
        return _num(ind.get(k)) if k in ind else _num(s.get(k))

    pe   = r("pe")  or _num(s.get("PE Ratio"))
    pb   = r("pb")  or _num(s.get("PB Ratio"))
    roe  = r("roe") or _num(s.get("ROE"))
    roce = r("roce") or _num(s.get("ROCE"))
    de   = r("debt_equity") or _num(s.get("Debt to Equity"))
    prom = r("promoter_holding") or _num(s.get("Promoter Holding"))
    sg   = r("sales_growth") or _num(s.get("Revenue Growth"))
    pg   = r("profit_growth") or _num(s.get("Profit Growth"))
    mcap = r("market_cap") or _num(s.get("Market Cap"))
    sect = s.get("Sector") or (s.get("screener_data") or {}).get("sector", "")
    rsi  = i("rsi") or _num(s.get("RSI"))
    macd = i("macd") or _num(s.get("MACD"))
    msig = i("macd_signal") or _num(s.get("MACD Signal"))
    cl   = i("close") or _num(s.get("Price"))
    s50  = i("sma50") or _num(s.get("SMA 50"))
    s200 = i("sma200") or _num(s.get("SMA 200"))
    adx  = i("adx") or _num(s.get("ADX"))
    tv   = s.get("TradingView") or (s.get("tv_analysis") or {}).get("recommendation", "")
    fs   = _num(s.get("Final Score"))
    ts   = _num(s.get("Technical Score"))
    fus  = _num(s.get("Fundamental Score"))
    pats = s.get("Patterns") or []
    top_pat = (pats[0] if pats else {})
    pat_name = top_pat.get("name") or s.get("Top Pattern", "")
    pat_conf = _num(top_pat.get("confidence") or s.get("Pattern Confidence"))
    pat_dir  = top_pat.get("direction") or s.get("Pattern Direction", "")

    def between(v, lo, hi):
        if v is None: return True
        if lo is not None and v < lo: return False
        if hi is not None and v > hi: return False
        return True

    if not between(mcap, c.market_cap_min, c.market_cap_max): return False
    if c.sectors and sect and sect not in c.sectors: return False
    if not between(pe, c.pe_min, c.pe_max): return False
    if not between(pb, c.pb_min, c.pb_max): return False
    if c.roe_min is not None and roe is not None and roe < c.roe_min: return False
    if c.roce_min is not None and roce is not None and roce < c.roce_min: return False
    if c.debt_max is not None and de is not None and de > c.debt_max: return False
    if c.promoter_min is not None and prom is not None and prom < c.promoter_min: return False
    if c.sales_growth_min is not None and sg is not None and sg < c.sales_growth_min: return False
    if c.profit_growth_min is not None and pg is not None and pg < c.profit_growth_min: return False
    if not between(rsi, c.rsi_min, c.rsi_max): return False
    if c.macd_bullish and macd is not None and msig is not None and macd <= msig: return False
    if c.price_above_sma50 and cl is not None and s50 is not None and cl <= s50: return False
    if c.price_above_sma200 and cl is not None and s200 is not None and cl <= s200: return False
    if c.adx_min is not None and adx is not None and adx < c.adx_min: return False
    if c.pattern_types and pat_name and not any(p.lower() in pat_name.lower() for p in c.pattern_types): return False
    if c.min_pattern_confidence is not None and pat_conf is not None and pat_conf < c.min_pattern_confidence: return False
    if c.tv_ratings and tv and tv.upper() not in [r.upper() for r in c.tv_ratings]: return False
    if c.min_final_score is not None and fs is not None and fs < c.min_final_score: return False
    if c.min_tech_score is not None and ts is not None and ts < c.min_tech_score: return False
    if c.min_funda_score is not None and fus is not None and fus < c.min_funda_score: return False
    return True

def criteria_from_dict(d: dict) -> FilterCriteria:
    return FilterCriteria(
        market_cap_min=d.get("market_cap_min"),
        market_cap_max=d.get("market_cap_max"),
        sectors=d.get("sectors", []),
        pe_min=d.get("pe_min"),
        pe_max=d.get("pe_max"),
        pb_min=d.get("pb_min"),
        pb_max=d.get("pb_max"),
        roe_min=d.get("roe_min"),
        roce_min=d.get("roce_min"),
        debt_max=d.get("debt_max"),
        promoter_min=d.get("promoter_min"),
        sales_growth_min=d.get("sales_growth_min"),
        profit_growth_min=d.get("profit_growth_min"),
        rsi_min=d.get("rsi_min"),
        rsi_max=d.get("rsi_max"),
        macd_bullish=d.get("macd_bullish", False),
        price_above_sma50=d.get("price_above_sma50", False),
        price_above_sma200=d.get("price_above_sma200", False),
        adx_min=d.get("adx_min"),
        pattern_types=d.get("pattern_types", []),
        min_pattern_confidence=d.get("min_pattern_confidence"),
        tv_ratings=d.get("tv_ratings", []),
        min_final_score=d.get("min_final_score"),
        min_tech_score=d.get("min_tech_score"),
        min_funda_score=d.get("min_funda_score"),
    )

FILTER_PRESETS = {
    "Breakout Stocks": {
        "rsi_min": 55, "rsi_max": 75, "macd_bullish": True, "price_above_sma50": True,
        "min_final_score": 60,
    },
    "Undervalued Quality": {
        "pe_max": 25, "pb_max": 3, "roe_min": 15, "roce_min": 15, "debt_max": 1.0,
    },
    "Growth Stocks": {
        "sales_growth_min": 15, "profit_growth_min": 15, "roe_min": 15,
    },
    "Strong Momentum": {
        "rsi_min": 60, "price_above_sma50": True, "price_above_sma200": True,
        "tv_ratings": ["BUY", "STRONG_BUY"], "min_final_score": 65,
    },
    "Dividend Stocks": {
        "debt_max": 1.0, "roe_min": 12, "promoter_min": 40,
    },
    "Techno-Funda": {
        "pe_max": 30, "roe_min": 15, "debt_max": 1.5, "rsi_min": 45, "rsi_max": 70,
        "min_tech_score": 50, "min_funda_score": 50,
    },
    "High Promoter": {
        "promoter_min": 60, "profit_growth_min": 10,
    },
    "PSU Value": {
        "pe_max": 15, "pb_max": 2, "debt_max": 3,
    },
}
