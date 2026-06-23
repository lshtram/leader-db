"""Stage 2 -- RSF World Press Freedom Index DB writes: sources, observations, manifest.

This module is the DB half of the RSF adapter. It owns:

- :func:`register_rsf_press_freedom_source` -- upsert the ``sources``
  row from the RSF bundle's ``metadata.json``.
- :func:`write_rsf_press_freedom_observations` -- write one
  ``source_observations`` row per ``(iso3, year, variable_name)``
  triple. Idempotent: deletes existing rows for the requested year
  before inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_rsf_press_freedom_observations`, separated for
  testability.
- :func:`write_rsf_press_freedom_run_manifest` -- write the
  audit-trail JSON next to the narrow parquet.

The pure helpers (observation-row builder, bundle-metadata parsing)
live in :mod:`leaders_db.ingest.rsf_press_freedom_db_helpers`. The
CSV read + parquet write functions live in
:mod:`leaders_db.ingest.rsf_press_freedom_csv` and
:mod:`leaders_db.ingest.rsf_press_freedom_parquet`. The catalog
loader and path helpers live in
:mod:`leaders_db.ingest.rsf_press_freedom_io`. The orchestrator
that ties everything together lives in
:mod:`leaders_db.ingest.rsf_press_freedom`.

The split into ``rsf_press_freedom_db`` (this file) +
:mod:`rsf_press_freedom_db_helpers` follows the V-Dem / WGI /
UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI pattern.
The pure helpers are extracted so the DB-write contract stays
clean.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .rsf_press_freedom_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_rsf_press_freedom_bundle_metadata,
)
from .rsf_press_freedom_io import (
    _DEFAULT_CATALOG_PATH,
    RSF_PRESS_FREEDOM_ATTRIBUTION,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    RUN_MANIFEST_NAME,
    YEAR_END,
    YEAR_START,
    load_rsf_press_freedom_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_rsf_press_freedom_source",
    "write_rsf_press_freedom_observations",
    "write_rsf_press_freedom_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def _resolve_coverage_range(
    bundle_meta: dict[str, object],
) -> tuple[int | None, int | None]:
    """Resolve the ``coverage_start_year`` / ``coverage_end_year``
    pair from the bundle metadata.

    The RSF ``metadata.json`` shape carries the integer
    ``coverage_start_year`` / ``coverage_end_year`` fields
    directly. As a defense-in-depth fallback (e.g. when the bundle
    metadata uses a different schema), this helper also accepts
    a ``"YYYY-YYYY"`` year_range string or a ``years_available``
    list and maps it to ``(start, end)``.

    Returns ``(None, None)`` when no coverage info is available.
    """
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range"),
    )

    # Bundle stores ``coverage_start_year`` / ``coverage_end_year``
    # as separate integers (per metadata.json). Fall back to the
    # integer fields if the range parse returned ``(None, None)``.
    if coverage_start is None:
        cs = bundle_meta.get("coverage_start_year")
        if isinstance(cs, int):
            coverage_start = cs
    if coverage_end is None:
        ce = bundle_meta.get("coverage_end_year")
        if isinstance(ce, int):
            coverage_end = ce

    # The bundle's ``years_available`` is a list, not a single
    # range; map it to start/end if the explicit range fields are
    # missing.
    if coverage_start is None:
        ya = bundle_meta.get("years_available")
        if isinstance(ya, list) and ya:
            try:
                coverage_start = int(min(int(x) for x in ya))
            except (TypeError, ValueError):
                coverage_start = None
    if coverage_end is None:
        ya = bundle_meta.get("years_available")
        if isinstance(ya, list) and ya:
            try:
                coverage_end = int(max(int(x) for x in ya))
            except (TypeError, ValueError):
                coverage_end = None

    return coverage_start, coverage_end


def register_rsf_press_freedom_source(session: Session) -> int:
    """Upsert the RSF source row into the ``sources`` table.

    Keyed by ``(source_name='Reporters Without Borders World Press
    Freedom Index', version='annual CSV series 2002-2026')``.
    Idempotent: returns the same ``sources.id`` on every call.
    Reads the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``, ``coverage_*_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as the V-Dem / WGI / UCDP
    / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI
    adapters).
    """
    source_name = "Reporters Without Borders World Press Freedom Index"
    version = "annual CSV series 2002-2026"

    bundle_meta = _read_rsf_press_freedom_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _resolve_coverage_range(bundle_meta)

    existing = session.execute(
        select(Source).where(
            Source.source_name == source_name,
            Source.version == version,
        ),
    ).scalar_one_or_none()

    if existing is None:
        row = Source(
            source_name=source_name,
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url")
                or "https://rsf.org/en/index",
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Public RSF World Press Freedom Index data; "
                    "cite Reporters Without Borders / Reporters "
                    "sans frontières (see "
                    "docs/sources/attributions.md)."
                ),
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/rsf_press_freedom.csv. "
                "See docs/sources/attributions.md for the exact "
                "citation text. Pre/post-2022 schema break: pre-2022 "
                "files (2002-2021) do not carry the 5 "
                "component-context columns (Political Context / "
                "Economic Context / Legal Context / Social Context "
                "/ Safety) that are present in 2022+ files; the "
                "adapter emits no component observations for pre-"
                "2022 years. Direct 2011.csv is absent -- RSF's "
                "combined 2011/2012 edition is represented by the "
                "2012 CSV (Year (N) = '2011-12')."
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


def write_rsf_press_freedom_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(iso3, year, variable_name)``.

    The ``df`` is the narrow-format frame returned by
    :func:`rsf_press_freedom_csv.read_rsf_press_freedom_csv`. The
    function iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per spec. ``country_id`` is left
    ``NULL`` (Stage 3 fills it). ``leader_id`` is left ``NULL``
    (Stage 4 fills it). ``source_row_reference`` carries the
    year-specific actual RSF column name prefixed with
    ``"rsf_press_freedom:<iso3>:"`` (e.g.
    ``"rsf_press_freedom:MEX:Score N"`` for the 2002 file or
    ``"rsf_press_freedom:MEX:Score"`` for the 2023+ file) so
    Stage 3 / 5 / 15 can locate the source row without re-parsing
    the CSV. ``confidence`` is left ``NULL`` (Stage 11 fills it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years outside
    the frame are untouched (so a single-year re-run does not
    erase older data).

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_rsf_press_freedom_catalog(catalog_path=catalog_path)
    years = sorted({int(y) for y in df["year"].tolist()})

    _delete_existing_observations(session, source_id, years)
    rows = _build_observation_rows(source_id, df, specs)
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session, source_id: int, years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched. Pulled out of
    :func:`write_rsf_press_freedom_observations` so the orchestrator
    stays short.
    """
    existing_rows = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_id == source_id,
            SourceObservation.year.in_(years),
        ),
    ).scalars().all()
    for row in existing_rows:
        session.delete(row)
    session.flush()


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_rsf_press_freedom_run_manifest(
    result,  # RsfPressFreedomIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, country count, years, indicator count,
    ``pre_2022_country_count`` / ``post_2022_country_count`` (the
    per-schema split, useful for the audit trail), the
    ``year_window`` ``(start, end)`` tuple, the ``source_key``, the
    catalog path, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.
    """
    out_dir = manifest_dir or processed_dir(RSF_PRESS_FREEDOM_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / RUN_MANIFEST_NAME
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "pre_2022_country_count": result.pre_2022_country_count,
        "post_2022_country_count": result.post_2022_country_count,
        "year_window": list(result.year_window),
        "year_start": YEAR_START,
        "year_end": YEAR_END,
        "source_key": RSF_PRESS_FREEDOM_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": RSF_PRESS_FREEDOM_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
