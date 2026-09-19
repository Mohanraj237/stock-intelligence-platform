"""Confluence-scoring configuration schema — user-editable category weights."""
from __future__ import annotations
from pydantic import BaseModel


class ScoringConfig(BaseModel):
    trend_weight: int = 30
    momentum_weight: int = 25
    volume_weight: int = 15
    candle_weight: int = 25
    structural_weight: int = 5
    default_threshold: int = 65
