"""Unified-source Transparency International CPI
missing-value / coercion helpers.

This module owns the per-cell coercion helpers used by the
unified-source Transparency International CPI
observation-emission code in :mod:`._transform`. The
helpers handle:

- ``_is_real_number`` -- NaN / None / boolean guard for the
  wide-format cells (the CPI score is an integer 0-100 per
  the TI methodology since 2012).
- ``_coerce_score_cell`` -- converts a wide-format cell
  into the ``(float, string)`` tuple the unified
  observation contract expects (``value`` is the canonical
  numeric; ``raw_value`` is the audit-trail string).
- ``_coerce_float_or_none`` -- converts an audit-trail
  cell (``standard_error`` / ``lower_ci`` / ``upper_ci``)
  into ``float | None``.
- ``_coerce_int_or_none`` -- converts the legacy
  integer-cell columns (``rank`` / ``sources``) into
  ``int | None``.

Split out of :mod:`._transform` so the transform module
stays focused on the per-row emission loop + the
:class:`NormalizedObservation` construction, and so each
module respects the documented 400-line convention. The
helpers mirror the UCDP ``_is_real_number`` / ``_coerce_cell``
shape so the unified-source subsystem stays consistent.
"""

from __future__ import annotations

import math
from typing import Any

# String sentinels the HDX CSV may emit on missing values.
# Treated as missing. The HDX CSV uses empty cells;
# defensively handle ``NA`` / ``NaN`` / ``nan`` / ``null``
# / ``None`` / ``""`` strings too. Mirrors the legacy
# ``transparency_cpi_csv._MISSING_STRINGS`` set so the
# unified adapter preserves the legacy contract byte-for-
# byte.
_CPI_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", ""},
)


def _is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None
    numeric.

    Mirrors the UCDP ``_is_real_number`` helper. Used to
    skip NaN cells in the wide-format CPI score column
    without silently converting missing raw cells
    (SRC-OBS-007).
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, (int,))


def _coerce_score_cell(
    value: Any,
) -> tuple[float | None, str | None]:
    """Coerce a wide-format CPI score cell into
    ``(float, string)`` for emission.

    Returns ``(None, None)`` when the cell is NaN /
    missing; otherwise returns
    ``(float(value), str(value))`` where ``float(value)``
    is the canonical CPI score (the legacy CPI is integer
    0-100; the unified contract carries it as float for
    cross-source alignment) and ``str(value)`` is the
    audit-trail string. The ``float(value)`` cast surfaces
    pandas Int64 NaN cells (the pandas nullable Integer
    type's NaN is silently coerced via ``float`` and
    rejected by ``_is_real_number``).
    """
    if not _is_real_number(value):
        return None, None
    try:
        return float(value), str(value)
    except (TypeError, ValueError):
        return None, None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float_or_none`.

    Extracted to a helper so the type-dispatch in
    :func:`_coerce_float_or_none` stays under the ruff
    PLR0911 (too-many-return-statements) threshold.
    """
    stripped = raw.strip()
    if stripped in _CPI_MISSING_STRINGS:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _coerce_float_or_none(value: Any) -> float | None:
    """Coerce an HDX CSV numeric audit-trail cell to
    ``float | None``.

    Used for the audit-trail columns (``standard_error``,
    ``lower_ci``, ``upper_ci``) which are floats in the HDX
    CSV. Returns ``None`` for empty / missing / non-parseable
    cells.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    return None


def _coerce_int_from_string(raw: str) -> int | None:
    """String variant of :func:`_coerce_int_or_none`.

    Extracted to a helper so the type-dispatch in
    :func:`_coerce_int_or_none` stays under the ruff
    PLR0911 (too-many-return-statements) threshold.
    """
    stripped = raw.strip()
    if stripped in _CPI_MISSING_STRINGS:
        return None
    try:
        return int(float(stripped))
    except ValueError:
        return None


def _coerce_int_or_none(value: Any) -> int | None:
    """Coerce an HDX CSV integer audit-trail cell to
    ``int | None``.

    Used for the audit-trail columns (``rank``, ``sources``)
    which are integers in the HDX CSV. Returns ``None`` for
    empty / missing / non-parseable cells.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _coerce_int_from_string(value)
    return None


def _raw_value_to_string(cell: Any) -> str:
    """Render a raw cell for the audit-trail
    ``raw_value`` field.

    Rules (matches the legacy
    ``transparency_cpi_db_helpers._raw_value_to_string``):

    - ``None`` -> ``""`` (no audit trail for missing
      cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit
      trail of what pandas saw).
    - All other values -> ``str(cell)`` (preserves the
      verbatim HDX cell as the user uploaded it).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and math.isnan(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_CPI_MISSING_STRINGS",
    "_coerce_float_from_string",
    "_coerce_float_or_none",
    "_coerce_int_from_string",
    "_coerce_int_or_none",
    "_coerce_score_cell",
    "_is_real_number",
    "_raw_value_to_string",
]
