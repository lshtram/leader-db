"""Unified-source RSF missing-value / decimal-comma
helpers.

This module owns the per-cell coercion helpers used by
the unified-source RSF observation-emission code in
:mod:`._transform`. The helpers handle:

- :func:`_coerce_score_value` -- apply the
  comma-decimal separator parsing to a score /
  component cell (``"72,67"`` -> ``72.67``).
- :func:`_coerce_rank_value` -- parse an RSF rank
  cell into ``int`` (``"149"`` -> ``149``).
- :func:`_raw_cell_text` -- render the verbatim RSF
  cell text for the ``raw_value`` audit column.

Split out of :mod:`._transform` so the transform
module stays focused on the per-row emission loop +
the :class:`NormalizedObservation` construction, and
so each module respects the documented 400-line
convention. The helpers mirror the UCDP / V-Dem /
WGI / CPI / PTS missing-value helper shape so the
unified-source subsystem stays consistent across
adapters.

Decimal-comma semantics
-----------------------

The RSF files use ``";"`` as the delimiter and
``","`` as the decimal separator (European
convention). The legacy reader
(:func:`leaders_db.ingest.rsf_press_freedom_csv.read_rsf_press_freedom_csv`)
applies the comma-decimal normalization at read time
and produces a narrow-format DataFrame where:

- Score / component cells appear as ``float`` values
  with the comma already normalized to period (e.g.
  ``72.67`` from the raw ``"72,67"``).
- Rank cells appear as ``int`` values (``149`` from
  the raw ``"149"``).
- Empty / missing cells appear as ``None``.
- The pre-coercion raw cell text is preserved in
  the narrow frame's ``raw_value`` column (a
  ``str``) so the unified transform can carry the
  verbatim RSF cell text onto the observation's
  ``extension["raw_value"]`` audit column.

This module provides the per-cell coercion helpers
the unified transform uses to apply the same
comma-decimal / int-coercion semantics to the narrow
frame's ``normalized_value`` column. The legacy
reader already produces a normalized ``float`` /
``int`` in the ``normalized_value`` column; the
helpers here are defensive guards for a future
refactor that surfaces a raw ``str`` cell (e.g. a
string-typed CSV cell that needs comma-decimal
coercion before ``float()`` is applied).

The unified transform skips rows whose
``normalized_value`` cell is ``None`` / ``NaN`` -- no
silent conversion of missing raw cells (SRC-OBS-007).
The audit-trail ``raw_value`` is preserved on the
observation's ``extension`` so downstream audit code
can recover the original RSF cell text without
re-reading the legacy CSV.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decimal-comma + int coercion
# ---------------------------------------------------------------------------


def _normalize_decimal(cell: str | float | int | None) -> str:
    """Convert an RSF comma-decimal cell to a
    period-decimal string.

    RSF files use ``","`` as the decimal separator
    (European convention) and ``";"`` as the
    delimiter. ``"72,67"`` -> ``"72.67"``;
    ``"0,5"`` -> ``"0.5"``. The function is a no-op
    for cells without a comma; integer cells like
    ``"149"`` round-trip unchanged. Used by the float
    coercion helper below.
    """
    if cell is None:
        return ""
    return str(cell).replace(",", ".").strip()


def _coerce_numeric_to_float(cell: Any) -> float | None:
    """Return the ``float`` of a numeric ``cell``, or
    ``None`` if the cell is missing / non-numeric.

    Handles ``None`` / ``bool`` (rejected -- bool is
    subclass of ``int``; reject so ``True`` /
    ``False`` are not coerced to ``1.0`` / ``0.0``) /
    ``int`` / ``float`` directly. The string path
    (with comma-decimal normalization) is handled
    separately by :func:`_coerce_score_value`.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    return None


