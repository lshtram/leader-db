"""Stage 2 -- FAS Nuclear Notebook result model.

Pydantic ``BaseModel`` (not a dataclass) because the result crosses
a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the
core fields to print the end-of-run summary, and the manifest
writer in :mod:`fas_db` also consumes the same fields.

Fields: 10 total -- ``source_id``, ``parquet_path``,
``observation_rows``, ``countries``, ``years``, ``indicators``,
``snapshot_year``, ``html_cached``, ``html_fetched``,
``status_page_url``. The HTML cache audit fields (the
``html_cached`` / ``html_fetched`` flags) live on the result so
the CLI end-of-run echo can surface them, mirroring the WHO GHO
API ``indicators_cached`` / ``indicators_fetched`` and the
Transparency International CPI ``csv_cached`` / ``csv_fetched``
patterns.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .fas_io import FAS_ATTRIBUTION, FAS_STATUS_PAGE_URL


class FasIngestResult(BaseModel):
    """Summary of a single ``ingest_fas`` run.

    See module docstring for the design rationale. Pydantic v2
    models are the standard for any payload that crosses a file,
    CLI, provider, or artifact boundary
    (:file:`docs/process/coding-guidelines.md` § Python Standards).
    """

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow FAS parquet."
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
        description="Distinct country names in the narrow frame.",
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted."
    )
    indicators: int = Field(
        ..., ge=0, description="Number of catalog indicators used."
    )
    snapshot_year: int = Field(
        ...,
        ge=1900,
        description=(
            "FAS page snapshot year parsed from the meta date "
            "element (e.g. 2014 for the live page). Recorded for "
            "audit; the Stage 11 confidence engine penalises the "
            "temporal-fit gap between this snapshot year and the "
            "prototype's target year."
        ),
    )
    html_cached: bool = Field(
        ...,
        description=(
            "Whether the FAS HTML was read from the local cache "
            "(no HTTP call)."
        ),
    )
    html_fetched: bool = Field(
        ...,
        description=(
            "Whether the FAS HTML was HTTP-fetched in this run."
        ),
    )
    status_page_url: str = Field(
        ..., description="The FAS status page URL."
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
        """The FAS attribution text (Always-On Rule #15)."""
        return FAS_ATTRIBUTION


__all__ = ["FasIngestResult"]


# Module-level fallback for the status page URL constant when
# :data:`fas_io.FAS_STATUS_PAGE_URL` is unavailable (defensive;
# the constant is normally always defined).
_DEFAULT_STATUS_PAGE_URL: str = FAS_STATUS_PAGE_URL
