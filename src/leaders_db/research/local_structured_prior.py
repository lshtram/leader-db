"""Local structured priors for cited/manual ruler-quality research."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from leaders_db.research.registry import get_question_spec_by_methodology_id

from .local_prior_query import (
    load_country_name,
    load_included_scope_years,
    load_local_prior_facts,
)
from .local_prior_schema import (
    CLIENT_MATRIX_SOURCE_SLUGS,
    LOCAL_PRIOR_MAPPINGS,
    LOCAL_PRIOR_METHOD_VERSION,
    OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS,
    POLITICAL_FREEDOM_PRIOR_FIELD_KEYS,
    LeaderPriorMetadata,
    LocalPriorCountry,
    LocalPriorFact,
    LocalPriorMapping,
    LocalPriorPeriod,
    LocalStructuredPriorArtifact,
    LocalStructuredPriorRequest,
    PriorStatus,
    mapping_for_methodology_id,
)


def build_local_structured_prior(
    bind: Engine | Session,
    request: LocalStructuredPriorRequest,
) -> LocalStructuredPriorArtifact:
    """Build a local structured prior for one internet/manual methodology task."""

    spec = get_question_spec_by_methodology_id(request.methodology_id)
    if spec is None:
        return _error_artifact(
            request=request,
            question_text="",
            category="",
            country_name=None,
            missing_or_empty_reason=(
                f"Unknown methodology question id: {request.methodology_id!r}."
            ),
        )
    if spec.evidence_strategy != "internet_manual":
        return _error_artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=None,
            missing_or_empty_reason=(
                "Local structured priors are only for internet_manual questions."
            ),
        )

    try:
        return _build_local_structured_prior_for_spec(bind, request, spec)
    except (SQLAlchemyError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _error_artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=None,
            missing_or_empty_reason=f"Failed to build local structured prior: {exc}",
        )


def _build_local_structured_prior_for_spec(
    bind: Engine | Session,
    request: LocalStructuredPriorRequest,
    spec: Any,
) -> LocalStructuredPriorArtifact:
    mapping = mapping_for_methodology_id(request.methodology_id)
    if mapping is None:
        return _artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=load_country_name(bind, request.iso3),
            status="no_evidence_found",
            facts=(),
            missing_or_empty_reason=(
                "No local structured-prior mapping is configured for this methodology_id."
            ),
            mapping_note=None,
        )

    country_name = load_country_name(bind, request.iso3)
    included_years = load_included_scope_years(
        bind, iso3=request.iso3, years=_evidence_years(request)
    )
    if not included_years:
        return _artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=country_name,
            status="not_applicable",
            facts=(),
            missing_or_empty_reason=(
                "No included project country-year exists for the requested local-prior scope."
            ),
            mapping_note=mapping.mapping_note,
        )

    if not mapping.field_keys:
        return _artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=country_name,
            status="no_evidence_found",
            facts=(),
            missing_or_empty_reason=(
                "No structured country-year field is semantically sufficient for this "
                "lens; collect ruler-specific narrative evidence."
            ),
            mapping_note=mapping.mapping_note,
        )

    facts = load_local_prior_facts(
        bind,
        request=request,
        field_keys=mapping.field_keys,
        included_years=included_years,
    )
    if not facts:
        return _artifact(
            request=request,
            question_text=spec.text,
            category=spec.category,
            country_name=country_name,
            status="no_evidence_found",
            facts=(),
            missing_or_empty_reason=(
                "No selected non-client country_year_facts matched the configured local-prior "
                "field keys for this country and year/period."
            ),
            mapping_note=mapping.mapping_note,
        )

    return _artifact(
        request=request,
        question_text=spec.text,
        category=spec.category,
        country_name=country_name,
        status="evidence_found",
        facts=facts,
        missing_or_empty_reason=None,
        mapping_note=mapping.mapping_note,
    )


def _evidence_years(request: LocalStructuredPriorRequest) -> tuple[int, ...]:
    target_year = max(request.period.years())
    context_end = target_year + request.post_target_context_years
    accession_year = request.leader.accession_year
    if accession_year is None:
        return tuple(range(min(request.period.years()), context_end + 1))
    baseline_start = max(0, accession_year - 10)
    return tuple(range(baseline_start, context_end + 1))


def local_structured_prior_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for local prior artifacts."""

    return LocalStructuredPriorArtifact.model_json_schema()


def _artifact(
    *,
    request: LocalStructuredPriorRequest,
    question_text: str,
    category: str,
    country_name: str | None,
    status: PriorStatus,
    facts: tuple[LocalPriorFact, ...] | list[LocalPriorFact],
    missing_or_empty_reason: str | None,
    mapping_note: str | None,
) -> LocalStructuredPriorArtifact:
    return LocalStructuredPriorArtifact(
        methodology_id=request.methodology_id,
        question_text=question_text,
        category=category,
        country=LocalPriorCountry(iso3=request.iso3, name=country_name),
        period=request.period,
        leader=request.leader,
        status=status,
        local_facts=list(facts),
        missing_or_empty_reason=missing_or_empty_reason,
        recommended_research_instructions=_research_instructions(status),
        mapping_note=mapping_note,
    )


def _error_artifact(
    *,
    request: LocalStructuredPriorRequest,
    question_text: str,
    category: str,
    country_name: str | None,
    missing_or_empty_reason: str,
) -> LocalStructuredPriorArtifact:
    return _artifact(
        request=request,
        question_text=question_text,
        category=category,
        country_name=country_name,
        status="error",
        facts=(),
        missing_or_empty_reason=missing_or_empty_reason,
        mapping_note=None,
    )


def _research_instructions(status: PriorStatus) -> list[str]:
    instructions = [
        "Use this local structured prior before starting internet/manual research.",
        (
            "Do not re-fetch local structured datasets (including Freedom House, V-Dem, "
            "WGI, BTI, RSF, or Polity) when this artifact contains relevant "
            "non-contradictory facts."
        ),
        (
            "Fetch web/narrative sources only when the local prior is absent, "
            "contradictory, needs ruler-specific attribution, or needs narrative detail "
            "beyond structured country-year facts."
        ),
        (
            "Never use the client matrix as evidence; it is excluded from this artifact "
            "and from research citations."
        ),
    ]
    if status == "error":
        instructions.append(
            "The local structured-prior builder failed; inspect missing_or_empty_reason "
            "before launching dependent research workers."
        )
    if status in {"no_evidence_found", "not_applicable"}:
        instructions.append(
            "The empty state is explicit; if narrative research proceeds, explain that "
            "no local structured prior was available for this scope."
        )
    return instructions


__all__ = [
    "CLIENT_MATRIX_SOURCE_SLUGS",
    "LOCAL_PRIOR_MAPPINGS",
    "LOCAL_PRIOR_METHOD_VERSION",
    "OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS",
    "POLITICAL_FREEDOM_PRIOR_FIELD_KEYS",
    "LeaderPriorMetadata",
    "LocalPriorCountry",
    "LocalPriorFact",
    "LocalPriorMapping",
    "LocalPriorPeriod",
    "LocalStructuredPriorArtifact",
    "LocalStructuredPriorRequest",
    "build_local_structured_prior",
    "local_structured_prior_json_schema",
]
