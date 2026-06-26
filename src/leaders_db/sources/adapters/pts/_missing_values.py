"""Unified-source PTS sentinel-matrix and missing-value
helpers.

This module owns the per-cell coercion helpers used by the
unified-source Political Terror Scale observation-emission
code in :mod:`._transform`. The helpers handle:

- :data:`PTS_NA_STATUS_CODES` -- the 5 known
  ``NA_Status_X`` provenance codes (``0`` / ``66`` / ``77``
  / ``88`` / ``99``) plus the §6.5 defensive
  ``PTS_UNKNOWN_NA_STATUS`` warning code.
- :func:`_coerce_pts_value` -- applies the 4-case
  §6 sentinel matrix to a ``(PTS_X, NA_Status_X)`` cell
  pair (the precedence rule: NA_Status takes precedence
  over PTS_X).
- :func:`_raw_cell_text` -- renders the original
  ``PTS_X`` cell text for the ``raw_value`` audit column
  per the §6.3 audit-trail matrix.

Split out of :mod:`._transform` so the transform module
stays focused on the per-row emission loop + the
:class:`NormalizedObservation` construction, and so each
module respects the documented 400-line convention. The
helpers mirror the UCDP / V-Dem / WGI missing-value
helper shape so the unified-source subsystem stays
consistent across adapters.

Sentinel-matrix semantics
-------------------------

The PTS xlsx carries TWO independent signals per
indicator cell (verified live 2026-06-18 per
``docs/architecture/pts.md`` §2 + §6):

- ``PTS_X`` -- int 1-5 or str ``'NA'``.
- ``NA_Status_X`` -- int 0 / 66 / 77 / 88 / 99.

The 4-case precedence rule is documented in the design
doc §6:

1. ``int 1-5`` + ``NA_Status_X == 0`` -> **valid**;
   return the int.
2. ``int 1-5`` + ``NA_Status_X != 0`` -> drop the
   indicator (NA_Status confirms missing); audit value
   is ``str(int)``.
3. ``'NA'`` + ``NA_Status_X != 0`` -> drop the indicator
   (the sentinel was a missing-value flag, and NA_Status
   confirms it); audit value is ``"NA"``.
4. ``'NA'`` + ``NA_Status_X == 0`` -> drop the
   indicator AND log a WARNING (the inconsistency case:
   the cell says ``'NA'`` but the provenance flag says
   "present"); audit value is ``"NA"``.

The §6.5 defensive check (an unknown ``NA_Status``
code -- e.g. the hypothetical ``55`` per architecture
§6.5) is logged at WARNING and treated as missing.
This guard lets a future xlsx release introduce a new
code without silently dropping cells or raising.

The helper preserves the raw ``'NA'`` string and the
raw ``int`` in the audit trail (per design doc §6.3)
so downstream code can recover the original cell text
without re-reading the xlsx.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NA_Status constants
# ---------------------------------------------------------------------------

#: The 5 known ``NA_Status_X`` provenance codes
#: (verified live 2026-06-18 per ``docs/architecture/pts.md``
#: §2). ``0`` is the only value that admits the
#: published ``PTS_X`` value; the other 4
#: (``66 / 77 / 88 / 99``) drop the indicator per
#: the §6 precedence rule. The frozenset is the canonical
#: defensive check target: any cell with a ``NA_Status``
#: value NOT in this set triggers a WARNING + the missing
#: treatment (the §6.5 guard).
PTS_NA_STATUS_CODES: frozenset[int] = frozenset(
    {0, 66, 77, 88, 99},
)

#: Module-local structured warning code used to surface
#: a §6.5 unknown ``NA_Status`` code. Distinct from the
#: ``PTS_INCONSISTENCY_WARNING_CODE`` because the
#: diagnostic is different: an unknown code is a future-
#: release schema-drift guard, NOT a data inconsistency.
PTS_UNKNOWN_NA_STATUS_WARNING_CODE: str = (
    "pts_unknown_na_status"
)

#: Module-local structured warning code used to surface
#: a §6.4 case-4 data-inconsistency row (PTS_X='NA' with
#: NA_Status_X=0). Distinct from the unknown-code
#: warning so audit code can tell the two failure classes
#: apart.
PTS_INCONSISTENCY_WARNING_CODE: str = (
    "pts_na_with_present_status"
)

#: The expected ``PTS_X`` literal string sentinel.
#: Per design doc §2, ``PTS_X`` is ``int 1-5`` OR
#: literal ``'NA'`` (uppercase, no whitespace).
PTS_NA_SENTINEL_STRING: str = "NA"

#: The lower / upper bounds of the PTS raw scale.
#: Used by the coercion helper's int range check.
PTS_RAW_SCALE_MIN: int = 1
PTS_RAW_SCALE_MAX: int = 5


# ---------------------------------------------------------------------------
# Sentinel matrix
# ---------------------------------------------------------------------------


def _coerce_pts_value(  # noqa: PLR0911
    pts_cell: Any,
    na_status: Any,
    *,
    country: str,
    year: int,
    indicator: str,
) -> int | None:
    """Apply the §6 4-case sentinel matrix with the §6.5
    defensive check.

    Returns the int 1-5 for valid cells, ``None`` for
    missing or inconsistent cells. Logs a warning for
    case-4 (the inconsistency case) and for the §6.5
    unknown ``NA_Status`` code.

    Precedence rule (per §6): **NA_Status takes
    precedence over ``PTS_X``**. A cell is valid iff
    ``NA_Status == 0`` AND ``PTS_X`` is an int in 1-5.
    Any other combination drops the indicator.

    Cases (per ``docs/architecture/pts.md`` §6):

    1. int 1-5 + ``NA_Status == 0`` -> valid; return the int.
    2. int 1-5 + ``NA_Status != 0`` -> drop (NA_Status confirms missing).
    3. ``'NA'`` + ``NA_Status != 0`` -> drop (expected sentinel path).
    4. ``'NA'`` + ``NA_Status == 0`` -> drop + WARNING (inconsistency).

    §6.5 defensive check: an unknown ``NA_Status`` code
    (one NOT in :data:`PTS_NA_STATUS_CODES`) is logged at
    WARNING and treated as missing.

    Args:
        pts_cell: the ``PTS_X`` cell value (int 1-5 or str
            ``'NA'``; defensive for unexpected types).
        na_status: the paired ``NA_Status_X`` value (int
            0/66/77/88/99; defensive for unexpected types).
        country, year, indicator: used in the case-4
            and §6.5 warning messages.

    Returns:
        The int 1-5 for valid cells; ``None`` otherwise.
    """
    # §6.5 defensive check: an unknown ``NA_Status`` code
    # is logged and treated as missing. A future xlsx
    # release that introduces a new code (e.g., the
    # hypothetical 55 per architecture §6.5) will surface
    # here rather than silently dropping the cell or
    # raising.
    try:
        na_status_int = int(na_status)
    except (TypeError, ValueError):
        _logger.warning(
            "PTS non-integer NA_Status: country=%s year=%d "
            "indicator=%s na_status=%r. Treating as missing.",
            country, year, indicator, na_status,
        )
        return None

    if na_status_int not in PTS_NA_STATUS_CODES:
        _logger.warning(
            "PTS unknown NA_Status code: country=%s "
            "year=%d indicator=%s na_status=%s. Treating "
            "as missing.",
            country, year, indicator, na_status_int,
        )
        return None

    # NA_Status takes precedence over PTS_X.
    if na_status_int != 0:
        return None  # Cases 2 and 3.

    # Defensive: bool is a subclass of int in Python;
    # exclude so True/False are not coerced to 1/0 (a
    # bug, not data).
    if isinstance(pts_cell, bool):
        _logger.warning(
            "PTS unexpected cell value (bool): country=%s "
            "year=%d indicator=%s pts_cell=%r "
            "na_status=%d. Treating as missing.",
            country, year, indicator, pts_cell, na_status_int,
        )
        return None

    # Case 1: valid int in 1-5.
    if isinstance(pts_cell, int) and (
        PTS_RAW_SCALE_MIN <= pts_cell <= PTS_RAW_SCALE_MAX
    ):
        return pts_cell

    # Case 4: 'NA' with NA_Status=0 -> inconsistency.
    if isinstance(pts_cell, str) and (
        pts_cell.strip() == PTS_NA_SENTINEL_STRING
    ):
        _logger.warning(
            "PTS data inconsistency: country=%s year=%d "
            "indicator=%s has PTS_X='NA' with NA_Status=0. "
            "Treating as missing.",
            country, year, indicator,
        )
        return None

    # Anything else (float, unexpected string, None).
    # Log and treat as missing.
    _logger.warning(
        "PTS unexpected cell value: country=%s year=%d "
        "indicator=%s pts_cell=%r na_status=%d. Treating "
        "as missing.",
        country, year, indicator, pts_cell, na_status_int,
    )
    return None


def _raw_cell_text(pts_cell: Any) -> str:
    """Render the original ``PTS_X`` cell text for the
    ``raw_value`` audit column.

    Per the §6.3 audit-trail matrix:

    - int 1-5 -> ``str(int)`` (e.g. ``"3"``).
    - int 1-5 with ``NA_Status != 0`` -> ``str(int)``
      (audit shows the published value even though the
      row was dropped).
    - ``'NA'`` (any ``NA_Status``) -> ``"NA"`` (literal
      sentinel).
    - ``None`` -> ``"None"`` (defensive: never silently
      drop the audit cell).
    - bool -> ``str(bool)`` (defensive: should not
      happen; preserved verbatim so the audit trail
      shows the actual cell text).
    - float -> ``repr(float)`` (preserves the audit
      trail of what openpyxl saw; float cells are not
      expected in a real PTS xlsx but defensive
      coverage matches the §6.2 defensive path).
    - other string -> the string verbatim (preserves
      any unexpected cell text in the audit trail).

    Args:
        pts_cell: the raw ``PTS_X`` cell value (``int``,
            ``str 'NA'``, ``None``, or defensive for
            other types).

    Returns:
        The stringified cell text. Never ``None`` -- the
        audit column always carries a value so the
        dropped-row reason is recoverable from the run
        audit trail.
    """
    if pts_cell is None:
        return "None"
    if isinstance(pts_cell, bool):
        return str(pts_cell)
    if isinstance(pts_cell, int):
        return str(pts_cell)
    if isinstance(pts_cell, float):
        return repr(pts_cell)
    if isinstance(pts_cell, str):
        return pts_cell
    return str(pts_cell)


def _raw_na_status_text(na_status: Any) -> str:
    """Render the original ``NA_Status_X`` cell text for
    the audit trail.

    Per design doc §6.3, the audit-trail NA_Status cell
    text is the int code (or its string representation
    for defensive coverage). Preserves the audit trail
    so a downstream Stage 12 cross-source comparison can
    recover the original ``NA_Status`` per
    ``(country, year, variable_name)``.

    Args:
        na_status: the raw ``NA_Status_X`` cell value
            (``int 0/66/77/88/99`` or defensive for
            unexpected types).

    Returns:
        The stringified cell text. Never ``None``.
    """
    if na_status is None:
        return "None"
    if isinstance(na_status, bool):
        return str(na_status)
    if isinstance(na_status, int):
        return str(na_status)
    if isinstance(na_status, float):
        return repr(na_status)
    if isinstance(na_status, str):
        return na_status
    return str(na_status)


__all__ = [
    "PTS_INCONSISTENCY_WARNING_CODE",
    "PTS_NA_SENTINEL_STRING",
    "PTS_NA_STATUS_CODES",
    "PTS_RAW_SCALE_MAX",
    "PTS_RAW_SCALE_MIN",
    "PTS_UNKNOWN_NA_STATUS_WARNING_CODE",
    "_coerce_pts_value",
    "_raw_cell_text",
    "_raw_na_status_text",
]
