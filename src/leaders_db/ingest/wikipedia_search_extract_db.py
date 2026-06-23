"""Stage 2 -- Wikipedia search-extract DB writes.

This module is the DB half of the Wikipedia search-extract adapter.
It owns:

- :func:`register_wikipedia_search_extract_source` -- upsert the
  ``sources`` row from the bundle's ``metadata.json``.
- :func:`write_wikipedia_search_extract_observations` -- write one
  ``source_observations`` row per (Action API row, matching catalog
  spec) pair. Idempotent: deletes existing rows for the matching
  variable_names before inserting.
- :func:`_delete_existing_observations` -- helper for the
  observations write, separated for testability.
- :func:`write_wikipedia_search_extract_run_manifest` -- write the
  audit-trail JSON next to the narrow parquet.

The pure helpers (bundle metadata reader, observation-row builder,
source-row-reference builder) live in
:mod:`leaders_db.ingest.wikipedia_search_extract_db_helpers`. The HTTP
+ cache I/O lives in
:mod:`leaders_db.ingest.wikipedia_search_extract_http`. The parser
lives in :mod:`leaders_db.ingest.wikipedia_search_extract_parse`. The
catalog + paths + parquet write live in
:mod:`leaders_db.ingest.wikipedia_search_extract_io`. The orchestrator
lives in :mod:`leaders_db.ingest.wikipedia_search_extract`.

Helper-blocked / needs downstream inputs (per the user's Stage 2
contract):

Wikipedia does not produce a Stage 2 evidence bundle without
explicit input terms -- the orchestrator's ``queries`` parameter is
the deterministic input interface. When the caller passes an empty
list the orchestrator raises ``ValueError`` (the Stage 2 contract
is "do not browse / score"). When the caller passes terms, the
adapter persists the verbatim API responses as
``source_observations`` rows; Stage 3 / Stage 4 resolve country /
leader from the persisted ``source_row_reference`` + ``raw_value``
audit trail.
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
from .wikipedia_search_extract_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _read_wikipedia_bundle_metadata,
)
from .wikipedia_search_extract_io import (
    _DEFAULT_CATALOG_PATH,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "register_wikipedia_search_extract_source",
    "write_wikipedia_search_extract_observations",
    "write_wikipedia_search_extract_run_manifest",
]

#: Module-level constant used by
#: :func:`register_wikipedia_search_extract_source` when the bundle
#: has no ``source_url`` field. Kept here (not in the io module)
#: because it is the Action API URL, not a catalog / data-lake
#: concept.
WIKIPEDIA_SEARCH_EXTRACT_SOURCE_URL: str = (
    "https://en.wikipedia.org/w/api.php"
)


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_wikipedia_search_extract_source(session: Session) -> int:
    """Upsert the Wikipedia search-extract source row into ``sources``.

    Keyed by
    ``(source_name='Wikipedia Action API (search + extract)',
    version='Action API')``. Idempotent: returns the same
    ``sources.id`` on every call. Reads the bundle's
    ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note`` (all optional).

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem / WDI / WHO GHO
    API / Wikidata).
    """
    source_name = "Wikipedia Action API (search + extract)"
    version = "Action API"

    bundle_meta = _read_wikipedia_bundle_metadata()
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
                or WIKIPEDIA_SEARCH_EXTRACT_SOURCE_URL
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or "CC BY-SA 4.0 (text of articles); Action API responses per wiki terms of use"
            ),
            download_date=download_date_value,
            coverage_start_year=None,
            coverage_end_year=None,
            notes=(
                "Stage 2 always-on helper adapter (Phase C). "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/"
                "wikipedia_search_extract.csv. See "
                "docs/sources/attributions.md for the exact "
                "attribution text. Wikipedia Action API is "
                "JSON-backed (no auth, public) with a mandatory "
                "descriptive User-Agent header per the Wikimedia "
                "User-Agent policy. The Stage 2 helper is a thin "
                "wrapper: the caller passes explicit queries; the "
                "adapter persists the verbatim Action API "
                "responses and does NOT browse, score, or do "
                "leader resolution. normalized_value is NULL at "
                "Stage 2 (the extract is text, not a number); "
                "country_id and leader_id are also NULL at Stage 2 "
                "-- Stage 3 / Stage 4 resolve them from the "
                "persisted source_row_reference + raw_value."
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


def write_wikipedia_search_extract_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (row, spec) pair.

    The ``df`` is the long-format frame returned by the parser (one
    row per Action API page / search hit). The function iterates the
    frame and emits one :class:`SourceObservation` row per row whose
    ``action`` matches a catalog spec's ``raw_column``.

    ``country_id``, ``leader_id``, and ``year`` are intentionally
    ``NULL`` (Wikipedia does not emit a year for ``extracts`` or
    ``search``; Stage 3 / Stage 4 resolve them downstream).
    ``normalized_value`` is ``NULL`` for every row because Wikipedia
    has no numeric value to normalize.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``variable_name`` is in the catalog's variable_names AND whose
    ``year IS NULL`` before inserting. The variable_name scope
    (rather than a per-year scope) is correct because the Action API
    does not return a year, so a re-run with the same queries must
    replace the previous run's rows entirely. Outside the
    catalog's variable_names, no rows are touched.

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_indicator_catalog(catalog_path=catalog_path)
    variable_names = [spec.variable_name for spec in specs]

    _delete_existing_observations(
        session, source_id, variable_names=variable_names,
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
    variable_names: list[str],
) -> None:
    """Delete existing ``source_observations`` rows for the catalog's variable_names.

    Pulled out of
    :func:`write_wikipedia_search_extract_observations` so the
    orchestrator stays short and so the test can mock the deletion
    step. The function deletes every row whose ``source_id``
    matches AND whose ``variable_name`` is in the supplied list AND
    whose ``year IS NULL`` (Wikipedia rows always have year=NULL).
    """
    if not variable_names:
        return
    existing_rows = (
        session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name.in_(variable_names),
                SourceObservation.year.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for row in existing_rows:
        session.delete(row)
    session.flush()


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_wikipedia_search_extract_run_manifest(
    result,  # WikipediaSearchExtractIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    indicators_cached: int = 0,
    indicators_fetched: int = 0,
    queries: tuple[str, ...] = (),
    actions: tuple[str, ...] = (),
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, distinct queries + actions, cached-vs-
    fetched counts, the catalog path, and the attribution. Written
    every run (not best-effort) so Stage 15 reports can find the
    attribution without re-reading the parquet metadata.
    """
    out_dir = (
        manifest_dir
        or processed_dir(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        out_dir / "wikipedia_search_extract_run_manifest.json"
    )
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "queries": list(queries),
        "actions": list(actions),
        "indicators": result.indicators,
        "indicators_cached": int(indicators_cached),
        "indicators_fetched": int(indicators_fetched),
        "source_key": WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION,
        "action_api_base": WIKIPEDIA_SEARCH_EXTRACT_SOURCE_URL,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path
