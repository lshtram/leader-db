"""Unified-source V-Dem missing-value coercion helpers.

This module owns the small helpers that coerce a V-Dem
``raw_value`` cell into the unified observation ``value``
contract. The contract mirrors the legacy
``leaders_db.ingest.vdem_db._coerce_float`` /
``_raw_value_to_string`` semantics:

- ``-999`` (and any value at or below ``-999.0``) is the
  V-Dem missing-data sentinel; other negative values on the
  continuous C-type estimates (e.g. ``v2csreprss`` /
  ``v2clkill``) are LEGITIMATE data and are preserved
  verbatim.
- pandas ``NaN`` and the canonical string sentinels
  (``""`` / ``"NA"`` / ``"NaN"`` / ``"nan"`` / ``"-999"``)
  are also treated as missing.

Split out of :mod:`._transform` so the transform module
stays under the documented 400-line convention while
keeping the legacy sentinel contract verbatim.
"""

from __future__ import annotations

import math
from typing import Any

# V-Dem's missing-data sentinel: any value at or below this
# is missing. This is the V-Dem convention (see codebook).
# Other negative values on the continuous C-type estimates
# (e.g., v2csreprss) are LEGITIMATE data, not sentinels --
# do not lower the threshold.
VDEM_MISSING_SENTINEL: float = -999.0

# String sentinels pandas may emit on re-reads. Treated as
# missing by the unified transform.
VDEM_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "-999", ""},
)


def is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, (int,))


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`coerce_float`.

    Extracted to a helper so the type-dispatch in
    :func:`coerce_float` stays under the ruff
    ``PLR0911`` (too-many-return-statements) threshold.
    """
    stripped = raw.strip()
    if stripped in VDEM_MISSING_STRINGS:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        return None
    if numeric <= VDEM_MISSING_SENTINEL:
        return None
    return numeric


def coerce_float(value: Any) -> float | None:
    """Coerce a V-Dem cell to ``float`` or return ``None``.

    V-Dem's missing-data convention is the sentinel ``-999``
    (and any value at or below ``VDEM_MISSING_SENTINEL``).
    Other negative values on the continuous C-type
    estimates are LEGITIMATE data, not sentinels. pandas
    ``NaN`` and the common string sentinels (``""`` /
    ``"NA"`` / ``"NaN"`` / ``"nan"`` / ``"-999"``) are
    also treated as missing.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return None if value <= VDEM_MISSING_SENTINEL else value
    if isinstance(value, int) and not isinstance(value, bool):
        return (
            None
            if value <= int(VDEM_MISSING_SENTINEL)
            else float(value)
        )
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return
    # None.
    return None


def raw_value_to_string(cell: Any) -> str:
    """Render a raw cell for the audit-trail ``raw_value`` field.

    Rules (matches the legacy
    ``leaders_db.ingest.vdem_db._raw_value_to_string``):

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit
      trail of what pandas saw).
    - All other values -> ``str(cell)`` (preserves the
      V-Dem missing sentinel like ``"-999.0"`` so the
      audit trail shows what the source file actually
      said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and math.isnan(cell):
        return "nan"
    return str(cell)


__all__ = [
    "VDEM_MISSING_SENTINEL",
    "VDEM_MISSING_STRINGS",
    "coerce_float",
    "is_real_number",
    "raw_value_to_string",
]
