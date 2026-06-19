"""Stage 2 -- WHO GHO API DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`who_gho_api_db`. It is split out of :mod:`who_gho_api_db` so
the DB module stays focused on the DB-write contract (sources,
source_observations, run manifest) and the helper module stays
focused on the value-coercion and bundle-metadata parsing rules.

The split is mandated by architecture §5: "no separate
``_helpers.py`` unless the module grows past 350 lines." The DB
module mirrors the WGI / UCDP / SIPRI / PTS / UNDP HDI pattern and
will grow with the manifest content; extracting the pure helpers
keeps the public DB-write contract clean.

Owns:

- :func:`_read_who_gho_api_bundle_metadata` -- read
  ``data/raw/who_gho_api/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.
- :func:`_coerce_float` / :func:`_coerce_float_from_string` -- turn
  a raw cell into ``float | None`` for the
  ``source_observations.normalized_value`` column.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from the wide-format pandas
  frame produced by the reader.

The DB-write functions (:func:`who_gho_api_db.register_who_gho_api_source`,
:func:`who_gho_api_db.write_who_gho_api_observations`,
:func:`who_gho_api_db.write_who_gho_api_run_manifest`) live in
:mod:`leaders_db.ingest.who_gho_api_db`. The HTTP + cache I/O lives
in :mod:`leaders_db.ingest.who_gho_api_http`. The catalog + paths +
parquet write live in :mod:`leaders_db.ingest.who_gho_api_io`. The
orchestrator lives in :mod:`leaders_db.ingest.who_gho_api`.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .who_gho_api_io import WHO_GHO_API_SOURCE_KEY, IndicatorSpec

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

#: String sentinels pandas / JSON may emit on re-reads. Treated as
#: missing. The WHO GHO API uses ``null`` (the JSON literal) for
#: missing numeric values -- after JSON parsing, ``null`` becomes
#: Python ``None``; after pandas reads the wide frame, missing
#: cells become NaN. This helper handles both, plus the common
#: string sentinels (``""``, ``"NA"``, ``"NaN"``, ``"nan"``,
#: ``"null"``, ``"None"``).
_WHO_GHO_API_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", ""}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_who_gho_api_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/who_gho_api/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(WHO_GHO_API_SOURCE_KEY) / "metadata.json"
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
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)`` on failure.

    The WHO GHO API has no fixed ``coverage_start_year`` /
    ``coverage_end_year`` (data is updated per-indicator), so the
    helper accepts an optional range string from the bundle
    metadata and silently returns ``(None, None)`` when missing.
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


def _coerce_float(value: object) -> float | None:  # noqa: PLR0911
    """Coerce a WHO GHO API / pandas cell to ``float`` or ``None``.

    The WHO GHO API represents missing numeric values as
    ``NumericValue=null`` in the JSON response. After JSON parsing,
    ``null`` becomes Python ``None``; after pandas reads the wide
    frame, missing cells become NaN. This helper handles both,
    plus the common string sentinels (``""``, ``"NA"``, ``"NaN"``,
    ``"nan"``, ``"null"``, ``"None"``).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Defensive: bools should never appear in the wide frame,
        # but treat them as "not a number" to avoid Python's
        # ``True == 1`` trap.
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _WHO_GHO_API_MISSING_STRINGS:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of
      what pandas saw).
    - All other values -> ``str(cell)`` (preserves the original
      numeric value or the verbatim ``Value`` field as a string so
      the audit trail shows what the source file actually said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the wide-format DataFrame row-by-row. For each
    ``(iso3, year)`` pair, writes one ``SourceObservation`` row
    per catalog spec whose ``variable_name`` is a column in the
    frame. ``country_id`` and ``leader_id`` are intentionally left
    ``NULL`` -- Stage 3 fills them. ``source_row_reference``
    carries the catalog ``raw_column`` + ISO3, e.g.
    ``"who_gho_api:WHOSIS_000001:MEX"``, so Stage 3 can resolve
    the observation and the audit trail identifies both the
    indicator and the country.

    The wide frame's columns are the catalog ``variable_name``s
    (the reader renames raw WHO GHO API ``IndicatorCode`` to
    canonical ``variable_name`` during the long-to-wide pivot).
    """
    rows: list[SourceObservation] = []
    for _, raw_row in df.iterrows():
        iso3 = str(raw_row["iso3"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data for this indicator for this row (e.g. the
                # wide frame is missing the column for an indicator
                # that had no values anywhere). Skip -- no
                # observation to record.
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_float(cell)
            # The verbatim WHO GHO API ``Value`` field (e.g.
            # ``"76.4 [76.3-76.5]"`` with the confidence-interval
            # bounds) is preserved in the sibling
            # ``<variable>_raw_value`` column emitted by the read
            # orchestrator. When that column is absent (e.g. a
            # future caller constructs the wide frame by hand and
            # omits the raw-value column) fall back to the cell
            # stringification.
            raw_value_col = f"{spec.variable_name}_raw_value"
            if raw_value_col in raw_row.index:
                raw_value_audit = _raw_value_to_string(
                    raw_row[raw_value_col]
                )
            else:
                raw_value_audit = _raw_value_to_string(cell)
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=raw_value_audit,
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=(
                        f"who_gho_api:{spec.raw_column}:{iso3}"
                    ),
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better={1 if spec.higher_is_better else 0}; "
                        f"dim1_filter={spec.dim1_filter or '(none)'}"
                    ),
                )
            )
    return rows


__all__ = [
    "_build_observation_rows",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_who_gho_api_bundle_metadata",
]
