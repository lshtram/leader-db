"""Stage 2 -- Maddison Project Database 2023 DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`maddison_project_db`. It is split out of
:mod:`maddison_project_db` so the DB module stays focused on the
DB-write contract (sources, source_observations, run manifest) and
the helper module stays focused on the value-coercion and bundle-
metadata parsing rules.

Owns:

- :func:`_read_maddison_project_bundle_metadata` -- read
  ``data/raw/maddison_project/metadata.json`` if present, else
  empty dict.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure. Also accepts the
  ``coverage_start_year`` / ``coverage_end_year`` integer fields
  directly (same pattern as the UNDP HDI adapter).
- :func:`_coerce_float` -- turn an xlsx / pandas cell into
  ``float | None`` for the ``source_observations.normalized_value``
  column. Handles pandas NaN, the ``"nan"`` / ``"NA"`` strings,
  and empty string (defense in depth; the Maddison xlsx uses pandas
  NaN for missing cells, no string sentinels).
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the
  Maddison NaN rendering as ``"nan"`` so the audit trail records
  what pandas saw.

The DB-write functions (:func:`register_maddison_project_source`,
:func:`write_maddison_project_observations`,
:func:`write_maddison_project_run_manifest`) live in
:mod:`leaders_db.ingest.maddison_project_db`. The orchestrator that
ties everything together lives in
:mod:`leaders_db.ingest.maddison_project`.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .maddison_project_io import MADDISON_PROJECT_SOURCE_KEY

#: Maddison xlsx missing-data convention: pandas NaN (no string
#: sentinel). The xlsx never contains ``"NA"`` / ``"#N/A"`` /
#: ``"nan"`` strings, but we include the union of all known
#: Stage 2 sentinels as defense-in-depth in case a future
#: release re-uses them.
_MADDISON_PROJECT_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_maddison_project_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/maddison_project/metadata.json`` if present,
    else empty dict.
    """
    bundle_meta_path = raw_dir(MADDISON_PROJECT_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, object] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8"),
        )
        return result
    except json.JSONDecodeError:
        return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return ``None``
    on failure.
    """
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(
    raw: object,
) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)``
    on failure.
    """
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

    The Maddison xlsx's missing-data convention is pandas NaN (no
    string sentinel). After the read loop, missing cells are pandas
    NaN; this helper handles NaN + the union of known Stage 2
    string sentinels (``"NA"``, ``"NaN"``, ``"nan"``, ``"null"``,
    ``"None"``, ``"-999"``, ``"-999.0"``, ``""``) as defense in
    depth.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is a subclass of int but should be treated as missing
        # data (the Maddison xlsx has no boolean cells).
        return None
    if isinstance(value, float):
        return None if pd.isna(value) else float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in _MADDISON_PROJECT_MISSING_STRINGS:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value``
    audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of
      what pandas saw; the Maddison xlsx uses pandas NaN for
      missing ``gdppc`` and ``pop`` cells).
    - All other values -> ``str(cell)`` (preserves the numeric
      string the xlsx actually held).

    Per the design contract: the audit trail preserves the literal
    cell text the xlsx held. The wide parquet (and the
    ``source_observations.normalized_value`` column) drops the
    missing cells to NULL; the raw_value column records what the
    xlsx said.
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


__all__ = [
    "_coerce_float",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_maddison_project_bundle_metadata",
]
