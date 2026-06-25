"""Unified-source UCDP missing-value / coercion helpers.

This module owns the per-cell coercion helpers used by the
unified-source UCDP observation-emission code in
:mod:`._transform`. The helpers handle:

- ``_is_real_number`` -- NaN / None / boolean guard for the
  wide-format cells (event-count ``Int64`` columns +
  fatalities ``float`` columns).
- ``_coerce_cell`` -- converts a wide-format cell into the
  ``(float, string)`` tuple the unified observation contract
  expects (``value`` is the canonical numeric; ``raw_value``
  is the audit-trail string).

Split out of :mod:`._transform` so the transform module
stays focused on the per-row emission loop + the
:class:`NormalizedObservation` construction, and so each
module respects the documented 400-line convention. The
helpers are pure functions that mirror the WGI / V-Dem
``_is_real_number`` shape so the unified-source subsystem
stays consistent.
"""

from __future__ import annotations

import math
from typing import Any


def _is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric.

    Mirrors the WGI / V-Dem ``_is_real_number`` helper. Used
    to skip NaN cells in the wide-format fatalities columns
    (events with ``best=null``) without silently converting
    missing raw cells (SRC-OBS-007).

    The wide frame carries ``Int64`` for event counts and
    ``float`` for fatalities. ``pd.isna`` is invoked inside
    :func:`_coerce_cell` via ``float(value)`` for the
    ``Int64`` NaN handling; this leaf-level helper accepts
    the canonical plain ``int`` / ``float`` / ``bool`` /
    ``None`` shapes that survive ``DataFrame.iterrows()``
    on the wide frame.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, int)


def _coerce_cell(value: Any) -> tuple[float | None, str | None]:
    """Coerce a wide-format cell into ``(float, string)`` for emission.

    Returns ``(None, None)`` when the cell is NaN / missing;
    otherwise returns ``(float(value), str(value))`` where
    ``float(value)`` is the canonical numeric value and
    ``str(value)`` is the audit-trail string. Event-count
    columns (``Int64``) coerce to ``float`` for the unified
    contract (``value_type="numeric"`` requires ``value``
    to be a number); fatalities columns are already
    ``float``. The ``float(value)`` cast surfaces ``Int64``
    ``NaN`` cells (the pandas nullable Integer type's
    ``NaN`` is silently coerced via ``float`` and
    rejected by ``_is_real_number``).
    """
    if not _is_real_number(value):
        return None, None
    try:
        return float(value), str(value)
    except (TypeError, ValueError):
        return None, None


__all__ = [
    "_coerce_cell",
    "_is_real_number",
]
