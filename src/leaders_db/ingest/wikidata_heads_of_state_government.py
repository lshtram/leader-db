"""Stage 2 -- Wikidata WikiProject Heads of state and government orchestrator.

Wikidata heads-of-state-and-government is the **always-on leader-
identity helper** for the prototype. The source is the public
Wikidata SPARQL endpoint (``https://query.wikidata.org/sparql``,
CC0 1.0) and the adapter persists the verbatim API response as the
``source_observations.raw_value`` audit trail.

The adapter is split across small modules. ``wikidata_heads_of_state_government.py``
remains the public orchestrator and re-export surface, while helper
modules keep the documented line caps enforceable:

- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_io` --
  catalog, path helpers, attribution constant, parquet write.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_http` --
  SPARQL endpoint, cache I/O, retry policy, URL builder.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_parse` --
  canonical SPARQL query builder + JSON bindings parser.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_read` --
  read orchestrator (cache-first, HTTP-fallback, single-SPARQL-
  query per (year, country_qids) parameter set).
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_db` --
  source / observation DB writes + run manifest.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_db_helpers` --
  bundle metadata reader + observation-row builder.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_result` --
  :class:`WikidataHoSGoGIngestResult`.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government` (this) --
  public orchestrator, :func:`attribution` helper, and re-exports.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/wikidata_heads_of_state_government.csv``
   (the single source of truth for which Wikidata office QIDs are
   read).
2. Read the long-format frame via
   :func:`read_wikidata_heads_of_state_government` -- one SPARQL
   query per (year, country_qids) parameter set, cache-first, HTTP
   fallback, parse the bindings.
3. Write a long-format
   ``data/processed/wikidata_heads_of_state_government/wikidata_heads_of_state_government_country_year.parquet``
   with the Wikidata attribution in the file-level metadata.
4. Upsert the Wikidata source row into the ``sources`` provenance
   table.
5. Write one ``source_observations`` row per (binding, matching
   catalog spec) pair. ``country_id`` and ``leader_id`` are left
   ``NULL`` (Stage 3 + Stage 4 fill them). ``normalized_value`` is
   ``NULL`` (Wikidata is a leader-reference source; the "value" is a
   QID, not a number). ``source_row_reference`` carries the QID +
   statement hash so Stage 3 / Stage 4 can resolve the observation.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/sources/attributions.md``; the
:func:`test_wikidata_heads_of_state_government_attribution_matches_attributions_doc`
test enforces byte-for-byte consistency.

API-backed sources (per the source-vetting report) are permitted in
the data lake; a local raw cache under
``data/raw/wikidata_heads_of_state_government/cache/`` records every
fetched response verbatim so a re-run with the same parameters
makes zero HTTP calls. Tests use fixtures under
``tests/fixtures/wikidata_heads_of_state_government/cache/`` and never
touch the network.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .wikidata_heads_of_state_government_db import (
    register_wikidata_heads_of_state_government_source,
    write_wikidata_heads_of_state_government_observations,
    write_wikidata_heads_of_state_government_run_manifest,
)
from .wikidata_heads_of_state_government_io import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    write_wikidata_heads_of_state_government_parquet,
)
from .wikidata_heads_of_state_government_read import (
    read_wikidata_heads_of_state_government,
)
from .wikidata_heads_of_state_government_result import (
    WikidataHoSGoGIngestResult,
)

# Re-exports: ``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION``,
# ``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``wikidata_heads_of_state_government_io``
# (the lowest-level module that does NOT import from siblings) to
# break the import cycle, but callers (tests, the CLI) historically
# import them from here. Re-export so the public surface stays in
# one place. The DB helpers and the read orchestrator are also
# re-exported so the test-builder's tests can call them through the
# orchestrator module -- the V-Dem / WDI / WHO GHO API pattern.

__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY",
    "IndicatorSpec",
    "WikidataHoSGoGIngestResult",
    "attribution",
    "ingest_wikidata_heads_of_state_government",
    "load_indicator_catalog",
    "read_wikidata_heads_of_state_government",
    "register_wikidata_heads_of_state_government_source",
    "write_wikidata_heads_of_state_government_observations",
    "write_wikidata_heads_of_state_government_parquet",
    "write_wikidata_heads_of_state_government_run_manifest",
]


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the Wikidata attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches Wikidata data must include this
    block verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_wikidata_heads_of_state_government(
    *,
    year: int | None = None,
    country_qids: list[str] | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 60.0,
) -> WikidataHoSGoGIngestResult:
    """Run Stage 2 for Wikidata heads-of-state-and-government end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the long-format frame via
       :func:`read_wikidata_heads_of_state_government`. One SPARQL
       query per (year, country_qids) parameter set; cached files
       are read directly.
    3. Write the long parquet under
       ``data/processed/wikidata_heads_of_state_government/`` and
       attach the Wikidata attribution to the parquet's file-level
       metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort -- it
       is the audit trail for ``processed/``).
    6. Return a :class:`WikidataHoSGoGIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source
    wikidata_heads_of_state_government`` and the tests call it.

    Args:
        year: filter to a single calendar year (e.g. ``2023``).
            ``None`` (the default) returns all current holders (no
            end date) for every catalog office.
        country_qids: optional list of Wikidata country QIDs to
            scope the query. ``None`` (the default) returns holders
            for every country.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        cache_dir: override the JSON cache root. Default:
            data-lake path.
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the
        isolated test DB set up by the ``isolated_data_lake``
        fixture. No explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_wikidata_heads_of_state_government(
        year=year,
        country_qids=country_qids,
        catalog_path=catalog_path,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )
    parquet = write_wikidata_heads_of_state_government_parquet(
        df, parquet_path=parquet_path,
    )

    with session_scope() as session:
        source_id = (
            register_wikidata_heads_of_state_government_source(session)
        )
        rows = write_wikidata_heads_of_state_government_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    # Pull the cached/fetched counts that
    # ``read_wikidata_heads_of_state_government`` attached to the
    # frame's attrs. Default to 0 if the reader did not populate
    # them (e.g. a future caller bypasses the orchestrator and
    # constructs a DataFrame from scratch).
    indicators_cached = int(df.attrs.get("indicators_cached", 0))
    indicators_fetched = int(df.attrs.get("indicators_fetched", 0))

    # Distinct QID counts for the audit-trail result fields.
    if not df.empty:
        countries = int(df["country_qid"].dropna().astype(str).nunique())
        persons = int(df["person_qid"].dropna().astype(str).nunique())
        years = tuple(
            sorted(
                {
                    int(y)
                    for y in df["year"].dropna().tolist()
                    if _notna_int(y)
                }
            )
        )
    else:
        countries = 0
        persons = 0
        years = ()

    result = WikidataHoSGoGIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=countries,
        persons=persons,
        years=years,
        requested_year=year,
        indicators=len(specs),
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
    )

    offices = tuple(spec.raw_column for spec in specs)
    write_wikidata_heads_of_state_government_run_manifest(
        result,
        catalog_path=catalog_path,
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
        offices=offices,
    )
    return result


def _notna_int(value: object) -> bool:
    """Return ``True`` when ``value`` is a non-NaN integer.

    Defensive helper for the orchestrator's ``years`` tuple
    computation: a ``year`` cell may be ``None`` (no start-date
    qualifier), ``pd.NA``, ``numpy.nan``, or a real int. We
    want only the real int values. Underscore-prefixed because it
    is private to the orchestrator (not part of the public
    surface).
    """
    if value is None:
        return False
    try:
        # NaN-safe int conversion: ``int(float('nan'))`` raises
        # ``ValueError`` so we keep the try/except for safety.
        return int(value) >= 0
    except (TypeError, ValueError):
        return False
