"""Cell-formatting helpers for the Country-Year Chronicle row builder.

The row builder needs a small set of pure value-coercion helpers
(:func:`coerce_int`, :func:`coerce_float`, :func:`safe_int`,
:func:`empty_row_template`). They are deliberately kept in a
separate module so the row builder itself stays focused on row
composition logic and the helpers can be unit-tested in isolation.

All helpers are pure: no I/O, no logging, no shared mutable state.
"""

from __future__ import annotations

import math
from typing import Any

from .constants import CHRONICLE_CSV_COLUMNS


def coerce_int(value: Any) -> str:
    """Coerce a value to its CSV-string integer representation.

    ``None`` and empty strings become the empty string (the CSV
    writer writes a literal empty cell). Non-numeric values fall
    through to ``str(value)`` so the CSV preserves whatever the
    caller provided rather than silently dropping it.
    """
    if value is None or value == "":
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def coerce_float(value: Any, *, decimals: int = 0) -> str:
    """Format a float for CSV output.

    Empty / non-numeric / ``NaN`` values become the empty string
    (the CSV writer writes a literal empty cell, not the string
    ``"nan"``). When ``decimals`` is 0 the value is rounded to the
    nearest integer; otherwise it is formatted to ``decimals``
    decimal places.
    """
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(f):
        return ""
    if decimals == 0:
        return f"{round(f)}"
    return f"{f:.{decimals}f}"


def safe_int(value: Any) -> int | None:
    """Coerce a value to ``int`` or return ``None``.

    Used for metadata fields like ``start_year`` / ``end_year`` /
    ``colonial_status_until`` where ``None`` is the expected sentinel
    for "not set". Non-numeric strings fall through to ``None``
    rather than raising so the row builder can degrade gracefully.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def empty_row_template() -> dict[str, str]:
    """Return a fresh dict with every output column mapped to ``""``.

    The row builder starts from this template and overwrites the
    columns it has values for; columns it never touches stay as
    empty strings and become literal empty CSV cells.
    """
    return {col: "" for col in CHRONICLE_CSV_COLUMNS}


__all__ = [
    "coerce_float",
    "coerce_int",
    "empty_row_template",
    "safe_int",
]
