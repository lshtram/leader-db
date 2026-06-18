"""Year normalization helpers.

Source datasets use a variety of year encodings (smallint, two-digit,
fiscal year, ISO-8601 date). This module normalizes everything to a
smallint 1900–2100 as used by the schema's ``year`` columns.

Per requirement §13, pre-1900 years are out of scope for the first
prototype; this module raises on out-of-range values rather than silently
clamping.
"""

from __future__ import annotations

MIN_YEAR = 1900
MAX_YEAR = 2100


def normalize_year(value: int | str) -> int:
    """Coerce ``value`` to a 1900–2100 smallint year.

    Accepts ``int``, digit-only ``str``, and ISO-8601 date strings. ISO
    dates are parsed as the year component only — fiscal years, academic
    years, and similar constructs must be resolved upstream.
    """
    if isinstance(value, bool):
        # bool is a subclass of int; reject explicitly.
        raise ValueError("year must be a number, not a bool")
    if isinstance(value, int):
        return _check(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("year string is empty")
        if s.isdigit():
            return _check(int(s))
        # ISO-8601 date or datetime — take the first 4 chars only after a sanity check.
        if len(s) >= 4 and s[:4].isdigit():
            return _check(int(s[:4]))
        raise ValueError(f"unrecognized year string: {value!r}")
    raise TypeError(f"unsupported year type: {type(value).__name__}")


def _check(year: int) -> int:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(
            f"year {year} out of prototype range [{MIN_YEAR}, {MAX_YEAR}] "
            f"(requirement §13: pre-1900 out of scope)"
        )
    return year
