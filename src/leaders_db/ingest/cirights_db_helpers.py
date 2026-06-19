"""Stage 2 -- CIRI Human Rights Data Project (CIRIGHTS) DB helpers.

This module holds the pure helper functions used by :mod:`cirights_db`.
It is split out of :mod:`cirights_db` so the DB module stays focused
on the DB-write contract (sources, source_observations, run manifest)
and the helper module stays focused on the value-coercion rules,
bundle-metadata parsing, and the in-memory observation-row builder.

Owns:

- :data:`_CIRIGHTS_MISSING_STRINGS` -- the CIRIGHTS defense-in-depth
  set of string sentinels. The live xlsx never produces these
  (missing is the empty cell), but future releases might; the
  coercion tolerates them.
- :func:`_coerce_int` -- turn an xlsx / pandas cell into
  ``int | None`` for ``source_observations.normalized_value``.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the
  empty string for missing cells.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from a wide-format pandas frame.
- :func:`_read_cirights_bundle_metadata` -- read
  ``data/raw/cirights/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date; ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  ``(None, None)`` on failure.

The DB-write functions (:func:`register_cirights_source`,
:func:`write_cirights_observations`, :func:`write_cirights_run_manifest`)
live in :mod:`leaders_db.ingest.cirights_db`. The orchestrator lives
in :mod:`leaders_db.ingest.cirights`.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .cirights_io import CIRIGHTS_SOURCE_KEY, IndicatorSpec, safe_country_token

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Missing-data conventions
# ---------------------------------------------------------------------------

#: CIRIGHTS' missing-data convention is the empty cell (openpyxl
#: reads as ``None``). The xlsx never produces string sentinels like
#: ``"NA"`` or ``"#N/A"``. The set below is the defense-in-depth
#: union of the V-Dem / WGI / WDI / SIPRI milex / SIPRI Yearbook Ch.7
#: / PTS / UNDP HCI sentinels so a future CIRIGHTS release that
#: re-uses any of them does not silently coerce them to ``float(0)``.
_CIRIGHTS_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", "#N/A", "-999", "-999.0", ""}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_cirights_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/cirights/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(CIRIGHTS_SOURCE_KEY) / "metadata.json"
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


def _parse_year_range(raw: object) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; ``(None, None)`` on failure."""
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


def _coerce_int(value: object) -> int | None:
    """Coerce an xlsx / pandas cell to ``int | None``.

    The CIRIGHTS wide frame uses ``Int64`` nullable dtype; missing
    cells are ``pd.NA``. Numeric cells (int / float) coerce to int;
    any float cell is rounded to int (defense in depth: the live
    xlsx never produces floats for the 7 catalog columns). String
    cells matching the CIRIGHTS / V-Dem / WGI / WDI / SIPRI milex /
    SIPRI Yearbook Ch.7 / PTS / UNDP HDI missing sentinel set are
    treated as missing.

    Per the design contract: the pipeline never invents missing
    values. A cell that is not a clean int is treated as missing
    rather than coerced to a sentinel like ``-1``.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return round(float(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in _CIRIGHTS_MISSING_STRINGS:
            return None
        try:
            return round(float(stripped))
        except ValueError:
            return None
    # pandas NA / unknown type: treat as missing.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` (empty cell) -> ``""`` (no audit trail; the row is
      skipped by the orchestrator anyway, so this branch is
      defensive).
    - pandas ``NaN`` -> ``""`` (defense in depth; the wide frame
      never holds a non-NA NaN for the 7 catalog columns).
    - int -> ``str(int)`` (e.g. ``"5"``).
    - Other types -> ``str(cell)`` (defense in depth).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return ""
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

    Iterates the wide frame row-by-row; for each spec, writes one
    :class:`SourceObservation` row. ``raw_value`` is recovered from
    ``df.attrs["_cirights_raw_lookup"]`` (the pre-coercion cell-text
    lookup built by :func:`cirights_xlsx.read_xlsx_to_wide_dataframe`).
    For missing cells (the wide frame's ``pd.NA``), the row is
    SKIPPED (per the design contract: do not invent values for
    missing cells).

    The :class:`SourceObservation.source_row_reference` is built per
    :func:`cirights_io.safe_country_token` substitution: e.g.
    ``cirights:Mexico:2022:Physical Integrity Rights Index``. The
    suffix uses the catalog ``raw_column`` (not the canonical
    ``variable_name``) so the audit trail can locate the original
    cell in the xlsx (the variable_name is the post-rename column
    label). Stage 3 (country match) post-processes the country token
    to ISO3 in a later iteration.

    Iteration order: ``(year ASC, country ASC)`` via stable
    mergesort. Same pattern as V-Dem / WGI / UCDP / SIPRI milex /
    SIPRI Yearbook Ch.7 / PTS / UNDP HDI.
    """
    rows: list[SourceObservation] = []
    # Sort: stable mergesort breaks ties by country so insertion
    # order is fully deterministic.
    sorted_df = df.sort_values(
        by=["year", "country"],
        ascending=[True, True],
        kind="mergesort",
    )
    # (country, year, variable_name) -> raw cell text lookup from
    # the read orchestrator's raw_lookup. The key uses the canonical
    # ``variable_name`` (not the raw column name) so the DB writer
    # can find it by the same key it iterates over.
    raw_lookup: dict[tuple[str, int, str], str] = (
        df.attrs.get("_cirights_raw_lookup", {}) or {}
    )

    for _, raw_row in sorted_df.iterrows():
        country = str(raw_row.get("country") or "")
        country_token = safe_country_token(country) or "unknown"
        try:
            year_value = int(raw_row["year"]) if raw_row["year"] is not None else 0
        except (TypeError, ValueError):
            year_value = 0
        if year_value == 0:
            # Defensive: skip rows with non-int year. The reader
            # should never produce these (the wide frame's year
            # column is ``Int64``).
            continue
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_int(cell)
            if value is None:
                # Missing cell. Per the design contract: do not
                # write a NULL ``normalized_value`` row for missing
                # cells. The audit trail records the cell's status
                # in ``_cirights_raw_lookup`` (empty string for
                # missing cells) so a future iteration can write
                # the dropped rows with NULL ``normalized_value`` if
                # the cross-source comparison needs them.
                continue
            raw_cell = raw_lookup.get((country, year_value, spec.variable_name))
            if raw_cell is None:
                # Defense in depth: stringify the int value.
                raw_value_str = str(int(value))
            else:
                raw_value_str = _raw_value_to_string(raw_cell)
            # source_row_reference: cirights:<country_token>:<year>:<raw_column>.
            # The raw_column (not variable_name) is used so the
            # audit trail can locate the original xlsx cell.
            source_row_reference = (
                f"cirights:{country_token}:{year_value}:{spec.raw_column}"
            )
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year_value,
                    variable_name=spec.variable_name,
                    raw_value=raw_value_str,
                    normalized_value=float(int(value)),
                    unit=spec.unit,
                    source_row_reference=source_row_reference,
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better={1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


__all__ = [
    "_build_observation_rows",
    "_coerce_int",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_cirights_bundle_metadata",
]
