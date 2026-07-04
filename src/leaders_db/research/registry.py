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
    "ruler_effectiveness_qualitative_evidence": ConceptSpec(
        concept_key="ruler_effectiveness_qualitative_evidence",
        expected_scope_keys=("country", "leader", "period"),
        evidence_shape="qualitative_cited",
        observation_families=("ruler_period_effectiveness",),
        required_output_schema="RulerEffectivenessEvidenceRecord",
        allowed_source_types=("official_record", "reputable_news", "scholarly_source"),
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
    "ruler_effectiveness_program": QuestionSpec(
        methodology_id="8B.1",
        question_code="effectiveness/program",
        question_key="ruler_effectiveness_program",
        text=(
            "Does the ruler articulate a clear governing ideology, strategic direction, "
            "or program, including explicit or revealed goals for power, policy, or "
            "regime control, that can be evaluated against later action?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_priorities": QuestionSpec(
        methodology_id="8B.2",
        question_code="effectiveness/priorities",
        question_key="ruler_effectiveness_priorities",
        text=(
            "Does the ruler translate that program into concrete priorities, plans, "
            "budgets, appointments, timelines, institutions, and enforcement mechanisms?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_mobilization": QuestionSpec(
        methodology_id="8B.3",
        question_code="effectiveness/mobilization",
        question_key="ruler_effectiveness_mobilization",
        text=(
            "Does the ruler mobilize the state apparatus, party, military, bureaucracy, "
            "coalition, or ruling network effectively toward the chosen program and the "
            "ruler's own goals?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_appointments": QuestionSpec(
        methodology_id="8B.4",
        question_code="effectiveness/appointments",
        question_key="ruler_effectiveness_appointments",
        text=(
            "Does the ruler select and empower people who are capable of executing the "
            "program, whether professionals, loyal operators, technocrats, organizers, "
            "security officials, or coercive administrators?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_coordination": QuestionSpec(
        methodology_id="8B.5",
        question_code="effectiveness/coordination",
        question_key="ruler_effectiveness_coordination",
        text=(
            "Does the ruler maintain internal discipline, coordination, control, and "
            "follow-through across ministries, regions, territory, institutions, "
            "security forces, party structures, and implementing agencies?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_implementation": QuestionSpec(
        methodology_id="8B.6",
        question_code="effectiveness/implementation",
        question_key="ruler_effectiveness_implementation",
        text=(
            "Does the ruler convert declarations into observable implementation and "
            "state reach rather than leaving goals as slogans, speeches, symbolic "
            "gestures, or propaganda only?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_outcomes": QuestionSpec(
        methodology_id="8B.7",
        question_code="effectiveness/outcomes",
        question_key="ruler_effectiveness_outcomes",
        text=(
            "Do outcome indicators move in the direction the ruler claimed or revealed "
            "they sought, after allowing for realistic lags, inherited conditions, and "
            "external constraints?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_adaptation": QuestionSpec(
        methodology_id="8B.8",
        question_code="effectiveness/adaptation",
        question_key="ruler_effectiveness_adaptation",
        text=(
            "When tactics fail, does the ruler adapt methods, replace ineffective "
            "implementers, reallocate resources, or otherwise correct course to keep "
            "advancing the program and maintaining effective control?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_crisis_management": QuestionSpec(
        methodology_id="8B.9",
        question_code="effectiveness/crisis_management",
        question_key="ruler_effectiveness_crisis_management",
        text=(
            "Does the ruler manage crises, opposition, international relationships, "
            "and institutional resistance in a way that preserves or advances the "
            "regime's chosen objectives, durability, and influence, regardless of "
            "whether those objectives are morally good?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_period_end": QuestionSpec(
        methodology_id="8B.10",
        question_code="effectiveness/period_end",
        question_key="ruler_effectiveness_period_end",
        text=(
            "By the end of the relevant period, is the ruler closer to achieving the "
            "stated or revealed ideological, policy, power-consolidation, or "
            "international-influence program than at the start, accounting for "
            "short-term wins, long-term durability, inherited conditions, and external "
            "shocks?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
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
