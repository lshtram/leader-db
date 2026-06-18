"""Stage 2 -- UNDP HDI ingest result model."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .undp_hdi_io import UNDP_HDI_ATTRIBUTION


class UndpHdiIngestResult(BaseModel):
    """Summary of a single ``ingest_undp_hdi`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the core
    fields to print the end-of-run summary. The manifest writer consumes
    the same fields.

    Fields: 8 total -- ``source_id``, ``parquet_path``,
    ``observation_rows``, ``countries``, ``years``, ``indicators``,
    ``regions_covered``, ``year_window``. Proxy-year semantics live in
    the manifest, not on the result, preserving this public contract.
    """

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow UNDP HDI parquet."
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this run."
        ),
    )
    countries: int = Field(
        ..., ge=0, description="Distinct ``iso3``s in the narrow frame."
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted."
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used."
    )
    regions_covered: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted list of region codes found in the narrow frame "
            "(known codes plus unknown / blank values preserved per §6)."
        ),
    )
    year_window: tuple[int, int] = Field(
        ...,
        description=(
            "(start_year, end_year) tuple representing the min/max "
            "year in the narrow frame."
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
                    f"years must contain ints, got {type(one_year).__name__}"
                )
        return value

    @field_validator("regions_covered")
    @classmethod
    def _regions_covered_is_sorted_unique(cls, value: list[str]) -> list[str]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "regions_covered must be a sorted list of unique strings"
            )
        return value

    @field_validator("year_window")
    @classmethod
    def _year_window_is_ordered_pair(
        cls, value: tuple[int, int]
    ) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        if value[0] > value[1]:
            raise ValueError("year_window must have start <= end")
        return value

    @property
    def attribution(self) -> str:
        """The UNDP HDI attribution text (Always-On Rule #15)."""
        return UNDP_HDI_ATTRIBUTION


__all__ = ["UndpHdiIngestResult"]
