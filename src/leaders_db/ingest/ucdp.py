"""Stage 2 -- UCDP (Uppsala Conflict Data Program) orchestrator (REQ-SRC-006).

UCDP is the **event-level** conflict data source for the prototype.
Unlike V-Dem / WDI / WGI (which are country-year tables), the UCDP GED
23.1 is a flat event-level dataset of ~316,818 events shipped as a zip
containing a single 218 MB CSV. The Stage 2 adapter must aggregate
events by ``(country_id, year)`` to produce the country-year x
indicator matrix the score modules need. This is the first Stage 2
adapter that requires aggregation logic.

UCDP is distributed under a free academic license per the
`UCDP Terms of Use <https://ucdp.uu.se/terms-of-use/>`_. The canonical
attribution text is the citation block in
:file:`docs/sources/attributions.md` (ucdp section), exposed as the
:data:`UCDP_ATTRIBUTION` constant (re-exported from
:mod:`leaders_db.ingest.ucdp_io`).

The adapter is split across four modules for clarity (each under the
400-line convention from :file:`docs/process/coding-guidelines.md`):

- :mod:`leaders_db.ingest.ucdp_io` -- catalog, zip read, parquet
  write. Owns :data:`UCDP_ATTRIBUTION`, :data:`UCDP_SOURCE_KEY`, the
  catalog loader, and the long->wide aggregation.
- :mod:`leaders_db.ingest.ucdp_db` -- source/observation DB writes,
  run manifest, missing-value coercion (``_normalize_cell`` and
  ``_raw_value_to_string``).
- :mod:`leaders_db.ingest.ucdp_db_helpers` -- pure helpers: bundle
  metadata read, ISO date parse, year-range parse, value coercion
  (counts -> int, fatalities -> float), ``raw_value_to_string`` for
  the audit trail.
- :mod:`leaders_db.ingest.ucdp` (this) -- public orchestrator, the
  :class:`UCDPIngestResult` model, the :func:`attribution` helper,
  and the canonical UCDP citation text.

There is no ``ucdp_http.py`` because UCDP has no HTTP layer (the zip
is staged locally). There is no ``ucdp_aggregate.py`` because the
aggregation is ~30 lines and fits in :mod:`ucdp_io`.

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/ucdp.csv`` (the single source of
   truth for which UCDP indicators are read).
2. Read the wide-format frame via :func:`ucdp_io.read_ucdp`. Open
   the zip with :class:`zipfile.ZipFile`, stream-read the CSV
   member, aggregate events to country-year (``groupby(country_id,
   year, type_of_violence)`` + the cross-border filter for
   ``ucdp_intl_*``), pivot long -> wide. ``df.attrs`` carries
   ``events_total`` and ``events_filtered``.
3. Write a narrow ``data/processed/ucdp/ucdp_country_year.parquet``
   with the UCDP attribution in the file-level metadata.
4. Upsert the UCDP source row into the ``sources`` provenance
   table. Keyed by ``(source_name='UCDP (Uppsala Conflict Data
   Program)', version='23.1')``.
5. Write one ``source_observations`` row per ``(country, year,
   variable)`` triple. ``country_id`` is left ``NULL``; Stage 3
   (country match) fills it. ``source_row_reference`` carries
   ``"ucdp:<ucdp_country_id>"`` (e.g., ``"ucdp:645"`` for Iraq) so
   Stage 3 can resolve it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-inserts
the ``source_observations`` rows for the requested year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution` is
the exact wording from ``docs/sources/attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_ucdp_attribution_matches_attributions_doc` test enforces
that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .ucdp_db import (
    register_ucdp_source,
    write_ucdp_observations,
    write_ucdp_run_manifest,
)
from .ucdp_io import (
    UCDP_ATTRIBUTION,
    UCDP_SOURCE_KEY,
    IndicatorSpec,
    default_processed_parquet_path,
    default_zip_path,
    load_indicator_catalog,
    read_ucdp,
    write_ucdp_parquet,
)

# Re-exports: ``UCDP_ATTRIBUTION``, ``UCDP_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``ucdp_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The path
# helpers (``default_zip_path``, ``default_processed_parquet_path``)
# are also re-exported so the test-builder's tests can call them
# through the orchestrator module -- the WGI / WDI / V-Dem pattern.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class UCDPIngestResult(BaseModel):
    """Summary of a single ``ingest_ucdp`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`ucdp_db` consumes the same fields.

    UCDP-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``events_total``: raw event count in the zip after the year
      filter, before the type / cross-border filter. Carried forward
      from ``df.attrs["events_total"]``.
    - ``events_filtered``: count after the type=1 OR type=3 filter
      (i.e., events that feed at least one of the 6 catalog
      indicators). Carried forward from
      ``df.attrs["events_filtered"]``.

    These are the UCDP-specific equivalents of WDI's
    ``indicators_cached`` / ``indicators_fetched``: they capture
    "how much data was in the input" vs "how much was used" for
    end-to-end audit.
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow UCDP parquet.")
    observation_rows: int = Field(
        ...,
        ge=0,
        description="Number of ``source_observations`` rows written by this run.",
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``country_id``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(..., description="Years included in the run, sorted.")
    indicators: int = Field(..., ge=0, description="Number of catalog indicators used.")
    events_total: int = Field(
        ...,
        ge=0,
        description="Raw event count after the year filter, before the type filter.",
    )
    events_filtered: int = Field(
        ...,
        ge=0,
        description="Count after the type=1 OR type=3 filter (events feeding the 6 indicators).",
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got {type(one_year).__name__}"
                )
        return value

    @property
    def attribution(self) -> str:
        """The UCDP attribution text (Always-On Rule #15)."""
        return UCDP_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the UCDP attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches UCDP data must include this block
    verbatim. The exact wording is the one in
    ``docs/sources/attributions.md``; do not paraphrase.
    """
    return UCDP_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_ucdp(
    *,
    year: int | None = None,
    zip_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> UCDPIngestResult:
    """Run Stage 2 for UCDP end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`ucdp_io.read_ucdp`.
       Open the zip with :class:`zipfile.ZipFile`, stream-read the
       CSV, aggregate to country-year, pivot to wide. ``df.attrs``
       carries ``events_total`` and ``events_filtered`` from the
       input.
    3. Write the narrow parquet under ``data/processed/ucdp/`` and
       attach the UCDP attribution to the parquet's file-level
       metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`UCDPIngestResult` and write the run
       manifest.
    6. Returns the :class:`UCDPIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source ucdp`` and the
    tests call it.

    Args:
        year: filter to a single year (e.g. ``2022``).
            Default: all years present in the zip (1989-2022,
            34 distinct years).
        zip_path: override the input zip. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the
        isolated test DB set up by the ``isolated_data_lake``
        fixture. No explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_ucdp(
        year=year, zip_path=zip_path, catalog_path=catalog_path,
    )
    parquet = write_ucdp_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_ucdp_source(session)
        rows = write_ucdp_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    result = UCDPIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country_id"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        events_total=int(df.attrs.get("events_total", 0)),
        events_filtered=int(df.attrs.get("events_filtered", 0)),
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata.
    write_ucdp_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``UCDP_ATTRIBUTION``, ``UCDP_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``ucdp_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The DB
# helpers are also re-exported so the tests can drive them through
# the orchestrator module (the test builder's test surface is
# ``from leaders_db.ingest import ucdp; ucdp.register_ucdp_source(...)``).
__all__ = [
    "UCDP_ATTRIBUTION",
    "UCDP_SOURCE_KEY",
    "IndicatorSpec",
    "UCDPIngestResult",
    "attribution",
    "default_processed_parquet_path",
    "default_zip_path",
    "ingest_ucdp",
    "load_indicator_catalog",
    "read_ucdp",
    "register_ucdp_source",
    "write_ucdp_observations",
    "write_ucdp_parquet",
    "write_ucdp_run_manifest",
]
