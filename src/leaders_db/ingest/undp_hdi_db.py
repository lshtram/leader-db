"""Stage 2 -- UNDP HDI DB writes: sources, source_observations, run manifest.

This module is the DB half of the UNDP HDI adapter. It owns:

- :func:`register_undp_hdi_source` -- upsert the ``sources`` row
  from the UNDP HDI bundle's ``metadata.json``.
- :func:`write_undp_hdi_observations` -- write one
  ``source_observations`` row per ``(iso3, year, variable_name)``
  triple. Idempotent: deletes existing rows for the requested years
  before inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_undp_hdi_observations`, separated for testability.
- :func:`write_undp_hdi_run_manifest` -- write the audit-trail
  JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, value coercion,
observation-row builder) live in
:mod:`leaders_db.ingest.undp_hdi_db_helpers`. The narrow-frame
construction (UNPIVOT) lives in
:mod:`leaders_db.ingest.undp_hdi_csv`. The catalog loader, path
helpers, and parquet write function live in
:mod:`leaders_db.ingest.undp_hdi_io`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.undp_hdi`.

The split into ``undp_hdi_db`` (this file) +
:mod:`undp_hdi_db_helpers` follows the WGI / UCDP / SIPRI milex /
SIPRI Yearbook Ch.7 / PTS pattern. Per architecture §5, the
split was triggered when the module approached the 350-line
cap (it hit 449 lines before the split); the pure helpers were
extracted to keep the DB-write contract clean.
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
from .undp_hdi_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_undp_hdi_bundle_metadata,
)
from .undp_hdi_io import (
    _DEFAULT_CATALOG_PATH,
    UNDP_HDI_ATTRIBUTION,
    UNDP_HDI_SOURCE_KEY,
    load_undp_hdi_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_undp_hdi_source",
    "write_undp_hdi_observations",
    "write_undp_hdi_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_undp_hdi_source(session: Session) -> int:
    """Upsert the UNDP HDI source row into the ``sources`` table.

    Keyed by
    ``(source_name='UNDP Human Development Index (HDR 2023-24)',
    version='2023-24')``. Idempotent: returns the same ``sources.id``
    on every call. Reads the bundle's ``metadata.json`` for
    ``source_url``, ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as the V-Dem / WDI / WGI /
    UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS adapters).
    """
    source_name = "UNDP Human Development Index (HDR 2023-24)"
    version = "2023-24"

    bundle_meta = _read_undp_hdi_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range"),
    )

    # Bundle stores ``coverage_start_year`` / ``coverage_end_year``
    # as separate integers (rather than a ``"YYYY-YYYY"`` range
    # string); the helper supports both shapes via the bundle
    # metadata. Fall back to the integer fields if the range parse
    # returned ``(None, None)``.
    if coverage_start is None:
        cs = bundle_meta.get("coverage_start_year")
        if isinstance(cs, int):
            coverage_start = cs
    if coverage_end is None:
        ce = bundle_meta.get("coverage_end_year")
        if isinstance(ce, int):
            coverage_end = ce

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
                or (
                    "https://hdr.undp.org/sites/default/files/"
                    "2023-24_HDR/HDR23-24_Composite_indices_"
                    "complete_time_series.csv"
                ),
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license")
                or (
                    "Free with attribution; cite UNDP (see "
                    "docs/source-attributions.md)."
                ),
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C.8. "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/undp_hdi.csv. See "
                "docs/source-attributions.md for the exact citation "
                "text. Year 2023 requests are proxied to 2022 data "
                "(1-year-gap, per CIRIGHTS / Leader Survival "
                "pattern)."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh. See the docstring's update policy.
    if bundle_meta.get("source_url"):
        existing.source_url = str(bundle_meta["source_url"])
    if bundle_meta.get("license"):
        existing.license_note = str(bundle_meta["license"])
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


def write_undp_hdi_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(iso3, year, variable_name)``.

    The ``df`` is the narrow-format frame returned by
    :func:`undp_hdi_csv.build_undp_hdi_observations` (one row per
    ``(iso3, year, variable_name)`` triple). The function iterates
    the frame row-by-row and writes one :class:`SourceObservation`
    row per spec. ``country_id`` is left ``NULL`` (Stage 3 fills
    it). ``source_row_reference`` carries the ISO3 prefixed with
    ``"undp_hdi:"`` (e.g. ``"undp_hdi:USA"``) so Stage 3 can
    resolve it. ``confidence`` is left ``NULL`` (Stage 11 fills
    it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years outside
    the frame are untouched (so a single-year re-run does not
    erase older data).

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_undp_hdi_catalog(catalog_path=catalog_path)
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
    :func:`write_undp_hdi_observations` so the orchestrator stays
    short.
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


def write_undp_hdi_run_manifest(
    result,  # UndpHdiIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    proxy_year_semantics: str | None = None,
    requested_year: int | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    ``regions_covered`` (sorted list of the region codes found in
    the narrow frame), the ``year_window`` ``(start, end)`` tuple,
    the ``source_key``, the ``proxy_year_semantics`` (when the
    requested year was the 2023 proxy), the ``requested_year`` (when
    a year filter was applied), the catalog path, and the
    attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.

    Args:
        result: the :class:`UndpHdiIngestResult` returned by
            :func:`ingest_undp_hdi`.
        manifest_dir: override the output dir. Default: data-lake
            path (``data/processed/undp_hdi/``).
        catalog_path: override the catalog path. Default: checked-in.
        proxy_year_semantics: when the caller asked for ``year=2023``,
            this records the ``2023 -> 2022`` mapping. Surfaced as
            ``payload["proxy_year_semantics"]`` so the audit trail
            records the proxy mapping explicitly.
        requested_year: the literal year the caller asked for (e.g.
            ``2023`` for the proxy). Surfaced as
            ``payload["requested_year"]``.
    """
    out_dir = manifest_dir or processed_dir(UNDP_HDI_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "undp_hdi_run_manifest.json"
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "regions_covered": list(result.regions_covered),
        "year_window": list(result.year_window),
        "source_key": UNDP_HDI_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": UNDP_HDI_ATTRIBUTION,
    }
    if proxy_year_semantics:
        payload["proxy_year_semantics"] = proxy_year_semantics
    if requested_year is not None:
        payload["requested_year"] = int(requested_year)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
