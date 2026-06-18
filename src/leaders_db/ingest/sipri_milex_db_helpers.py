"""Stage 2 -- SIPRI milex DB helpers: coercion + bundle metadata (REQ-SRC-002).

This module holds the pure helper functions used by
:mod:`sipri_milex_db`. It is split out of :mod:`sipri_milex_db` so
the DB module stays focused on the DB-write contract (sources,
source_observations, run manifest) and the helper module stays
focused on the value-coercion and bundle-metadata parsing rules.
Splitting was triggered by the 400-line convention; the helpers
total ~80 lines and warrant their own file (the WGI / UCDP
precedent).

Owns:

- :func:`_coerce_float` -- turn an xlsx / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles the SIPRI missing-data convention (``"..."``,
  ``"xxx"``, ``""``) plus the V-Dem / WDI / WGI / UCDP sentinels
  (defense in depth).
- :func:`_coerce_float_from_string` -- string variant.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the
  SIPRI literal ``"..."`` / ``"xxx"`` / ``""`` for missing cells.
- :func:`_read_sipri_milex_bundle_metadata` -- read
  ``data/raw/sipri_milex/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.

The DB-write functions (:func:`register_sipri_milex_source`,
:func:`write_sipri_milex_observations`,
:func:`write_sipri_milex_run_manifest`) live in
:mod:`leaders_db.ingest.sipri_milex_db`. The xlsx read + parquet
write live in :mod:`leaders_db.ingest.sipri_milex_io` and
:mod:`leaders_db.ingest.sipri_milex_xlsx`. The orchestrator lives
in :mod:`leaders_db.ingest.sipri_milex`.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .sipri_milex_io import (
    _SIPRI_MILEX_MISSING_SENTINEL,
    _SIPRI_MILEX_MISSING_STRINGS,
    SIPRI_MILEX_SOURCE_KEY,
)

# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_sipri_milex_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/sipri_milex/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(SIPRI_MILEX_SOURCE_KEY) / "metadata.json"
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


def _parse_year_range(
    raw: object,
) -> tuple[int | None, int | None]:
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

    SIPRI's missing-data convention is three tokens: ``"..."``
    (data unavailable), ``"xxx"`` (country did not exist), and
    ``""`` (empty cell). After the wide pivot, missing cells
    become pandas NaN. This helper handles all of them, plus the
    common string sentinels from V-Dem / WDI / WGI / UCDP as
    defense in depth.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return None if value <= _SIPRI_MILEX_MISSING_SENTINEL else value
    if isinstance(value, int) and not isinstance(value, bool):
        return None if value <= int(_SIPRI_MILEX_MISSING_SENTINEL) else float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _SIPRI_MILEX_MISSING_STRINGS:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        return None
    if numeric <= _SIPRI_MILEX_MISSING_SENTINEL:
        return None
    return numeric


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    - ``None`` -> ``""``.
    - pandas NaN -> ``"nan"``.
    - All other values -> ``str(cell)`` (preserves ``"..."`` /
      ``"xxx"`` so the audit trail shows what the source file
      actually said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_sipri_milex_bundle_metadata",
]
