"""Stage 2 -- WHO Global Health Observatory (GHO) OData API result model.

Pydantic ``BaseModel`` (not a dataclass) because the result crosses
a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the
core fields to print the end-of-run summary, and the manifest
writer in :mod:`who_gho_api_db` also consumes the same fields.

Fields: 8 total -- ``source_id``, ``parquet_path``,
``observation_rows``, ``countries``, ``years``, ``indicators``,
``indicators_cached``, ``indicators_fetched``. The HTTP cache
audit fields (the ``indicators_cached`` / ``indicators_fetched``
counts) live on the result so the CLI end-of-run echo can
surface them, mirroring the WDI / WGI / UCDP / SIPRI / PTS /
UNDP HDI pattern.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .who_gho_api_io import WHO_GHO_API_ATTRIBUTION


class WhoGhoApiIngestResult(BaseModel):
    """Summary of a single ``ingest_who_gho_api`` run.

    See module docstring for the design rationale. Pydantic v2
    models are the standard for any payload that crosses a file,
    CLI, provider, or artifact boundary
    (:file:`docs/coding-guidelines.md` § Python Standards).
    """

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow WHO GHO API parquet."
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
        description="Distinct ``iso3``s in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted."
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used."
    )
    indicators_cached: int = Field(
        ...,
        ge=0,
        description=(
            "How many of the catalog indicators were read from the "
            "JSON cache (no HTTP call)."
        ),
    )
    indicators_fetched: int = Field(
        ...,
        ge=0,
        description=(
            "How many of the catalog indicators were HTTP-fetched in "
            "this run."
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

    @property
    def attribution(self) -> str:
        """The WHO GHO API attribution text (Always-On Rule #15)."""
        return WHO_GHO_API_ATTRIBUTION


__all__ = ["WhoGhoApiIngestResult"]