def _coerce_numeric_to_int(cell: Any) -> int | None:
    """Return the ``int`` of a numeric ``cell``, or
    ``None`` if the cell is missing / non-numeric.

    Handles ``None`` / ``bool`` (rejected) / ``int``
    / ``float`` directly. The string path
    (with whitespace stripping + sentinel rejection)
    is handled separately by :func:`_coerce_rank_value`.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, int):
        return int(cell)
    if isinstance(cell, float):
        try:
            return int(cell)
        except (TypeError, ValueError):
            return None
    return None


def _coerce_score_value(
    cell: Any,
    raw_value: str | None = None,
) -> float | None:
    """Coerce an RSF score / component cell to ``float``.

    Returns the ``float`` value for non-empty cells
    (e.g. ``"72,67"`` -> ``72.67``); ``None`` for
    empty / whitespace-only / ``"nan"`` / ``"NA"``
    cells. The ``raw_value`` argument carries the
    verbatim cell text (preserved on the
    ``extension["raw_value"]`` audit column) so the
    audit trail recovers the original cell text when
    the cell is missing.

    The function mirrors the legacy
    :func:`leaders_db.ingest.rsf_press_freedom_csv._parse_decimal_optional`
    helper shape so the unified transform layer can
    apply the same comma-decimal / float coercion
    semantics as the legacy reader.
    """
    direct = _coerce_numeric_to_float(cell)
    if direct is not None:
        return direct
    normalized = _normalize_decimal(cell)
    if not normalized or normalized.lower() in {
        "nan", "na", "null",
    }:
        return None
    try:
        return float(normalized)
    except ValueError:
        _logger.debug(
            "RSF could not parse decimal cell %r; "
            "treating as missing.",
            cell,
        )
        return None


def _coerce_rank_value(
    cell: Any,
    raw_value: str | None = None,
) -> int | None:
    """Coerce an RSF rank cell to ``int``.

    RSF rank cells are always integers in the live
    data (e.g. ``"149"``, ``"1"``); the function
    handles empty cells and defensive fall-throughs to
    ``None`` (a missing rank would itself be a data
    anomaly worth flagging).

    The function mirrors the legacy
    :func:`leaders_db.ingest.rsf_press_freedom_csv._coerce_rank_optional`
    helper shape so the unified transform layer can
    apply the same int-coercion semantics as the
    legacy reader.
    """
    direct = _coerce_numeric_to_int(cell)
    if direct is not None:
        return direct
    stripped = str(cell).strip()
    if not stripped or stripped.lower() in {
        "nan", "na", "null",
    }:
        return None
    try:
        return int(stripped)
    except ValueError:
        _logger.debug(
            "RSF could not parse rank cell %r; "
            "treating as missing.",
            cell,
        )
        return None


def _raw_cell_text(cell: Any) -> str:
    """Render the original RSF cell text for the
    ``raw_value`` audit column.

    Per the legacy reader's audit-trail shape:

    - ``int`` 1-180 -> ``str(int)`` (e.g. ``"3"``).
    - ``float`` 0.0-100.0 -> ``repr(float)`` (preserves
      the audit trail of what the legacy reader saw;
      float cells are the canonical post-comma-decimal
      normalized form).
    - ``str`` -> the string verbatim (preserves any
      unexpected cell text in the audit trail; the
      comma-decimal raw form like ``"72,67"`` is
      preserved verbatim when the legacy reader
      surfaces the pre-coercion cell text).
    - ``None`` -> ``"None"`` (defensive: never
      silently drop the audit cell).
    - ``bool`` -> ``str(bool)`` (defensive: should
      not happen; preserved verbatim so the audit
      trail shows the actual cell text).
    - other -> ``str(cell)``.

    Args:
        cell: the raw cell value (``int`` / ``float``
            / ``str`` / ``None``, or defensive for
            other types).

    Returns:
        The stringified cell text. Never ``None`` --
        the audit column always carries a value so
        the dropped-row reason is recoverable from
        the run audit trail.
    """
    if cell is None:
        return "None"
    if isinstance(cell, bool):
        return str(cell)
    if isinstance(cell, int):
        return str(cell)
    if isinstance(cell, float):
        return repr(cell)
    if isinstance(cell, str):
        return cell
    return str(cell)


def _is_missing(cell: Any) -> bool:
    """Return ``True`` if the cell should be treated as
    missing by the unified transform layer.

    Mirrors the legacy reader's missing-cell shape:
    ``None`` and ``NaN`` are both treated as missing.
    Empty / whitespace-only strings are also missing.
    The function is defensive for non-pandas types so
    the unified transform can be exercised without a
    pandas dependency at the test boundary.
    """
    if cell is None:
        return True
    if isinstance(cell, str) and not cell.strip():
        return True
    try:
        import math
        if isinstance(cell, float) and math.isnan(cell):
            return True
    except ImportError:
        pass
    try:
        import pandas as _pd
        if _pd.isna(cell):
            return True
    except ImportError:
        pass
    return False


__all__ = [
    "_coerce_rank_value",
    "_coerce_score_value",
    "_is_missing",
    "_normalize_decimal",
    "_raw_cell_text",
]
