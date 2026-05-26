from __future__ import annotations
import logging
import operator
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

OPERATORS = {
    ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
    "==": operator.eq, "!=": operator.ne,
    "between": lambda v, lo, hi: lo <= v <= hi,
    "in": lambda v, lst: v in lst,
}

FIELD_MAP = {
    # Technical
    "rsi":              lambda d: _tv_ind(d, "rsi"),
    "macd":             lambda d: _tv_ind(d, "macd"),
    "close":            lambda d: _tv_ind(d, "close"),
    "price":            lambda d: d.get("Price") or _tv_ind(d, "close"),
    "volume":           lambda d: _tv_ind(d, "volume"),
    "ema20":            lambda d: _tv_ind(d, "ema20"),
    "sma50":            lambda d: _tv_ind(d, "sma50"),
    "sma200":           lambda d: _tv_ind(d, "sma200"),
    "adx":              lambda d: _tv_ind(d, "adx"),
    "change_pct":       lambda d: d.get("Change %") or _tv_ind(d, "change"),
    "breakout_prob":    lambda d: d.get("Breakout Probability"),
    "technical_score":  lambda d: d.get("Technical Score"),
    "tv_score":         lambda d: d.get("TV Score"),
    "final_score":      lambda d: d.get("Final Score"),
    # Fundamental
    "pe":               lambda d: _funda(d, "pe") or d.get("PE Ratio"),
    "pb":               lambda d: _funda(d, "pb") or d.get("PB Ratio"),
    "roe":              lambda d: _funda(d, "roe") or d.get("ROE"),
    "roce":             lambda d: _funda(d, "roce") or d.get("ROCE"),
    "debt_equity":      lambda d: _funda(d, "debt_equity") or d.get("Debt to Equity"),
    "dividend_yield":   lambda d: _funda(d, "dividend_yield"),
    "promoter":         lambda d: _funda(d, "promoter_holding") or _sh(d, "promoter") or d.get("Promoter Holding"),
    "sales_growth":     lambda d: _funda(d, "sales_growth") or d.get("Revenue Growth"),
    "profit_growth":    lambda d: _funda(d, "profit_growth") or d.get("Profit Growth"),
    "market_cap":       lambda d: _funda(d, "market_cap") or d.get("Market Cap"),
    "fundamental_score": lambda d: d.get("Fundamental Score"),
    # Patterns
    "pattern_confidence": lambda d: d.get("Pattern Confidence"),
    "has_bullish_pattern": lambda d: 1 if d.get("Pattern Direction") == "Bullish" else 0,
    "has_bearish_pattern": lambda d: 1 if d.get("Pattern Direction") == "Bearish" else 0,
    # TV recommendation
    "tv_recommendation": lambda d: _rec_score(d.get("TradingView") or d.get("tv_recommendation", "")),
}

def _tv_ind(d: dict, key: str) -> Optional[float]:
    tv = d.get("tv_analysis") or {}
    ind = tv.get("indicators") or {}
    return ind.get(key)

def _funda(d: dict, key: str) -> Optional[float]:
    r = (d.get("screener_data") or {}).get("ratios") or d.get("ratios") or {}
    return r.get(key)

def _sh(d: dict, key: str) -> Optional[float]:
    sh = (d.get("screener_data") or {}).get("shareholding") or {}
    return sh.get(key)

def _rec_score(rec: str) -> float:
    return {"STRONG_BUY": 5, "BUY": 4, "NEUTRAL": 3, "SELL": 2, "STRONG_SELL": 1}.get(str(rec).upper(), 3)

def _get_field(stock: dict, field_name: str) -> Optional[float]:
    fn = FIELD_MAP.get(field_name.lower())
    if fn is None:
        return stock.get(field_name)
    try:
        v = fn(stock)
        return float(v) if v is not None else None
    except Exception:
        return None

@dataclass
class RuleCondition:
    field: str
    op: str
    value: Any
    value2: Any = None      # for "between"

    def evaluate(self, stock: dict) -> tuple[bool, Optional[float]]:
        actual = _get_field(stock, self.field)
        if actual is None:
            return False, None
        op_fn = OPERATORS.get(self.op)
        if op_fn is None:
            return False, actual
        try:
            if self.op == "between":
                result = op_fn(actual, self.value, self.value2)
            elif self.op == "in":
                result = op_fn(actual, self.value)
            else:
                result = op_fn(actual, self.value)
            return bool(result), actual
        except Exception:
            return False, actual

@dataclass
class Rule:
    id: str
    name: str
    description: str = ""
    conditions: list[dict] = field(default_factory=list)
    logic: str = "AND"      # AND / OR
    tags: list[str] = field(default_factory=list)

    def evaluate(self, stock: dict) -> dict:
        results = []
        for cond_dict in self.conditions:
            cond = RuleCondition(
                field=cond_dict["field"],
                op=cond_dict["op"],
                value=cond_dict["value"],
                value2=cond_dict.get("value2"),
            )
            passed, actual = cond.evaluate(stock)
            results.append({
                "field": cond_dict["field"],
                "op": cond_dict["op"],
                "expected": cond_dict["value"],
                "actual": actual,
                "passed": passed,
            })
        if self.logic == "AND":
            overall = all(r["passed"] for r in results)
        else:
            overall = any(r["passed"] for r in results)
        return {
            "rule_id": self.id,
            "rule_name": self.name,
            "passed": overall,
            "conditions": results,
            "passed_count": sum(1 for r in results if r["passed"]),
            "total_conditions": len(results),
        }

