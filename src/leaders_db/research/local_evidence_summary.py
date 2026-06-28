"""Local structured evidence summaries for ruler-period research helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_GDP_TOTAL,
    CONCEPT_POPULATION,
    KNOWN_CONCEPT_KEYS,
    ConceptCatalogError,
    ConceptObservation,
    extract_concept_result,
    resolve_concept,
)
from leaders_db.sources.contracts import EvidenceQuery, SourceWarning
from leaders_db.sources.query import EvidenceRepository

DEFAULT_RULER_EVIDENCE_CONCEPTS: tuple[str, ...] = (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_POPULATION,
    CONCEPT_GDP_TOTAL,
)


@dataclass(frozen=True)
class RulerPeriodEvidenceRequest:
    """Request for a local evidence summary over a ruler time window."""

    country: str
    leader: str | None
    start_year: int
    end_year: int
    concepts: tuple[str, ...] = DEFAULT_RULER_EVIDENCE_CONCEPTS


def summarize_ruler_period_evidence(
    repository: EvidenceRepository,
    request: RulerPeriodEvidenceRequest,
) -> dict[str, object]:
    """Return a compact JSON-serializable local evidence summary.

    The summary reads only through :class:`EvidenceRepository` and uses the
    existing concept catalog. ``leader`` is preserved as request metadata only;
    no ruler matching or leader-scoped filtering is attempted in this helper.
    """

    _validate_request(request)
    years = tuple(range(request.start_year, request.end_year + 1))
    observations = repository.query_observations(
        EvidenceQuery(years=years, countries=(request.country,))
    )

    concept_keys = _resolved_concept_keys(request.concepts)
    warnings: list[dict[str, object]] = []
    available: dict[str, dict[str, dict[str, dict[str, list[dict[str, object]]]]]] = {}
    coverage: dict[str, dict[str, object]] = {}

    for concept_key in concept_keys:
        result = extract_concept_result(observations, concept_key)
        concept_rows = _filter_concept_rows(result.observations, request.country, years)
        available[concept_key] = _group_rows(concept_rows)
        coverage[concept_key] = _coverage_payload(concept_rows, years)
        warnings.extend(_warning_payload(warning) for warning in result.warnings)
        if not concept_rows:
            warnings.append(
                {
                    "code": "evidence_gap",
                    "message": "No local structured observations matched this concept/window.",
                    "severity": "warning",
                    "concept_key": concept_key,
                }
            )

    return {
        "request": {
            "country": request.country,
            "leader": request.leader,
            "start_year": request.start_year,
            "end_year": request.end_year,
            "concepts": list(concept_keys),
            "leader_matching": "not_attempted",
            "client_matrix_policy": "excluded_as_evidence",
        },
        "resolved_concepts": [_concept_payload(concept_key) for concept_key in concept_keys],
        "available_observations": available,
        "coverage": coverage,
        "warnings": warnings,
    }


def parse_concept_options(values: Sequence[str] | None) -> tuple[str, ...]:
    """Parse repeatable and comma-separated concept CLI values."""

    if not values:
        return DEFAULT_RULER_EVIDENCE_CONCEPTS
    parsed = tuple(
        part.strip()
        for value in values
        for part in value.split(",")
        if part.strip()
    )
    if not parsed:
        return DEFAULT_RULER_EVIDENCE_CONCEPTS
    return tuple(dict.fromkeys(parsed))


def _validate_request(request: RulerPeriodEvidenceRequest) -> None:
    if not request.country.strip():
        raise ValueError("country must be non-empty")
    if request.end_year < request.start_year:
        raise ValueError("end_year must be greater than or equal to start_year")
    for concept_key in request.concepts:
        if concept_key not in KNOWN_CONCEPT_KEYS:
            raise ValueError(
                f"Unknown concept key {concept_key!r}; known concepts: {list(KNOWN_CONCEPT_KEYS)}"
            )


def _resolved_concept_keys(concepts: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(concepts))


def _filter_concept_rows(
    rows: Sequence[ConceptObservation],
    country: str,
    years: Sequence[int],
) -> tuple[ConceptObservation, ...]:
    year_set = set(years)
    return tuple(
        row for row in rows
        if row.year in year_set and country in (row.country_code, row.country_name)
    )


def _group_rows(
    rows: Sequence[ConceptObservation],
) -> dict[str, dict[str, dict[str, list[dict[str, object]]]]]:
    grouped: dict[str, dict[str, dict[str, list[dict[str, object]]]]] = {}
    for row in sorted(rows, key=_row_sort_key):
        country_key = row.country_code or row.country_name or "unknown_country"
        year_key = str(row.year) if row.year is not None else "unknown_year"
        source_key = row.source_id.slug
        grouped.setdefault(country_key, {}).setdefault(year_key, {}).setdefault(
            source_key, []
        ).append(_row_payload(row))
    return grouped


def _row_sort_key(row: ConceptObservation) -> tuple[str, int, str, tuple[str, ...]]:
    return (
        row.country_code or row.country_name or "",
        row.year if row.year is not None else -1,
        row.source_id.slug,
        row.input_observation_ids,
    )


def _row_payload(row: ConceptObservation) -> dict[str, object]:
    return {
        "country_code": row.country_code,
        "country_name": row.country_name,
        "year": row.year,
        "source_id": row.source_id.slug,
        "source_version": row.source_version,
        "value": row.value,
        "value_type": row.value_type,
        "unit": row.unit,
        "scale": row.scale,
        "source_indicator_codes": list(row.source_indicator_codes),
        "input_observation_ids": list(row.input_observation_ids),
        "quality_flags": list(row.quality_flags),
        "warning_codes": [warning.code for warning in row.warnings],
        "recipe_key": row.recipe_key,
    }


def _coverage_payload(
    rows: Sequence[ConceptObservation],
    years: Sequence[int],
) -> dict[str, object]:
    years_with_observations = sorted({row.year for row in rows if row.year is not None})
    missing_years = [year for year in years if year not in years_with_observations]
    return {
        "observation_count": len(rows),
        "source_count": len({row.source_id.slug for row in rows}),
        "years_requested": len(years),
        "years_with_observations": years_with_observations,
        "missing_years": missing_years,
        "first_year": years_with_observations[0] if years_with_observations else None,
        "last_year": years_with_observations[-1] if years_with_observations else None,
        "coverage_status": "available" if rows else "missing",
    }


def _concept_payload(concept_key: str) -> dict[str, object]:
    try:
        mappings = resolve_concept(concept_key)
    except ConceptCatalogError:
        mappings = ()
    return {
        "concept_key": concept_key,
        "supported_source_ids": [mapping.source_id.slug for mapping in mappings],
        "mapping_types": sorted({mapping.mapping_type for mapping in mappings}),
    }


def _warning_payload(warning: SourceWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "source_id": warning.source_id.slug if warning.source_id is not None else None,
        "context": dict(warning.context),
    }


__all__ = [
    "DEFAULT_RULER_EVIDENCE_CONCEPTS",
    "RulerPeriodEvidenceRequest",
    "parse_concept_options",
    "summarize_ruler_period_evidence",
]
