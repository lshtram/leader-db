"""Stage 2 -- Transparency International CPI DB writes: sources, source_observations, run manifest.

This module is the DB half of the Transparency International CPI
adapter. It owns:

- :func:`register_transparency_cpi_source` -- upsert the
  ``sources`` row from the Transparency International CPI
  bundle's ``metadata.json``.
- :func:`write_transparency_cpi_observations` -- write one
  ``source_observations`` row per ``(iso3, year, variable)``
  triple. Idempotent: deletes existing rows for the requested
  years before inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_transparency_cpi_observations`, separated for
  testability.
- :func:`write_transparency_cpi_run_manifest` -- write the
  audit-trail JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, value coercion,
observation-row builder) live in
:mod:`leaders_db.ingest.transparency_cpi_db_helpers`. The HTTP +
cache I/O lives in :mod:`transparency_cpi_http`. The catalog +
paths + CSV reader + parquet write live in
:mod:`transparency_cpi_io` / :mod:`transparency_cpi_csv`. The
orchestrator lives in :mod:`transparency_cpi`.
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
from .transparency_cpi_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_transparency_cpi_bundle_metadata,
)
from .transparency_cpi_io import (
    _DEFAULT_CATALOG_PATH,
    TRANSPARENCY_CPI_ATTRIBUTION,
    TRANSPARENCY_CPI_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_transparency_cpi_source",
    "write_transparency_cpi_observations",
    "write_transparency_cpi_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------

#: Canonical publisher URL. Used as the ``source_url`` when the
#: bundle metadata has no ``source_url`` field. The Transparency
#: International CPI is published by Transparency International;
#: the HDX resource is the durable CSV mirror.
TRANSPARENCY_CPI_PUBLISHER_URL: str = "https://www.transparency.org/en/cpi/2023"

#: HDX mirror URL. Recorded in the run manifest for audit (the
#: HDX dataset UUID is part of the URL pattern in
#: :mod:`transparency_cpi_http`).
TRANSPARENCY_CPI_HDX_MIRROR_URL: str = (
    "https://data.humdata.org/dataset/"
    "fb4adde0-93d5-4ff9-befc-4a6916c1181b"
)


def register_transparency_cpi_source(session: Session) -> int:
    """Upsert the Transparency International CPI source row into the ``sources`` table.

    Keyed by ``(source_name='Transparency International Corruption
    Perceptions Index', version='CPI <year>')``. Idempotent:
    returns the same ``sources.id`` on every call. Reads the
    bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``, ``coverage_start_year``,
    ``coverage_end_year`` (all optional).

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem / WDI / WGI /
    UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI /
    WHO GHO API / CIRIGHTS / BTI / RSF). A future bundle with a
    new ``source_url`` will overwrite the existing row's URL, but
    a missing ``download_date`` will not blank the field.
    """
    bundle_meta = _read_transparency_cpi_bundle_metadata()

    version = str(bundle_meta.get("version") or "CPI 2023")
    source_name = (
        "Transparency International Corruption Perceptions Index"
    )

    download_date_value = _parse_download_date(
        bundle_meta.get("download_date")
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range")
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
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url") or TRANSPARENCY_CPI_PUBLISHER_URL
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free for non-commercial use with attribution; "
                    "cite Transparency International per "
                    "docs/source-attributions.md."
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator "
                "catalog at "
                "src/leaders_db/ingest/catalogs/transparency_cpi.csv. "
                "See docs/source-attributions.md for the exact "
                "citation text. The direct xlsx download from "
                "transparency.org is CDN-gated; the adapter "
                "downloads the canonical CSV from the OCHA HDX "
                "mirror (data.humdata.org), which preserves the "
                "verbatim Transparency International release."
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


def write_transparency_cpi_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per ``(iso3, year, variable)``.

    The ``df`` is the wide-format frame returned by the reader
    (one row per ``(iso3, year)``, one column per catalog
    ``variable_name`` plus audit-trail columns). The function
    iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per spec. ``country_id`` is
    left ``NULL`` (Stage 3 fills it). ``source_row_reference``
    carries the catalog ``raw_column`` + ISO3 (e.g.
    ``"transparency_cpi:score:MEX"``) so Stage 3 can resolve it.
    ``confidence`` is left ``NULL`` (Stage 11 fills it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years
    outside the frame are untouched (so a single-year re-run
    does not erase older data).

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
    :func:`write_transparency_cpi_observations` so the
    orchestrator stays short.
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


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_transparency_cpi_run_manifest(
    result,  # TransparencyCpiIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    csv_cached: bool = False,
    csv_fetched: bool = False,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator
    count, the catalog path used, the HDX mirror URL, the
    publisher URL, the cache status (``csv_cached`` /
    ``csv_fetched``), and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.

    Args:
        result: the :class:`TransparencyCpiIngestResult` returned
            by :func:`transparency_cpi.ingest_transparency_cpi`.
        manifest_dir: override the output dir. Default:
            ``data/processed/transparency_cpi/``.
        catalog_path: override the catalog path. Default:
            checked-in.
        csv_cached: whether the per-year CSV was read from the
            local cache (no HTTP call).
        csv_fetched: whether the per-year CSV was HTTP-fetched in
            this call.
    """
    out_dir = manifest_dir or processed_dir(TRANSPARENCY_CPI_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "transparency_cpi_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "csv_cached": bool(csv_cached),
        "csv_fetched": bool(csv_fetched),
        "source_key": TRANSPARENCY_CPI_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": TRANSPARENCY_CPI_ATTRIBUTION,
        "publisher_url": TRANSPARENCY_CPI_PUBLISHER_URL,
        "hdx_mirror_url": TRANSPARENCY_CPI_HDX_MIRROR_URL,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
