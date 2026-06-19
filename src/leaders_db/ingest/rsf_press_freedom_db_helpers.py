"""Stage 2 -- RSF World Press Freedom Index DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`rsf_press_freedom_db`. It is split out of :mod:`rsf_press_freedom_db`
so the DB module stays focused on the DB-write contract (sources,
source_observations, run manifest) and the helper module stays
focused on the value-coercion and bundle-metadata parsing rules.

The split follows the V-Dem / WGI / UCDP / SIPRI milex / SIPRI
Yearbook Ch.7 / PTS / UNDP HDI convention: a separate ``_helpers.py``
appears when the DB module grows past the 350-line soft cap.

Owns:

- :func:`_read_rsf_press_freedom_bundle_metadata` -- read
  ``data/raw/rsf_press_freedom/metadata.json`` if present; return
  ``{}`` on missing / invalid JSON.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from the narrow-format pandas
  frame.

The DB-write functions
(:func:`rsf_press_freedom_db.register_rsf_press_freedom_source`,
:func:`rsf_press_freedom_db.write_rsf_press_freedom_observations`,
:func:`rsf_press_freedom_db.write_rsf_press_freedom_run_manifest`)
live in :mod:`leaders_db.ingest.rsf_press_freedom_db`. The CSV read
+ parquet write live in :mod:`leaders_db.ingest.rsf_press_freedom_csv`
and :mod:`leaders_db.ingest.rsf_press_freedom_parquet`. The
catalog loader and path helpers live in
:mod:`leaders_db.ingest.rsf_press_freedom_io`. The orchestrator that
ties everything together lives in
:mod:`leaders_db.ingest.rsf_press_freedom`.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .rsf_press_freedom_io import (
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    IndicatorSpec,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_rsf_press_freedom_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/rsf_press_freedom/metadata.json`` if present.

    Returns an empty dict on missing file or JSON decode error so
    the DB writer can fall back to hard-coded defaults
    (matches the V-Dem / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI pattern).
    """
    bundle_meta_path = raw_dir(RSF_PRESS_FREEDOM_SOURCE_KEY) / "metadata.json"
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
    """Parse an ISO date from the bundle metadata; ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(
    raw: object,
) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; ``(None, None)`` on failure.

    RSF's bundle metadata uses the integer fields
    ``coverage_start_year`` / ``coverage_end_year`` directly (per the
    ``metadata.json`` shape); this helper is here for parity with
    the other Stage 2 adapters and for any future bundle that uses
    a range string.
    """
    if not isinstance(raw, str) or "-" not in raw:
        return (None, None)
    start_str, end_str = raw.split("-", 1)
    try:
        return (int(start_str.strip()), int(end_str.strip()))
    except ValueError:
        return (None, None)


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory.

    The ``df`` is the narrow-format frame from
    :func:`rsf_press_freedom_csv.read_rsf_press_freedom_csv` (one
    row per ``(iso3, year, variable_name)`` triple). One
    :class:`SourceObservation` row per narrow-frame row. ``raw_value``
    preserves the verbatim RSF cell text (the comma-decimal string
    like ``"72,67"``; the int string like ``"149"``; or ``""`` for
    missing); ``normalized_value`` is the ``float`` / ``int``-coerced
    value or ``None`` for missing.

    Iteration order: the frame is pre-sorted by
    ``(year, iso3, variable_name)`` by
    :func:`rsf_press_freedom_csv.read_rsf_press_freedom_csv`; the
    order here is therefore deterministic without a re-sort.
    """
    rows: list[SourceObservation] = []
    spec_by_var = {s.variable_name: s for s in specs}
    for _, raw_row in df.iterrows():
        iso3 = str(raw_row["iso3"])
        year = int(raw_row["year"])
        variable_name = str(raw_row["variable_name"])
        raw_value_cell = raw_row["raw_value"]
        source_row_reference = str(raw_row["source_row_reference"])
        spec = spec_by_var.get(variable_name)
        if spec is None:
            # Defensive: the narrow frame should only carry
            # catalog-driven variable names, but a malformed
            # frame would otherwise write a row with a missing
            # spec. Skip.
            _logger.warning(
                "RSF DB write: no spec for variable_name=%s "
                "(iso3=%s, year=%d). Skipping.",
                variable_name, iso3, year,
            )
            continue
        # ``normalized_value`` is already coerced by the CSV reader
        # (float for score/components; int for rank). Defensive: if
        # the value is ``NaN``, treat as None.
        normalized_raw = raw_row["normalized_value"]
        if normalized_raw is None:
            value: float | int | None = None
        elif isinstance(normalized_raw, float) and pd.isna(normalized_raw):
            value = None
        else:
            value = normalized_raw
        raw_value_str = (
            str(raw_value_cell)
            if raw_value_cell is not None
            and not (
                isinstance(raw_value_cell, float)
                and pd.isna(raw_value_cell)
            )
            else ""
        )
        rows.append(
            SourceObservation(
                source_id=source_id,
                country_id=None,  # Stage 3 fills this in
                leader_id=None,
                year=year,
                variable_name=variable_name,
                raw_value=raw_value_str,
                normalized_value=(
                    float(value) if isinstance(value, int) else value
                ),
                unit=spec.unit,
                source_row_reference=source_row_reference,
                confidence=None,  # set by Stage 11
                notes=(
                    f"raw_scale={spec.raw_scale}; "
                    f"higher_is_better={1 if spec.higher_is_better else 0}"
                ),
            ),
        )
    return rows


__all__ = [
    "_build_observation_rows",
    "_parse_download_date",
    "_parse_year_range",
    "_read_rsf_press_freedom_bundle_metadata",
]