def build_rule(rule_dict: dict) -> Rule:
    return Rule(
        id=rule_dict.get("id", ""),
        name=rule_dict.get("name", "Unnamed Rule"),
        description=rule_dict.get("description", ""),
        conditions=rule_dict.get("conditions", []),
        logic=rule_dict.get("logic", "AND"),
        tags=rule_dict.get("tags", []),
    )

def evaluate_rules(rules: list[dict], stock: dict) -> list[dict]:
    return [build_rule(r).evaluate(stock) for r in rules]

def apply_rules_to_universe(rules: list[dict], stocks: list[dict], logic: str = "ALL") -> list[dict]:
    """Filter stocks that match rules. logic='ALL' means all rules pass, 'ANY' means at least one."""
    results = []
    for stock in stocks:
        evals = evaluate_rules(rules, stock)
        if logic == "ALL":
            passes = all(e["passed"] for e in evals)
        else:
            passes = any(e["passed"] for e in evals)
        if passes:
            stock = dict(stock)
            stock["_rule_results"] = evals
            results.append(stock)
    return results

PRESET_RULES = [
    {
        "id": "techno_funda",
        "name": "Techno-Funda Quality",
        "description": "Low PE + High ROE + Low Debt + RSI in buy zone",
        "logic": "AND",
        "conditions": [
            {"field": "pe", "op": "<", "value": 30},
            {"field": "roe", "op": ">", "value": 15},
            {"field": "debt_equity", "op": "<", "value": 1.5},
            {"field": "rsi", "op": "between", "value": 45, "value2": 70},
        ],
        "tags": ["fundamental", "technical"],
    },
    {
        "id": "breakout_momentum",
        "name": "Breakout + Momentum",
        "description": "Strong technicals with TradingView buy signal",
        "logic": "AND",
        "conditions": [
            {"field": "rsi", "op": "between", "value": 55, "value2": 75},
            {"field": "macd", "op": ">", "value": 0},
            {"field": "tv_recommendation", "op": ">=", "value": 4},
            {"field": "has_bullish_pattern", "op": "==", "value": 1},
        ],
        "tags": ["technical", "momentum"],
    },
    {
        "id": "promoter_growth",
        "name": "Promoter + Growth",
        "description": "High promoter holding with sales & profit growth",
        "logic": "AND",
        "conditions": [
            {"field": "promoter", "op": ">", "value": 50},
            {"field": "sales_growth", "op": ">", "value": 10},
            {"field": "profit_growth", "op": ">", "value": 10},
            {"field": "debt_equity", "op": "<", "value": 1},
        ],
        "tags": ["fundamental", "quality"],
    },
    {
        "id": "undervalued_quality",
        "name": "Undervalued Quality",
        "description": "Cheap valuation + high profitability",
        "logic": "AND",
        "conditions": [
            {"field": "pe", "op": "<", "value": 20},
            {"field": "pb", "op": "<", "value": 3},
            {"field": "roce", "op": ">", "value": 18},
            {"field": "roe", "op": ">", "value": 15},
        ],
        "tags": ["value", "quality"],
    },
    {
        "id": "swing_trade",
        "name": "Swing Trade Setup",
        "description": "Technical momentum with controlled RSI",
        "logic": "AND",
        "conditions": [
            {"field": "rsi", "op": "between", "value": 50, "value2": 68},
            {"field": "final_score", "op": ">", "value": 60},
            {"field": "change_pct", "op": ">", "value": -2},
        ],
        "tags": ["technical", "swing"],
    },
]

AVAILABLE_FIELDS = [
    ("RSI (14)", "rsi"), ("MACD", "macd"), ("Price", "price"), ("Volume", "volume"),
    ("EMA 20", "ema20"), ("SMA 50", "sma50"), ("SMA 200", "sma200"), ("ADX", "adx"),
    ("Change %", "change_pct"), ("Breakout Prob", "breakout_prob"),
    ("Technical Score", "technical_score"), ("TV Score", "tv_score"), ("Final Score", "final_score"),
    ("PE Ratio", "pe"), ("PB Ratio", "pb"), ("ROE %", "roe"), ("ROCE %", "roce"),
    ("Debt/Equity", "debt_equity"), ("Dividend Yield", "dividend_yield"),
    ("Promoter %", "promoter"), ("Sales Growth %", "sales_growth"), ("Profit Growth %", "profit_growth"),
    ("Market Cap (Cr)", "market_cap"), ("Fundamental Score", "fundamental_score"),
    ("Pattern Confidence", "pattern_confidence"),
    ("Has Bullish Pattern", "has_bullish_pattern"), ("Has Bearish Pattern", "has_bearish_pattern"),
    ("TV Recommendation", "tv_recommendation"),
]
