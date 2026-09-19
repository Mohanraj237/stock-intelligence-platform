"""
Generate frontend/lib/lot-sizes.generated.ts from services/lot_sizes.py.

    python scripts/gen_lot_sizes.py

services/lot_sizes.py is the single source of truth. tests/test_lot_sizes.py
fails if the generated file has drifted, so run this after any edit to the
Python table.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.lot_sizes import DEFAULT_LOT_SIZE, INDEX_SYMBOLS, LOT_SIZES  # noqa: E402

OUT = ROOT / "frontend" / "lib" / "lot-sizes.generated.ts"

HEADER = """// AUTO-GENERATED — DO NOT EDIT.
// Source of truth: services/lot_sizes.py
// Regenerate with: python scripts/gen_lot_sizes.py
// tests/test_lot_sizes.py fails the build if this file drifts from the Python table.
"""


def _key(symbol: str) -> str:
    """Quote keys that are not valid bare JS identifiers (M&M, BAJAJ-AUTO, 360ONE)."""
    if symbol.isidentifier() and not symbol[0].isdigit():
        return symbol
    return f'"{symbol}"'


def render() -> str:
    lines = [HEADER, "", "export const LOT_SIZES: Record<string, number> = {"]
    for sym in sorted(LOT_SIZES):
        lines.append(f"  {_key(sym)}: {LOT_SIZES[sym]},")
    lines.append("};")
    lines.append("")
    lines.append(f"export const DEFAULT_LOT_SIZE = {DEFAULT_LOT_SIZE};")
    lines.append("")
    lines.append("export const INDEX_SYMBOLS = [")
    for sym in INDEX_SYMBOLS:
        lines.append(f'  "{sym}",')
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    content = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {len(LOT_SIZES)} lot sizes to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
