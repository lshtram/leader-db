"""Deterministic first-slice research planning."""

from __future__ import annotations

from itertools import product

from leaders_db.sources.contracts import EvidenceQuery

from .models import (
    ConceptSpec,
    DimensionBinding,
    DimensionFilter,
    DimensionValue,
    InvestigationPlan,
    QuestionClassification,
    QuestionSpec,
    ResearchQuestion,
    RowScope,
    ScopeFilter,
    source_ids_from_slugs,
)
from .registry import get_concept_spec, get_question_spec

NEEDS_QUESTION_SPEC_REVIEW = "needs_question_spec_review"


class QuestionSpecReviewNeeded(ValueError):
    """Raised when a question cannot be mapped to executable registry specs."""

    code = NEEDS_QUESTION_SPEC_REVIEW


def plan_question(question: ResearchQuestion) -> InvestigationPlan:
    """Convert a supported question into an explicit investigation plan."""

    question_spec = get_question_spec(question.question_key)
    if question_spec is None:
        raise QuestionSpecReviewNeeded(
            f"{NEEDS_QUESTION_SPEC_REVIEW}: unsupported research question_key "
            f"{question.question_key!r}"
        )

    concept_specs = tuple(_concept_spec(concept_key) for concept_key in question.concepts)
    if tuple(question.concepts) != question_spec.concept_keys:
        raise ValueError(
            f"Question {question.question_key!r} requires concepts {question_spec.concept_keys!r}; "
            f"got {question.concepts!r}"
        )
    _validate_required_scope_keys(
        question.scope_filter,
        _required_scope_keys(question_spec.expected_scope_keys, concept_specs),
    )

    return InvestigationPlan(
        question_id=question.question_id,
        concept_keys=question.concepts,
        evidence_query=EvidenceQuery(
            source_ids=source_ids_from_slugs(question.preferred_sources),
            observation_families=_observation_families(concept_specs),
            indicator_codes=question.concepts,
            years=_integer_dimension_values(question.scope_filter, "year"),
            countries=_string_dimension_values(question.scope_filter, "country"),
            leaders=_string_dimension_values(question.scope_filter, "leader"),
        ),
        source_priority=question.preferred_sources,
        scope_filter=question.scope_filter,
        output_grain="dimensioned_concept",
        analyses=question.analyses,
        include_missing_rows=True,
        acquisition_policy=question_spec.acquisition_policy,
    )


def question_from_classification(
    *,
    question_id: str,
    display_text: str,
    classification: QuestionClassification,
) -> ResearchQuestion:
    """Map a validated classification contract to a registered question."""

    question_spec = validate_question_classification(classification)
    return ResearchQuestion(
        question_id=question_id,
        question_key=classification.question_key,
        display_text=display_text,
        concepts=classification.concept_keys,
        scope_filter=classification.scope_filter,
        analyses=classification.analyses or question_spec.default_analyses,
        preferred_sources=classification.preferred_sources,
    )


def validate_question_classification(classification: QuestionClassification) -> QuestionSpec:
    """Validate a provider-produced classification against curated registries."""

    question = ResearchQuestion(
        question_id="classification-contract-validation",
        question_key=classification.question_key,
        display_text="Classification contract validation.",
        concepts=classification.concept_keys,
        scope_filter=classification.scope_filter,
        analyses=classification.analyses,
        preferred_sources=classification.preferred_sources,
    )
    plan_question(question)
    question_spec = get_question_spec(classification.question_key)
    if question_spec is None:  # pragma: no cover - guarded by plan_question
        raise QuestionSpecReviewNeeded(NEEDS_QUESTION_SPEC_REVIEW)
    return question_spec


def expand_scope_filter(scope_filter: ScopeFilter) -> tuple[RowScope, ...]:
    """Expand values and simple integer ranges into concrete row scopes."""

    expanded_dimensions = tuple(
        _expand_dimension_filter(filter_) for filter_ in scope_filter.filters
    )
    if not expanded_dimensions:
        return (RowScope(dimensions=()),)

    return tuple(RowScope(dimensions=dimensions) for dimensions in product(*expanded_dimensions))


def _expand_dimension_filter(filter_: DimensionFilter) -> tuple[DimensionBinding, ...]:
    values: tuple[DimensionValue, ...]
    if filter_.values:
        values = filter_.values
    elif isinstance(filter_.start, int) and isinstance(filter_.end, int):
        step = 1 if filter_.start <= filter_.end else -1
        values = tuple(range(filter_.start, filter_.end + step, step))
    else:
        values = (filter_.start,) if filter_.start is not None else ()

    return tuple(
        DimensionBinding(
            key=filter_.key,
            value=value,
            value_type=_value_type(value),
            role=filter_.role,
        )
        for value in values
    )


def _value_type(value: DimensionValue) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _integer_dimension_values(scope_filter: ScopeFilter, key: str) -> tuple[int, ...] | None:
    values: list[int] = []
    for filter_ in scope_filter.filters:
        if filter_.key != key:
            continue
        values.extend(value for value in filter_.values if isinstance(value, int))
        if isinstance(filter_.start, int) and isinstance(filter_.end, int):
            step = 1 if filter_.start <= filter_.end else -1
            values.extend(range(filter_.start, filter_.end + step, step))
    return tuple(values) if values else None


def _string_dimension_values(scope_filter: ScopeFilter, key: str) -> tuple[str, ...] | None:
    values = tuple(
        str(value)
        for filter_ in scope_filter.filters
        if filter_.key == key
        for value in filter_.values
    )
    return values or None


def _concept_spec(concept_key: str) -> ConceptSpec:
    concept_spec = get_concept_spec(concept_key)
    if concept_spec is None:
        raise QuestionSpecReviewNeeded(
            f"{NEEDS_QUESTION_SPEC_REVIEW}: unsupported concept_key {concept_key!r}"
        )
    return concept_spec


def _required_scope_keys(
    question_keys: tuple[str, ...], concept_specs: tuple[ConceptSpec, ...]
) -> tuple[str, ...]:
    required: list[str] = []
    for key in question_keys:
        if key not in required:
            required.append(key)
    for concept_spec in concept_specs:
        for key in concept_spec.expected_scope_keys:
            if key not in required:
                required.append(key)
    return tuple(required)


def _validate_required_scope_keys(
    scope_filter: ScopeFilter, required_keys: tuple[str, ...]
) -> None:
    present_keys = {filter_.key for filter_ in scope_filter.filters if _has_scope_value(filter_)}
    missing_keys = tuple(key for key in required_keys if key not in present_keys)
    if missing_keys:
        raise ValueError(f"Missing required scope key(s): {missing_keys!r}")


def _has_scope_value(filter_: DimensionFilter) -> bool:
    return bool(filter_.values) or filter_.start is not None or filter_.end is not None


def _observation_families(concept_specs: tuple[ConceptSpec, ...]) -> tuple[str, ...]:
    families: list[str] = []
    for concept_spec in concept_specs:
        for family in concept_spec.observation_families:
            if family not in families:
                families.append(family)
    return tuple(families)
