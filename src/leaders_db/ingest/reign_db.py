"""Stage 2 -- REIGN (Bell 2016) DB writes: sources, source_observations, run manifest.

This module is the DB half of the REIGN adapter. It owns:

- :func:`register_reign_source` -- upsert the ``sources`` row
  from the REIGN bundle's ``metadata.json``.
- :func:`write_reign_observations` -- write one
  ``source_observations`` row per long-format row. Idempotent:
  deletes existing rows for the requested years before
  inserting.
- :func:`_delete_existing_observations` -- helper for
  :func:`write_reign_observations`, separated for testability.
- :func:`write_reign_run_manifest` -- write the audit-trail
  JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, value coercion,
observation-row builder) live in
:mod:`leaders_db.ingest.reign_db_helpers`. The CSV read +
coercion lives in :mod:`leaders_db.ingest.reign_csv`. The
catalog loader, path helpers, and parquet write function live in
:mod:`leaders_db.ingest.reign_io`. The Pydantic result model
lives in :mod:`leaders_db.ingest.reign_result`. The
orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.reign`.
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
from .reign_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_reign_bundle_metadata,
)
from .reign_io import (
    _DEFAULT_CATALOG_PATH,
    REIGN_ATTRIBUTION,
    REIGN_SOURCE_KEY,
    load_reign_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_reign_source",
    "write_reign_observations",
    "write_reign_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_reign_source(session: Session) -> int:
    """Upsert the REIGN source row into the ``sources`` table.

    Keyed by
    ``(source_name='REIGN (Rulers, Elections, and Irregular Governance)',
    version='2021-8')``. Idempotent: returns the same
    ``sources.id`` on every call. Reads the bundle's
    ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``,
    ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as the V-Dem / CIRIGHTS /
    WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP
    HDI / WHO GHO API / Archigos adapters).
    """
    source_name = "REIGN (Rulers, Elections, and Irregular Governance)"
    version = "2021-8"

    bundle_meta = _read_reign_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("years_available"),
    )
    # Bundle stores ``coverage_start_year`` / ``coverage_end_year``
    # as separate integers (the REIGN bundle metadata uses
    # ``years_available`` as a free-text string; the helper
    # gracefully returns ``(None, None)`` if the string is not in
    # ``"YYYY-YYYY"`` shape). Fall back to the integer fields
    # only as a last resort, and only when the bundle does not
    # provide any coverage hint at all.
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
        ),
    ).scalar_one_or_none()

    if existing is None:
        row = Source(
            source_name=source_name,
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url")
                or (
                    "https://raw.githubusercontent.com/OEFDataScience/"
                    "REIGN.github.io/gh-pages/data_sets/REIGN_2021_8.csv"
                ),
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free academic; cite Bell 2016 (OEF Research) "
                    "(see docs/source-attributions.md)."
                ),
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C.10. "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/reign.csv. See "
                "docs/source-attributions.md for the exact citation "
                "text. REIGN 2021-8 is leader-month data (138,600 "
                "leader-month rows, 1950-2021-08); the Stage 2 "
                "adapter writes one source_observations row per "
                "(leader-month-row, identity-column) pair, keyed by "
                "the row's year column. The Stage 4 leader "
                "resolver (not implemented in this phase) will "
                "join REIGN with Archigos, Leader Survival, "
                "Wikidata, and the client bundle."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh.
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


def write_reign_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per long-format row.

    The ``df`` is the long-format frame returned by
    :func:`leaders_db.ingest.reign_io.read_reign` (one row per
    (leader-month-row, identity-column) pair). The function
    iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per long row.
    ``country_id`` is left ``NULL`` (Stage 3 fills it).
    ``leader_id`` is left ``NULL`` (Stage 4 fills it).
    ``source_row_reference`` carries
    ``reign:<country_token>:<leader_token>:<year>:<month>:<raw_column>``
    (e.g. ``reign:USA:Truman:1950:1:leader``) so Stage 3 / Stage
    4 can resolve it. ``confidence`` is left ``NULL`` (Stage 11
    fills it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years outside
    the frame are untouched (so a single-year re-run does not
    erase older data).

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_reign_catalog(catalog_path=catalog_path)
    years = sorted(
        {
            int(y) for y in df["year"].tolist()
            if y is not None and not pd.isna(y)
        },
    )

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
    :func:`write_reign_observations` so the orchestrator stays
    short.
    """
    if not years:
        return
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


def write_reign_run_manifest(
    result,  # ReignIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    ``year_window`` ``(start, end)`` tuple, the ``source_key``,
    the catalog path, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.

    Args:
        result: the :class:`ReignIngestResult` returned by
            :func:`ingest_reign`.
        manifest_dir: override the output dir. Default: data-lake
            path (``data/processed/reign/``).
        catalog_path: override the catalog path. Default: checked-in.
    """
    out_dir = manifest_dir or processed_dir(REIGN_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "reign_run_manifest.json"
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "year_window": list(result.year_window),
        "source_key": REIGN_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": REIGN_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
