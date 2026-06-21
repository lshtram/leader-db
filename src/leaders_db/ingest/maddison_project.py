"""Stage 2 -- Maddison Project Database 2023 orchestrator.

The Maddison Project Database 2023 release is the prototype's
canonical historical real-economy source for the ``economic_wellbeing``
rating category. It is a single xlsx (one workbook, 7 sheets;
``Full data`` is the canonical Stage 2 input with 131,144 data rows
x 6 columns: ``countrycode``, ``country``, ``region``, ``year``,
``gdppc``, ``pop``). It is distributed under CC BY 4.0 per the
Maddison Project release notes. The dataset covers 1-2022 (no 2023
data in the 2023 release), so the prototype target year 2023 is
proxied to 2022 (1-year-gap pattern, same as CIRIGHTS / UNDP HDI /
Leader Survival). The proxy mapping is surfaced in the run manifest
and on the result model.

The adapter is split across five modules for clarity:

- :mod:`leaders_db.ingest.maddison_project_io` -- catalog, path
  helpers, parquet write, constants.
- :mod:`leaders_db.ingest.maddison_project_xlsx` -- xlsx read of
  the ``Full data`` sheet, per-row derived GDP computation, narrow
  long-format frame construction.
- :mod:`leaders_db.ingest.maddison_project_db` -- source /
  observation DB writes + run manifest.
- :mod:`leaders_db.ingest.maddison_project_db_helpers` -- value
  coercion + bundle metadata parsing.
- :mod:`leaders_db.ingest.maddison_project` (this) -- public
  orchestrator, the :class:`MaddisonProjectIngestResult` Pydantic
  model, the :func:`attribution` helper, and the canonical
  Maddison Project citation text.

There is no ``maddison_project_http.py`` because Maddison is read
from a single local xlsx (no HTTP API). The Stage 2 contract:
open the xlsx with ``openpyxl.read_only=True``, walk the
``Full data`` sheet, validate the 6 required columns, extract the
``gdppc`` and ``pop`` cells per ``(countrycode, year)`` row,
compute the derived GDP total when both cells are present, and
pivot to long format (one row per ``(countrycode, year,
variable_name)`` triple).

The Stage 2 end-to-end flow is:

1. Load the indicator catalog from
   ``src/leaders_db/ingest/catalogs/maddison_project.csv`` (the
   single source of truth for which Maddison indicators are read).
2. Read the long-format frame via
   :func:`read_maddison_project`. One openpyxl pass over the
   ``Full data`` sheet; per-cell coercion; derived GDP total
   computed at row time when both ``gdppc`` and ``pop`` are
   non-NaN.
3. Write a narrow ``data/processed/maddison_project/maddison_project_country_year.parquet``
   with the Maddison attribution in the file-level metadata.
4. Upsert the Maddison Project source row into the ``sources``
   provenance table.
5. Write one ``source_observations`` row per
   ``(countrycode, year, variable_name)`` triple.
   ``country_id`` is left ``NULL``; Stage 3 (country match) fills
   it in. ``source_row_reference`` carries
   ``"maddison_project:<raw_column>:<iso3>:<year>"`` so Stage 3 can
   resolve it.
6. Write the run-manifest JSON (with year_window + proxy_year
   semantics when applicable) as the audit trail.

The orchestrator is idempotent: re-running it deletes and re-
inserts the ``source_observations`` rows for the requested year(s)
only.

Per Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/source-attributions.md``; the
:func:`test_maddison_project_attribution_matches_attributions_doc`
test enforces byte-for-byte consistency.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..db.session import session_scope
from .maddison_project_db import (
    register_maddison_project_source,
    write_maddison_project_observations,
    write_maddison_project_run_manifest,
)
from .maddison_project_io import (
    MADDISON_PROJECT_ATTRIBUTION,
    MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
    MADDISON_PROJECT_PROXY_YEAR,
    MADDISON_PROJECT_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
    write_maddison_project_parquet,
)
from .maddison_project_xlsx import read_maddison_project

# Re-exports: ``MADDISON_PROJECT_ATTRIBUTION``,
# ``MADDISON_PROJECT_SOURCE_KEY``, and :class:`IndicatorSpec` are
# defined in :mod:`maddison_project_io` to break the import cycle,
# but callers (tests, the CLI) historically import them from here.
# Re-export so the public surface stays in one place. The DB
# helpers are also re-exported so the test-builder's tests can call
# them through the orchestrator module -- the WGI / BTI / CIRIGHTS
# pattern.


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class MaddisonProjectIngestResult(BaseModel):
    """Summary of a single ``ingest_maddison_project`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: the ``leaders-db ingest-source
    --source maddison_project`` command reads ``source_id``,
    ``parquet_path``, ``observation_rows``, ``countries``,
    ``years``, and ``indicators`` to print the end-of-run summary.
    The manifest writer in :mod:`maddison_project_db` also
    consumes the same fields. Pydantic v2 models are the standard
    for any payload that crosses a file, CLI, provider, or
    artifact boundary (``docs/coding-guidelines.md`` § Python
    Standards).

    Carries the ``year_window`` so the CLI can print the proxy /
    source-edition semantics without re-reading the parquet
    metadata.
    """

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow Maddison Project parquet.",
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
        description="Distinct ``countrycode`` s in the narrow frame.",
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
            "The (start_year, end_year) range the run covered (e.g. "
            "``(2022, 2022)`` for a single-year 2023 proxy run)."
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
    def _year_window_is_int_pair(
        cls, value: tuple[int, int],
    ) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"year_window must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        if value[0] > value[1]:
            raise ValueError(
                f"year_window start ({value[0]}) must be <= "
                f"end ({value[1]})"
            )
        return value

    @property
    def attribution(self) -> str:
        """The Maddison Project attribution text (Always-On Rule #15)."""
        return MADDISON_PROJECT_ATTRIBUTION


# ---------------------------------------------------------------------------
# Attribution (Rule #15)
# ---------------------------------------------------------------------------


def attribution() -> str:
    """Return the Maddison Project attribution block for public
    output.

    Per AGENTS.md Always-On Rule #15, every public output (Stage 15
    report, manual-review queue, exported CSV, run log, CLI end-of-
    run echo) that touches Maddison Project data must include this
    block verbatim. The exact wording is the one in
    ``docs/source-attributions.md``; do not paraphrase.
    """
    return MADDISON_PROJECT_ATTRIBUTION


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def ingest_maddison_project(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> MaddisonProjectIngestResult:
    """Run Stage 2 for the Maddison Project Database 2023 end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog (3 indicators: ``gdppc``, ``pop``,
       derived ``__derived_gdp_total__``).
    2. Read the long-format frame via
       :func:`read_maddison_project`. One openpyxl pass over the
       ``Full data`` sheet; per-cell coercion; derived GDP total
       computed at row time when both ``gdppc`` and ``pop`` are
       non-NaN.
    3. Write the narrow parquet under
       ``data/processed/maddison_project/`` and attach the Maddison
       attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Write the run-manifest JSON (with proxy_year_semantics when
       the caller asked for ``year=2023``) as the audit trail.
    6. Returns a :class:`MaddisonProjectIngestResult` summary.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source maddison_project``
    and the tests call it.

    Args:
        year: filter to a single year (e.g. ``2022``). Default: all
            years present in the xlsx (1-2022, ~131,144 rows).
            ``year=2023`` is mapped to the 2022 proxy (1-year-gap
            pattern, per CIRIGHTS / UNDP HDI / Leader Survival).
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake
            path.
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

    # Year 2023 -> 2022 proxy (per architecture §4 + CIRIGHTS /
    # UNDP HDI / Leader Survival 1-year-gap pattern). The
    # orchestrator surfaces the proxy mapping on the result so the
    # manifest can record it.
    requested_year = year
    effective_year = year
    proxy_year_semantics: str | None = None
    if (
        year is not None
        and year == MADDISON_PROJECT_PROXY_REQUESTED_YEAR
    ):
        effective_year = MADDISON_PROJECT_PROXY_YEAR
        proxy_year_semantics = (
            f"year={MADDISON_PROJECT_PROXY_REQUESTED_YEAR} -> "
            f"data_year={MADDISON_PROJECT_PROXY_YEAR} "
            "(1-year-gap proxy, per the CIRIGHTS / UNDP HDI / "
            "Leader Survival pattern; the 2023 Maddison release "
            "ends at 2022)."
        )

    # Read the long-format frame. The ``year=`` argument affects
    # the schema validation AND the per-row filter; the long frame
    # itself is correctly scoped for the parquet write + the DB
    # observation write.
    narrow_df = read_maddison_project(
        year=effective_year,
        xlsx_path=xlsx_path,
        catalog_path=catalog_path,
    )

    # Surface the audit-trail extras from the narrow frame.
    year_window_attr = narrow_df.attrs.get("year_window", (0, 0))
    year_window_tuple: tuple[int, int] = (
        int(year_window_attr[0]),
        int(year_window_attr[1]),
    )

    # Write the narrow parquet. Even an empty narrow frame is
    # written so downstream stages can detect "this run produced
    # no data" without re-reading the xlsx.
    parquet = write_maddison_project_parquet(
        narrow_df, parquet_path=parquet_path,
    )

    # DB writes (idempotent by source/year scope).
    with session_scope() as session:
        source_id = register_maddison_project_source(session)
        rows = write_maddison_project_observations(
            session, source_id, narrow_df, catalog_path=catalog_path,
        )

    result = MaddisonProjectIngestResult(
        source_id=source_id,
        parquet_path=parquet,
        observation_rows=rows,
        countries=(
            int(narrow_df["countrycode"].nunique())
            if not narrow_df.empty
            else 0
        ),
        years=(
            tuple(
                sorted({int(y) for y in narrow_df["year"].tolist()}),
            )
            if not narrow_df.empty
            else ()
        ),
        indicators=len(specs),
        year_window=year_window_tuple,
    )
    # Audit trail: write the run manifest every time (not
    # best-effort). Rule #15 makes the attribution normative; the
    # manifest is how downstream stages find it without re-reading
    # the parquet metadata. The proxy_year_semantics /
    # requested_year are surfaced here (not on the result model)
    # so the result's 7-field contract is preserved while the
    # manifest still records the 2023 -> 2022 proxy mapping.
    write_maddison_project_run_manifest(
        result,
        catalog_path=catalog_path,
        proxy_year_semantics=proxy_year_semantics,
        requested_year=(
            int(requested_year) if requested_year is not None else None
        ),
    )
    return result


# Public surface: ``MADDISON_PROJECT_ATTRIBUTION``,
# ``MADDISON_PROJECT_SOURCE_KEY``, and :class:`IndicatorSpec` are
# defined in :mod:`maddison_project_io` (the lowest-level module)
# to break the import cycle. The re-exports at the top of this
# file make them importable from the canonical orchestrator path;
# this ``__all__`` documents the full public surface. The DB
# helpers are also re-exported so the tests can drive the adapter
# through the orchestrator module.
__all__ = [
    "MADDISON_PROJECT_ATTRIBUTION",
    "MADDISON_PROJECT_SOURCE_KEY",
    "IndicatorSpec",
    "MaddisonProjectIngestResult",
    "attribution",
    "ingest_maddison_project",
    "register_maddison_project_source",
    "write_maddison_project_observations",
    "write_maddison_project_run_manifest",
]
