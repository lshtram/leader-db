"""Stage 2 -- REIGN (Bell 2016): Pydantic result model.

This module is the result-model half of the REIGN adapter. It owns:

- :class:`ReignIngestResult` -- the 8-field Pydantic ``BaseModel``
  returned by :func:`leaders_db.ingest.reign.ingest_reign`.
  Mirrors the V-Dem / CIRIGHTS / UNDP HDI / WHO GHO API /
  Archigos result shapes for consistency: 8 fields covering
  source_id, parquet_path, observation_rows, countries, years,
  indicators, year_window, attribution.

REIGN-specific extras vs the V-Dem result:

- ``year_window``: a ``(start_year, end_year)`` tuple representing
  the min/max year in the long frame (e.g. ``(2020, 2020)`` for
  a single-year 2020 run, or ``(1950, 2021)`` for the full
  unfiltered run).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .reign_io import REIGN_ATTRIBUTION


class ReignIngestResult(BaseModel):
    """Summary of a single ``ingest_reign`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: the CLI subcommand reads ``source_id``,
    ``parquet_path``, ``observation_rows``, ``countries``, ``years``,
    and ``indicators`` to print the end-of-run summary. Pydantic
    v2 models are the standard for any payload that crosses a
    file, CLI, provider, or artifact boundary
    (``docs/coding-guidelines.md`` § Python Standards).
    """

    source_id: int = Field(
        ..., ge=1,
        description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow REIGN parquet.",
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
            "year in the long frame."
        ),
    )
    attribution: str = Field(
        default=REIGN_ATTRIBUTION,
        description=(
            "The REIGN attribution block (Always-On Rule #15). "
            "Embedded in the result so the CLI end-of-run echo does "
            "not need a separate import."
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


__all__ = ["ReignIngestResult"]
