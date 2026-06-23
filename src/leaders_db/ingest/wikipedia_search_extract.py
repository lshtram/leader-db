"""Stage 2 -- Wikipedia Action API (search + extract) orchestrator.

Wikipedia search-extract is the **always-on narrative-context helper**
for the prototype. The source is the public Wikipedia Action API
(``https://en.wikipedia.org/w/api.php``, CC BY-SA 4.0) and the
adapter persists the verbatim API response as the
``source_observations.raw_value`` audit trail.

The adapter is split across small modules.

``wikipedia_search_extract.py`` remains the public orchestrator and
re-export surface, while helper modules keep the documented line
caps enforceable:

- :mod:`leaders_db.ingest.wikipedia_search_extract_io` -- catalog,
  path helpers, attribution constant, parquet write.
- :mod:`leaders_db.ingest.wikipedia_search_extract_http` -- Action
  API endpoint, cache I/O, retry policy, URL builder for the
  ``extracts`` and ``search`` actions.
- :mod:`leaders_db.ingest.wikipedia_search_extract_parse` -- Action
  API JSON -> long-format DataFrame parser for ``extracts`` and
  ``search``.
- :mod:`leaders_db.ingest.wikipedia_search_extract_read` -- read
  orchestrator (cache-first, HTTP-fallback, one Action API request
  per (query, action) pair).
- :mod:`leaders_db.ingest.wikipedia_search_extract_db` -- source /
  observation DB writes + run manifest.
- :mod:`leaders_db.ingest.wikipedia_search_extract_db_helpers` --
  bundle metadata reader + observation-row builder.
- :mod:`leaders_db.ingest.wikipedia_search_extract_result` --
  :class:`WikipediaSearchExtractIngestResult`.
- :mod:`leaders_db.ingest.wikipedia_search_extract` (this) --
  public orchestrator, :func:`attribution` helper, and re-exports.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/wikipedia_search_extract.csv``
   (the single source of truth for which Wikipedia Action API
   actions are called).
2. Read the long-format frame via
   :func:`read_wikipedia_search_extract` -- one Action API request
   per (query, action) pair, cache-first, HTTP fallback, parse the
   JSON.
3. Write a long-format
   ``data/processed/wikipedia_search_extract/wikipedia_search_extract_observations.parquet``
   with the Wikipedia attribution in the file-level metadata.
4. Upsert the Wikipedia source row into the ``sources`` provenance
   table.
5. Write one ``source_observations`` row per (Action API row,
   matching catalog spec) pair. ``country_id`` and ``leader_id``
   are left ``NULL`` (Stage 3 + Stage 4 fill them). ``year`` is
   ``NULL`` (the Action API does not return a year for ``extracts``
   or ``search``). ``normalized_value`` is ``NULL`` (Wikipedia is a
   narrative-context source; the "value" is text, not a number).
   ``source_row_reference`` carries the variable_name + pageid + title
   so Stage 3 / Stage 4 can resolve the observation.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it with the same
``queries`` deletes and re-inserts the ``source_observations`` rows
for the matching ``variable_name`` values (Wikipedia rows always
have ``year=NULL``).

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/sources/attributions.md``; the
:func:`test_wikipedia_search_extract_attribution_matches_attributions_doc`
test enforces byte-for-byte consistency.

Helper-blocked / needs downstream inputs (per the user's Stage 2
contract):

The orchestrator's ``queries`` parameter is the deterministic
input interface -- the adapter does NOT browse Wikipedia to
discover leaders, and does NOT do leader resolution. The orchestrator
raises ``ValueError`` when ``queries`` is ``None`` or empty (the
Stage 2 contract is "do not browse / score"). When ``queries`` is
supplied, the adapter persists the verbatim API responses as
``source_observations`` rows; Stage 3 / Stage 4 resolve country /
leader from the persisted ``source_row_reference`` + ``raw_value``
audit trail.

API-backed sources (per the source-vetting report) are permitted in
the data lake; a local raw cache under
``data/raw/wikipedia_search_extract/cache/`` records every fetched
response verbatim so a re-run with the same parameters makes zero
HTTP calls. Tests use fixtures under
``tests/fixtures/wikipedia_search_extract/cache/`` and never touch
the network.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .wikipedia_search_extract_db import (
    register_wikipedia_search_extract_source,
    write_wikipedia_search_extract_observations,
    write_wikipedia_search_extract_run_manifest,
)
from .wikipedia_search_extract_io import (
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    write_wikipedia_search_extract_parquet,
)
from .wikipedia_search_extract_read import (
    read_wikipedia_search_extract,
)
from .wikipedia_search_extract_result import (
    WikipediaSearchExtractIngestResult,
)

# Re-exports: ``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION``,
# ``WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY``, and ``IndicatorSpec`` are
# defined in ``wikipedia_search_extract_io`` (the lowest-level module
# that does NOT import from siblings) to break the import cycle,
# but callers (tests, the CLI) historically import them from here.
# Re-export so the public surface stays in one place. The DB helpers
# and the read orchestrator are also re-exported so the test-builder's
# tests can call them through the orchestrator module -- the V-Dem
# / WDI / WHO GHO API / Wikidata pattern.

__all__ = [
    "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION",
    "WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY",
    "IndicatorSpec",
    "WikipediaSearchExtractIngestResult",
    "attribution",
    "ingest_wikipedia_search_extract",
    "load_indicator_catalog",
    "read_wikipedia_search_extract",
    "register_wikipedia_search_extract_source",
    "write_wikipedia_search_extract_observations",
    "write_wikipedia_search_extract_parquet",
    "write_wikipedia_search_extract_run_manifest",
]


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the Wikipedia attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches Wikipedia data must include this
    block verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_wikipedia_search_extract(
    *,
    queries: list[str] | None = None,
    actions: list[str] | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
    search_limit: int = 10,
) -> WikipediaSearchExtractIngestResult:
    """Run Stage 2 for the Wikipedia Action API end-to-end.

    Steps (each idempotent):

    1. Validate the explicit ``queries`` list (the Stage 2 contract
       is "do not browse / score"; the adapter requires explicit
       input terms).
    2. Read the long-format frame via
       :func:`read_wikipedia_search_extract`. One Action API
       request per (query, action) pair; cached files are read
       directly.
    3. Write the long parquet under
       ``data/processed/wikipedia_search_extract/`` and attach the
       Wikipedia attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort -- it
       is the audit trail for ``processed/``).
    6. Return a :class:`WikipediaSearchExtractIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source
    wikipedia_search_extract`` and the tests call it.

    Args:
        queries: explicit list of query / title strings to send to
            the Action API. ``None`` or an empty list raises
            ``ValueError``. The orchestrator passes the list through
            verbatim to the reader.
        actions: optional list of action names to scope the call.
            Default: every action in the catalog.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        cache_dir: override the JSON cache root. Default:
            data-lake path.
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.
        search_limit: per-request ``srlimit`` for the ``search``
            action (1..50 per the API docs; default 10).

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the
        isolated test DB set up by the ``isolated_data_lake``
        fixture. No explicit ``database_url`` kwarg is needed.

    Helper-blocked / needs downstream inputs (per the user's Stage 2
    contract):

    When ``queries`` is ``None`` or empty, the orchestrator raises
    ``ValueError`` and does NOT write any DB rows or parquet. This
    is the Stage 2 contract: the helper does not browse / score.
    Stage 3 / Stage 4 resolve country / leader from the persisted
    ``source_row_reference`` + ``raw_value`` audit trail.
    """
    if not queries:
        # Surface the helper-blocked condition explicitly (do not
        # silently write a 0-row parquet -- the caller should know
        # they passed an invalid input).
        raise ValueError(
            "ingest_wikipedia_search_extract requires an explicit "
            "queries= list (the Stage 2 contract is 'do not browse / "
            "score'; the helper needs explicit input terms)."
        )

    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_wikipedia_search_extract(
        queries=list(queries),
        actions=list(actions) if actions is not None else None,
        catalog_path=catalog_path,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
        search_limit=search_limit,
    )
    parquet = write_wikipedia_search_extract_parquet(
        df, parquet_path=parquet_path,
    )

    with session_scope() as session:
        source_id = register_wikipedia_search_extract_source(session)
        rows = write_wikipedia_search_extract_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    # Pull the cached/fetched counts that
    # ``read_wikipedia_search_extract`` attached to the frame's
    # attrs. Default to 0 if the reader did not populate them
    # (e.g. a future caller bypasses the orchestrator and
    # constructs a DataFrame from scratch).
    indicators_cached = int(df.attrs.get("indicators_cached", 0))
    indicators_fetched = int(df.attrs.get("indicators_fetched", 0))

    result = WikipediaSearchExtractIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        queries=tuple(queries),
        indicators=len(specs),
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
    )

    effective_actions = tuple(
        spec.raw_column for spec in specs
        if actions is None or spec.raw_column in actions
    )
    write_wikipedia_search_extract_run_manifest(
        result,
        catalog_path=catalog_path,
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
        queries=tuple(queries),
        actions=effective_actions,
    )
    return result
