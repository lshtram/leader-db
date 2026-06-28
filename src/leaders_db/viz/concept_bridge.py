"""Bridge source concepts into visualization metric rows."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_GDP_TOTAL,
    CONCEPT_POPULATION,
    KNOWN_CONCEPT_KEYS,
    ConceptObservation,
    extract_concept_result,
)
from leaders_db.sources.contracts import (
    EvidenceQuery,
    NormalizedObservation,
    SourceId,
    SourceWarning,
)
from leaders_db.sources.query import EvidenceRepository

from .metrics import lookup_metric

CONCEPT_METRIC_SOURCE_PRECEDENCE: tuple[str, ...] = (
    "world_bank_wdi",
    "maddison_project",
    "pwt",
)

CONCEPT_METRIC_IDS: dict[str, str] = {
    CONCEPT_GDP_PER_CAPITA: "concept.gdp_per_capita",
    CONCEPT_POPULATION: "concept.population",
    CONCEPT_GDP_TOTAL: "concept.gdp_total",
}


@dataclass(frozen=True)
class ConceptMetricMapping:
    """Explicit mapping from a source concept to a viz metric id."""

    concept_key: str
    metric_id: str
    source_precedence: tuple[str, ...]


@dataclass(frozen=True)
class ConceptCoverageDiagnostic:
    """Per-concept/per-source extraction diagnostics for metric publication."""

    concept_key: str
    metric_id: str
    source_id: SourceId
    observation_rows: int
    concept_rows: int
    warning_codes: tuple[str, ...]
    coverage_status: str


@dataclass(frozen=True)
class ConceptMetricPublishResult:
    """Concept-to-viz publication output and diagnostics."""

    metric_rows: pd.DataFrame
    coverage: tuple[ConceptCoverageDiagnostic, ...]
    warnings: tuple[SourceWarning, ...]


def concept_metric_mappings() -> tuple[ConceptMetricMapping, ...]:
    """Return the canonical concept-to-viz metric mapping list."""

    return tuple(
        ConceptMetricMapping(
            concept_key=concept_key,
            metric_id=metric_id,
            source_precedence=CONCEPT_METRIC_SOURCE_PRECEDENCE,
        )
        for concept_key, metric_id in CONCEPT_METRIC_IDS.items()
    )


def publish_concept_metrics(
    repository: EvidenceRepository,
    *,
    concept_keys: Sequence[str] = KNOWN_CONCEPT_KEYS,
    source_ids: Sequence[SourceId] | None = None,
) -> ConceptMetricPublishResult:
    """Extract concept rows from SQL/in-memory evidence and shape viz metrics."""

    observations = repository.query_observations(EvidenceQuery(source_ids=source_ids))
    rows: list[dict[str, object]] = []
    diagnostics: list[ConceptCoverageDiagnostic] = []
    warnings: list[SourceWarning] = []
    diagnostic_sources = _diagnostic_source_slugs(source_ids)

    for concept_key in concept_keys:
        metric_id = _metric_id_for_concept(concept_key)
        result = extract_concept_result(observations, concept_key)
        warnings.extend(result.warnings)
        rows.extend(_metric_row(metric_id, row) for row in result.observations)
        diagnostics.extend(
            _coverage_diagnostic(
                concept_key,
                metric_id,
                source_slug,
                observations,
                result.observations,
                result.warnings,
            )
            for source_slug in diagnostic_sources
        )

    return ConceptMetricPublishResult(
        metric_rows=pd.DataFrame(rows),
        coverage=tuple(diagnostics),
        warnings=tuple(warnings),
    )


def _metric_id_for_concept(concept_key: str) -> str:
    try:
        return CONCEPT_METRIC_IDS[concept_key]
    except KeyError as exc:
        known = sorted(CONCEPT_METRIC_IDS)
        raise ValueError(
            f"No viz metric mapping for concept {concept_key!r}; known: {known}"
        ) from exc


def _metric_row(metric_id: str, row: ConceptObservation) -> dict[str, object]:
    metric = lookup_metric(metric_id)
    metric_label = metric.label if metric is not None else metric_id
    value_unit = row.unit or (metric.unit if metric is not None else None) or ""
    warning_codes = tuple(warning.code for warning in row.warnings)
    return {
        "query_id": "concept_metric_bridge",
        "metric_id": metric_id,
        "metric_label": metric_label,
        "grain": "country_year",
        "year": row.year,
        "country_iso3": row.country_code,
        "country_name": row.country_name,
        "leader_name": row.leader_name,
        "category_key": "",
        "value": row.value,
        "value_unit": value_unit,
        "aggregation": "none",
        "transform": "identity",
        "source_keys": row.source_id.slug,
        "source_row_references": "|".join(row.input_observation_ids),
        "attribution_texts": "",
        "provenance_json": json.dumps(
            {
                "concept_key": row.concept_key,
                "source_indicator_codes": row.source_indicator_codes,
                "input_observation_ids": row.input_observation_ids,
                "source_version": row.source_version,
                "recipe_key": row.recipe_key,
            },
            sort_keys=True,
        ),
        "coverage_status": "available" if row.value_type == "numeric" else "missing",
        "confidence_score": None,
        "missingness_flags": "|".join((*row.quality_flags, *warning_codes)),
        "client_matrix_policy": "excluded",
        "client_score": None,
        "system_proposed_score": None,
        "final_score": None,
        "score_delta_vs_client": None,
    }


def _diagnostic_source_slugs(source_ids: Sequence[SourceId] | None) -> tuple[str, ...]:
    if source_ids is not None:
        return tuple(source_id.slug for source_id in source_ids)
    return CONCEPT_METRIC_SOURCE_PRECEDENCE


def _coverage_diagnostic(
    concept_key: str,
    metric_id: str,
    source_slug: str,
    observations: Sequence[NormalizedObservation],
    concept_rows: Sequence[ConceptObservation],
    warnings: Sequence[SourceWarning],
) -> ConceptCoverageDiagnostic:
    observation_count = sum(
        1 for observation in observations if observation.source_id.slug == source_slug
    )
    concept_count = sum(1 for row in concept_rows if row.source_id.slug == source_slug)
    warning_codes = tuple(
        warning.code
        for warning in warnings
        if warning.source_id is not None and warning.source_id.slug == source_slug
    )
    return ConceptCoverageDiagnostic(
        concept_key=concept_key,
        metric_id=metric_id,
        source_id=SourceId(slug=source_slug),
        observation_rows=observation_count,
        concept_rows=concept_count,
        warning_codes=warning_codes,
        coverage_status="available" if concept_count else "missing",
    )


__all__ = [
    "CONCEPT_METRIC_IDS",
    "CONCEPT_METRIC_SOURCE_PRECEDENCE",
    "ConceptCoverageDiagnostic",
    "ConceptMetricMapping",
    "ConceptMetricPublishResult",
    "concept_metric_mappings",
    "publish_concept_metrics",
]
