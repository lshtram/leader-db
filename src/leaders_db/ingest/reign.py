"""Stage 2 -- REIGN (Bell 2016) orchestrator.

REIGN (Rulers, Elections, and Irregular Governance) is the
**leader-month** historical leader-identity source for the
prototype. The dataset is a single GitHub-hosted CSV
(``REIGN_2021_8.csv``, 34.4 MB, 138,600 leader-month rows x 41
columns x 200 country-codes, coverage 1950-2021-08) hosted by
OEF Research on GitHub. The Stage 2 adapter narrows the 41
columns to the 8 identity / governance columns documented in
:file:`src/leaders_db/ingest/catalogs/reign.csv`:

- ``leader`` (text)
- ``government`` (text regime-type label)
- ``elected`` (0/1)
- ``age`` (years; float)
- ``male`` (0/1; light-coerced to 1/2)
- ``tenure_months`` (months; float)
- ``political_violence`` (continuous; float)
- ``irregular`` (continuous; float)

The adapter is split across small modules. ``reign.py`` remains
the public orchestrator and re-export surface, while helper
modules keep the documented line caps enforceable:

- :mod:`leaders_db.ingest.reign_io` -- catalog, path helpers,
  read orchestrator, parquet write, named constants,
  :class:`IndicatorSpec`, :func:`safe_country_token`.
- :mod:`leaders_db.ingest.reign_csv` -- CSV read with pandas,
  per-cell coercion, gender -> 1/2 coercion, numeric -> float
  coercion.
- :mod:`leaders_db.ingest.reign_db` -- sources upsert,
  source_observations writes, run-manifest writer.
- :mod:`leaders_db.ingest.reign_db_helpers` -- pure helpers:
  bundle metadata reader, value coercion, observation-row
  builder.
- :mod:`leaders_db.ingest.reign_result` --
  :class:`ReignIngestResult`.
- :mod:`leaders_db.ingest.reign` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

REIGN is structurally distinct from every prior Stage 2 adapter:

- It is the first Stage 2 source that reads a **GitHub raw CSV**
  (UTF-8, comma-delimited, no special parameters; the live
  bundle is 34.4 MB and takes ~1.5 s to read with pandas).
- The natural unit of observation is **leader-month** (1 row per
  (country, year, month) for 138,600 rows), NOT country-year.
  The Stage 2 adapter writes one ``source_observations`` row
  per (leader-month-row, identity-column) pair, keyed by the
  row's ``year`` column. The ``month`` column is preserved in
  ``source_row_reference`` (e.g.
  ``reign:USA:Truman:1950:1:leader``) so the audit trail
  identifies the specific month.
- The Stage 4 leader resolver (not implemented in this phase)
  will join REIGN with Archigos, Leader Survival, Wikidata, and
  the client bundle. ``country_id`` / ``leader_id`` are left
  ``NULL`` in this phase.
- REIGN is the first Stage 2 adapter that uses the country
  display name URL-safe substitution helper
  (:func:`reign_io.safe_country_token`) for the
  ``source_row_reference`` audit suffix (the country column
  carries display names like ``"Trinidad & Tobago"`` that need
  URL-safe substitution).

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/reign.csv`` (the single
   source of truth for which REIGN columns are read).
2. Read the wide CSV via :func:`reign_io.read_reign`. One
   ``pandas.read_csv`` call; narrow to the 8 catalog
   ``raw_column`` s + the 4 audit columns (``ccode``,
   ``country``, ``year``, ``month``); pivot wide -> long. The
   long frame carries the per-cell coercion (text preserved
   verbatim, numerics -> float, gender -> 1/2).
3. Optionally filter to a single year.
4. Write the narrow long-format parquet under
   ``data/processed/reign/`` with the REIGN attribution
   attached to the file-level metadata.
5. Upsert the REIGN source row into the ``sources``
   provenance table. Keyed by
   ``(source_name='REIGN (Rulers, Elections, and Irregular
   Governance)', version='2021-8')``.
6. Write one ``source_observations`` row per long-format row.
   ``country_id`` is left ``NULL``; ``leader_id`` is left
   ``NULL``; ``source_row_reference`` carries
   ``reign:<country_token>:<leader_token>:<year>:<month>:<raw_column>``
   (e.g. ``reign:USA:Truman:1950:1:leader``). ``confidence`` is
   left ``NULL``.
7. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
year(s) only.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/sources/attributions.md``; the
:func:`test_reign_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .reign_csv import read_reign_csv_to_long_dataframe
from .reign_db import (
    register_reign_source,
    write_reign_observations,
    write_reign_run_manifest,
)
from .reign_io import (
    REIGN_ATTRIBUTION,
    REIGN_IDENTITY_RAW_COLUMNS,
    REIGN_SOURCE_KEY,
    REIGN_YEAR_END,
    REIGN_YEAR_START,
    IndicatorSpec,
    default_csv_path,
    default_processed_parquet_path,
    load_reign_catalog,
    read_reign,
    safe_country_token,
    write_reign_parquet,
)
from .reign_result import ReignIngestResult

# Re-exports: ``REIGN_ATTRIBUTION``, ``REIGN_SOURCE_KEY``, the
# year-window constants, and :class:`IndicatorSpec` are defined in
# ``reign_io`` (the lowest-level module) to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The
# path helpers, the read orchestrator, the parquet writer, the CSV
# reader, and the DB helpers are also re-exported so the test-
# builder's tests can drive the adapter through the orchestrator
# module (the V-Dem / CIRIGHTS / WGI / UCDP / SIPRI milex / SIPRI
# Yearbook Ch.7 / PTS / UNDP HDI / WHO GHO API / Archigos
# pattern).


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the REIGN attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches REIGN data must include this block
    verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return REIGN_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_reign(
    *,
    year: int | None = None,
    csv_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> ReignIngestResult:
    """Run Stage 2 for REIGN end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide CSV via :func:`reign_io.read_reign`. One
       ``pandas.read_csv`` call; narrow to the 8 catalog
       ``raw_column`` s + the 4 audit columns; pivot wide ->
       long. The long frame carries the per-cell coercion
       (text preserved verbatim, numerics -> float, gender ->
       1/2).
    3. Optionally filter to a single year.
    4. Write the narrow long-format parquet under
       ``data/processed/reign/`` with the REIGN attribution
       attached to the file-level metadata.
    5. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    6. Build the :class:`ReignIngestResult` and write the run
       manifest. The manifest records the ``year_window`` tuple
       (min/max year in the long frame) and the attribution.
    7. Return the result.

    **Year semantics.** The Stage 2 adapter writes observations
    keyed by the leader-month row's ``year`` column. The
    ``month`` column is preserved in ``source_row_reference``
    (e.g. ``reign:USA:Truman:1950:1:leader``) so the audit
    trail identifies the specific month. REIGN data ends
    2021-08 (per the live CSV and the bundle metadata); the
    prototype target year 2023 has no REIGN data (~16-month
    gap per the source-vetting report §3.1).

    The function is the single public entry point -- both the
    CLI command ``leaders-db ingest-source --source reign`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2020`` for all
            REIGN leader-month rows in 2020). Default: all
            138,600 leader-month rows.
        csv_path: override the input CSV. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_reign_catalog(catalog_path=catalog_path)

    actual_csv_path = csv_path or default_csv_path()
    df = read_reign(
        csv_path=actual_csv_path, year=year, catalog_path=catalog_path,
    )

    # Compute the audit-trail extras from the long frame. The
    # ``year_window`` tuple is the (min, max) year in the long
    # frame. The ``years`` tuple is the sorted set of distinct
    # years.
    if not df.empty:
        year_window_tuple: tuple[int, int] = (
            int(df["year"].min()),
            int(df["year"].max()),
        )
        years_sorted = tuple(
            sorted({int(y) for y in df["year"].tolist()}),
        )
        countries = int(df["country"].nunique())
    else:
        year_window_tuple = (0, 0)
        years_sorted = ()
        countries = 0

    # Write the narrow parquet. Even an empty long frame is
    # written so downstream stages can detect "this run produced
    # no data" without re-reading the CSV.
    parquet = write_reign_parquet(df, parquet_path=parquet_path)

    # DB writes (idempotent by source/year scope).
    with session_scope() as session:
        source_id = register_reign_source(session)
        rows = write_reign_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    result = ReignIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=countries,
        years=years_sorted,
        indicators=len(specs),
        year_window=year_window_tuple,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_reign_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``REIGN_ATTRIBUTION``, ``REIGN_SOURCE_KEY``, the
# year-window constants, and :class:`IndicatorSpec` are defined in
# ``reign_io`` (the lowest-level module) to break the import
# cycle. The re-exports at the top of this file make them
# importable from the canonical orchestrator path; this ``__all__``
# documents the full public surface. The path helpers, the read
# orchestrator, the parquet writer, the CSV reader, and the DB
# helpers are also re-exported so the tests can drive the adapter
# through the orchestrator module.
__all__ = [
    "REIGN_ATTRIBUTION",
    "REIGN_IDENTITY_RAW_COLUMNS",
    "REIGN_SOURCE_KEY",
    "REIGN_YEAR_END",
    "REIGN_YEAR_START",
    "IndicatorSpec",
    "ReignIngestResult",
    "attribution",
    "default_csv_path",
    "default_processed_parquet_path",
    "ingest_reign",
    "load_reign_catalog",
    "read_reign",
    "read_reign_csv_to_long_dataframe",
    "register_reign_source",
    "safe_country_token",
    "write_reign_observations",
    "write_reign_parquet",
    "write_reign_run_manifest",
]
