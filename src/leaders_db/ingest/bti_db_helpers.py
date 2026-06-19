"""Stage 2 -- Bertelsmann BTI DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by :mod:`bti_db`. It
is split out of :mod:`bti_db` so the DB module stays focused on the
DB-write contract (sources, source_observations, run manifest) and the
helper module stays focused on the value-coercion and bundle-metadata
parsing rules.

Owns:

- :data:`_BTI_MISSING_STRINGS` -- defense-in-depth union of missing
  string sentinels (BTI uses blank cells, but a future BTI release
  could introduce an explicit token).
- :func:`_coerce_float` -- turn an xlsx / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles the BTI blank-cell convention plus the V-Dem /
  WGI / PTS / WDI sentinels (defense in depth).
- :func:`_coerce_float_from_string` -- string variant of
  :func:`_coerce_float`.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field.
- :func:`_read_bti_bundle_metadata` -- read
  ``data/raw/bti/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.

The DB-write functions (:func:`register_bti_source`,
:func:`write_bti_observations`, :func:`write_bti_run_manifest`) live
in :mod:`leaders_db.ingest.bti_db`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.bti`.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .bti_io import BTI_SOURCE_KEY

#: BTI's missing-data convention is a blank cell. The xlsx never
#: contains ``"NA"`` / ``"#N/A"`` / ``-999`` (those are V-Dem / WGI /
#: V-Dem / V-Dem-sentinel conventions), but we include the union of
#: common string sentinels as defense-in-depth in case a future BTI
#: release re-uses them.
_BTI_MISSING_STRINGS: frozenset[str] = frozenset(
    {"#N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", "", "n/a"}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_bti_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/bti/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(BTI_SOURCE_KEY) / "metadata.json"
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
    """Coerce an xlsx / pandas cell to ``float`` or return ``None``.

    BTI's missing-data convention is a blank cell. After wide-pivot,
    missing cells become pandas NaN. This helper handles both, plus the
    common string sentinels from V-Dem / WGI / PTS / WDI
    (``""``, ``"NA"``, ``"NaN"``, ``"nan"``, ``"null"``, ``"None"``,
    ``"-999"``, ``"-999.0"``, ``"#N/A"``, ``"n/a"``) as defense in depth.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return float(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _BTI_MISSING_STRINGS:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of what
      pandas saw).
    - All other values -> ``str(cell)`` (preserves the BTI cell text
      for the audit trail).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_BTI_MISSING_STRINGS",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_bti_bundle_metadata",
]
