"""Stage 2 -- UCDP DB helpers: coercion + bundle metadata (REQ-SRC-006).

This module holds the pure helper functions used by :mod:`ucdp_db`. It
is split out of :mod:`ucdp_db` so the DB module stays focused on the
DB-write contract (sources, source_observations, run manifest) and
the helper module stays focused on the value-coercion and
bundle-metadata parsing rules.

Owns:

- :func:`_coerce_float` -- turn a CSV / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles the UCDP missing-data convention (no sentinels in
  the live data) plus the V-Dem / WDI / WGI sentinels as
  defense in depth.
- :func:`_coerce_float_from_string` -- string variant of
  :func:`_coerce_float`.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the UCDP
  literal cell for present cells.
- :func:`_read_ucdp_bundle_metadata` -- read
  ``data/raw/ucdp/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.

The DB-write functions (:func:`register_ucdp_source`,
:func:`write_ucdp_observations`, :func:`write_ucdp_run_manifest`)
live in :mod:`leaders_db.ingest.ucdp_db`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.ucdp`.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .ucdp_io import UCDP_SOURCE_KEY

#: UCDP has no missing-data sentinels in the live data (the ``best``
#: column is always a non-negative integer or null; the
#: ``type_of_violence`` column is always 1, 2, or 3). We include the
#: union of all source-specific sentinels as defense in depth in case
#: a future UCDP release re-uses them.
_UCDP_MISSING_STRINGS: frozenset[str] = frozenset(
    {"#N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)

#: Numeric UCDP missing sentinel (defense in depth; UCDP has no
#: sentinels in the live data, but the V-Dem-style helper still
#: recognizes it).
_UCDP_MISSING_SENTINEL: float = -999.0


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_ucdp_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/ucdp/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(UCDP_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, object] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8")
        )
        return result
    except json.JSONDecodeError:
        return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(raw: object) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)`` on failure."""
    if not isinstance(raw, str) or "-" not in raw:
        return (None, None)
    start_str, end_str = raw.split("-", 1)
    try:
        return (int(start_str.strip()), int(end_str.strip()))
    except ValueError:
        return (None, None)


# ---------------------------------------------------------------------------
# Missing-value coercion
# ---------------------------------------------------------------------------


def _coerce_float(value: object) -> float | None:
    """Coerce a CSV / pandas cell to ``float`` or return ``None``.

    UCDP has no missing-data sentinels in the live data: ``best`` is
    always a non-negative integer or NaN; ``type_of_violence`` is
    always 1, 2, or 3. This helper handles the UCDP convention
    (None / NaN -> None) plus the common string sentinels from
    V-Dem / WDI / WGI (``""``, ``"NA"``, ``"NaN"``, ``"nan"``,
    ``"null"``, ``"None"``, ``"-999"``, ``"-999.0"``) as defense in
    depth.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return None if value <= _UCDP_MISSING_SENTINEL else value
    if isinstance(value, int) and not isinstance(value, bool):
        return None if value <= int(_UCDP_MISSING_SENTINEL) else float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _UCDP_MISSING_STRINGS:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        return None
    if numeric <= _UCDP_MISSING_SENTINEL:
        return None
    return numeric


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of what
      pandas saw).
    - All other values -> ``str(cell)`` (preserves the UCDP cell
      text so the audit trail shows what the source file actually
      said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_UCDP_MISSING_SENTINEL",
    "_UCDP_MISSING_STRINGS",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_ucdp_bundle_metadata",
]
