"""Stage 2 -- Archigos v4.1 orchestrator.

Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009) is the
**leader-spell** historical leader-identity source for the
prototype. The dataset is a single Stata 14 ``.dta`` file
(``Archigos_4.1_stata14.dta``, ~2.9 MB, 3,409 leader spells x
28 columns x 189 country-codes, coverage 1840-2015) hosted at
the University of Rochester's political-leaders page. The Stage
2 adapter narrows the 28 columns to the 6 identity columns
documented in
:file:`src/leaders_db/ingest/catalogs/archigos.csv`:

- ``leader`` (text)
- ``startdate`` (date, light-coerced to decimal year)
- ``enddate`` (date, light-coerced to decimal year)
- ``entry`` (categorical, light-coerced to ordinal code)
- ``exit`` (categorical, light-coerced to ordinal code)
- ``gender`` (``M``/``F``, light-coerced to 1/2)

The adapter is split across small modules. ``archigos.py``
remains the public orchestrator and re-export surface, while
helper modules keep the documented line caps enforceable:

- :mod:`leaders_db.ingest.archigos_io` -- catalog, path helpers,
  read orchestrator, parquet write, named constants,
  :class:`IndicatorSpec`.
- :mod:`leaders_db.ingest.archigos_dta` -- Stata read with
  ``pyreadstat``, per-cell coercion, date -> decimal-year
  coercion, categorical -> ordinal-code coercion, gender -> 1/2
  coercion.
- :mod:`leaders_db.ingest.archigos_db` -- sources upsert,
  source_observations writes, run-manifest writer.
- :mod:`leaders_db.ingest.archigos_db_helpers` -- pure helpers:
  bundle metadata reader, value coercion, observation-row
  builder.
- :mod:`leaders_db.ingest.archigos_result` --
  :class:`ArchigosIngestResult`.
- :mod:`leaders_db.ingest.archigos` (this) -- public
  orchestrator, :func:`attribution` helper, and re-exports.

Archigos is structurally distinct from every prior Stage 2
adapter:

- It is the first Stata-based source (``.dta`` format; ``cp1252``
  encoding; ``pyreadstat`` reader).
- The natural unit of observation is **leader-spell** (1 row per
  leader's tenure), NOT country-year. The Stage 2 adapter writes
  one ``source_observations`` row per (leader-spell,
  identity-column) pair, keyed by the spell's **start year**.
- The Stage 4 leader resolver (not implemented in this phase)
  will join Archigos with REIGN, Leader Survival, Wikidata, and
  the client bundle. ``country_id`` / ``leader_id`` are left
  ``NULL`` in this phase.
- Archigos is the first Stage 2 adapter that uses pyreadstat;
  the new ``pyreadstat>=1.3`` runtime dependency was added in
  Phase C for this source.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/archigos.csv`` (the single
   source of truth for which Archigos identity columns are read).
2. Read the wide-format .dta via
   :func:`archigos_io.read_archigos`. One ``pyreadstat`` call
   (with ``encoding='cp1252'``); narrow to the 6 catalog
   ``raw_column`` s + the 3 audit columns (``obsid``,
   ``idacr``, ``ccode``); extract start year + end year from the
   Stata ``%td`` columns; pivot wide -> long. The long frame
   carries the per-cell coercion (text preserved verbatim, dates
   -> decimal year, categoricals -> ordinal code, gender -> 1/2).
3. Optionally filter to a single start year.
4. Write the narrow long-format parquet under
   ``data/processed/archigos/`` with the Archigos attribution
   attached to the file-level metadata.
5. Upsert the Archigos source row into the ``sources``
   provenance table. Keyed by
   ``(source_name='Archigos v4.1', version='v4.1 (Stata 14)')``.
6. Write one ``source_observations`` row per long-format row.
   ``country_id`` is left ``NULL``; ``leader_id`` is left
   ``NULL``; ``source_row_reference`` carries
   ``archigos:<obsid>:<start_year>:<raw_column>`` (e.g.
   ``archigos:USA-1869:1869:leader``). ``confidence`` is left
   ``NULL``.
7. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and
re-inserts the ``source_observations`` rows for the requested
start-year(s) only.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/sources/attributions.md``; the
:func:`test_archigos_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from ..db.session import session_scope
from .archigos_db import (
    register_archigos_source,
    write_archigos_observations,
    write_archigos_run_manifest,
)
from .archigos_io import (
    ARCHIGOS_ATTRIBUTION,
    ARCHIGOS_DTA_ENCODING,
    ARCHIGOS_SOURCE_KEY,
    ARCHIGOS_YEAR_END,
    ARCHIGOS_YEAR_START,
    IndicatorSpec,
    default_dta_path,
    default_processed_parquet_path,
    load_archigos_catalog,
    read_archigos,
    write_archigos_parquet,
)
from .archigos_result import ArchigosIngestResult

# Re-exports: ``ARCHIGOS_ATTRIBUTION``, ``ARCHIGOS_SOURCE_KEY``, the
# year-window constants, and :class:`IndicatorSpec` are defined in
# ``archigos_io`` (the lowest-level module) to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The
# path helpers, the read orchestrator, the parquet writer, and the
# DB helpers are also re-exported so the test-builder's tests can
# drive the adapter through the orchestrator module (the
# V-Dem / CIRIGHTS / WGI / UCDP / SIPRI milex / SIPRI Yearbook
# Ch.7 / PTS / UNDP HDI / WHO GHO API pattern).


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the Archigos attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches Archigos data must include this block
    verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return ARCHIGOS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_archigos(
    *,
    year: int | None = None,
    dta_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> ArchigosIngestResult:
    """Run Stage 2 for Archigos v4.1 end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide .dta via :func:`archigos_io.read_archigos`.
       One ``pyreadstat.read_dta(encoding='cp1252')`` call;
       narrow to the 6 catalog ``raw_column`` s + the 3 audit
       columns; extract start year + end year from the Stata
       ``%td`` columns; pivot wide -> long. The long frame
       carries the per-cell coercion (text preserved verbatim,
       dates -> decimal year, categoricals -> ordinal code,
       gender -> 1/2).
    3. Optionally filter to a single start year.
    4. Write the narrow long-format parquet under
       ``data/processed/archigos/`` with the Archigos attribution
       attached to the file-level metadata.
    5. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    6. Build the :class:`ArchigosIngestResult` and write the run
       manifest. The manifest records the ``year_window`` tuple
       (min/max start-year in the long frame) and the
       attribution.
    7. Return the result.

    **Year semantics.** The Stage 2 adapter writes observations
    keyed by the **start year** of the leader's tenure. End years
    are recorded as a separate variable (``archigos_tenure_end_date``)
    with its own ``source_row_reference`` suffix. Archigos data
    ends 2015 (per the live .dta and the bundle metadata); the
    prototype target year 2023 has no Archigos data (8-year gap
    per the source-vetting report §3.1).

    The function is the single public entry point -- both the
    CLI command ``leaders-db ingest-source --source archigos`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single start-year (e.g. ``2000`` for all
            Archigos spells starting in 2000). Default: all
            3,409 spells.
        dta_path: override the input .dta. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_archigos_catalog(catalog_path=catalog_path)

    actual_dta_path = dta_path or default_dta_path()
    df = read_archigos(
        dta_path=actual_dta_path, year=year, catalog_path=catalog_path,
    )

    # Compute the audit-trail extras from the long frame. The
    # ``year_window`` tuple is the (min, max) start-year in the
    # long frame. The ``years`` tuple is the sorted set of
    # distinct start-years.
    if not df.empty:
        year_window_tuple: tuple[int, int] = (
            int(df["year"].min()),
            int(df["year"].max()),
        )
        years_sorted = tuple(
            sorted({int(y) for y in df["year"].tolist()}),
        )
        countries = int(df["idacr"].nunique())
    else:
        year_window_tuple = (0, 0)
        years_sorted = ()
        countries = 0

    # Write the narrow parquet. Even an empty long frame is
    # written so downstream stages can detect "this run produced
    # no data" without re-reading the .dta.
    parquet = write_archigos_parquet(df, parquet_path=parquet_path)

    # DB writes (idempotent by source/start-year scope).
    with session_scope() as session:
        source_id = register_archigos_source(session)
        rows = write_archigos_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    result = ArchigosIngestResult(
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
    write_archigos_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``ARCHIGOS_ATTRIBUTION``, ``ARCHIGOS_SOURCE_KEY``,
# the year-window constants, and :class:`IndicatorSpec` are defined
# in ``archigos_io`` (the lowest-level module) to break the import
# cycle. The re-exports at the top of this file make them
# importable from the canonical orchestrator path; this ``__all__``
# documents the full public surface. The path helpers, the read
# orchestrator, the parquet writer, and the DB helpers are also
# re-exported so the tests can drive the adapter through the
# orchestrator module.
__all__ = [
    "ARCHIGOS_ATTRIBUTION",
    "ARCHIGOS_DTA_ENCODING",
    "ARCHIGOS_SOURCE_KEY",
    "ARCHIGOS_YEAR_END",
    "ARCHIGOS_YEAR_START",
    "ArchigosIngestResult",
    "IndicatorSpec",
    "attribution",
    "default_dta_path",
    "default_processed_parquet_path",
    "ingest_archigos",
    "load_archigos_catalog",
    "read_archigos",
    "register_archigos_source",
    "write_archigos_observations",
    "write_archigos_parquet",
    "write_archigos_run_manifest",
]
