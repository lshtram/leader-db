"""Unified-source Polity V sentinel + coercion helpers.

This module owns the per-cell coercion helpers used by the
unified-source Polity V observation-emission code in
:mod:`._transform`. The helpers handle:

- :data:`POLITY_V_SPECIAL_CODES` (re-exported from
  :mod:`._descriptor`) -- the documented ``-66`` / ``-77`` /
  ``-88`` provenance codes that are NOT numeric observations.
- :data:`POLITY_V_VALID_NEGATIVE_MIN` / :data:`POLITY_V_VALID_NEGATIVE_MAX`
  -- the documented valid negative range for ``polity`` /
  ``polity2`` composite scores. Valid negative scores
  (``-10..-1``) ARE numeric observations; the ``-66`` /
  ``-77`` / ``-88`` codes are NOT.
- :func:`_is_special_code` -- returns True iff the cell value is
  one of the documented special codes.
- :func:`_coerce_polity_value` -- applies the documented
  coercion matrix: returns ``int`` for valid cells (valid range
  + non-special), ``None`` for special codes + ``NaN`` /
  missing / non-numeric cells. The valid range is
  indicator-specific (see :func:`_coerce_polity_value`): the
  ``durable`` indicator (regime-durability YEARS counter) is
  special-cased with a valid range of ``>= 0`` and NO upper cap
  (long-running regimes produce values well above 10; the live
  ``p5v2018.sav`` carries ``durable`` values up to 170).
- :func:`_raw_cell_text` -- renders the original cell text for
  the ``raw_value`` audit column per the documented audit-trail
  matrix.

Split out of :mod:`._transform` so the transform module stays
focused on the per-row emission loop + the
:class:`NormalizedObservation` construction, and so each module
respects the documented 400-line convention. The helpers mirror
the PTS / FAS / RSF missing-value helper shape so the
unified-source subsystem stays consistent across adapters.

Sentinel-matrix semantics
-------------------------

Polity V component cells carry TWO independent signals:

- A valid score: ``int -10..+10`` for ``polity`` / ``polity2``;
  ``int 0..10`` for ``democ`` / ``autoc`` / ``xrreg`` /
  ``xrcomp`` / ``xropen`` / ``xconst`` / ``parreg`` /
  ``parcomp``; ``int >= 0`` (unbounded above) for ``durable``
  (regime-durability YEARS counter; the live ``p5v2018.sav``
  carries values up to 170). Valid negative scores on
  ``polity`` / ``polity2`` are NOT sentinels -- they are real
  political-freedom observations and must be preserved as
  numeric.
- A documented special code: ``-66`` / ``-77`` / ``-88``. These
  ARE NOT numeric observations; per the Polity V codebook they
  encode interregnum / foreign occupation / transition states.
  The unified transform emits ``value=None`` /
  ``value_type="missing"`` + the verbatim raw cell text on
  ``extension.raw_value`` for every special-code cell so audit
  code can recover the original cell.

NaN / blank / non-numeric cells are treated as missing
(``value=None`` / ``value_type="missing"``) per the documented
no-invented-observations contract.
"""

from __future__ import annotations

import math
from typing import Any

from ._descriptor import (
    POLITY_V_COMPONENT_SCORE_MAX,
    POLITY_V_COMPONENT_SCORE_MIN,
    POLITY_V_DURABLE_MIN_VALUE,
    POLITY_V_POLITY_SCORE_MAX,
    POLITY_V_POLITY_SCORE_MIN,
    POLITY_V_RAW_COLUMN_DURABLE,
    POLITY_V_SPECIAL_CODE_MEANINGS,
    POLITY_V_SPECIAL_CODES,
)

# Re-exports for the canonical module-level re-export contract.
__all__ = [
    "POLITY_V_SPECIAL_CODES",
    "POLITY_V_SPECIAL_CODE_MEANINGS",
    "POLITY_V_VALID_NEGATIVE_MAX",
    "POLITY_V_VALID_NEGATIVE_MIN",
    "_coerce_polity_value",
    "_is_special_code",
    "_raw_cell_text",
]

# Convenience aliases: the documented valid negative range for
# ``polity`` / ``polity2`` composite scores (the documented
# ``-10..-1`` band, NOT including the special codes
# ``-66`` / ``-77`` / ``-88``).
POLITY_V_VALID_NEGATIVE_MIN: int = POLITY_V_POLITY_SCORE_MIN
POLITY_V_VALID_NEGATIVE_MAX: int = -1


