"""Stage 2 -- REIGN (Bell 2016): pure DB coercion + bundle-metadata helpers.

This module is the pure-helpers half of the REIGN DB layer. It
owns:

- :func:`_read_reign_bundle_metadata` -- read the
  ``data/raw/reign/metadata.json`` for ``source_url``,
  ``download_date``, ``license_note``, ``coverage_start_year``,
  ``coverage_end_year``.
- :func:`_parse_download_date` -- convert the bundle's
  ``download_date`` (an ISO ``YYYY-MM-DD`` string) to a
  :class:`datetime.date` for the ``sources.download_date`` column.
- :func:`_parse_year_range` -- pull the ``coverage_start_year`` /
  ``coverage_end_year`` integers from the bundle metadata.
- :func:`_build_observation_rows` -- convert the long-format
  DataFrame into a list of :class:`SourceObservation` ORM objects
  ready for ``session.add_all``.

The DB writer (source registration, source_observations write, run
manifest) lives in :mod:`reign_db`. The pure helpers are extracted
to keep the DB-write contract clean (per the
V-Dem / CIRIGHTS / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7
/ PTS / UNDP HDI / WHO GHO API / Archigos pattern of one file per
concern).
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .reign_io import (
    REIGN_SOURCE_KEY,
    IndicatorSpec,
)

__all__ = [
    "_build_observation_rows",
    "_parse_download_date",
    "_parse_year_range",
    "_read_reign_bundle_metadata",
]


# ---------------------------------------------------------------------------
# Bundle metadata
# ---------------------------------------------------------------------------


def _read_reign_bundle_metadata() -> dict[str, object]:
    """Read the REIGN bundle ``metadata.json``.

    Looks at ``data/raw/reign/metadata.json`` (per the data-lake
    rules in ``docs/architecture/local-data-store.md``). Returns an empty
    dict if the file is missing -- the DB writer treats missing
    fields as "no update" (the existing row's value is kept).

    The reader does NOT require the ``.csv`` to be present (the
    metadata is its own file; the data file's presence is the
    orchestrator's concern, not the DB writer's). This matches
    the CIRIGHTS / UNDP HDI / Archigos pattern.
    """
    bundle_meta_path = raw_dir(REIGN_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        return json.loads(bundle_meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_download_date(value: object) -> date | None:
    """Convert the bundle's ``download_date`` string to a
    :class:`datetime.date`.

    Accepts the ISO ``YYYY-MM-DD`` format. Returns ``None`` for
    missing or unparseable values (the DB writer keeps the
    existing row's value).
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_year_range(value: object) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` string into ``(start, end)`` ints.

    Returns ``(None, None)`` for missing or unparseable values.
    """
    if not isinstance(value, str) or not value:
        return None, None
    parts = value.split("-")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


# ---------------------------------------------------------------------------
# Observation row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Convert the long-format DataFrame to :class:`SourceObservation`
    rows.

    The DataFrame columns are documented in
    :func:`leaders_db.ingest.reign_io.read_reign`. Each row in
    the long frame produces one :class:`SourceObservation` row.
    ``country_id`` is left ``NULL`` (Stage 3 fills it).
    ``leader_id`` is left ``NULL`` (Stage 4 fills it).
    ``source_row_reference`` is the audit-trail locator.
    ``confidence`` is left ``NULL`` (Stage 11 fills it). The
    ``raw_value`` and ``normalized_value`` fields are the
    verbatim text and the light-coerced numeric value,
    respectively.

    The function iterates the DataFrame row-by-row (the long
    frame is large -- 138,600 leader-month rows x 8 catalog
    variables = up to ~1.1M rows for the full unfiltered run;
    the row construction is O(N) and dominated by the Python-
    level loop).
    """
    spec_by_var = {s.variable_name: s for s in specs}
    rows: list[SourceObservation] = []
    for _, long_row in df.iterrows():
        variable_name = str(long_row["variable_name"])
        spec = spec_by_var.get(variable_name)
        if spec is None:
            # Defensive: a long row's variable_name should always
            # be in the catalog. If not, skip (do not invent).
            continue
        raw_value = long_row.get("raw_value")
        normalized = long_row.get("normalized_value")
        # ``pd.NA`` and ``NaN`` both map to Python ``None`` for
        # the nullable columns. The DB column is Float (nullable).
        if pd.isna(normalized):
            normalized = None
        else:
            try:
                normalized = float(normalized)
            except (TypeError, ValueError):
                normalized = None
        year = long_row.get("year")
        if pd.isna(year):
            year_value: int | None = None
        else:
            try:
                year_value = int(year)
            except (TypeError, ValueError):
                year_value = None
        rows.append(
            SourceObservation(
                source_id=source_id,
                country_id=None,  # Stage 3 fills this.
                leader_id=None,  # Stage 4 fills this.
                year=year_value,
                variable_name=variable_name,
                raw_value=None if pd.isna(raw_value) else str(raw_value),
                normalized_value=normalized,
                unit=spec.unit,
                source_row_reference=(
                    None if pd.isna(long_row.get("source_row_reference"))
                    else str(long_row["source_row_reference"])
                ),
                confidence=None,  # Stage 11 fills this.
                notes=(
                    f"reign raw_column={spec.raw_column}; "
                    f"country={long_row.get('country')}; "
                    f"leader={long_row.get('leader')}; "
                    "month="
                    f"{_month_str(long_row)}"
                ),
            ),
        )
    return rows


def _month_str(long_row: pd.Series) -> str:
    """Format the ``month`` value for the notes column."""
    month = long_row.get("month")
    if pd.isna(month):
        return "NA"
    return str(int(month))
