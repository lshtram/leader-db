"""Stage 2 -- Transparency International CPI result model.

Pydantic ``BaseModel`` (not a dataclass) because the result crosses
a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the
core fields to print the end-of-run summary, and the manifest
writer in :mod:`transparency_cpi_db` also consumes the same
fields.

Fields: 8 total -- ``source_id``, ``parquet_path``,
``observation_rows``, ``countries``, ``years``, ``indicators``,
``csv_cached``, ``csv_fetched``. The CSV cache audit fields (the
``csv_cached`` / ``csv_fetched`` flags) live on the result so the
CLI end-of-run echo can surface them, mirroring the WHO GHO API
``indicators_cached`` / ``indicators_fetched`` pattern.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .transparency_cpi_io import TRANSPARENCY_CPI_ATTRIBUTION


class TransparencyCpiIngestResult(BaseModel):
    """Summary of a single ``ingest_transparency_cpi`` run.

    See module docstring for the design rationale. Pydantic v2
    models are the standard for any payload that crosses a file,
    CLI, provider, or artifact boundary
    (:file:`docs/process/coding-guidelines.md` § Python Standards).
    """

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ...,
        description=(
            "Path to the narrow Transparency International CPI "
            "parquet."
        ),
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this "
            "run."
        ),
    )
    countries: int = Field(
        ...,
        ge=0,
        description="Distinct ``iso3``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted."
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used."
    )
    csv_cached: bool = Field(
        ...,
        description=(
            "Whether the per-year CSV was read from the local cache "
            "(no HTTP call)."
        ),
    )
    csv_fetched: bool = Field(
        ...,
        description=(
            "Whether the per-year CSV was HTTP-fetched in this run."
        ),
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...]
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("years must be a sorted tuple of unique ints")
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        return value

    @property
    def attribution(self) -> str:
        """The Transparency International CPI attribution text (Always-On Rule #15)."""
        return TRANSPARENCY_CPI_ATTRIBUTION


__all__ = ["TransparencyCpiIngestResult"]
