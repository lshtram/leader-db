"""Stage 2 -- UCDP DB writes: sources, source_observations, run manifest.

This module is the DB half of the UCDP adapter. It owns:

- :func:`register_ucdp_source` -- upsert the ``sources`` row from the
  UCDP bundle's ``metadata.json``.
- :func:`write_ucdp_observations` -- write one ``source_observations``
  row per ``(country, year, variable)`` triple. Idempotent (deletes
  existing rows for the requested years before inserting).
- :func:`_delete_existing_observations` -- helper for
  :func:`write_ucdp_observations`, separated for testability.
- :func:`_build_observation_rows` -- in-memory builder for
  ``SourceObservation`` rows from a wide-format pandas frame.
- :func:`write_ucdp_run_manifest` -- write the audit-trail JSON next
  to the narrow parquet.

The pure helpers (value coercion, bundle metadata parsing) live in
:mod:`leaders_db.ingest.ucdp_db_helpers`. The zip read + parquet
write functions live in :mod:`leaders_db.ingest.ucdp_io`. The
orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.ucdp`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .ucdp_catalog import (
    DEFAULT_CATALOG_PATH as _DEFAULT_CATALOG_PATH,
)
from .ucdp_catalog import (
    IndicatorSpec,
    load_indicator_catalog,
)
from .ucdp_db_helpers import (
    _parse_download_date,
    _parse_year_range,
    _raw_value_to_string,
    _read_ucdp_bundle_metadata,
)
from .ucdp_io import UCDP_ATTRIBUTION, UCDP_SOURCE_KEY

# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_ucdp_source(session: Session) -> int:
    """Upsert the UCDP source row into the ``sources`` table.

    Keyed by
    ``(source_name='UCDP (Uppsala Conflict Data Program)',
    version='23.1')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``, ``coverage_start_year``,
    ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source` and WGI's
    :func:`wgi_db.register_wgi_source`).
    """
    source_name = "UCDP (Uppsala Conflict Data Program)"
    version = "23.1"

    bundle_meta = _read_ucdp_bundle_metadata()
    download_date_value = _parse_download_date(bundle_meta.get("download_date"))
    coverage_start, coverage_end = _parse_year_range(bundle_meta.get("year_range"))

    existing = session.execute(
        select(Source).where(
            Source.source_name == source_name,
            Source.version == version,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = Source(
            source_name=source_name,
            source_type="academic",
            source_url=str(
                bundle_meta.get("source_url")
                or "https://ucdp.uu.se/downloads/ged/ged231-csv.zip"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free academic license per UCDP Terms of Use; "
                    "see https://ucdp.uu.se/terms-of-use/"
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator catalog at "
                "src/leaders_db/ingest/catalogs/ucdp.csv. See "
                "docs/sources/attributions.md for the exact citation text."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh. See the docstring's update policy.
    if bundle_meta.get("source_url"):
        existing.source_url = str(bundle_meta["source_url"])
    if bundle_meta.get("license_note"):
        existing.license_note = str(bundle_meta["license_note"])
    if download_date_value is not None:
        existing.download_date = download_date_value
    if coverage_start is not None:
        existing.coverage_start_year = coverage_start
    if coverage_end is not None:
        existing.coverage_end_year = coverage_end
    return int(existing.id)


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_ucdp_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    ``country_id`` is intentionally left ``NULL`` -- Stage 3 (country
    match) populates it after the UCDP ``country_id`` is resolved
    to our canonical country key. ``source_row_reference`` carries
    the UCDP ``country_id`` prefixed with ``"ucdp:"`` (e.g.
    ``"ucdp:645"`` for Iraq) so Stage 3 can resolve it directly.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose ``year``
    is present in ``df`` before inserting. Years outside the frame
    are untouched (so a single-year re-run does not erase older
    data).

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_indicator_catalog(catalog_path=catalog_path)
    years = sorted({int(y) for y in df["year"].tolist()})

    _delete_existing_observations(session, source_id, years)
    rows = _build_observation_rows(source_id, df, specs)
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session, source_id: int, years: list[int]
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched. Pulled out of
    :func:`write_ucdp_observations` so the orchestrator stays short.
    """
    existing_rows = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_id == source_id,
            SourceObservation.year.in_(years),
        )
    ).scalars().all()
    for row in existing_rows:
        session.delete(row)
    session.flush()


def _build_observation_rows(
    source_id: int, df: pd.DataFrame, specs: list[IndicatorSpec]
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    The ``df`` is the wide-format frame returned by
    :func:`ucdp_io.read_ucdp` (one row per ``(country_id, year)``,
    one column per catalog ``variable_name``). The function iterates
    the frame row-by-row and, for each spec, writes one
    ``SourceObservation`` row. The raw_value preserves the
    stringified cell so the audit trail records the original event
    count / fatalities.

    Iteration order: rows are emitted in
    ``(year ASC, country_id ASC)`` order via a stable mergesort.
    The sort + the orchestrator's test assertions on a single
    ``variable_name`` guarantee deterministic results.

    Normalization: event-count cells are stored as ``int``,
    fatalities cells as ``float``. Pandas ``Int64`` (nullable
    integer) is unwrapped to a plain Python int for the
    ``normalized_value`` column.
    """
    rows: list[SourceObservation] = []
    # Sort the frame by year ascending, then country_id ascending. The
    # sort is stable; ties on year are broken by country_id so the
    # insertion order is fully deterministic.
    sorted_df = df.sort_values(
        by=["year", "country_id"], ascending=[True, True], kind="mergesort",
    )

    for _, raw_row in sorted_df.iterrows():
        country_id = int(raw_row["country_id"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data for this indicator for this row (e.g. the
                # wide frame is missing the column for an indicator
                # that had no values anywhere). Skip -- no
                # observation to record.
                continue
            cell = raw_row[spec.variable_name]
            value = _normalize_cell(cell, spec)
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=_raw_value_to_string(cell),
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=f"ucdp:{country_id}",
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better="
                        f"{1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


def _normalize_cell(cell: object, spec: IndicatorSpec) -> float | int | None:
    """Normalize one wide-frame cell into the ``normalized_value`` column.

    UCDP has two ``raw_scale`` shapes:
    - ``count`` (event-count indicators): non-negative int.
    - ``deaths`` (fatalities indicators): non-negative float
      (UCDP's ``best`` is integer-valued, but the column type is
      float to accept NaN from missing cells).

    ``None`` and pandas ``NaN`` map to ``None``.
    """
    if cell is None:
        return None
    # pandas Int64 is a pandas extension type; the value is unwrapped
    # by ``int()`` / ``float()`` below. The isinstance(float) guard
    # is needed so we don't mistake pandas NaN (a float) for a
    # legitimate value.
    if isinstance(cell, float) and pd.isna(cell):
        return None
    if spec.raw_scale == "count":
        try:
            return int(cell)
        except (TypeError, ValueError):
            return None
    # Default: float (deaths, or any other scale we add later).
    try:
        return float(cell)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_ucdp_run_manifest(
    result,  # UCDPIngestResult, imported lazily to avoid circular import
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    the ``events_total`` and ``events_filtered`` (UCDP-specific
    extras that the WGI manifest does not carry), the catalog path
    used, and the attribution. Written every run (not best-effort)
    so Stage 15 reports can find the attribution without re-reading
    the parquet metadata.

    Args:
        result: the :class:`UCDPIngestResult` returned by
            :func:`ingest_ucdp`.
        manifest_dir: override the output dir. Default: data-lake
            path.
        catalog_path: override the catalog path. Default: checked-in.
    """
    out_dir = manifest_dir or processed_dir(UCDP_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "ucdp_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "events_total": result.events_total,
        "events_filtered": result.events_filtered,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": UCDP_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_ucdp_source",
    "write_ucdp_observations",
    "write_ucdp_run_manifest",
]
