"""Stage 2 -- FAS Nuclear Notebook DB writes: sources, source_observations, run manifest.

This module is the DB half of the FAS Nuclear Notebook adapter.
It owns:

- :func:`register_fas_source` -- upsert the ``sources`` row from
  the FAS bundle's ``metadata.json``.
- :func:`write_fas_observations` -- write one
  ``source_observations`` row per ``(country, year, variable)``
  triple. Idempotent: deletes existing rows for the requested
  years before inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_fas_observations`, separated for testability.
- :func:`write_fas_run_manifest` -- write the audit-trail JSON
  next to the narrow parquet.

The pure helpers (bundle metadata reader, value coercion,
observation-row builder) live in
:mod:`leaders_db.ingest.fas_db_helpers`. The HTTP + cache I/O
lives in :mod:`fas_http`. The HTML reader + catalog + paths +
parquet write live in :mod:`fas_io` / :mod:`fas_html`. The
orchestrator lives in :mod:`fas`.
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
from .fas_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _read_fas_bundle_metadata,
)
from .fas_io import (
    _DEFAULT_CATALOG_PATH,
    FAS_ATTRIBUTION,
    FAS_PUBLISHER_URL,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_fas_source",
    "write_fas_observations",
    "write_fas_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_fas_source(session: Session) -> int:
    """Upsert the FAS Nuclear Notebook source row into the ``sources`` table.

    Keyed by ``(source_name='Federation of American Scientists
    Nuclear Notebook', version='consolidated status table')``.
    Idempotent: returns the same ``sources.id`` on every call.
    Reads the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note`` (all optional).

    Non-destructive update policy: missing bundle fields keep
    the existing row's old value (same rule as V-Dem / WDI / WGI
    / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI
    / WHO GHO API / Transparency International CPI / CIRIGHTS /
    BTI / RSF).
    """
    bundle_meta = _read_fas_bundle_metadata()

    source_name = (
        "Federation of American Scientists Nuclear Notebook"
    )
    version = str(
        bundle_meta.get("version") or "consolidated status table"
    )

    download_date_value = _parse_download_date(
        bundle_meta.get("download_date")
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
                bundle_meta.get("source_url") or FAS_STATUS_PAGE_URL
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free; cite Federation of American Scientists "
                    "per docs/source-attributions.md."
                )
            ),
            download_date=download_date_value,
            coverage_start_year=None,
            coverage_end_year=None,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator "
                "catalog at "
                "src/leaders_db/ingest/catalogs/fas.csv. See "
                "docs/source-attributions.md for the exact citation "
                "text. The consolidated status page snapshot year "
                "(e.g. 2014 for the live page) is recorded in the "
                "run manifest; the Stage 11 confidence engine "
                "penalises the temporal-fit gap between the "
                "snapshot year and the prototype's target year. "
                "The consolidated page is cited by SIPRI "
                "Yearbook Ch.7 as the FAS-Nuclear-Notebook "
                "summary table."
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
    return int(existing.id)


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_fas_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per ``(country, year, variable)``.

    The ``df`` is the wide-format frame returned by the reader
    (one row per ``(country, year)``, one column per catalog
    ``variable_name`` plus audit-trail columns). The function
    iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per spec. ``country_id`` is
    left ``NULL`` (Stage 3 fills it; the FAS table uses country
    names, not ISO3). ``source_row_reference`` carries the
    catalog ``raw_column`` + country name (e.g.
    ``"fas:Operational Strategic:Russia"``) so Stage 3 can
    resolve it. ``confidence`` is left ``NULL`` (Stage 11 fills
    it).

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
    """Delete existing ``source_observations`` rows for the given years."""
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


def write_fas_run_manifest(
    result,  # FasIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    snapshot_year: int | None = None,
    html_cached: bool = False,
    html_fetched: bool = False,
    status_page_url: str | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator
    count, the ``snapshot_year`` parsed from the page's meta
    date element, the ``html_cached`` / ``html_fetched`` flags,
    the catalog path used, the FAS status page URL, the
    publisher URL, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.

    Args:
        result: the :class:`FasIngestResult` returned by
            :func:`fas.ingest_fas`.
        manifest_dir: override the output dir. Default:
            ``data/processed/fas/``.
        catalog_path: override the catalog path. Default:
            checked-in.
        snapshot_year: the FAS page snapshot year (parsed from
            the meta date element). Recorded for audit so
            downstream stages know the freshness of the data.
        html_cached: whether the HTML was read from the local
            cache (no HTTP call).
        html_fetched: whether the HTML was HTTP-fetched in this
            call.
        status_page_url: the FAS status page URL (default:
            :data:`FAS_STATUS_PAGE_URL`).
    """
    out_dir = manifest_dir or processed_dir(FAS_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "fas_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "snapshot_year": int(snapshot_year) if snapshot_year else None,
        "html_cached": bool(html_cached),
        "html_fetched": bool(html_fetched),
        "source_key": FAS_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": FAS_ATTRIBUTION,
        "status_page_url": status_page_url or FAS_STATUS_PAGE_URL,
        "publisher_url": FAS_PUBLISHER_URL,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
