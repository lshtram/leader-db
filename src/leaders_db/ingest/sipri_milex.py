"""Stage 2 -- SIPRI milex (Military Expenditure Database) orchestrator (REQ-SRC-002).

SIPRI milex is the **expenditure-based** conflict signal for the
prototype, complementing UCDP's **event-based** signal. The data
is a single xlsx (one workbook, 10 sheets, ~177 countries x up to
77 years x 4 catalog indicators). It is distributed under a free
academic license with attribution per SIPRI's
[Terms of Use for the Milex Database](
https://www.sipri.org/databases/milex).

The adapter is split across four modules for clarity (each under
the 400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.sipri_milex_io` -- catalog, path
  helpers, parquet write. Owns :data:`SIPRI_MILEX_ATTRIBUTION`,
  :data:`SIPRI_MILEX_SOURCE_KEY`, the catalog loader, the
  region denylist, the missing-string set, and the parquet
  metadata attach.
- :mod:`leaders_db.ingest.sipri_milex_xlsx` -- xlsx read with
  per-sheet header-row detection, region filter, missing-value
  coercion, long-to-wide pivot.
- :mod:`leaders_db.ingest.sipri_milex_db` -- source/observation
  DB writes, run manifest.
- :mod:`leaders_db.ingest.sipri_milex_db_helpers` -- pure
  coercion and bundle-metadata helpers (extracted to keep
  :mod:`sipri_milex_db` under the 400-line convention).
- :mod:`leaders_db.ingest.sipri_milex` (this) -- public
  orchestrator, the :class:`SipriMilexIngestResult` model, the
  :func:`attribution` helper, and the canonical SIPRI milex
  citation text.

There is no ``sipri_milex_http.py`` because SIPRI milex has no
HTTP layer (the xlsx is staged locally).

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/sipri_milex.csv`` (the single
   source of truth for which SIPRI milex sheets are read).
2. Read the wide-format frame via :func:`read_sipri_milex`. Open
   the xlsx with ``openpyxl.read_only=True``, walk the 4 catalog
   sheets, **detect the header row dynamically** (per-sheet
   positions vary: 6, 7, or 8), filter out the 15 region/sub-
   region labels, coerce the 3 missing-value tokens (``"..."``,
   ``"xxx"``, ``""``) to ``None``, pivot long -> wide. SIPRI
   milex has no ISO3 column; the wide frame's ``country`` column
   carries the raw display name.
3. Write a narrow
   ``data/processed/sipri_milex/sipri_milex_country_year.parquet``
   with the SIPRI milex attribution in the file-level metadata.
4. Upsert the SIPRI milex source row into the ``sources``
   provenance table. Keyed by
   ``(source_name='SIPRI Military Expenditure Database',
   version='v1.2 (1949-2025)')``.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it.
   ``source_row_reference`` carries ``"sipri_milex:<display_name>"``
   so Stage 3 can resolve it. ``confidence`` is left ``NULL``;
   Stage 11 fills it.
6. Write the run-manifest JSON as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-
inserts the ``source_observations`` rows for the requested
year(s) only.

Per Rule #15, the attribution text returned by :func:`attribution`
is the exact wording from ``docs/source-attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_sipri_milex_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .sipri_milex_db import (
    register_sipri_milex_source,
    write_sipri_milex_observations,
    write_sipri_milex_run_manifest,
)
from .sipri_milex_io import (
    SIPRI_MILEX_ATTRIBUTION,
    SIPRI_MILEX_SOURCE_KEY,
    IndicatorSpec,
    default_processed_parquet_path,
    default_xlsx_path,
    load_indicator_catalog,
    write_sipri_milex_parquet,
)
from .sipri_milex_xlsx import read_sipri_milex

# Re-exports: ``SIPRI_MILEX_ATTRIBUTION``, ``SIPRI_MILEX_SOURCE_KEY``,
# and ``IndicatorSpec`` are defined in ``sipri_milex_io`` to break
# the import cycle, but callers (tests, the CLI) historically
# import them from here. Re-export so the public surface stays in
# one place. The path helpers (``default_xlsx_path``,
# ``default_processed_parquet_path``) and the parquet writer
# (``write_sipri_milex_parquet``) are also re-exported so the
# test-builder's tests can call them through the orchestrator
# module -- the WGI / WDI / V-Dem / UCDP pattern. The DB helpers
# are also re-exported so the tests can drive them through the
# orchestrator module.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class SipriMilexIngestResult(BaseModel):
    """Summary of a single ``ingest_sipri_milex`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: :func:`leaders_db.cli.ingest_source`
    reads these fields to print the end-of-run summary, and the
    manifest writer in :mod:`sipri_milex_db` consumes the same
    fields. Same shape as V-Dem's :class:`vdem.IngestResult`,
    WGI's :class:`wgi.WGIIngestResult`, and UCDP's
    :class:`ucdp.UCDPIngestResult` for consistency.

    SIPRI-milex-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``regions_covered``: a sorted list of the region labels
      found in the input data (e.g. ``["Africa", "Americas",
      "Asia & Oceania", "Europe", "Middle East"]``). Carried
      forward from ``df.attrs["regions_covered"]``. The
      orchestrator filters out these rows from the wide frame
      (they are aggregate labels, not countries), but preserves
      the list as an audit field.
    - ``country_count``: the count of distinct country names in
      the wide frame (after the region filter). Carried
      forward from ``df.attrs["country_count"]``.

    These are the SIPRI-milex-specific equivalents of UCDP's
    ``events_total`` / ``events_filtered``: they capture "what
    was filtered out" for end-to-end audit.
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow SIPRI milex parquet.")
    observation_rows: int = Field(
        ...,
        ge=0,
        description="Number of ``source_observations`` rows written by this run.",
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct country names in the narrow frame.",
    )
    years: tuple[int, ...] = Field(..., description="Years included in the run, sorted.")
    indicators: int = Field(..., ge=0, description="Number of catalog indicators used.")
    regions_covered: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted list of region labels found in the input data "
            "(filtered out of the wide frame but preserved as audit)."
        ),
    )
    country_count: int = Field(
        ...,
        ge=0,
        description="Distinct country names in the wide frame.",
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...],
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got {type(one_year).__name__}"
                )
        return value

    @field_validator("regions_covered")
    @classmethod
    def _regions_covered_is_sorted_unique(
        cls, value: list[str],
    ) -> list[str]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "regions_covered must be a sorted list of unique strings"
            )
        return value

    @property
    def attribution(self) -> str:
        """The SIPRI milex attribution text (Always-On Rule #15)."""
        return SIPRI_MILEX_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the SIPRI milex attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches SIPRI milex data must include this
    block verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return SIPRI_MILEX_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_sipri_milex(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> SipriMilexIngestResult:
    """Run Stage 2 for SIPRI milex end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_sipri_milex`. One
       openpyxl per-catalog-sheet pass; per-sheet header-row
       detection; region filter; long -> wide pivot; missing-value
       coercion.
    3. Write the narrow parquet under
       ``data/processed/sipri_milex/`` and attach the SIPRI milex
       attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`SipriMilexIngestResult` and write the run
       manifest.
    6. Return the result.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source sipri_milex`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2023``). Default: all
            years present in the xlsx (1949-2025 for Share of GDP
            / Constant USD; 1988-2025 for Per capita / Share of
            Govt. spending).
        xlsx_path: override the input xlsx. Default: data-lake
            path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_sipri_milex(
        year=year, xlsx_path=xlsx_path, catalog_path=catalog_path,
    )
    parquet = write_sipri_milex_parquet(
        df, parquet_path=parquet_path,
    )

    with session_scope() as session:
        source_id = register_sipri_milex_source(session)
        rows = write_sipri_milex_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    # Surface the SIPRI-specific extras from df.attrs. The
    # parquet writer already stripped the non-JSON-serializable
    # ``_sipri_milex_raw_long`` attr; ``regions_covered`` and
    # ``country_count`` are JSON-serializable and survive.
    regions_covered = list(df.attrs.get("regions_covered", []))
    country_count = int(df.attrs.get("country_count", 0))

    result = SipriMilexIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})),
        indicators=len(specs),
        regions_covered=regions_covered,
        country_count=country_count,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-
    # reading the parquet metadata.
    write_sipri_milex_run_manifest(result, catalog_path=catalog_path)
    return result


# Public surface: ``SIPRI_MILEX_ATTRIBUTION``, ``SIPRI_MILEX_SOURCE_KEY``,
# and ``IndicatorSpec`` are defined in ``sipri_milex_io`` (the
# lowest-level module) to break the import cycle. The re-exports
# at the top of this file make them importable from the
# canonical orchestrator path; this ``__all__`` documents the
# full public surface. The DB helpers are also re-exported so
# the tests can drive them through the orchestrator module.
__all__ = [
    "SIPRI_MILEX_ATTRIBUTION",
    "SIPRI_MILEX_SOURCE_KEY",
    "IndicatorSpec",
    "SipriMilexIngestResult",
    "attribution",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "ingest_sipri_milex",
    "load_indicator_catalog",
    "read_sipri_milex",
    "register_sipri_milex_source",
    "write_sipri_milex_observations",
    "write_sipri_milex_parquet",
    "write_sipri_milex_run_manifest",
]
