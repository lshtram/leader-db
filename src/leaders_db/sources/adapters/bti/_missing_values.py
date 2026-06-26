"""Unified-source Bertelsmann Transformation Index (BTI)
missing-value coercion helpers.

This module owns the cell-coercion + raw-cell-text helpers used by
:mod:`._transform` and :mod:`._observation_builder` to keep the
per-row emission loop focused on the iteration + emission contract.

The helpers delegate to the legacy
:func:`leaders_db.ingest.bti_db_helpers` module (loaded lazily so
the unified package boundary is preserved) so the unified adapter
does not duplicate the BTI missing-data coercion contract:

- :func:`_coerce_float` -- turn an xlsx / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles the BTI blank-cell convention plus the V-Dem /
  WGI / PTS / WDI sentinels (defense in depth).
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field. Preserves the
  BTI cell text (numeric string for valid cells, ``"nan"`` for
  pandas NaN, ``""`` for None).

BTI missing-data convention
---------------------------

BTI's missing-data convention is a blank cell (the xlsx never
carries ``"NA"`` / ``"#N/A"`` / ``"-999"`` -- those are V-Dem /
WGI / WDI sentinel conventions). The legacy reader coerces blank
cells to ``NaN`` (pandas) after wide-pivot; the unified transform
skips ``None`` / ``NaN`` cells (no silent conversion of missing
raw cells; SRC-OBS-007). The audit-trail ``raw_value`` is
recovered from the legacy ``df.attrs["_bti_raw_long"]`` pre-coercion
long frame so even the dropped cells carry an auditable raw cell
string.
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.contracts import ObservationValueType


def _coerce_float(value: Any) -> float | None:
    """Coerce an xlsx / pandas cell to ``float`` or
    return ``None``.

    BTI's missing-data convention is a blank cell.
    After wide-pivot, missing cells become pandas
    ``NaN``. This helper handles both, plus the
    common string sentinels from V-Dem / WGI / PTS
    / WDI (``""``, ``"NA"``, ``"NaN"``, ``"nan"``,
    ``"null"``, ``"None"``, ``"-999"``,
    ``"-999.0"``, ``"#N/A"``, ``"n/a"``) as defense
    in depth via the legacy
    :func:`leaders_db.ingest.bti_db_helpers._coerce_float`
    bridge.

    The legacy helper is imported lazily so the
    unified package boundary is preserved.
    """
    # Lazy import: keeps ``leaders_db.sources``
    # importable without ``leaders_db.ingest``
    # (docs/architecture/sources.md §10.1 +
    # docs/requirements/sources.md §12
    # SRC-MIG-007).
    from leaders_db.ingest.bti_db_helpers import (
        _coerce_float as _legacy_coerce_float,
    )

    return _legacy_coerce_float(value)


def _raw_value_to_string(cell: Any) -> str:
    """Render a raw cell for the
    ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing
      cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the
      audit trail of what pandas saw).
    - All other values -> ``str(cell)`` (preserves
      the BTI cell text for the audit trail).

    Delegates to the legacy
    :func:`leaders_db.ingest.bti_db_helpers._raw_value_to_string`
    helper via lazy import.
    """
    from leaders_db.ingest.bti_db_helpers import (
        _raw_value_to_string as _legacy_raw_value_to_string,
    )

    return _legacy_raw_value_to_string(cell)


def _resolve_value_type(cell: Any) -> ObservationValueType:
    """Resolve the canonical ``ObservationValueType``
    for one BTI cell.

    The BTI xlsx carries numeric 1-10 scores
    (verified live against the cumulative xlsx); a
    blank cell coerces to ``None`` and the legacy
    transform skips it (no silent conversion per
    SRC-OBS-007). The emitted observation therefore
    always carries ``value_type="numeric"`` for
    valid BTI cells; missing cells never emit an
    observation.
    """
    coerced = _coerce_float(cell)
    if coerced is None:
        # Defensive: missing cells are NOT emitted
        # by the transform layer, but the helper
        # returns ``"missing"`` so a future caller
        # that filters outside the transform can
        # distinguish missing from numeric.
        return "missing"
    return "numeric"


__all__ = [
    "_coerce_float",
    "_raw_value_to_string",
    "_resolve_value_type",
]
