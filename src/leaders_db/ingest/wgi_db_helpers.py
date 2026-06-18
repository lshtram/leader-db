"""Stage 2 -- World Bank WGI DB helpers: coercion + bundle metadata (REQ-SRC-002).

This module holds the pure helper functions used by :mod:`wgi_db`. It is
split out of :mod:`wgi_db` so the DB module stays focused on the
DB-write contract (sources, source_observations, run manifest) and the
helper module stays focused on the value-coercion and bundle-metadata
parsing rules.

Owns:

- :data:`_WGI_MISSING_SENTINEL` / :data:`_WGI_MISSING_STRINGS` -- the
  WGI missing-data convention (``"#N/A"`` literal) plus the
  defense-in-depth union of V-Dem / WDI sentinels.
- :func:`_coerce_float` -- turn an xlsx / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles the WGI missing-data convention plus all the V-Dem /
  WDI sentinels (defense in depth).
- :func:`_coerce_float_from_string` -- string variant of
  :func:`_coerce_float`.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the WGI
  literal ``"#N/A"`` for missing cells.
- :func:`_read_wgi_bundle_metadata` -- read
  ``data/raw/world_bank_wgi/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range; return
  ``(None, None)`` on failure.

The DB-write functions (:func:`register_wgi_source`,
:func:`write_wgi_observations`, :func:`write_wgi_run_manifest`) live in
:mod:`leaders_db.ingest.wgi_db`. The orchestrator that ties everything
together lives in :mod:`leaders_db.ingest.wgi`.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .wgi_io import WGI_SOURCE_KEY

#: WGI's missing-data convention is the literal string ``"#N/A"``. The
#: xlsx never contains ``-999`` (V-Dem's convention) or ``null`` (WDI's
#: convention), but we include the union of all three sets as
#: defense-in-depth in case a future WGI release re-uses them.
_WGI_MISSING_STRINGS: frozenset[str] = frozenset(
    {"#N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)

#: Numeric WGI missing sentinel (defense in depth; WGI uses ``"#N/A"``,
#: not ``-999``, but the WGI V-Dem-style helper still recognizes it).
_WGI_MISSING_SENTINEL: float = -999.0


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_wgi_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/world_bank_wgi/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(WGI_SOURCE_KEY) / "metadata.json"
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

    WGI's missing-data convention is the literal string ``"#N/A"``.
    After wide-pivot, missing cells become pandas NaN. This helper
    handles both, plus the common string sentinels from V-Dem and WDI
    (``""``, ``"NA"``, ``"NaN"``, ``"nan"``, ``"null"``, ``"None"``,
    ``"-999"``, ``"-999.0"``) as defense in depth.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return None if value <= _WGI_MISSING_SENTINEL else value
    if isinstance(value, int) and not isinstance(value, bool):
        return None if value <= int(_WGI_MISSING_SENTINEL) else float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _WGI_MISSING_STRINGS:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        return None
    if numeric <= _WGI_MISSING_SENTINEL:
        return None
    return numeric


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of what
      pandas saw).
    - All other values -> ``str(cell)`` (preserves the WGI missing
      sentinel like ``"#N/A"`` so the audit trail shows what the source
      file actually said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_WGI_MISSING_SENTINEL",
    "_WGI_MISSING_STRINGS",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_wgi_bundle_metadata",
]
