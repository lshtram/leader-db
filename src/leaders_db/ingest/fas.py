"""Stage 2 -- FAS Nuclear Notebook orchestrator (REQ-SRC-008).

The FAS (Federation of American Scientists) Nuclear Notebook is
the second source for the ``nuclear`` category in the prototype,
complementing the SIPRI Yearbook Ch.7 PDF. The FAS public "Status
of World Nuclear Forces" page
(https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html)
contains a single parseable HTML table with all 9 nuclear-armed
states and 5 numeric columns (Operational Strategic, Operational
Nonstrategic, Reserve/Nondeployed, Military Stockpile, Total
Inventory). The page is updated "continuously" per FAS's promise
but as of probe (2026-06-19) the consolidated snapshot is dated
April 30, 2014. The Stage 2 adapter ingests the snapshot year as
documented in the page's metadata; the snapshot year is recorded
in the run manifest as the freshness stamp. Stage 11 confidence
penalises the temporal-fit gap between the FAS snapshot year and
the prototype's target year (2023).

The adapter is split across six modules for clarity (each under
the 400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.fas_io` -- catalog, paths, parquet
  write, attribution constant, FAS status page URL.
- :mod:`leaders_db.ingest.fas_http` -- HTTP + HTML cache I/O,
  retry policy, fetch helper.
- :mod:`leaders_db.ingest.fas_html` -- HTML table parser
  (response-shape -> wide DataFrame; sentinel handling; snapshot
  year extraction from meta date).
- :mod:`leaders_db.ingest.fas_db_helpers` -- pure helpers: value
  coercion, bundle metadata parser, observation row builder.
- :mod:`leaders_db.ingest.fas_db` -- source / observation DB
  writes, run manifest.
- :mod:`leaders_db.ingest.fas_result` -- :class:`FasIngestResult`.
- :mod:`leaders_db.ingest.fas` (this) -- public orchestrator,
  :func:`attribution` helper, and re-exports.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/fas.csv`` (the single source
   of truth for which FAS indicators are read).
2. Read the wide-format frame via
   :func:`read_fas_status_html` -- one HTTP call per uncached
   run, the verbatim HTML is parsed into a 9-country x
   5-indicator wide frame.
3. Write a narrow
   ``data/processed/fas/fas_country_year.parquet`` with the FAS
   attribution in the file-level metadata.
4. Upsert the FAS source row into the ``sources`` provenance
   table. Keyed by
   ``(source_name='Federation of American Scientists Nuclear
   Notebook', version='consolidated status table')``.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it (the FAS table
   uses country names, not ISO3).
   ``source_row_reference`` carries
   ``"fas:<raw_column>:<country>"`` so Stage 3 can resolve it
   and the audit trail identifies both the indicator and the
   country.
6. Write the run-manifest JSON as the audit trail, including
   the ``snapshot_year`` parsed from the page's meta date.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/source-attributions.md`; the
:func:`test_fas_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .fas_db import (
    register_fas_source,
    write_fas_observations,
    write_fas_run_manifest,
)
from .fas_html import read_fas_status_html
from .fas_http import fetch_fas_status_html
from .fas_io import (
    FAS_ATTRIBUTION,
    FAS_PUBLISHER_URL,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
    IndicatorSpec,
    default_html_path,
    default_processed_parquet_path,
    load_indicator_catalog,
    write_fas_parquet,
)
from .fas_result import FasIngestResult

# Re-exports: ``FAS_ATTRIBUTION``, ``FAS_PUBLISHER_URL``,
# ``FAS_SOURCE_KEY``, ``FAS_STATUS_PAGE_URL``, and
# ``IndicatorSpec`` are defined in ``fas_io`` (the lowest-level
# module that does NOT import from siblings) to break the import
# cycle, but callers (tests, the CLI) historically import them
# from here. Re-export so the public surface stays in one place.
# The path helpers (``default_html_path``,
# ``default_processed_parquet_path``), the parquet writer
# (``write_fas_parquet``), the HTML reader
# (``read_fas_status_html``), the HTTP fetch helper
# (``fetch_fas_status_html``), and the DB writers
# (``register_fas_source``, ``write_fas_observations``,
# ``write_fas_run_manifest``) are also re-exported so the
# test-builder's tests can call them through the orchestrator
# module -- the WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook
# Ch.7 / PTS / UNDP HDI / WHO GHO API / Transparency International
# CPI / CIRIGHTS / BTI / RSF pattern.


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the FAS Nuclear Notebook attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage
    15 report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches FAS data must include this
    block verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return FAS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_fas(
    *,
    year: int | None = None,  # ignored -- FAS is a single-snapshot source
    html_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
    snapshot_year: int | None = None,
) -> FasIngestResult:
    """Run Stage 2 for the FAS Nuclear Notebook end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via
       :func:`read_fas_status_html`. One HTTP call per uncached
       run (the HTML is fetched from the FAS status page);
       cached files are read directly.
    3. Write the narrow parquet under ``data/processed/fas/``
       and attach the FAS attribution to the parquet's
       file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort --
       it is the audit trail for ``processed/``).
    6. Returns a :class:`FasIngestResult` summary.

    The function is the single public entry point -- both the
    CLI command ``leaders-db ingest-source --source fas`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: accepted for CLI compatibility (the
            ``leaders-db ingest-source --source fas --year
            <year>`` command passes the config's target year);
            **ignored**. The FAS consolidated status page is a
            single-snapshot source; the snapshot year is
            parsed from the page's ``<meta name="date">``
            element (or the page footer text) and recorded in
            the run manifest. To override the snapshot year
            programmatically, pass ``snapshot_year=<int>``.
        html_path: override the raw HTML cache path. Default:
            data-lake path (``data/raw/fas/``).
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        force_refresh: re-download even when the cache file
            exists.
        request_timeout: per-request HTTP timeout in seconds.
        snapshot_year: override the parsed snapshot year.
            Default: parse from the page's meta date element.

    Notes:
        The FAS status page (live as of probe 2026-06-19) has a
        snapshot year of 2014 per the meta date element. Stage
        11 confidence penalises the temporal-fit gap between
        this snapshot year and the prototype's target year
        (2023). This is a known limitation; it is not a
        blocker for the integrity of the data (the snapshot
        values are the authoritative FAS estimates for that
        year).
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)

    cache_html_path = html_path or default_html_path()
    html, came_from_cache = fetch_fas_status_html(
        cache_path=cache_html_path,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )
    df, parsed_snapshot_year = read_fas_status_html(
        html,
        catalog=specs,
        snapshot_year=snapshot_year,
    )
    parquet = write_fas_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_fas_source(session)
        rows = write_fas_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    result = FasIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        snapshot_year=int(parsed_snapshot_year),
        html_cached=came_from_cache,
        html_fetched=not came_from_cache,
        status_page_url=FAS_STATUS_PAGE_URL,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative;
    # the manifest is how downstream stages find it without
    # re-reading the parquet metadata.
    write_fas_run_manifest(
        result,
        catalog_path=catalog_path,
        snapshot_year=parsed_snapshot_year,
        html_cached=came_from_cache,
        html_fetched=not came_from_cache,
        status_page_url=FAS_STATUS_PAGE_URL,
    )
    return result


# Public surface: ``FAS_ATTRIBUTION``, ``FAS_PUBLISHER_URL``,
# ``FAS_SOURCE_KEY``, ``FAS_STATUS_PAGE_URL``, and
# ``IndicatorSpec`` are defined in ``fas_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top
# of this file make them importable from the canonical
# orchestrator path; this ``__all__`` documents the full public
# surface.
__all__ = [
    "FAS_ATTRIBUTION",
    "FAS_PUBLISHER_URL",
    "FAS_SOURCE_KEY",
    "FAS_STATUS_PAGE_URL",
    "FasIngestResult",
    "IndicatorSpec",
    "attribution",
    "default_html_path",
    "default_processed_parquet_path",
    "ingest_fas",
    "load_indicator_catalog",
    "read_fas_status_html",
    "register_fas_source",
    "write_fas_observations",
    "write_fas_parquet",
    "write_fas_run_manifest",
]
