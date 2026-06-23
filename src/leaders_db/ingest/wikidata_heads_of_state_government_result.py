"""Stage 2 -- Wikidata heads-of-state-and-government result model.

Pydantic ``BaseModel`` (not a dataclass) because the result crosses
a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the core
fields to print the end-of-run summary, and the manifest writer in
:mod:`wikidata_heads_of_state_government_db` also consumes the same
fields.

Fields: 9 total -- ``source_id``, ``parquet_path``,
``observation_rows``, ``countries``, ``persons``, ``years``,
``requested_year``, ``indicators``, plus the HTTP cache audit
``indicators_cached`` / ``indicators_fetched`` -- see the
``WikidataHoSGoGIngestResult`` model below.

Pydantic v2 models are the standard for any payload that crosses a
file, CLI, provider, or artifact boundary
(:file:`docs/process/coding-guidelines.md` § Python Standards).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .wikidata_heads_of_state_government_io import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION,
)


class WikidataHoSGoGIngestResult(BaseModel):
    """Summary of a single ``ingest_wikidata_heads_of_state_government`` run."""

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow Wikidata parquet."
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this "
            "run (one per SPARQL binding whose office matches a "
            "catalog spec)."
        ),
    )
    countries: int = Field(
        ...,
        ge=0,
        description=(
            "Distinct ``country_qid``s in the long frame."
        ),
    )
    persons: int = Field(
        ...,
        ge=0,
        description=(
            "Distinct ``person_qid``s in the long frame."
        ),
    )
    years: tuple[int, ...] = Field(
        ..., description="Calendar years present in the frame, sorted."
    )
    requested_year: int | None = Field(
        None,
        description=(
            "The year the caller requested (None for the "
            "all-current-holders run). Recorded for the audit trail."
        ),
    )
    indicators: int = Field(
        ...,
        ge=0,
        description="Number of catalog indicators used (offices).",
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
            "How many of the catalog indicators were HTTP-fetched "
            "in this run."
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
        """The Wikidata attribution text (Always-On Rule #15)."""
        return WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION


__all__ = ["WikidataHoSGoGIngestResult"]
