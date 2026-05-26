"""Rule-engine schemas."""
from __future__ import annotations
from typing import Optional, List, Any
from enum import Enum
from pydantic import BaseModel


class RuleOp(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    BETWEEN = "between"


class RuleLogic(str, Enum):
    AND = "AND"
    OR = "OR"


class RuleCondition(BaseModel):
    field: str           # e.g. "rsi", "pe", "change_pct"
    op: RuleOp
    value: Any
    value2: Optional[Any] = None  # for BETWEEN


class Rule(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    conditions: List[RuleCondition]
    logic: RuleLogic = RuleLogic.AND


class RuleSet(BaseModel):
    rules: List[Rule]
    cross_logic: RuleLogic = RuleLogic.AND


class RuleMatchRow(BaseModel):
    symbol: str
    company: Optional[str] = None
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    rules_passed: List[str] = []
    rules_failed: List[str] = []
    pass_count: int = 0
