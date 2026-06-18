"""Stage 2 -- Political Terror Scale (PTS) DB writes: sources, observations, manifest.

This module is the DB half of the PTS adapter. It owns:

- :func:`register_pts_source` -- upsert the ``sources`` row from the
  PTS bundle's ``metadata.json``.
- :func:`write_pts_observations` -- write one ``source_observations``
  row per ``(country, year, variable)`` triple. Idempotent (deletes
  existing rows for the requested years before inserting).
- :func:`_delete_existing_observations` -- helper for
  :func:`write_pts_observations`, separated for testability.
- :func:`write_pts_run_manifest` -- write the audit-trail JSON next
  to the narrow parquet.

The pure helpers (observation-row builder, bundle-metadata parsing)
live in :mod:`leaders_db.ingest.pts_db_helpers`. The xlsx read +
parquet write functions live in :mod:`leaders_db.ingest.pts_io` and
:mod:`leaders_db.ingest.pts_xlsx`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.pts`.

The split into ``pts_db`` + ``pts_db_helpers`` is mandated by
architecture §5: "no separate ``_helpers.py`` unless the module
grows past 350 lines." :mod:`pts_db` reached 431 lines (the trigger
fired at 351), so the helpers were extracted. This mirrors the WGI
5-module split (``wgi_db.py`` + ``wgi_db_helpers.py``).
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
from .pts_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_pts_bundle_metadata,
)
from .pts_io import (
    _DEFAULT_CATALOG_PATH,
    PTS_ATTRIBUTION,
    PTS_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_pts_source(session: Session) -> int:
    """Upsert the PTS source row into the ``sources`` table.

    Keyed by
    ``(source_name='Political Terror Scale (PTS)', version='PTS-2025')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``, ``coverage_*_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`, WGI's
    :func:`wgi_db.register_wgi_source`, UCDP's
    :func:`ucdp_db.register_ucdp_source`, SIPRI milex's
    :func:`sipri_milex_db.register_sipri_milex_source`, and SIPRI
    Yearbook Ch.7's
    :func:`sipri_yearbook_ch7_db.register_sipri_yearbook_ch7_source`).
    """
    source_name = "Political Terror Scale (PTS)"
    version = "PTS-2025"

    bundle_meta = _read_pts_bundle_metadata()
    download_date_value = _parse_download_date(bundle_meta.get("download_date"))
    coverage_start, coverage_end = _parse_year_range(bundle_meta.get("year_range"))

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
            source_type="academic",
            source_url=str(
                bundle_meta.get("source_url")
                or "https://www.politicalterrorscale.org/"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license")
                or (
                    "Free academic use with attribution; cite Wood, "
                    "Gibney, et al. (see docs/source-attributions.md)."
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator "
                "catalog at "
                "src/leaders_db/ingest/catalogs/pts.csv. See "
                "docs/source-attributions.md for the exact citation "
                "text."
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


def write_pts_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per ``(country, year,
    variable)``.

    Same shape as the WGI / WDI / V-Dem / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 adapters (mirrors the SIPRI Yearbook Ch.7 pattern
    per the design prompt):

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills
      it from the PTS ``COW_Code_A`` via the country lookup table (a
      future Stage 3 deliverable).
    - ``source_row_reference`` carries the ``COW_Code_A`` prefixed
      with ``"pts:"`` (e.g. ``"pts:USA"``) so Stage 3 can resolve it.
    - ``raw_value`` preserves the original cell text per the §6.3
      audit-trail matrix. For dropped cells (any of cases 2, 3, 4),
      ``raw_value`` is ``None`` (per the design prompt; the row is
      still written so the audit trail records the cell's status).
    - ``normalized_value`` is the int 1-5 for valid cells (case 1),
      or ``None`` if the cell is missing per §6 (any of the 4 cases
      that drop the indicator).
    - Idempotent: deletes existing rows for the requested years
      (from the frame) before inserting. Years outside the frame are
      untouched.

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
    session: Session, source_id: int, years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched. Pulled out of
    :func:`write_pts_observations` so the orchestrator stays short.
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


def write_pts_run_manifest(
    result,  # PtsIngestResult, imported lazily to avoid circular import
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, the parquet path,
    the observation row count, the countries count, the years, the
    indicator count, the ``regions_covered`` (sorted list of the
    Region codes found in the wide frame), the ``year_window``
    ``(start, end)`` tuple, the ``source_key``, a ``status`` flag
    (``"ok"`` for a successful run; ``"no_data"`` for a year-out-of-
    range short-circuit), the catalog path, and the attribution.
    Written every run (not best-effort) so Stage 15 reports can find
    the attribution without re-reading the parquet metadata.

    Args:
        result: the :class:`PtsIngestResult` returned by
            :func:`ingest_pts`.
        manifest_dir: override the output dir. Default: data-lake
            path (``data/processed/pts/``).
        catalog_path: override the catalog path. Default: checked-in.
    """
    out_dir = manifest_dir or processed_dir(PTS_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "pts_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "regions_covered": list(result.regions_covered),
        "year_window": list(result.year_window),
        "source_key": PTS_SOURCE_KEY,
        "status": "ok",
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": PTS_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_pts_source",
    "write_pts_observations",
    "write_pts_run_manifest",
]
