"""Publish harmonized source concepts into generic country-year facts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.db.models import Country, CountryYear, CountryYearFact
from leaders_db.normalize.countries import alias_to_iso3, normalize_country_name
from leaders_db.sources.concepts import (
    KNOWN_CONCEPT_KEYS,
    ConceptObservation,
    extract_concept_result,
    list_concepts,
    resolve_concept,
)
from leaders_db.sources.contracts import EvidenceQuery, SourceId, SourceWarning
from leaders_db.sources.query import EvidenceRepository

from .country_year_facts import upsert_country_year_fact

CONCEPT_FACT_PRODUCER = "concept_country_year_facts"
CONCEPT_FACT_METHOD_VERSION = "concept-country-year-facts-v1"
DEFAULT_CONCEPT_SOURCE_PRECEDENCE: tuple[str, ...] = (
    "world_bank_wdi",
    "maddison_project",
    "pwt",
    "undp_hdi",
    "who_gho_api",
    "vdem",
    "rsf_press_freedom",
    "fas",
)


@dataclass(frozen=True)
class ConceptCountryYearFactBuildResult:
    """Summary from publishing concept observations to country-year facts."""

    rows_created: int
    rows_updated: int
    total_rows: int
    skipped_without_country_year: int
    adjudication_status_counts: dict[str, int]
    field_counts: dict[str, int]
    warnings: tuple[SourceWarning, ...]


def publish_concept_country_year_facts(
    engine: Engine,
    repository: EvidenceRepository,
    *,
    concept_keys: Sequence[str] = KNOWN_CONCEPT_KEYS,
    source_precedence: Sequence[str] = DEFAULT_CONCEPT_SOURCE_PRECEDENCE,
    source_ids: Sequence[SourceId] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    run_id: str | None = None,
) -> ConceptCountryYearFactBuildResult:
    """Extract concepts and upsert one generic fact per country/year/concept.

    Existing ``country_years`` rows define the publication scope. Concept rows for
    countries or years not present in that scope are skipped rather than creating
    new country/year rows implicitly.
    """

    observations = repository.query_observations(
        EvidenceQuery(
            source_ids=source_ids,
            indicator_codes=_indicator_codes_for_concepts(concept_keys),
            years=_year_filter(start_year, end_year),
        )
    )
    descriptors = {descriptor.concept_key: descriptor for descriptor in list_concepts()}
    concept_rows: list[ConceptObservation] = []
    warnings: list[SourceWarning] = []

    for concept_key in concept_keys:
        result = extract_concept_result(observations, concept_key)
        concept_rows.extend(result.observations)
        warnings.extend(result.warnings)

    with Session(engine, expire_on_commit=False) as session:
        country_years = _country_year_index(
            session,
            start_year=start_year,
            end_year=end_year,
        )
        country_codes_by_name = _country_code_by_normalized_name(session)
        grouped_rows = _group_concept_rows(
            concept_rows,
            country_codes_by_name=country_codes_by_name,
        )
        rows_created = 0
        rows_updated = 0
        skipped_without_country_year = 0

        for key, rows in sorted(grouped_rows.items()):
            country_code, year, concept_key = key
            country_year = country_years.get((country_code, year))
            if country_year is None:
                skipped_without_country_year += 1
                continue
            selected = _select_concept_row(rows, source_precedence)
            payload = _fact_payload(
                country_year,
                concept_key=concept_key,
                field_label=descriptors[concept_key].display_name,
                selected=selected,
                candidates=rows,
                source_precedence=source_precedence,
                run_id=run_id,
            )
            action = upsert_country_year_fact(session, payload)
            rows_created += int(action == "created")
            rows_updated += int(action == "updated")
        session.commit()

    counts = _concept_fact_counts(
        engine,
        concept_keys=tuple(concept_keys),
        start_year=start_year,
        end_year=end_year,
    )
    return ConceptCountryYearFactBuildResult(
        rows_created=rows_created,
        rows_updated=rows_updated,
        total_rows=counts["total_rows"],
        skipped_without_country_year=skipped_without_country_year,
        adjudication_status_counts=counts["adjudication_status_counts"],
        field_counts=counts["field_counts"],
        warnings=tuple(warnings),
    )


def _group_concept_rows(
    rows: Sequence[ConceptObservation],
    *,
    country_codes_by_name: dict[str, str],
) -> dict[tuple[str, int, str], tuple[ConceptObservation, ...]]:
    grouped: dict[tuple[str, int, str], list[ConceptObservation]] = defaultdict(list)
    for row in rows:
        if row.year is None:
            continue
        country_code = _resolve_country_code(row, country_codes_by_name)
        if country_code is None:
            continue
        grouped[(country_code, row.year, row.concept_key)].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _resolve_country_code(
    row: ConceptObservation,
    country_codes_by_name: dict[str, str],
) -> str | None:
    if row.country_code is not None:
        return row.country_code.upper()
    if row.country_name is None:
        return None
    normalized_name = normalize_country_name(row.country_name)
    return country_codes_by_name.get(normalized_name) or alias_to_iso3(normalized_name)


def _indicator_codes_for_concepts(concept_keys: Sequence[str]) -> tuple[str, ...]:
    codes: list[str] = []
    for concept_key in concept_keys:
        for mapping in resolve_concept(concept_key):
            codes.extend(mapping.indicator_codes)
    return tuple(dict.fromkeys(codes))


def _year_filter(start_year: int | None, end_year: int | None) -> tuple[int, ...] | None:
    if start_year is None and end_year is None:
        return None
    if start_year is None or end_year is None:
        raise ValueError("start_year and end_year must be provided together")
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    return tuple(range(start_year, end_year + 1))


def _country_year_index(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
) -> dict[tuple[str, int], CountryYear]:
    statement = (
        select(CountryYear, Country.iso3)
        .join(Country, CountryYear.country_id == Country.id)
        .where(CountryYear.included_in_project.is_(True))
    )
    if start_year is not None:
        statement = statement.where(CountryYear.year >= start_year)
    if end_year is not None:
        statement = statement.where(CountryYear.year <= end_year)
    rows = session.execute(statement).all()
    return {(iso3.upper(), country_year.year): country_year for country_year, iso3 in rows}


def _country_code_by_normalized_name(session: Session) -> dict[str, str]:
    return {
        country.country_name_normalized: country.iso3.upper()
        for country in session.scalars(select(Country)).all()
    }


def _select_concept_row(
    rows: Sequence[ConceptObservation],
    source_precedence: Sequence[str],
) -> ConceptObservation:
    source_rank = {source_slug: rank for rank, source_slug in enumerate(source_precedence)}
    fallback_rank = len(source_precedence)
    indexed = tuple(enumerate(rows))
    return min(
        indexed,
        key=lambda item: (
            item[1].value_type != "numeric",
            source_rank.get(item[1].source_id.slug, fallback_rank),
            item[0],
        ),
    )[1]


def _fact_payload(
    country_year: CountryYear,
    *,
    concept_key: str,
    field_label: str,
    selected: ConceptObservation,
    candidates: Sequence[ConceptObservation],
    source_precedence: Sequence[str],
    run_id: str | None,
) -> dict[str, Any]:
    candidate_payloads = [_candidate_payload(row) for row in candidates]
    selected_value_text = None if selected.value is None else str(selected.value)
    warning_payloads = [_warning_payload(warning) for row in candidates for warning in row.warnings]
    quality_signals = {
        "concept_key": concept_key,
        "selected_mapping_type": selected.mapping_type,
        "selected_quality_flags": list(selected.quality_flags),
        "selected_source_version": selected.source_version,
        "source_precedence": list(source_precedence),
    }
    adjudication_status = "auto_resolved" if selected.value_type == "numeric" else "needs_review"
    return {
        "country_year_id": country_year.id,
        "country_id": country_year.country_id,
        "year": country_year.year,
        "field_key": concept_key,
        "field_label": field_label,
        "value_type": "number" if selected.value_type == "numeric" else "missing",
        "selected_value_text": selected_value_text,
        "selected_value_number": selected.value if selected.value_type == "numeric" else None,
        "selected_value_json": _dumps(_candidate_payload(selected)),
        "selected_entity_table": None,
        "selected_entity_id": None,
        "candidate_values_json": _dumps(candidate_payloads),
        "selection_rule": "concept_source_precedence_numeric_first",
        "adjudication_status": adjudication_status,
        "confidence_score": _confidence_score(selected),
        "agreement_score": None,
        "authority_score": None,
        "specificity_score": None,
        "temporal_fit_score": 1.0,
        "quality_signals_json": _dumps(quality_signals),
        "warnings_json": _dumps(warning_payloads),
        "rationale": _rationale(selected, concept_key),
        "review_reason": (
            None if adjudication_status == "auto_resolved" else "selected concept value is missing"
        ),
        "research_prompt": None,
        "recommended_next_action": (
            "none" if adjudication_status == "auto_resolved" else "review missing concept value"
        ),
        "source_slugs_json": _dumps(_unique(row.source_id.slug for row in candidates)),
        "source_observation_ids_json": _dumps(
            _unique(
                observation_id for row in candidates for observation_id in row.input_observation_ids
            )
        ),
        "producer": CONCEPT_FACT_PRODUCER,
        "method_version": CONCEPT_FACT_METHOD_VERSION,
        "run_id": run_id,
    }


def _candidate_payload(row: ConceptObservation) -> dict[str, Any]:
    return {
        "concept_key": row.concept_key,
        "source_slug": row.source_id.slug,
        "value": row.value,
        "value_type": row.value_type,
        "unit": row.unit,
        "scale": row.scale,
        "source_version": row.source_version,
        "source_indicator_codes": list(row.source_indicator_codes),
        "input_observation_ids": list(row.input_observation_ids),
        "mapping_type": row.mapping_type,
        "recipe_key": row.recipe_key,
        "quality_flags": list(row.quality_flags),
        "warnings": [_warning_payload(warning) for warning in row.warnings],
    }


def _warning_payload(warning: SourceWarning) -> dict[str, Any]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "source_slug": warning.source_id.slug if warning.source_id is not None else None,
        "context": warning.context,
    }


def _confidence_score(row: ConceptObservation) -> int | None:
    if row.value_type != "numeric":
        return None
    return 70 if row.mapping_type == "derived" else 80


def _rationale(row: ConceptObservation, concept_key: str) -> str:
    if row.value_type != "numeric":
        return (
            f"No numeric value selected for concept {concept_key!r}; retained source "
            f"traceability for review."
        )
    return (
        f"Selected {concept_key!r} from source {row.source_id.slug!r} using "
        "numeric-first concept source precedence."
    )


def _concept_fact_counts(
    engine: Engine,
    *,
    concept_keys: tuple[str, ...],
    start_year: int | None,
    end_year: int | None,
) -> dict[str, Any]:
    with Session(engine) as session:
        statement = select(CountryYearFact).where(
            CountryYearFact.field_key.in_(concept_keys),
            CountryYearFact.producer == CONCEPT_FACT_PRODUCER,
        )
        if start_year is not None:
            statement = statement.where(CountryYearFact.year >= start_year)
        if end_year is not None:
            statement = statement.where(CountryYearFact.year <= end_year)
        rows = session.scalars(statement).all()
    return {
        "total_rows": len(rows),
        "adjudication_status_counts": dict(
            sorted(Counter(row.adjudication_status for row in rows).items())
        ),
        "field_counts": dict(sorted(Counter(row.field_key for row in rows).items())),
    }


def _unique(values: Any) -> list[Any]:
    return list(dict.fromkeys(values))


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "CONCEPT_FACT_METHOD_VERSION",
    "CONCEPT_FACT_PRODUCER",
    "DEFAULT_CONCEPT_SOURCE_PRECEDENCE",
    "ConceptCountryYearFactBuildResult",
    "publish_concept_country_year_facts",
]
