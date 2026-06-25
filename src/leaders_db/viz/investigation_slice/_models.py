"""Public dataclasses and the supported question catalog for the slice.

The slice ships a frozen set of dataclasses so the caller-facing
contract is type-safe and immutable across a single run. The supported
question catalog is built once at import time so unknown keys surface
as :class:`UnknownInvestigationQuestionError` with the known list,
not as silent default fallbacks.

This module also owns the small helpers used to fill
:attr:`SourceCoverageRow.concept_rows` after concept extraction:
:func:`concept_rows_by_source` aggregates the per-source count and
:func:`finalize_coverage_rows` rebuilds the frozen coverage row
instances with the actual count. These helpers live next to the
dataclass because they are tightly coupled to the dataclass shape
and have no other natural home.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ...sources.concepts import CONCEPT_GDP_PER_CAPITA, ConceptObservation
from ...sources.contracts import SourceWarning
from ...sources.registry import SourceRegistry
from ...sources.runner import SourceIngestRunner

# ---------------------------------------------------------------------------
# Question catalog (constrained, deterministic)
# ---------------------------------------------------------------------------


#: Ordered tuple of supported investigation question keys.
#: Adding a new question requires adding an entry here AND in
#: :data:`SUPPORTED_QUESTIONS` so the slice cannot silently invent
#: questions on the fly.
SUPPORTED_QUESTION_KEYS: tuple[str, ...] = (
    "gdp_per_capita_major_powers",
)


@dataclass(frozen=True)
class InvestigationQuestion:
    """A constrained investigation question supported by the slice.

    The dataclass is frozen so a question spec is immutable across a
    single run. ``question_key`` is the stable registry key (used for
    filename and CLI dispatch); ``concept_key`` is the stable concept
    catalog key; ``display_title`` is the human-readable question
    surfaced in the HTML graph title; ``display_countries`` is the
    ordered list of ISO-3 country codes the slice expects to plot.
    """

    question_key: str
    concept_key: str
    display_title: str
    display_countries: tuple[str, ...]


#: Mapping from supported question keys to their canonical definition.
#: The dict is built once at import time from :data:`SUPPORTED_QUESTION_KEYS`
#: so unknown keys surface as :class:`UnknownInvestigationQuestionError`
#: with the known list, not as silent default fallbacks.
SUPPORTED_QUESTIONS: Mapping[str, InvestigationQuestion] = {
    "gdp_per_capita_major_powers": InvestigationQuestion(
        question_key="gdp_per_capita_major_powers",
        concept_key=CONCEPT_GDP_PER_CAPITA,
        display_title=(
            "Real GDP per capita for major powers (1950-2023)"
        ),
        display_countries=("USA", "GBR", "FRA", "IND", "CHN"),
    ),
}


class UnknownInvestigationQuestionError(ValueError):
    """Raised when a question key is not in :data:`SUPPORTED_QUESTIONS`."""

    def __init__(self, question_key: str) -> None:
        self.question_key = question_key
        super().__init__(
            f"Unknown investigation question {question_key!r}; "
            f"supported keys: {list(SUPPORTED_QUESTIONS)}"
        )


# ---------------------------------------------------------------------------
# Request / result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvestigationSliceRequest:
    """Caller-facing request contract for the vertical slice.

    ``registry`` is optional: when omitted, the slice builds an
    :class:`InMemorySourceRegistry` with the real PWT, Maddison, and
    WDI adapters registered. Tests pass a registry with fake adapters
    so the slice is exercisable without staged raw bundles.

    ``raw_root`` defaults to ``data/raw`` (project-relative); the
    default data directory is the canonical
    ``data/processed/viz/country-year-chronicle`` folder consumed by
    the existing Superset builder.
    """

    question_key: str
    countries: tuple[str, ...]
    start_year: int
    end_year: int
    raw_root: Path = Path("data/raw")
    data_dir: Path | None = None
    superset_db_path: Path | None = None
    rebuild_superset_db: bool = True
    registry: SourceRegistry | None = None
    runner: SourceIngestRunner | None = None


@dataclass(frozen=True)
class SourceCoverageRow:
    """Per-source coverage row emitted in the slice summary.

    ``requested`` is the set of ``(country, year)`` tuples the slice
    asked the source to cover. ``emitted`` is the count of
    :class:`NormalizedObservation` rows the adapter actually returned.
    ``concept_rows`` is the count of those rows that survived concept
    extraction for the slice's concept key inside the requested scope;
    it is filled in by the caller (after concept extraction) so the
    summary envelope can show how many gdp_per_capita rows each source
    ultimately contributed.
    """

    source_id: str
    requested: int
    emitted: int
    concept_rows: int
    readiness_ready: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InvestigationSliceResult:
    """End-of-slice summary returned by :func:`run_investigation_slice`."""

    question: InvestigationQuestion
    countries: tuple[str, ...]
    start_year: int
    end_year: int
    csv_path: Path
    html_path: Path
    concept_rows: tuple[ConceptObservation, ...]
    source_coverage: tuple[SourceCoverageRow, ...]
    concept_warnings: tuple[SourceWarning, ...]
    superset_db_path: Path | None
    superset_db_tables: tuple[str, ...] = ()

    @property
    def source_count(self) -> int:
        """Number of sources the slice attempted to dispatch."""
        return len(self.source_coverage)

    @property
    def total_concept_rows(self) -> int:
        """Total concept rows the slice emitted (across all sources)."""
        return len(self.concept_rows)


# ---------------------------------------------------------------------------
# Coverage-row post-processing helpers
# ---------------------------------------------------------------------------


def concept_rows_by_source(
    concept_rows: Iterable[ConceptObservation],
) -> dict[str, int]:
    """Return ``{source_slug: concept_row_count}`` for ``concept_rows``.

    Counts preserve order of first occurrence so iteration is
    deterministic when surfaced in debugging output. The slice uses
    this to populate :attr:`SourceCoverageRow.concept_rows` after
    concept extraction -- the per-source dispatcher can only count
    raw :class:`NormalizedObservation` rows, not which ones survived
    concept extraction inside the requested scope.
    """
    counts: dict[str, int] = {}
    for row in concept_rows:
        slug = row.source_id.slug
        counts[slug] = counts.get(slug, 0) + 1
    return counts


def finalize_coverage_rows(
    coverage_rows: Iterable[SourceCoverageRow],
    per_source_counts: Mapping[str, int],
) -> tuple[SourceCoverageRow, ...]:
    """Return a new tuple of coverage rows with ``concept_rows`` filled in.

    Each row in ``coverage_rows`` is rebuilt via
    :func:`dataclasses.replace` so the original frozen instances stay
    untouched. A source without any concept rows keeps its
    ``concept_rows=0`` placeholder -- that is the truthful result for
    a source that emitted observations which did not survive the
    concept catalog (e.g. PWT population rows for the
    ``gdp_per_capita`` concept).
    """
    return tuple(
        dataclasses.replace(
            row,
            concept_rows=per_source_counts.get(row.source_id, 0),
        )
        for row in coverage_rows
    )
