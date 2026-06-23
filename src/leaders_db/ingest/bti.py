"""Stage 2 -- Bertelsmann BTI orchestrator (REQ-SRC-002).

BTI is the **governance / effectiveness** expert-coded assessment
for the prototype, complementing WGI's quantitative estimates and
V-Dem's broader democracy indicators. The dataset is a single
cumulative xlsx (12 sheets, one per BTI edition from 2006 through
2026, plus the 2006_old pre-methodology sheet; 137-159 countries per
edition; 123 columns of composite indices + Q1-Q17 question fields
+ trend / classification columns). BTI is distributed free with
attribution per the BTI terms of use.

The attribution text returned by :func:`attribution` is the
**short form** ``"BTI 2026 (Bertelsmann Stiftung 2026)."`` -- the
canonical "Attribution text in reports" line in
``docs/sources/attributions.md``. This deviates from the V-Dem / WGI
convention (which uses the long citation form) and matches the BTI
section of the attributions doc exactly. The full citation is the
BTI citation block in the same doc.

The adapter is split across four modules for clarity:

- :mod:`leaders_db.ingest.bti_io` -- catalog, path helpers, parquet
  write, sheet-to-year mapping.
- :mod:`leaders_db.ingest.bti_xlsx` -- xlsx read with header-row
  walk, per-indicator column resolution, country-row extraction,
  long-to-wide pivot.
- :mod:`leaders_db.ingest.bti_db` -- source/observation DB writes,
  run manifest.
- :mod:`leaders_db.ingest.bti_db_helpers` -- coercion + bundle
  metadata parsing.
- :mod:`leaders_db.ingest.bti` (this) -- public orchestrator, the
  :class:`BtiIngestResult` Pydantic model, the :func:`attribution`
  helper, and the canonical BTI citation text.

There is no ``bti_http.py`` because BTI is read from a single local
cumulative xlsx (no HTTP API). The Stage 2 contract: open the xlsx
with ``openpyxl.read_only=True``, walk the 12 edition sheets, pick
the sheet whose covered interval matches the requested target year
(e.g. ``BTI 2024`` for year=2023), extract 12 catalog indicator
columns, pivot long -> wide.

The Stage 2 end-to-end flow:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/bti.csv`` (the single source of
   truth for which BTI indicators are read).
2. Read the wide-format frame via :func:`bti_xlsx.read_bti`. One
   openpyxl pass over the resolved edition sheet; per-indicator
   column resolution by header match; blank-cell -> NaN coercion;
   long -> wide pivot.
3. Write a narrow ``data/processed/bti/bti_country_year.parquet``
   with the BTI attribution in the file-level metadata.
4. Upsert the BTI source row into the ``sources`` provenance table.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it.
   ``source_row_reference`` carries ``"bti:<country>"`` so Stage 3
   can resolve it.
6. Write the run-manifest JSON (with edition sheet name + covered
   interval) as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-
inserts the ``source_observations`` rows for the requested year(s)
only.

Per Rule #15, the attribution text returned by :func:`attribution` is
the exact wording from ``docs/sources/attributions.md``; if the
attributions doc is updated, the same change must be made here in
the same commit. The
:func:`test_bti_attribution_matches_attributions_doc` test enforces
that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .bti_db import (
    register_bti_source,
    write_bti_observations,
    write_bti_run_manifest,
)
from .bti_io import (
    BTI_ATTRIBUTION,
    BTI_SOURCE_KEY,
    IndicatorSpec,
    covered_interval_for_sheet,
    load_indicator_catalog,
    sheet_for_year,
    target_year_for_sheet,
    write_bti_parquet,
)
from .bti_xlsx import read_bti

# Re-exports: ``BTI_ATTRIBUTION``, ``BTI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``bti_io`` to break the import
# cycle, but callers (tests, the CLI) historically import them from
# here. Re-export so the public surface stays in one place. The DB
# helpers (``register_bti_source``, ``write_bti_observations``,
# ``write_bti_run_manifest``) are also re-exported so the test
# builder's tests can call them through the orchestrator module.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class BtiIngestResult(BaseModel):
    """Summary of a single ``ingest_bti`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: a future ``leaders-db ingest-source
    --source bti`` will read ``source_id``, ``parquet_path``,
    ``observation_rows``, ``countries``, ``years``, ``indicators``,
    and ``edition_sheet`` to print the end-of-run summary. The
    manifest writer in :mod:`bti_db` also consumes the same fields.
    Pydantic v2 models are the standard for any payload that
    crosses a file, CLI, provider, or artifact boundary
    (:file:`docs/process/coding-guidelines.md` § Python Standards).

    Carries the resolved edition sheet name + covered interval so
    the CLI can print the proxy/source-edition semantics without
    re-reading the parquet metadata.
    """

    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow BTI parquet.")
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
    edition_sheet: str = Field(
        ...,
        description="The BTI edition sheet name resolved for the run "
        "(e.g. ``\"BTI 2024\"`` for the 2023 target year).",
    )
    covered_interval: tuple[int, int] = Field(
        ...,
        description="The (start_year, end_year) ~2-year window the "
        "edition covers (e.g. ``(2022, 2023)`` for BTI 2024).",
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

    @field_validator("covered_interval")
    @classmethod
    def _covered_interval_is_int_pair(cls, value: tuple[int, int]) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("covered_interval must be a 2-tuple")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"covered_interval must contain ints, got {type(one_year).__name__}"
                )
        if value[0] > value[1]:
            raise ValueError(
                f"covered_interval start ({value[0]}) must be <= end ({value[1]})"
            )
        return value

    @property
    def attribution(self) -> str:
        """The BTI attribution text (Always-On Rule #15)."""
        return BTI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the BTI attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-run
    echo) that touches BTI data must include this block verbatim. The
    exact wording is the one in ``docs/sources/attributions.md``; do
    not paraphrase.
    """
    return BTI_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_bti(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    sheet_name: str | None = None,
) -> BtiIngestResult:
    """Run Stage 2 for BTI end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`bti_xlsx.read_bti`.
       One openpyxl pass over the resolved edition sheet; blank-cell
       -> NaN coercion; long -> wide pivot.
    3. Write the narrow parquet under ``data/processed/bti/`` and
       attach the BTI attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (always, not best-effort -- it is
       the audit trail for ``processed/``).
    6. Returns a :class:`BtiIngestResult` summary.

    The function is the single public entry point -- both the future
    CLI command ``leaders-db ingest-source --source bti`` and the
    tests call it.

    Args:
        year: target year to filter to (e.g. ``2023``). The adapter
            resolves the BTI edition whose covered interval contains
            the year (e.g. ``BTI 2024`` for 2023). If ``None`` and
            ``sheet_name`` is also ``None``, the latest edition
            (``BTI 2026``) is used.
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.
        sheet_name: override the BTI edition sheet name. When given,
            used directly (no year-to-sheet resolution).

    Notes:
        The database session resolves through :func:`session_scope`,
        which honors the ``LEADERSDB_PROJECT_ROOT`` env var. The CLI
        runs against the production DB; tests run against the isolated
        test DB set up by the ``isolated_data_lake`` fixture. No
        explicit ``database_url`` kwarg is needed.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    df = read_bti(
        year=year,
        xlsx_path=xlsx_path,
        catalog_path=catalog_path,
        sheet_name=sheet_name,
    )

    # Resolve the edition sheet + covered interval for the manifest.
    # If the caller passed ``sheet_name`` explicitly, use it; else
    # resolve from the target year; else default to BTI 2026.
    resolved_sheet = sheet_name
    if resolved_sheet is None and year is not None:
        resolved_sheet = sheet_for_year(int(year))
    if resolved_sheet is None:
        resolved_sheet = "BTI 2026"

    # Compute the covered interval from the sheet name (or fall back
    # to the year itself if the sheet is unrecognized).
    interval = covered_interval_for_sheet(resolved_sheet)
    if interval is None:
        # Defensive: unrecognized sheet name. Use the requested year
        # alone (or the default 2025) so the manifest is still
        # well-formed.
        fallback_year = int(year) if year is not None else (
            int(target_year_for_sheet("BTI 2026") or 2025)
        )
        interval = (fallback_year, fallback_year)

    parquet = write_bti_parquet(df, parquet_path=parquet_path)

    with session_scope() as session:
        source_id = register_bti_source(session)
        rows = write_bti_observations(
            session, source_id, df, catalog_path=catalog_path
        )

    result = BtiIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country"].nunique()) if not df.empty else 0,
        years=tuple(sorted({int(y) for y in df["year"].tolist()})) if not df.empty else (),
        indicators=len(specs),
        edition_sheet=resolved_sheet,
        covered_interval=interval,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata. The covered_interval + sheet_name record
    # the proxy/source-edition semantics for BTI.
    write_bti_run_manifest(
        result,
        catalog_path=catalog_path,
        sheet_name=resolved_sheet,
        covered_interval=interval,
    )
    return result


# Public surface: ``BTI_ATTRIBUTION``, ``BTI_SOURCE_KEY``, and
# ``IndicatorSpec`` are defined in ``bti_io`` (the lowest-level
# module) to break the import cycle. The re-exports at the top of
# this file make them importable from the canonical orchestrator
# path; this ``__all__`` documents the full public surface. The DB
# helpers are also re-exported so the tests can drive them through
# the orchestrator module.
__all__ = [
    "BTI_ATTRIBUTION",
    "BTI_SOURCE_KEY",
    "BtiIngestResult",
    "IndicatorSpec",
    "attribution",
    "ingest_bti",
    "register_bti_source",
    "write_bti_observations",
    "write_bti_run_manifest",
]
