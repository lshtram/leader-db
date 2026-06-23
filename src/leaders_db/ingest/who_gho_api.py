"""Stage 2 -- WHO Global Health Observatory (GHO) OData API orchestrator.

WHO GHO is the social-wellbeing health sub-signal source for the
prototype. The API is a public OData 4.0 endpoint hosted on Azure
(``https://ghoapi.azureedge.net/api/``) with ~2000 indicators
including the headline ``WHOSIS_000001`` (life expectancy at
birth). The Stage 2 adapter narrows to the 5 in-scope indicators
in the ``social_wellbeing`` category defined in
``src/leaders_db/ingest/catalogs/who_gho_api.csv`` and pulls one
country-year observation per ``(country, year, indicator)``
triple.

The adapter is split across six modules for clarity:

- :mod:`leaders_db.ingest.who_gho_api_io` -- catalog, paths,
  parquet write, attribution constant.
- :mod:`leaders_db.ingest.who_gho_api_read` -- read
  orchestrator (cache-first, HTTP-fallback, long-to-wide
  pivot with raw-value column, year resolution).
- :mod:`leaders_db.ingest.who_gho_api_http` -- WHO GHO OData
  HTTP fetch, JSON cache I/O, retry policy, URL builder,
  response parser.
- :mod:`leaders_db.ingest.who_gho_api_db` -- source/observation
  DB writes, run manifest.
- :mod:`leaders_db.ingest.who_gho_api_db_helpers` -- pure
  helpers: value coercion, bundle metadata parser, observation
  row builder.
- :mod:`leaders_db.ingest.who_gho_api_result` --
  :class:`WhoGhoApiIngestResult`.
- :mod:`leaders_db.ingest.who_gho_api` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/who_gho_api.csv`` (the single
   source of truth for which WHO GHO API indicators are read).
2. Read the wide-format frame via :func:`read_who_gho_api` -- one
   HTTP call per uncached ``(indicator, year)`` pair, pivot
   long to wide, filter to country-level records.
3. Write a narrow
   ``data/processed/who_gho_api/who_gho_api_country_year.parquet``
   with the WHO GHO API attribution in the file-level metadata.
4. Upsert the WHO GHO API source row into the ``sources``
   provenance table.
5. Write one ``source_observations`` row per
   ``(iso3, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it in.
   ``source_row_reference`` carries
   ``"who_gho_api:<raw_column>:<iso3>"`` so Stage 3 can resolve
   it and the audit trail identifies the WHO GHO API indicator
   code + ISO3.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/sources/attributions.md``; the
:func:`test_who_gho_api_attribution_matches_attributions_doc`
test enforces that the code and the doc are byte-for-byte
consistent.

API-backed sources (per the Phase B vetting report) are permitted
in the data lake; a local raw cache under
``data/raw/who_gho_api/cache/`` records every fetched response
verbatim so a re-run with the same year + indicators makes zero
HTTP calls. Tests use fixtures under
``tests/fixtures/who_gho_api/cache/`` and never touch the
network.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field  # noqa: F401  (re-exported via __all__)

from ..db.session import session_scope
from .who_gho_api_db import (
    register_who_gho_api_source,
    write_who_gho_api_observations,
    write_who_gho_api_run_manifest,
)
from .who_gho_api_io import (
    WHO_GHO_API_ATTRIBUTION,
    WHO_GHO_API_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    write_who_gho_api_parquet,
)
from .who_gho_api_read import read_who_gho_api
from .who_gho_api_result import WhoGhoApiIngestResult

# Re-exports: ``WHO_GHO_API_ATTRIBUTION``, ``WHO_GHO_API_SOURCE_KEY``,
# and ``IndicatorSpec`` are defined in ``who_gho_api_io`` (the
# lowest-level module that does NOT import from siblings) to break
# the import cycle, but callers (tests, the CLI) historically
# import them from here. Re-export so the public surface stays in
# one place. The DB helpers and the read orchestrator are also
# re-exported so the test-builder's tests can call them through
# the orchestrator module -- the WDI / WGI / UCDP / SIPRI / PTS /
# UNDP HDI pattern.

__all__ = [
    "WHO_GHO_API_ATTRIBUTION",
    "WHO_GHO_API_SOURCE_KEY",
    "IndicatorSpec",
    "WhoGhoApiIngestResult",
    "attribution",
    "ingest_who_gho_api",
    "load_indicator_catalog",
    "read_who_gho_api",
    "register_who_gho_api_source",
    "write_who_gho_api_observations",
    "write_who_gho_api_parquet",
    "write_who_gho_api_run_manifest",
]


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the WHO GHO API attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage
    15 report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches WHO GHO API data must include
    this block verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return WHO_GHO_API_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_who_gho_api(
    *,
    year: int | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> WhoGhoApiIngestResult:
    """Run Stage 2 for the WHO GHO API end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_who_gho_api`.
       One HTTP call per uncached indicator; cached files are
       read directly.
    3. Write the narrow parquet under
       ``data/processed/who_gho_api/`` and attach the WHO GHO API
       attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort --
       it is the audit trail for ``processed/``).
    6. Returns a :class:`WhoGhoApiIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source who_gho_api`` and
    the tests call it.

    Args:
        year: filter to a single year (e.g. ``2023``). The WHO
            GHO API Stage 2 reader is a single-year reader; the
            prototype's CLI always passes the resolved
            ``RunConfig.project.target_year`` (2023 by default).
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in catalog.
        cache_dir: override the JSON cache root. Default:
            data-lake path (``data/raw/who_gho_api/cache/``).
        force_refresh: re-download even when the cache file
            exists.
        request_timeout: per-request HTTP timeout in seconds.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The
        CLI runs against the production DB; tests run against the
        isolated test DB set up by the ``isolated_data_lake``
        fixture. No explicit ``database_url`` kwarg is needed.

    Notes on year coverage:
        The WHO GHO API is updated on a per-indicator basis;
        some indicators carry 2023 data, others only through
        2021. If a caller asks for a year with no data the result
        is an empty Stage 2 frame (no observations, no error).
        The orchestrator does not invent values and does not
        silently proxy to an earlier year -- Stage 11
        confidence penalises ``not_available`` cells and the
        downstream scorer decides how to handle them.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_who_gho_api(
        year=year,
        catalog_path=catalog_path,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )
    parquet = write_who_gho_api_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_who_gho_api_source(session)
        rows = write_who_gho_api_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    # Pull the cached/fetched counts that read_who_gho_api attached
    # to the frame's attrs. Default to 0 if read_who_gho_api did
    # not populate them (e.g. a future caller bypasses the
    # orchestrator and constructs a DataFrame from scratch).
    indicators_cached = int(df.attrs.get("indicators_cached", 0))
    indicators_fetched = int(df.attrs.get("indicators_fetched", 0))

    result = WhoGhoApiIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["iso3"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_who_gho_api_run_manifest(
        result,
        catalog_path=catalog_path,
        indicators_cached=indicators_cached,
        indicators_fetched=indicators_fetched,
    )
    return result
