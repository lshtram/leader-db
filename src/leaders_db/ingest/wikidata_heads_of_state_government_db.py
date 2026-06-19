"""Stage 2 -- Wikidata heads-of-state-and-government DB writes.

This module is the DB half of the Wikidata heads-of-state-and-
government adapter. It owns:

- :func:`register_wikidata_heads_of_state_government_source` -- upsert
  the ``sources`` row from the bundle's ``metadata.json``.
- :func:`write_wikidata_heads_of_state_government_observations` --
  write one ``source_observations`` row per (binding, matching
  catalog spec) pair. Idempotent: deletes existing rows for the
  requested years before inserting.
- :func:`_delete_existing_observations` -- helper for the observations
  write, separated for testability.
- :func:`write_wikidata_heads_of_state_government_run_manifest` --
  write the audit-trail JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, observation-row builder,
source-row-reference builder) live in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_db_helpers`.
The HTTP + cache I/O lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_http`. The
parser lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_parse`. The
catalog + paths + parquet write live in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_io`. The
orchestrator lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government`.
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
from .wikidata_heads_of_state_government_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _read_wikidata_bundle_metadata,
)
from .wikidata_heads_of_state_government_io import (
    _DEFAULT_CATALOG_PATH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

# Module-level constant used by
# :func:`register_wikidata_heads_of_state_government_source` when the
# bundle has no ``source_url`` field. Kept here (not in the io
# module) because it is the SPARQL endpoint URL, not a catalog /
# data-lake concept.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_URL: str = (
    "https://query.wikidata.org/sparql"
)


__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_URL",
    "register_wikidata_heads_of_state_government_source",
    "write_wikidata_heads_of_state_government_observations",
    "write_wikidata_heads_of_state_government_run_manifest",
]


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_wikidata_heads_of_state_government_source(
    session: Session,
) -> int:
    """Upsert the Wikidata heads-of-state source row into ``sources``.

    Keyed by
    ``(source_name='Wikidata WikiProject Heads of state and government',
    version='SPARQL')``. Idempotent: returns the same ``sources.id``
    on every call. Reads the bundle's ``metadata.json`` for
    ``source_url``, ``download_date``, ``license_note`` (all
    optional).

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem / WDI / WHO GHO API
    / etc.). A future bundle with a new ``source_url`` will overwrite
    the existing row's URL, but a missing ``download_date`` will not
    blank the field.
    """
    source_name = (
        "Wikidata WikiProject Heads of state and government"
    )
    version = "SPARQL"

    bundle_meta = _read_wikidata_bundle_metadata()
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
                bundle_meta.get("source_url")
                or WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_URL
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note") or "CC0 1.0 (Public Domain Dedication)"
            ),
            download_date=download_date_value,
            coverage_start_year=None,
            coverage_end_year=None,
            notes=(
                "Stage 2 always-on helper adapter (Phase C). "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/"
                "wikidata_heads_of_state_government.csv. See "
                "docs/source-attributions.md for the exact "
                "attribution text. Wikidata SPARQL endpoint is "
                "JSON-backed (CC0 1.0, public, no auth) with a "
                "mandatory descriptive User-Agent header per the "
                "Wikimedia User-Agent policy. normalized_value is "
                "NULL at Stage 2 (a Wikidata leader reference is "
                "a QID, not a number); country_id and leader_id are "
                "also NULL at Stage 2 -- Stage 3 maps QID -> "
                "countries.id (ISO3) and Stage 4 maps QID -> "
                "leaders.id."
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


def write_wikidata_heads_of_state_government_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (binding, spec) pair.

    The ``df`` is the long-format frame returned by the parser (one
    row per SPARQL binding). The function iterates the frame and
    emits one :class:`SourceObservation` row per binding whose
    ``office_qid`` matches a catalog spec's ``raw_column``.

    ``country_id`` and ``leader_id`` are intentionally left ``NULL``
    (Stage 3 + Stage 4 fill them). ``source_row_reference`` carries
    the QID + statement hash. ``confidence`` is left ``NULL`` (Stage
    11 fills it). ``normalized_value`` is ``NULL`` for every row
    because Wikidata has no numeric value to normalize.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose ``year``
    is present in ``df`` (or whose year is NULL when the frame
    contains any year-NULL rows) before inserting. Years outside the
    frame are untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_indicator_catalog(catalog_path=catalog_path)
    years_in_frame = sorted(
        {
            int(y)
            for y in df["year"].dropna().tolist()
            if pd.notna(y)
        }
    )
    has_null_year = bool(df["year"].isna().any())

    _delete_existing_observations(
        session, source_id, years=years_in_frame,
        has_null_year=has_null_year,
    )
    rows = _build_observation_rows(df, specs=specs)
    # Stamp the source_id on every row (the helper builds with 0 so
    # the caller owns the source_id).
    for row in rows:
        row.source_id = source_id
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session,
    source_id: int,
    *,
    years: list[int],
    has_null_year: bool,
) -> None:
    """Delete existing ``source_observations`` rows for the given scope.

    Pulled out of
    :func:`write_wikidata_heads_of_state_government_observations` so
    the orchestrator stays short and so the test can mock the
    deletion step. The function deletes every row whose ``source_id``
    matches AND whose ``year`` is either in the supplied list OR is
    NULL (when the frame contains any year-NULL bindings).
    """
    existing_rows = (
        session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.year.in_(years)
                if years
                else SourceObservation.year.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if has_null_year:
        null_year_rows = (
            session.execute(
                select(SourceObservation).where(
                    SourceObservation.source_id == source_id,
                    SourceObservation.year.is_(None),
                )
            )
            .scalars()
            .all()
        )
        existing_rows = list(existing_rows) + list(null_year_rows)
    for row in existing_rows:
        session.delete(row)
    session.flush()


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_wikidata_heads_of_state_government_run_manifest(
    result,  # WikidataHoSGoGIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    indicators_cached: int = 0,
    indicators_fetched: int = 0,
    offices: tuple[str, ...] = (),
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, distinct country QIDs, distinct person
    QIDs, offices queried, requested year, cached-vs-fetched counts,
    the catalog path, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution without
    re-reading the parquet metadata.
    """
    out_dir = (
        manifest_dir
        or processed_dir(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        out_dir / "wikidata_heads_of_state_government_run_manifest.json"
    )
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "persons": result.persons,
        "years": list(result.years),
        "requested_year": (
            int(result.requested_year)
            if result.requested_year is not None
            else None
        ),
        "indicators": result.indicators,
        "indicators_cached": int(indicators_cached),
        "indicators_fetched": int(indicators_fetched),
        "offices": list(offices),
        "source_key": WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION,
        "sparql_endpoint": WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_URL,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
