"""Stage 2 -- SIPRI milex DB writes: sources, source_observations, run manifest.

This module is the DB half of the SIPRI milex adapter. It owns:

- :func:`register_sipri_milex_source` -- upsert the ``sources``
  row.
- :func:`write_sipri_milex_observations` -- write one
  ``source_observations`` row per ``(country, year, variable)``
  triple. Idempotent.
- :func:`_delete_existing_observations` -- helper.
- :func:`_build_observation_rows` -- in-memory row builder.
- :func:`write_sipri_milex_run_manifest` -- write the audit-trail
  JSON.

The pure coercion and bundle-metadata helpers live in
:mod:`leaders_db.ingest.sipri_milex_db_helpers` (extracted during
implementation to keep this module under the 400-line convention).

The xlsx read + parquet write functions live in
:mod:`leaders_db.ingest.sipri_milex_io` and
:mod:`leaders_db.ingest.sipri_milex_xlsx`. The orchestrator lives
in :mod:`leaders_db.ingest.sipri_milex`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .sipri_milex_db_helpers import (
    _coerce_float,
    _parse_download_date,
    _parse_year_range,
    _raw_value_to_string,
    _read_sipri_milex_bundle_metadata,
)
from .sipri_milex_io import (
    _DEFAULT_CATALOG_PATH,
    SIPRI_MILEX_ATTRIBUTION,
    SIPRI_MILEX_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)

# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_sipri_milex_source(session: Session) -> int:
    """Upsert the SIPRI milex source row into the ``sources`` table.

    Keyed by ``(source_name='SIPRI Military Expenditure Database',
    version='v1.2 (1949-2025)')``. Idempotent. Reads the bundle's
    ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``,
    ``coverage_end_year``. Non-destructive update policy: missing
    bundle fields keep the existing row's old value.
    """
    source_name = "SIPRI Military Expenditure Database"
    version = "v1.2 (1949-2025)"

    bundle_meta = _read_sipri_milex_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range"),
    )

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
                or "https://www.sipri.org/databases/milex"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free academic with attribution per SIPRI Terms of Use; "
                    "see https://www.sipri.org/databases/milex"
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. See "
                "src/leaders_db/ingest/catalogs/sipri_milex.csv and "
                "docs/source-attributions.md."
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


def write_sipri_milex_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    ``country_id`` is left ``NULL`` (Stage 3 fills it).
    ``source_row_reference`` carries the SIPRI display name
    prefixed with ``"sipri_milex:"`` (e.g. ``"sipri_milex:Mexico"``).

    Idempotent: deletes existing rows for the requested years
    before inserting. Years outside the frame are untouched.
    Returns the number of rows inserted.
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
    session: Session,
    source_id: int,
    years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched.
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
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the wide frame row-by-row; for each spec, writes
    one ``SourceObservation`` row. ``raw_value`` preserves the
    original cell (the literal ``"..."`` / ``"xxx"`` / ``""`` for
    missing cells). Iteration order: ``(year ASC, country ASC)``
    via stable mergesort. The pre-coercion long frame in
    ``df.attrs["_sipri_milex_raw_long"]`` feeds the audit trail.
    """
    rows: list[SourceObservation] = []
    # Sort: stable mergesort breaks ties by country so insertion
    # order is fully deterministic.
    sorted_df = df.sort_values(
        by=["year", "country"],
        ascending=[True, True],
        kind="mergesort",
    )
    # (country, year, variable_name) -> raw cell lookup from the
    # pre-coercion long frame for the raw_value audit trail.
    raw_long = df.attrs.get("_sipri_milex_raw_long")
    raw_lookup: dict[tuple[str, int, str], object] = {}
    if raw_long is not None and not raw_long.empty:
        for _, raw_long_row in raw_long.iterrows():
            key = (
                str(raw_long_row["country"]),
                int(raw_long_row["year"]),
                str(raw_long_row["variable_name"]),
            )
            raw_lookup[key] = raw_long_row["value"]

    for _, raw_row in sorted_df.iterrows():
        country = str(raw_row["country"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data for this indicator; skip.
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_float(cell)
            raw_cell = raw_lookup.get(
                (country, year, spec.variable_name), cell,
            )
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=_raw_value_to_string(raw_cell),
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=f"sipri_milex:{country}",
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better={1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_sipri_milex_run_manifest(
    result,  # SipriMilexIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    Records the run's ``source_id``, parquet path, observation
    row count, countries count, years, indicator count,
    ``regions_covered`` and ``country_count`` (SIPRI-specific
    extras), the catalog path, and the attribution. Written
    every run (not best-effort) so Stage 15 reports can find
    the attribution without re-reading the parquet metadata.
    """
    out_dir = manifest_dir or processed_dir(SIPRI_MILEX_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "sipri_milex_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "regions_covered": list(result.regions_covered),
        "country_count": result.country_count,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": SIPRI_MILEX_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_sipri_milex_source",
    "write_sipri_milex_observations",
    "write_sipri_milex_run_manifest",
]
