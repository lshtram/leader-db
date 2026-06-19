"""Stage 2 -- CIRI Human Rights Data Project (CIRIGHTS) orchestrator.

CIRIGHTS is the **additive-index** domestic-violence source for the
prototype. The dataset is a single xlsx
(``cirights_v3.12.10.24.xlsx``, 1.2 MB, 7,931 country-year rows x
50 columns, 1 sheet ``Sheet1``) distributed by the CIRI Human
Rights Data Project under free academic use with attribution. The
Stage 2 adapter narrows the 48 indicator/ID columns to the 7
Physical Integrity Rights (PIR) + Repression + Civil-Political
Rights indices documented in the catalog.

The adapter is split across four modules for clarity (each under
the 400-line convention from :file:`docs/coding-guidelines.md`):

- :mod:`leaders_db.ingest.cirights_io` -- catalog, path helpers,
  parquet write, read orchestrator. Owns :data:`CIRIGHTS_ATTRIBUTION`,
  :data:`CIRIGHTS_SOURCE_KEY`, the catalog loader, the
  :data:`CIRIGHTS_PROXY_YEAR` and :data:`CIRIGHTS_PROXY_REQUESTED_YEAR`
  constants, the :class:`IndicatorSpec` dataclass, the
  :func:`safe_country_token` URL-safe substitution helper, the
  parquet metadata attach, and the read orchestrator.
- :mod:`leaders_db.ingest.cirights_xlsx` -- the xlsx read: single-
  sheet openpyxl ``read_only=True`` pass, per-cell coercion (empty
  cell -> None, int stays int), 7-indicator wide pivot, and the
  ``_cirights_raw_lookup`` audit-trail attr.
- :mod:`leaders_db.ingest.cirights_db_helpers` -- pure helpers:
  coercion, bundle-metadata parsing, the in-memory observation-row
  builder.
- :mod:`leaders_db.ingest.cirights_db` -- sources upsert,
  source_observations writes, the run-manifest writer (with
  ``proxy_year_semantics`` for the 2023 -> 2022 proxy).
- :mod:`leaders_db.ingest.cirights` (this) -- public orchestrator,
  the :class:`CirightsIngestResult` Pydantic model, the
  :func:`attribution` helper, and the re-export surface.

There is no ``cirights_http.py`` because CIRIGHTS has no HTTP layer
(the xlsx is staged locally; the user downloads it via the
project's download workflow). The Stage 2 contract: open the xlsx
with ``openpyxl.read_only=True``, walk the single ``Sheet1``,
narrow to the 7 catalog ``raw_column`` s, and pivot (the xlsx is
already in long format per country-year so the "pivot" is a column
rename + per-cell coercion).

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/cirights.csv`` (the single
   source of truth for which CIRIGHTS indicators are read).
2. Read the wide-format frame via :func:`cirights_io.read_cirights`.
   One openpyxl ``read_only=True`` pass; per-cell coercion; 7-
   indicator wide pivot. The wide frame carries the
   ``_cirights_raw_lookup`` attr (the pre-coercion cell-text
   lookup for the ``raw_value`` audit trail) and the
   ``year_window`` ``(start, end)`` tuple.
3. Write a narrow ``data/processed/cirights/cirights_country_year.parquet``
   with the CIRIGHTS attribution in the file-level metadata.
4. Upsert the CIRIGHTS source row into the ``sources`` provenance
   table. Keyed by
   ``(source_name='CIRI Human Rights Data Project',
   version='v3.12.10.24')``.
5. Write one ``source_observations`` row per
   ``(country, year, variable)`` triple. ``country_id`` is left
   ``NULL``; Stage 3 (country match) fills it.
   ``source_row_reference`` carries
   ``cirights:<country_token>:<year>:<raw_column>`` (e.g.
   ``cirights:Mexico:2022:Physical Integrity Rights Index``) so
   Stage 3 can resolve it. ``confidence`` is left ``NULL``;
   Stage 11 fills it.
6. Write the run-manifest JSON as the audit trail. The manifest
   carries the ``proxy_year_semantics`` (when the caller asked
   for ``year=2023``) and the ``proxy_requested_year`` /
   ``proxy_data_year`` constants so the audit trail documents
   the 1-year-gap proxy mapping.

The orchestrator is idempotent: re-running it deletes and re-
inserts the ``source_observations`` rows for the requested year(s)
only.

**Year proxy semantics.** The CIRIGHTS xlsx coverage ends 2022
(per ``metadata.json`` and the live xlsx). For the prototype
target year 2023, the orchestrator maps to 2022 as proxy and
records the mapping in the manifest (1-year-gap, same pattern as
UNDP HDI and Leader Survival). The mapping is controlled by the
``CIRIGHTS_PROXY_REQUESTED_YEAR`` and ``CIRIGHTS_PROXY_YEAR``
constants in :mod:`cirights_io`; the manifest records the
``proxy_year_semantics`` string and the
``proxy_requested_year`` / ``proxy_data_year`` integers.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/source-attributions.md`; if the attributions doc is updated,
the same change must be made here in the same commit. The
:func:`test_cirights_attribution_matches_attributions_doc` test
enforces that the code and the doc are byte-for-byte consistent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .cirights_db import (
    register_cirights_source,
    write_cirights_observations,
    write_cirights_run_manifest,
)
from .cirights_io import (
    CIRIGHTS_ATTRIBUTION,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_YEAR_END,
    CIRIGHTS_YEAR_START,
    IndicatorSpec,
    default_processed_parquet_path,
    default_xlsx_path,
    load_indicator_catalog,
    read_cirights,
    safe_country_token,
    write_cirights_parquet,
)
from .cirights_xlsx import (
    read_xlsx_to_wide_dataframe,
)
from .cirights_xlsx_pivot import read_cirights_from_dataframe

# Re-exports: ``CIRIGHTS_ATTRIBUTION``, ``CIRIGHTS_SOURCE_KEY``, the
# proxy + year-window constants, and :class:`IndicatorSpec` are
# defined in ``cirights_io`` (the lowest-level module) to break the
# import cycle, but callers (tests, the CLI) historically import them
# from here. Re-export so the public surface stays in one place. The
# path helpers (``default_xlsx_path``,
# ``default_processed_parquet_path``), the read orchestrators
# (:func:`read_cirights`, :func:`read_cirights_from_dataframe`,
# :func:`read_xlsx_to_wide_dataframe`), the URL-safe helper
# (:func:`safe_country_token`), the parquet writer
# (:func:`write_cirights_parquet`), and the DB helpers
# (:func:`register_cirights_source`,
# :func:`write_cirights_observations`,
# :func:`write_cirights_run_manifest`) are also re-exported so the
# test-builder's tests can drive the adapter through the
# orchestrator module (the V-Dem / WGI / UCDP / SIPRI milex / SIPRI
# Yearbook Ch.7 / PTS / UNDP HDI pattern).


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class CirightsIngestResult(BaseModel):
    """Summary of a single ``ingest_cirights`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: :func:`leaders_db.cli.ingest_source`
    reads ``source_id``, ``parquet_path``, ``observation_rows``,
    ``countries``, ``years``, and ``indicators`` to print the
    end-of-run summary. The manifest writer in :mod:`cirights_db`
    consumes the same fields. Pydantic v2 models are the standard
    for any payload that crosses a file, CLI, provider, or artifact
    boundary (``docs/coding-guidelines.md`` § Python Standards).

    Same shape as the WGI :class:`WGIIngestResult`, the SIPRI
    Yearbook Ch.7 :class:`SipriYearbookCh7IngestResult`, the PTS
    :class:`PtsIngestResult`, and the UNDP HDI
    :class:`UndpHdiIngestResult` for consistency: 8 fields
    (source_id, parquet_path, observation_rows, countries, years,
    indicators, year_window, attribution).

    CIRIGHTS-specific extras vs the WGI result:

    - ``year_window``: a ``(start_year, end_year)`` tuple
      representing the min/max year in the wide frame (e.g.
      ``(2022, 2022)`` for a single-year 2022 run, or
      ``(1981, 2022)`` for the full unfiltered run). Carried
      forward from ``df.attrs["year_window"]``. Useful for the
      audit trail to confirm the wide frame's temporal coverage
      and to document the 1-year-gap proxy mapping.
    """

    source_id: int = Field(
        ..., ge=1,
        description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow CIRIGHTS parquet.",
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this run."
        ),
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``country`` values in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted.",
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used.",
    )
    year_window: tuple[int, int] = Field(
        ...,
        description=(
            "(start_year, end_year) tuple representing the min/max "
            "year in the wide frame."
        ),
    )
    proxy_year_semantics: str | None = Field(
        default=None,
        description=(
            "The 1-year-gap proxy mapping when the caller asked "
            "for ``year=2023``; ``None`` otherwise. The "
            "manifest writer surfaces this in the run-manifest "
            "JSON so the audit trail records the proxy mapping."
        ),
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...],
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "years must be a sorted tuple of unique ints"
            )
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        return value

    @field_validator("year_window")
    @classmethod
    def _year_window_is_ordered_pair(
        cls, value: tuple[int, int],
    ) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        if value[0] > value[1]:
            raise ValueError("year_window must have start <= end")
        return value

    @property
    def attribution(self) -> str:
        """The CIRIGHTS attribution text (Always-On Rule #15)."""
        return CIRIGHTS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the CIRIGHTS attribution block for public output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI
    end-of-run echo) that touches CIRIGHTS data must include this
    block verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return CIRIGHTS_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_cirights(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> CirightsIngestResult:
    """Run Stage 2 for CIRIGHTS end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via
       :func:`cirights_io.read_cirights`. One openpyxl
       ``read_only=True`` pass on the single ``Sheet1``; per-cell
       coercion; 7-indicator wide pivot. The wide frame carries the
       ``_cirights_raw_lookup`` attr (the pre-coercion cell-text
       lookup for the ``raw_value`` audit trail) and the
       ``year_window`` ``(start, end)`` tuple.
    3. Write the narrow parquet under ``data/processed/cirights/``
       and attach the CIRIGHTS attribution to the parquet's
       file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Build the :class:`CirightsIngestResult` and write the run
       manifest. The manifest carries the ``proxy_year_semantics``
       (when the caller asked for ``year=2023``) and the
       ``proxy_requested_year`` / ``proxy_data_year`` constants
       so the audit trail documents the 1-year-gap proxy mapping.
    6. Return the result.

    **Year proxy semantics.** When the caller asks for
    ``year=2023`` (the prototype target year), the adapter reads
    2022 data (the latest available per the live xlsx) and records
    the ``2023 -> 2022`` mapping in the run manifest. The mapping
    is controlled by the ``CIRIGHTS_PROXY_REQUESTED_YEAR`` and
    ``CIRIGHTS_PROXY_YEAR`` constants in :mod:`cirights_io`.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source cirights`` and the
    tests call it. The DB session resolves through
    :func:`session_scope`, which honors the
    ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2022`` for direct
            data; ``2023`` for the 1-year-gap proxy mapped to
            2022). Default: all 42 years present in the xlsx
            (1981-2022).
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default:
            data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)

    # Year 2023 -> 2022 proxy (per docs/workplan.md "Phase B
    # addendum -- CIRIGHTS user-managed (2026-06-17)" and the
    # source-vetting report §3.8). The orchestrator surfaces the
    # proxy mapping on the result so the manifest can record it.
    requested_year = year
    effective_year = year
    proxy_year_semantics: str | None = None
    if year is not None and year == CIRIGHTS_PROXY_REQUESTED_YEAR:
        effective_year = CIRIGHTS_PROXY_YEAR
        proxy_year_semantics = (
            f"year={CIRIGHTS_PROXY_REQUESTED_YEAR} -> "
            f"data_year={CIRIGHTS_PROXY_YEAR} (1-year-gap proxy, "
            "per docs/source-vetting-report.md §3.8 + the same "
            "pattern as UNDP HDI and Leader Survival)"
        )

    df = read_cirights(
        xlsx_path=xlsx_path, year=effective_year, catalog_path=catalog_path,
    )

    # Surface the audit-trail extras from df.attrs before the
    # parquet write strips the ``_cirights_raw_lookup`` attr. The
    # lookup is JSON-serializable but the parquet write strips it
    # for cleanliness; the DB writer reads it off the frame
    # before that.
    year_window_tuple: tuple[int, int] = df.attrs.get("year_window", (0, 0))

    parquet = write_cirights_parquet(df, parquet_path=parquet_path)

    # Short-circuit: if the wide frame is empty (year out of
    # range), skip the DB writes and return an empty result with a
    # "no_data" manifest. The parquet is still written (empty
    # frame) so downstream stages can detect "this run produced no
    # data" without re-reading the xlsx.
    if df.empty:
        with session_scope() as session:
            source_id = register_cirights_source(session)
        empty_result = CirightsIngestResult(
            source_id=source_id,
            parquet_path=parquet,
            observation_rows=0,
            countries=0,
            years=(),
            indicators=len(specs),
            year_window=(0, 0),
            proxy_year_semantics=proxy_year_semantics,
        )
        # Write the manifest with status="no_data" so the audit
        # trail records the short-circuit explicitly. The manifest
        # is written even on the short-circuit path (Rule #15).
        write_cirights_run_manifest(
            empty_result,
            catalog_path=catalog_path,
            proxy_year_semantics=proxy_year_semantics,
            requested_year=(
                int(requested_year) if requested_year is not None else None
            ),
        )
        return empty_result

    with session_scope() as session:
        source_id = register_cirights_source(session)
        rows = write_cirights_observations(
            session, source_id, df, catalog_path=catalog_path,
        )

    result = CirightsIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=int(df["country"].nunique()) if not df.empty else 0,
        years=tuple(
            sorted(
                {
                    int(y) for y in _dropna_to_ints(df["year"])
                },
            ),
        ),
        indicators=len(specs),
        year_window=year_window_tuple,
        proxy_year_semantics=proxy_year_semantics,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata. The proxy_year_semantics /
    # requested_year are surfaced here so the audit trail records
    # the 1-year-gap mapping explicitly.
    write_cirights_run_manifest(
        result,
        catalog_path=catalog_path,
        proxy_year_semantics=proxy_year_semantics,
        requested_year=(
            int(requested_year) if requested_year is not None else None
        ),
    )
    return result


def _dropna_to_ints(series: object) -> list[int]:
    """Drop ``pd.NA`` values from a year column and coerce to Python ``int``.

    The wide frame's ``year`` column is ``Int64`` (nullable);
    missing values become ``pd.NA``. This helper drops the
    ``pd.NA`` values and converts the rest to Python ``int`` for
    the result's ``years`` tuple. Underscore-prefixed because it is
    private to the orchestrator (not part of the public surface).
    """
    if not hasattr(series, "dropna"):
        return []
    return [int(y) for y in series.dropna().tolist()]


# Public surface: ``CIRIGHTS_ATTRIBUTION``, ``CIRIGHTS_SOURCE_KEY``,
# the proxy + year-window constants, and :class:`IndicatorSpec` are
# defined in ``cirights_io`` (the lowest-level module) to break the
# import cycle. The re-exports at the top of this file make them
# importable from the canonical orchestrator path; this ``__all__``
# documents the full public surface. The DB helpers, path helpers,
# and read orchestrators are also re-exported so the tests can
# drive the adapter through the orchestrator module.
__all__ = [
    "CIRIGHTS_ATTRIBUTION",
    "CIRIGHTS_PROXY_REQUESTED_YEAR",
    "CIRIGHTS_PROXY_YEAR",
    "CIRIGHTS_SOURCE_KEY",
    "CIRIGHTS_YEAR_END",
    "CIRIGHTS_YEAR_START",
    "CirightsIngestResult",
    "IndicatorSpec",
    "attribution",
    "default_processed_parquet_path",
    "default_xlsx_path",
    "ingest_cirights",
    "load_indicator_catalog",
    "read_cirights",
    "read_cirights_from_dataframe",
    "read_xlsx_to_wide_dataframe",
    "register_cirights_source",
    "safe_country_token",
    "write_cirights_observations",
    "write_cirights_parquet",
    "write_cirights_run_manifest",
]
