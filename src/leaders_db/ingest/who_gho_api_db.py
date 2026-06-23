"""Stage 2 -- WHO GHO API DB writes: sources, source_observations, run manifest.

This module is the DB half of the WHO GHO API adapter. It owns:

- :func:`register_who_gho_api_source` -- upsert the ``sources`` row
  from the WHO GHO API bundle's ``metadata.json``.
- :func:`write_who_gho_api_observations` -- write one
  ``source_observations`` row per ``(iso3, year, variable)``
  triple. Idempotent: deletes existing rows for the requested
  years before inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_who_gho_api_observations`, separated for testability.
- :func:`write_who_gho_api_run_manifest` -- write the audit-trail
  JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, value coercion,
observation-row builder) live in
:mod:`leaders_db.ingest.who_gho_api_db_helpers`. The HTTP + cache
I/O lives in :mod:`leaders_db.ingest.who_gho_api_http`. The
catalog + paths + parquet write live in
:mod:`leaders_db.ingest.who_gho_api_io`. The orchestrator lives in
:mod:`leaders_db.ingest.who_gho_api`.
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
from .who_gho_api_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_who_gho_api_bundle_metadata,
)
from .who_gho_api_io import (
    _DEFAULT_CATALOG_PATH,
    WHO_GHO_API_ATTRIBUTION,
    WHO_GHO_API_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_who_gho_api_source",
    "write_who_gho_api_observations",
    "write_who_gho_api_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_who_gho_api_source(session: Session) -> int:
    """Upsert the WHO GHO API source row into the ``sources`` table.

    Keyed by
    ``(source_name='WHO Global Health Observatory (OData API)',
    version='GHO OData v1')``. Idempotent: returns the same
    ``sources.id`` on every call. Reads the bundle's
    ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``, ``coverage_end_year``
    (all optional; the WHO GHO API has no fixed coverage window --
    per-indicator data freshness varies).

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem / WDI / WGI / UCDP
    / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI). A
    future bundle with a new ``source_url`` will overwrite the
    existing row's URL, but a missing ``download_date`` will not
    blank the field.
    """
    source_name = "WHO Global Health Observatory (OData API)"
    version = "GHO OData v1"

    bundle_meta = _read_who_gho_api_bundle_metadata()
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
                bundle_meta.get("source_url") or WHO_GHO_API_ATTRIBUTION_URL
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Open; cite WHO Global Health Observatory per "
                    "docs/sources/attributions.md."
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator "
                "catalog at "
                "src/leaders_db/ingest/catalogs/who_gho_api.csv. See "
                "docs/sources/attributions.md for the exact citation "
                "text. WHO GHO OData API is JSON-backed (OData 4.0, "
                "Azure, public, no auth) with a per-indicator "
                "data-freshness profile (no fixed coverage window)."
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


# Module-level constant used by :func:`register_who_gho_api_source`
# when the bundle has no ``source_url`` field. Kept here (not in
# ``who_gho_api_io``) because it is a public-API URL, not a
# catalog / data-lake concept.
WHO_GHO_API_ATTRIBUTION_URL: str = "https://www.who.int/data/gho"


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_who_gho_api_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(iso3, year, variable)``.

    The ``df`` is the wide-format frame returned by the reader
    (one row per ``(iso3, year)``, one column per catalog
    ``variable_name``). The function iterates the frame
    row-by-row and writes one :class:`SourceObservation` row per
    spec. ``country_id`` is left ``NULL`` (Stage 3 fills it).
    ``source_row_reference`` carries the WHO GHO API
    ``raw_column`` + ISO3 (e.g.
    ``"who_gho_api:WHOSIS_000001:MEX"``) so Stage 3 can resolve
    it. ``confidence`` is left ``NULL`` (Stage 11 fills it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years outside
    the frame are untouched (so a single-year re-run does not
    erase older data).

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
    :func:`write_who_gho_api_observations` so the orchestrator
    stays short.
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


def write_who_gho_api_run_manifest(
    result,  # WhoGhoApiIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    indicators_cached: int = 0,
    indicators_fetched: int = 0,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    ``indicators_cached`` / ``indicators_fetched``, the catalog
    path used, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.

    Args:
        result: the :class:`WhoGhoApiIngestResult` returned by
            :func:`ingest_who_gho_api`.
        manifest_dir: override the output dir. Default:
            ``data/processed/who_gho_api/``.
        catalog_path: override the catalog path. Default:
            checked-in.
        indicators_cached: how many of the catalog indicators
            were read from the JSON cache (no HTTP call). The
            orchestrator passes this from ``df.attrs``.
        indicators_fetched: how many of the catalog indicators
            were HTTP-fetched in this call.
    """
    out_dir = manifest_dir or processed_dir(WHO_GHO_API_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "who_gho_api_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "indicators_cached": int(indicators_cached),
        "indicators_fetched": int(indicators_fetched),
        "source_key": WHO_GHO_API_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": WHO_GHO_API_ATTRIBUTION,
        "api_base": "https://ghoapi.azureedge.net/api/",
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_who_gho_api_source",
    "write_who_gho_api_observations",
    "write_who_gho_api_run_manifest",
]
