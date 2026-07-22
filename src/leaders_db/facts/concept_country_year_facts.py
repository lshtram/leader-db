"""Publish harmonized source concepts into generic country-year facts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.db.models import Country, CountryYear, CountryYearFact
from leaders_db.normalize.countries import alias_to_iso3, normalize_country_name
from leaders_db.score.confidence import ConfidenceInputs, compute_confidence
from leaders_db.sources.concepts import (
    KNOWN_CONCEPT_KEYS,
    ConceptObservation,
    extract_concept_result,
    list_concepts,
    resolve_concept,
)
from leaders_db.sources.contracts import EvidenceQuery, SourceId, SourceWarning
from leaders_db.sources.country_codes import (
    iso3_from_source_country,
    iso3_from_ucdp_country_id,
    normalize_source_country_code,
)
from leaders_db.sources.query import EvidenceRepository

from .country_year_facts import upsert_country_year_fact

CONCEPT_FACT_PRODUCER = "concept_country_year_facts"
CONCEPT_FACT_METHOD_VERSION = "concept-country-year-facts-v2"
SOURCE_NATIVE_UCDP_COUNTRY_ID_SOURCES: frozenset[str] = frozenset({"ucdp"})
DEFAULT_CONCEPT_SOURCE_PRECEDENCE: tuple[str, ...] = (
    "world_bank_wdi",
    "maddison_project",
    "pwt",
    "undp_hdi",
    "who_gho_api",
    "vdem",
    "freedom_house",
    "ucdp",
    "rsf_press_freedom",
    "fas",
    "sipri_milex",
)

_GDP_FACT_VARIANTS: dict[tuple[str, str], tuple[str, str]] = {
    ("gdp_per_capita", "wdi_gdp_per_capita"): (
        "gdp_per_capita_nominal_current_usd",
        "GDP per capita — nominal current USD",
    ),
    ("gdp_per_capita", "wdi_gdp_per_capita_ppp_constant_2017"): (
        "gdp_per_capita_ppp_constant_2017_intl",
        "GDP per capita — PPP, constant 2017 international dollars",
    ),
    ("gdp_per_capita", "maddison_project_gdp_per_capita_2011_intl"): (
        "gdp_per_capita_ppp_constant_2011_intl",
        "GDP per capita — PPP, constant 2011 international dollars",
    ),
    ("gdp_per_capita", "pwt_real_gdp_output_side"): (
        "gdp_per_capita_ppp_constant_2017_usd",
        "GDP per capita — PPP, constant 2017 USD",
    ),
    ("gdp_total", "wdi_gdp_current_usd"): (
        "gdp_total_nominal_current_usd",
        "GDP total — nominal current USD",
    ),
    ("gdp_total", "wdi_gdp_constant_2015_usd"): (
        "gdp_total_real_constant_2015_usd",
        "GDP total — real, constant 2015 USD",
    ),
    ("gdp_total", "maddison_project_gdp_total_2011_intl_derived"): (
        "gdp_total_ppp_constant_2011_intl",
        "GDP total — PPP, constant 2011 international dollars",
    ),
    ("gdp_total", "pwt_real_gdp_expenditure_side"): (
        "gdp_total_ppp_expenditure_constant_2017_usd",
        "GDP total — expenditure-side PPP, constant 2017 USD",
    ),
    ("gdp_total", "pwt_real_gdp_output_side"): (
        "gdp_total_ppp_output_constant_2017_usd",
        "GDP total — output-side PPP, constant 2017 USD",
    ),
}

_SOURCE_AUTHORITY_SCORES: dict[str, int] = {
    "cirights": 100,
    "fas": 80,
    "freedom_house": 80,
    "maddison_project": 100,
    "pwt": 100,
    "rsf_press_freedom": 80,
    "sipri_milex": 100,
    "ucdp": 100,
    "undp_hdi": 100,
    "vdem": 100,
    "who_gho_api": 100,
    "world_bank_wdi": 100,
    "world_bank_wgi": 100,
}


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

        _delete_obsolete_gdp_fact_keys(
            session,
            concept_keys=concept_keys,
            start_year=start_year,
            end_year=end_year,
        )

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
                field_label=_field_label(concept_key, descriptors),
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
        concept_keys=_published_concept_keys(concept_keys),
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


def _delete_obsolete_gdp_fact_keys(
    session: Session,
    *,
    concept_keys: Sequence[str],
    start_year: int | None,
    end_year: int | None,
) -> None:
    """Remove v1 GDP rows whose mixed units were split in v2.

    The cleanup is restricted to this producer and the requested year scope;
    preserved releases and facts written by another producer are untouched.
    """
    obsolete = tuple(key for key in ("gdp_per_capita", "gdp_total") if key in concept_keys)
    if not obsolete:
        return
    statement = delete(CountryYearFact).where(
        CountryYearFact.producer == CONCEPT_FACT_PRODUCER,
        CountryYearFact.field_key.in_(obsolete),
    )
    if start_year is not None:
        statement = statement.where(CountryYearFact.year >= start_year)
    if end_year is not None:
        statement = statement.where(CountryYearFact.year <= end_year)
    session.execute(statement)


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
        grouped[(country_code, row.year, _published_concept_key(row))].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _resolve_country_code(
    row: ConceptObservation,
    country_codes_by_name: dict[str, str],
) -> str | None:
    if row.country_code is not None:
        if row.source_id.slug in SOURCE_NATIVE_UCDP_COUNTRY_ID_SOURCES:
            return iso3_from_ucdp_country_id(row.country_code, year=row.year)
        if row.country_name is not None:
            country_name_iso3 = iso3_from_source_country(row.country_name, year=row.year)
            if country_name_iso3 is not None:
                return country_name_iso3
        return normalize_source_country_code(row.country_code)
    if row.country_name is None:
        return None
    normalized_name = normalize_country_name(row.country_name)
    return (
        iso3_from_source_country(row.country_name, year=row.year)
        or country_codes_by_name.get(normalized_name)
        or alias_to_iso3(normalized_name)
    )


def _indicator_codes_for_concepts(concept_keys: Sequence[str]) -> tuple[str, ...]:
    codes: list[str] = []
    for concept_key in concept_keys:
        for mapping in resolve_concept(concept_key):
            codes.extend(mapping.indicator_codes)
    return tuple(dict.fromkeys(codes))


def _published_concept_key(row: ConceptObservation) -> str:
    """Split legacy GDP aliases into dimensionally compatible fact concepts."""

    if row.concept_key not in {"gdp_per_capita", "gdp_total"}:
        return row.concept_key
    indicator = row.source_indicator_codes[0] if row.source_indicator_codes else ""
    variant = _GDP_FACT_VARIANTS.get((row.concept_key, indicator))
    if variant is None:
        raise ValueError(
            f"GDP observation {row.input_observation_ids!r} has no semantic variant "
            f"for indicator {indicator!r}"
        )
    return variant[0]


def _field_label(concept_key: str, descriptors: dict[str, Any]) -> str:
    for field_key, label in _GDP_FACT_VARIANTS.values():
        if field_key == concept_key:
            return label
    if concept_key == "gdp_per_capita_ppp_constant_2017_usd":
        return "GDP per capita — PPP, constant 2017 USD"
    return descriptors[concept_key].display_name


def _published_concept_keys(concept_keys: Sequence[str]) -> tuple[str, ...]:
    published: list[str] = []
    for concept_key in concept_keys:
        if concept_key == "gdp_per_capita":
            published.extend(
                (
                    "gdp_per_capita_nominal_current_usd",
                    "gdp_per_capita_ppp_constant_2017_intl",
                    "gdp_per_capita_ppp_constant_2011_intl",
                    "gdp_per_capita_ppp_constant_2017_usd",
                )
            )
        elif concept_key == "gdp_total":
            published.extend(
                field_key
                for field_key, _ in _GDP_FACT_VARIANTS.values()
                if field_key.startswith("gdp_total_")
            )
        else:
            published.append(concept_key)
    return tuple(dict.fromkeys(published))


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
    candidate_payloads = [
        _candidate_payload(row, selection_role="selected" if row is selected else "alternative")
        for row in candidates
    ]
    selected_value_text = None if selected.value is None else str(selected.value)
    warning_payloads = [
        _warning_payload(warning) for row in candidates for warning in row.warnings
    ] + _semantic_warning_payloads(concept_key, selected)
    confidence_inputs = _confidence_inputs(selected, candidates)
    quality_signals = {
        "concept_key": concept_key,
        "selected_mapping_type": selected.mapping_type,
        "selected_quality_flags": list(selected.quality_flags),
        "selected_source_version": selected.source_version,
        "selected_unit": selected.unit,
        "selected_scale": selected.scale,
        "source_precedence": list(source_precedence),
        "confidence_components": (
            None
            if confidence_inputs is None
            else {
                "agreement": confidence_inputs.agreement,
                "authority": confidence_inputs.authority,
                "specificity": confidence_inputs.specificity,
                "temporal_fit": confidence_inputs.temporal_fit,
            }
        ),
        "confidence_formula": "0.35*agreement+0.25*authority+0.25*specificity+0.15*temporal_fit",
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
        "selected_value_json": _dumps(_candidate_payload(selected, selection_role="selected")),
        "selected_entity_table": None,
        "selected_entity_id": None,
        "candidate_values_json": _dumps(candidate_payloads),
        "selection_rule": "concept_source_precedence_numeric_first",
        "adjudication_status": adjudication_status,
        "confidence_score": (
            None if confidence_inputs is None else compute_confidence(confidence_inputs)
        ),
        "agreement_score": (None if confidence_inputs is None else confidence_inputs.agreement),
        "authority_score": (None if confidence_inputs is None else confidence_inputs.authority),
        "specificity_score": (None if confidence_inputs is None else confidence_inputs.specificity),
        "temporal_fit_score": (
            None if confidence_inputs is None else confidence_inputs.temporal_fit
        ),
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


def _candidate_payload(
    row: ConceptObservation,
    *,
    selection_role: str,
) -> dict[str, Any]:
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
        "selection_role": selection_role,
        "extension": dict(row.extension),
    }


def _semantic_warning_payloads(
    concept_key: str,
    selected: ConceptObservation,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if selected.source_id.slug == "sipri_milex":
        if concept_key == "military_spend_constant_usd":
            warnings.append(
                _interpretation_warning(
                    "sipri_exact_unit",
                    "The value is millions of constant 2024 USD; do not relabel "
                    "it as current USD or raw dollars.",
                )
            )
        warnings.append(
            _interpretation_warning(
                "military_spending_not_aggression",
                "Military expenditure is capacity and policy context; it does not "
                "by itself establish aggression or poor peace performance.",
            )
        )
    if selected.source_id.slug == "ucdp":
        if concept_key == "one_sided_government_actor_killings":
            warnings.append(
                _interpretation_warning(
                    "ucdp_government_actor_not_personal_direction",
                    "UCDP identifies a government actor as perpetrator, but this does "
                    "not by itself establish personal ruler direction or initiation.",
                )
            )
        elif concept_key == "one_sided_nonstate_actor_killings":
            warnings.append(
                _interpretation_warning(
                    "ucdp_nonstate_not_host_responsibility",
                    "UCDP identifies non-state perpetration at this location; do not "
                    "relabel it as host-government or ruler conduct.",
                )
            )
        else:
            warnings.append(
                _interpretation_warning(
                    "ucdp_location_not_responsibility",
                    "Country-year event exposure does not by itself identify the "
                    "perpetrator, conflict side, initiator, or ruler responsibility.",
                )
            )
    if selected.source_id.slug == "cirights":
        warnings.append(
            _interpretation_warning(
                "cirights_favorable_code_ambiguity",
                "A favorable CIRIGHTS code may mean either that abuse did not occur "
                "or that it was not reported; silence is not proof of favorable conduct.",
            )
        )
    return warnings


def _interpretation_warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": "warning",
        "source_slug": None,
        "context": {"prohibited_automatic_inference": True},
    }


def _warning_payload(warning: SourceWarning) -> dict[str, Any]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "source_slug": warning.source_id.slug if warning.source_id is not None else None,
        "context": warning.context,
    }


def _confidence_inputs(
    selected: ConceptObservation,
    candidates: Sequence[ConceptObservation],
) -> ConfidenceInputs | None:
    if selected.value_type != "numeric":
        return None
    return ConfidenceInputs(
        agreement=_agreement_score(selected, candidates),
        authority=_SOURCE_AUTHORITY_SCORES.get(selected.source_id.slug, 60),
        specificity=60 if selected.mapping_type == "derived" else 80,
        temporal_fit=_temporal_fit_score(selected),
    )


def _agreement_score(
    selected: ConceptObservation,
    candidates: Sequence[ConceptObservation],
) -> int:
    """Score independent source-family agreement without counting duplicates."""

    values_by_source: dict[str, float] = {}
    for candidate in candidates:
        if candidate.value_type != "numeric" or candidate.value is None:
            continue
        if (candidate.unit, candidate.scale) != (selected.unit, selected.scale):
            continue
        values_by_source.setdefault(candidate.source_id.slug, float(candidate.value))
    values = tuple(values_by_source.values())
    if len(values) < 2:
        return 0
    denominator = max(abs(value) for value in values)
    relative_spread = 0.0 if denominator == 0 else (max(values) - min(values)) / denominator
    if relative_spread <= 0.05:
        return 100 if len(values) >= 3 else 80
    if relative_spread <= 0.15:
        return 60
    if relative_spread <= 0.30:
        return 40
    return 20


def _temporal_fit_score(selected: ConceptObservation) -> int:
    flags = " ".join(selected.quality_flags).lower()
    warnings = " ".join(warning.code for warning in selected.warnings).lower()
    if "proxy" in flags or "proxy" in warnings:
        return 60
    return 100


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
