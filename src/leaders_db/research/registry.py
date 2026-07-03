"""Curated question and concept registries for the research planner."""

from __future__ import annotations

from .models import ConceptSpec, QuestionSpec

CONCEPT_SPECS: dict[str, ConceptSpec] = {
    "ucdp_state_based_conflict": ConceptSpec(
        concept_key="ucdp_state_based_conflict",
        expected_scope_keys=("country", "year"),
        evidence_shape="structured_numeric",
        observation_families=("international_peace_country_year",),
        required_output_schema="Question21AnswerRow",
        allowed_source_types=("structured_dataset",),
        acquisition_allowed=False,
    ),
    "conflict_fatalities": ConceptSpec(
        concept_key="conflict_fatalities",
        expected_scope_keys=("country", "year"),
        evidence_shape="structured_numeric",
        observation_families=("conflict",),
        required_output_schema="NormalizedObservation",
        allowed_source_types=("structured_dataset",),
        acquisition_allowed=False,
    ),
    "leader_open_criminal_or_corruption_case": ConceptSpec(
        concept_key="leader_open_criminal_or_corruption_case",
        expected_scope_keys=("country", "leader", "year"),
        evidence_shape="qualitative_cited",
        observation_families=("leader_legal_case",),
        required_output_schema="AcquiredEvidenceRecord",
        allowed_source_types=("official_record", "reputable_news"),
        acquisition_allowed=True,
    ),
}

QUESTION_SPECS: dict[str, QuestionSpec] = {
    "state_based_armed_conflict": QuestionSpec(
        methodology_id="2.1",
        question_code="international_peace/state_based_armed_conflict",
        question_key="state_based_armed_conflict",
        text="Was the country involved in state-based armed conflict in the target/proxy year?",
        category="international_peace",
        answer_level="country_year",
        answer_type="boolean",
        evidence_strategy="structured",
        support_status="structured",
        expected_scope_keys=("country", "year"),
        concept_keys=("ucdp_state_based_conflict",),
        default_analyses=("coverage",),
        acquisition_policy="none",
        output_fields=(
            "answer",
            "state_based_events",
            "state_based_fatalities",
            "evidence_year",
            "coverage_status",
            "source_observation_ids",
            "warning_codes",
        ),
    ),
    "conflict_fatalities_structured": QuestionSpec(
        methodology_id="2.3",
        question_code="conflict/fatalities",
        question_key="conflict_fatalities_structured",
        text="Get structured conflict fatalities for the requested country-year scope.",
        category="conflict",
        answer_level="country_year",
        answer_type="numeric",
        evidence_strategy="structured",
        support_status="structured",
        expected_scope_keys=("country", "year"),
        concept_keys=("conflict_fatalities",),
        default_analyses=("coverage",),
        acquisition_policy="none",
    ),
    "leader_legal_cases_qualitative": QuestionSpec(
        methodology_id="6B.legal_cases",
        question_code="integrity/legal_cases",
        question_key="leader_legal_cases_qualitative",
        text="Identify open criminal or corruption legal cases with cited evidence.",
        category="integrity",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "year"),
        concept_keys=("leader_open_criminal_or_corruption_case",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
    ),
}


def get_question_spec(question_key: str) -> QuestionSpec | None:
    """Return a registered question spec, if known."""

    return QUESTION_SPECS.get(question_key)


def get_question_spec_by_methodology_id(methodology_id: str) -> QuestionSpec | None:
    """Return a question spec by stable methodology-document question id."""

    for spec in QUESTION_SPECS.values():
        if spec.methodology_id == methodology_id:
            return spec
    return None


def list_question_specs() -> tuple[QuestionSpec, ...]:
    """Return all registered question specs in deterministic order."""

    return tuple(sorted(QUESTION_SPECS.values(), key=lambda spec: spec.methodology_id))


def get_concept_spec(concept_key: str) -> ConceptSpec | None:
    """Return a registered concept spec, if known."""

    return CONCEPT_SPECS.get(concept_key)


__all__ = [
    "CONCEPT_SPECS",
    "QUESTION_SPECS",
    "get_concept_spec",
    "get_question_spec",
    "get_question_spec_by_methodology_id",
    "list_question_specs",
]
