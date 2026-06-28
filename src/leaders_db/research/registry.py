"""Curated question and concept registries for the research planner."""

from __future__ import annotations

from .models import ConceptSpec, QuestionSpec

CONCEPT_SPECS: dict[str, ConceptSpec] = {
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
    "conflict_fatalities_structured": QuestionSpec(
        question_code="conflict/fatalities",
        question_key="conflict_fatalities_structured",
        text="Get structured conflict fatalities for the requested country-year scope.",
        category="conflict",
        expected_scope_keys=("country", "year"),
        concept_keys=("conflict_fatalities",),
        default_analyses=("coverage",),
        acquisition_policy="none",
    ),
    "leader_legal_cases_qualitative": QuestionSpec(
        question_code="integrity/legal_cases",
        question_key="leader_legal_cases_qualitative",
        text="Identify open criminal or corruption legal cases with cited evidence.",
        category="integrity",
        expected_scope_keys=("country", "leader", "year"),
        concept_keys=("leader_open_criminal_or_corruption_case",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
    ),
}


def get_question_spec(question_key: str) -> QuestionSpec | None:
    """Return a registered question spec, if known."""

    return QUESTION_SPECS.get(question_key)


def get_concept_spec(concept_key: str) -> ConceptSpec | None:
    """Return a registered concept spec, if known."""

    return CONCEPT_SPECS.get(concept_key)
