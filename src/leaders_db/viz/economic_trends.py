"""Reusable economic trend publishing helper over concept metrics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_GDP_TOTAL,
    CONCEPT_POPULATION,
)
from leaders_db.sources.contracts import SourceId, SourceWarning
from leaders_db.sources.query import EvidenceRepository

from .concept_bridge import ConceptCoverageDiagnostic, publish_concept_metrics
from .output_contract import VIZ_OUTPUT_REQUIRED_COLUMNS

ECONOMIC_TREND_CONCEPT_KEYS: tuple[str, ...] = (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_POPULATION,
    CONCEPT_GDP_TOTAL,
)

ECONOMIC_TRENDS_CSV_NAME = "viz_economic_trends.csv"


@dataclass(frozen=True)
class EconomicTrendRequest:
    """Country-year scope for the reusable economic trend proof path."""

    countries: tuple[str, ...]
    start_year: int
    end_year: int
    source_ids: tuple[SourceId, ...] | None = None


@dataclass(frozen=True)
class EconomicTrendResult:
    """Filtered economic trend rows and source/concept diagnostics."""

    trend_rows: pd.DataFrame
    coverage: tuple[ConceptCoverageDiagnostic, ...]
    warnings: tuple[SourceWarning, ...]
    csv_path: Path | None = None


def build_economic_trend_table(
    repository: EvidenceRepository,
    request: EconomicTrendRequest,
) -> EconomicTrendResult:
    """Build a chart/report-ready GDP/population trend table from evidence.

    The helper reads only through the ``EvidenceRepository`` boundary, publishes
    the existing GDP-per-capita, population, and total-GDP concepts through the
    concept metric bridge, then filters the bridge output to the requested
    countries and inclusive year range.
    """

    _validate_request(request)
    published = publish_concept_metrics(
        repository,
        concept_keys=ECONOMIC_TREND_CONCEPT_KEYS,
        source_ids=request.source_ids,
    )
    rows = _filter_trend_rows(published.metric_rows, request)
    return EconomicTrendResult(
        trend_rows=rows,
        coverage=published.coverage,
        warnings=published.warnings,
    )


def write_economic_trend_csv(
    repository: EvidenceRepository,
    request: EconomicTrendRequest,
    output_path: Path,
) -> EconomicTrendResult:
    """Write economic trend rows to a deterministic CSV artifact."""

    result = build_economic_trend_table(repository, request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.trend_rows.to_csv(output_path, index=False)
    return EconomicTrendResult(
        trend_rows=result.trend_rows,
        coverage=result.coverage,
        warnings=result.warnings,
        csv_path=output_path,
    )


def _validate_request(request: EconomicTrendRequest) -> None:
    if not _normalized_countries(request.countries):
        raise ValueError("EconomicTrendRequest requires at least one country")
    if request.end_year < request.start_year:
        raise ValueError("EconomicTrendRequest.end_year must be >= start_year")


def _filter_trend_rows(
    frame: pd.DataFrame,
    request: EconomicTrendRequest,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=VIZ_OUTPUT_REQUIRED_COLUMNS)

    countries = _normalized_countries(request.countries)
    filtered = frame[
        frame["country_iso3"].astype(str).str.upper().isin(countries)
        & (frame["year"] >= request.start_year)
        & (frame["year"] <= request.end_year)
    ].copy()
    if filtered.empty:
        return filtered.reset_index(drop=True)
    return filtered.sort_values(
        ["country_iso3", "year", "metric_id", "source_keys", "source_row_references"]
    ).reset_index(drop=True)


def _normalized_countries(countries: Sequence[str]) -> tuple[str, ...]:
    return tuple(country.strip().upper() for country in countries if country.strip())


__all__ = [
    "ECONOMIC_TRENDS_CSV_NAME",
    "ECONOMIC_TREND_CONCEPT_KEYS",
    "EconomicTrendRequest",
    "EconomicTrendResult",
    "build_economic_trend_table",
    "write_economic_trend_csv",
]
