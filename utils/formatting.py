from __future__ import annotations

import math
from typing import Any


def fmt_number(value: Any, suffix: str = "", digits: int = 2) -> str:
    try:
        number = float(value)
        if math.isnan(number):
            return "N/A"
        return f"{number:,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def fmt_rupees(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if number >= 1e7:
        return f"Rs {number / 1e7:,.2f} Cr"
    return f"Rs {number:,.2f}"


def fmt_market_cap(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"Rs {number / 1e7:,.0f} Cr"
