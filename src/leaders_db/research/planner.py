"""Deterministic first-slice research planning."""

from __future__ import annotations

from itertools import product

from leaders_db.sources.contracts import EvidenceQuery

from .models import (
    DimensionBinding,
    DimensionFilter,
    DimensionValue,
    InvestigationPlan,
    ResearchQuestion,
    RowScope,
    ScopeFilter,
    source_ids_from_slugs,
)

_SUPPORTED_QUESTIONS = {
    "conflict_fatalities_structured": {
        "concepts": ("conflict_fatalities",),
        "acquisition_policy": "none",
    },
    "leader_legal_cases_qualitative": {
        "concepts": ("leader_open_criminal_or_corruption_case",),
        "acquisition_policy": "plan_only",
    },
}


def plan_question(question: ResearchQuestion) -> InvestigationPlan:
    """Convert a supported question into an explicit investigation plan."""

    supported = _SUPPORTED_QUESTIONS.get(question.question_key)
    if supported is None:
        raise ValueError(f"Unsupported research question_key: {question.question_key!r}")

    expected_concepts = supported["concepts"]
    if tuple(question.concepts) != expected_concepts:
        raise ValueError(
            f"Question {question.question_key!r} requires concepts {expected_concepts!r}; "
            f"got {question.concepts!r}"
        )

    return InvestigationPlan(
        question_id=question.question_id,
        concept_keys=question.concepts,
        evidence_query=EvidenceQuery(
            source_ids=source_ids_from_slugs(question.preferred_sources),
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
        acquisition_policy=supported["acquisition_policy"],
    )


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
