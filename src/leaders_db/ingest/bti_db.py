"""Stage 2 -- Bertelsmann BTI DB writes: sources, source_observations, run manifest.

This module is the DB half of the BTI adapter. It owns:

- :func:`register_bti_source` -- upsert the ``sources`` row from the
  BTI bundle's ``metadata.json``.
- :func:`write_bti_observations` -- write one ``source_observations``
  row per ``(country, year, variable)`` triple. Idempotent (deletes
  existing rows for the requested years before inserting).
- :func:`_delete_existing_observations` -- helper for
  :func:`write_bti_observations`, separated for testability.
- :func:`_build_observation_rows` -- in-memory builder for
  ``SourceObservation`` rows from a wide-format pandas frame.
- :func:`write_bti_run_manifest` -- write the audit-trail JSON next to
  the narrow parquet.

The pure helpers (value coercion, bundle metadata parsing) live in
:mod:`leaders_db.ingest.bti_db_helpers`. The xlsx read + parquet write
functions live in :mod:`leaders_db.ingest.bti_io` and
:mod:`leaders_db.ingest.bti_xlsx`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.bti`.

Source-row-reference convention: BTI does not carry ISO3 codes. The
``source_row_reference`` is ``bti:<country>`` (e.g. ``bti:Mexico``)
so Stage 3 (country match) can resolve it via the country alias
table (same pattern as SIPRI milex's display-name convention and
V-Dem's pre-v13 country_text_id).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .bti_db_helpers import (
    _coerce_float,
    _parse_download_date,
    _parse_year_range,
    _raw_value_to_string,
    _read_bti_bundle_metadata,
)
from .bti_io import (
    _DEFAULT_CATALOG_PATH,
    BTI_ATTRIBUTION,
    BTI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)

# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_bti_source(session: Session) -> int:
    """Upsert the BTI source row into the ``sources`` table.

    Keyed by ``(source_name='Bertelsmann BTI', version='BTI 2026')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem / WGI / WDI / PTS
    source registration).
    """
    source_name = "Bertelsmann BTI"
    version = "BTI 2026"

    bundle_meta = _read_bti_bundle_metadata()
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
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url")
                or "https://bti-project.org/en/downloads"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or "Free; cite Bertelsmann Stiftung. Reprinted with permission "
                "per BTI terms of use."
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator catalog at "
                "src/leaders_db/ingest/catalogs/bti.csv. See "
                "docs/source-attributions.md for the exact citation text. "
                "BTI is biennial; each edition covers ~2 years preceding "
                "publication (e.g. BTI 2024 -> 2022-2023)."
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


def write_bti_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    ``country_id`` is intentionally left ``NULL`` -- Stage 3 (country
    match) populates it after the BTI display name is mapped to the
    canonical country key via the country alias table.
    ``source_row_reference`` carries the BTI display name prefixed with
    ``"bti:"`` (e.g. ``"bti:Mexico"``) so Stage 3 can resolve it.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose ``year`` is
    present in ``df`` before inserting. Years outside the frame are
    untouched (so a single-year re-run does not erase older data).

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
    :func:`write_bti_observations` so the orchestrator stays short.
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
    :func:`bti_xlsx.read_bti` (one row per ``(country, year)``, one
    column per catalog ``variable_name``). The function iterates the
    frame row-by-row and, for each spec, writes one
    ``SourceObservation`` row. The ``raw_value`` preserves the original
    cell so the audit trail records what the xlsx actually said.
    """
    rows: list[SourceObservation] = []
    # Sort the frame by year ascending, then country ascending. The sort
    # is stable; ties on year are broken by country alpha order so the
    # insertion order is fully deterministic.
    sorted_df = df.sort_values(
        by=["year", "country"], ascending=[True, True], kind="mergesort",
    )
    # Build a (country, year, variable_name) -> raw cell lookup from the
    # pre-coercion long frame. This lets us preserve the original
    # cell text for the raw_value audit trail.
    raw_long = df.attrs.get("_bti_raw_long")
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
                # No data for this indicator for this row (e.g. the
                # wide frame is missing the column for an indicator
                # that had no values anywhere). Skip -- no observation
                # to record.
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_float(cell)
            # Recover the pre-coercion raw cell for the audit trail.
            raw_cell = raw_lookup.get((country, year, spec.variable_name), cell)
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
                    source_row_reference=f"bti:{country}",
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


def write_bti_run_manifest(
    result,  # BtiIngestResult, imported lazily to avoid circular import
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    sheet_name: str | None = None,
    covered_interval: tuple[int, int] | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    the catalog path used, the attribution, and (for BTI) the resolved
    edition sheet name + covered interval so Stage 15 reports can
    surface the proxy/source-edition semantics without re-reading
    the parquet metadata.

    Args:
        result: the :class:`bti.BtiIngestResult` returned by
            :func:`bti.ingest_bti`.
        manifest_dir: override the output dir. Default: data-lake path.
        catalog_path: override the catalog path. Default: checked-in.
        sheet_name: the BTI edition sheet name the run resolved to
            (e.g. ``"BTI 2024"`` for the 2023 target year). Written to
            the manifest for audit.
        covered_interval: the ``(start_year, end_year)`` covered by
            the edition. Written to the manifest for audit.
    """
    out_dir = manifest_dir or processed_dir(BTI_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "bti_run_manifest.json"
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": BTI_ATTRIBUTION,
    }
    if sheet_name is not None:
        payload["sheet_name"] = sheet_name
    if covered_interval is not None:
        payload["covered_interval"] = list(covered_interval)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_bti_source",
    "write_bti_observations",
    "write_bti_run_manifest",
]