def _is_special_code(value: Any) -> bool:
    """Return True iff ``value`` is one of the documented special codes.

    The documented Polity V special codes are ``-66`` / ``-77`` /
    ``-88`` per the Polity V codebook. These encode
    interregnum / foreign occupation / transition states and
    are NOT numeric observations.

    The check accepts numeric values (int or float); non-numeric
    values (str / None / NaN) return False so the caller treats
    them as ``missing`` rather than ``special``.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        # bool is a subclass of int in Python; exclude so
        # True/False are not coerced to 1/0 (a bug, not data).
        return False
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return coerced in POLITY_V_SPECIAL_CODES


def _coerce_polity_value(  # noqa: PLR0911, PLR0912
    cell: Any,
    *,
    indicator: str,
    composite: bool = False,
) -> int | None:
    """Apply the Polity V coercion matrix to one cell.

    Parameters
    ----------
    cell:
        The raw SPSS cell value. May be ``int``, ``float`` (incl.
        ``NaN``), ``None``, or a defensive non-numeric value
        (the ``pyreadstat`` reader always returns numeric values
        for these columns so a non-numeric ``str`` would only
        occur in defensive test scenarios).
    indicator:
        The indicator variable name (e.g. ``polity`` /
        ``democ`` / ``xrreg`` / ``durable``). Used to choose the
        indicator-specific valid range. The ``durable`` indicator
        is special-cased: it is the regime-durability **years**
        counter per the Polity V codebook and has a documented
        valid range of ``>= 0`` with NO upper cap (long-running
        regimes produce values well above 10 -- the live
        ``p5v2018.sav`` carries ``durable`` values up to 170).
        Generic sub-component indicators (``democ`` / ``autoc``
        / ``xrreg`` / ``xrcomp`` / ``xropen`` / ``xconst`` /
        ``parreg`` / ``parcomp``) use ``0..10``.
    composite:
        True when ``indicator`` is a composite score
        (``polity`` or ``polity2``) whose valid range is
        ``-10..+10``. False for sub-component indicators whose
        valid lower bound is 0.

    Returns
    -------
    int | None
        The int score for valid cells, ``None`` for special
        codes / NaN / non-numeric / out-of-range cells.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    # NaN handling: ``pyreadstat`` returns ``numpy.float64('nan')``
    # for missing cells. ``math.isnan`` would not work on a
    # non-numeric ``cell`` so guard first.
    if isinstance(cell, float):
        if math.isnan(cell):
            return None
        # Coerce floats to int when they are whole numbers (the
        # Polity V .sav stores scores as float64; the integer
        # value is preserved by ``int(cell)`` only when the float
        # is exactly integral).
        if not cell.is_integer():
            return None
        coerced = int(cell)
    elif isinstance(cell, int):
        coerced = cell
    else:
        return None

    # Documented special codes are NEVER numeric observations.
    if coerced in POLITY_V_SPECIAL_CODES:
        return None

    # Documented valid range.
    # - ``durable``: regime-durability YEARS counter, valid range
    #   is ``>= 0`` with NO upper cap (long-running regimes produce
    #   values >> 10). Using the generic ``0..10`` cap here would
    #   silently drop the majority of Polity V durability
    #   observations (the live ``p5v2018.sav`` carries ``durable``
    #   values up to 170, with 8937 of the 17574 rows > 10). The
    #   special-code set above still excludes ``-66`` / ``-77`` /
    #   ``-88``; negative non-special values fall through to the
    #   ``lower`` check below.
    # - Composite scores (``polity`` / ``polity2``): ``-10..+10``.
    # - Sub-component indicators (``democ`` / ``autoc`` / etc.):
    #   ``0..10`` (documented Polity V sub-component range).
    if indicator == POLITY_V_RAW_COLUMN_DURABLE:
        lower = POLITY_V_DURABLE_MIN_VALUE
        upper = None
    elif composite:
        lower = POLITY_V_POLITY_SCORE_MIN
        upper = POLITY_V_POLITY_SCORE_MAX
    else:
        lower = POLITY_V_COMPONENT_SCORE_MIN
        upper = POLITY_V_COMPONENT_SCORE_MAX
    if coerced < lower:
        return None
    if upper is not None and coerced > upper:
        return None
    return coerced


def _raw_cell_text(cell: Any) -> str:  # noqa: PLR0911
    """Render the original SPSS cell text for the ``raw_value`` audit column.

    The audit column is preserved verbatim so downstream Stage 12
    cross-source comparison code can recover the original cell
    text without re-reading the .sav file.

    The helper matches the PTS / FAS / RSF audit-trail matrix:

    - int / float (incl. NaN): ``str(int(cell))`` for integral
      floats (e.g. ``"7"``) and ``repr(float)`` for non-integral
      floats (defensive -- should not happen in a real Polity V
      .sav but matches the PTS / RSF defensive coverage).
    - special codes: ``str(int)`` (e.g. ``"-66"``).
    - ``None`` -> ``"None"`` (defensive: never silently drop the
      audit cell).
    - bool -> ``str(bool)`` (defensive: should not happen;
      preserved verbatim so the audit trail shows the actual cell
      text).
    - other string -> the string verbatim.
    - other type -> ``str(cell)`` (defensive fallback).

    Args:
        cell: the raw SPSS cell value (``int``, ``float``, ``None``,
            or defensive for other types).

    Returns:
        The stringified cell text. Never ``None`` -- the audit
        column always carries a value so the dropped-row reason
        is recoverable from the run audit trail.
    """
    if cell is None:
        return "None"
    if isinstance(cell, bool):
        return str(cell)
    if isinstance(cell, int):
        return str(cell)
    if isinstance(cell, float):
        if math.isnan(cell):
            return "nan"
        if cell.is_integer():
            return str(int(cell))
        return repr(cell)
    if isinstance(cell, str):
        return cell
    return str(cell)
