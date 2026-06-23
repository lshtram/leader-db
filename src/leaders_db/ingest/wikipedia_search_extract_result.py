"""Stage 2 -- Wikipedia search-extract result model.

Pydantic ``BaseModel`` (not a dataclass) because the result crosses
a CLI boundary: :func:`leaders_db.cli.ingest_source` reads the core
fields to print the end-of-run summary, and the manifest writer in
:mod:`wikipedia_search_extract_db` also consumes the same fields.

Fields: 7 total -- ``source_id``, ``parquet_path``,
``observation_rows``, ``queries``, ``indicators``,
``indicators_cached``, ``indicators_fetched``. The HTTP cache audit
fields live on the result so the CLI end-of-run echo can surface
them, mirroring the V-Dem / WDI / WHO GHO API / Wikidata pattern.

Pydantic v2 models are the standard for any payload that crosses a
file, CLI, provider, or artifact boundary
(:file:`docs/process/coding-guidelines.md` § Python Standards).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .wikipedia_search_extract_io import (
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION,
)


class WikipediaSearchExtractIngestResult(BaseModel):
    """Summary of a single ``ingest_wikipedia_search_extract`` run."""

    source_id: int = Field(
        ..., ge=1, description="The ``sources.id`` row created/updated."
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow Wikipedia parquet."
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this "
            "run (one per Action API page / search hit whose action "
            "matches a catalog spec)."
        ),
    )
    queries: tuple[str, ...] = Field(
        ..., description="Caller-supplied queries, in input order."
    )
    indicators: int = Field(
        ...,
        ge=0,
        description="Number of catalog indicators used (actions).",
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

    @property
    def attribution(self) -> str:
        """The Wikipedia attribution text (Always-On Rule #15)."""
        return WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION


__all__ = ["WikipediaSearchExtractIngestResult"]
