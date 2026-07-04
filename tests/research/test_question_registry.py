from __future__ import annotations

from pathlib import Path

from leaders_db.research.models import DimensionFilter, QuestionClassification, ScopeFilter
from leaders_db.research.planner import (
    question_from_classification,
    validate_question_classification,
)
from leaders_db.research.registry import (
    get_concept_spec,
    get_question_spec_by_methodology_id,
    list_question_specs,
)
from leaders_db.research.slice_runner import default_slice_1_handlers


def test_q2_1_methodology_question_is_registered_with_i7_metadata(
    project_root: Path,
) -> None:
    spec = get_question_spec_by_methodology_id("2.1")

    assert spec is not None
    assert spec.question_key == "state_based_armed_conflict"
    assert spec.category == "international_peace"
    assert spec.answer_level == "country_year"
    assert spec.answer_type == "boolean"
    assert spec.evidence_strategy == "structured"
    assert spec.support_status == "structured"
    assert spec.expected_scope_keys == ("country", "year")
    assert spec.concept_keys == ("ucdp_state_based_conflict",)
    assert "answer" in spec.output_fields
    assert "state_based_fatalities" in spec.output_fields

    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    assert spec.text in methodology


def test_q2_1_registry_concept_and_slice_handler_are_connected() -> None:
    spec = get_question_spec_by_methodology_id("2.1")

    assert spec is not None
    concept = get_concept_spec(spec.concept_keys[0])
    assert concept is not None
    assert concept.observation_families == ("international_peace_country_year",)
    assert "2.1" in default_slice_1_handlers()


def test_registered_question_specs_have_unique_methodology_ids_and_i7_fields() -> None:
    specs = list_question_specs()
    methodology_ids = [spec.methodology_id for spec in specs]

    assert methodology_ids == sorted(methodology_ids)
    assert len(methodology_ids) == len(set(methodology_ids))
    for spec in specs:
        assert spec.methodology_id
        assert spec.answer_level in {"country_year", "ruler_year", "ruler_period"}
        assert spec.answer_type in {
            "boolean",
            "numeric",
            "categorical",
            "text",
            "evidence_bundle",
        }
        assert spec.evidence_strategy in {
            "structured",
            "structured_plus_context",
            "internet_manual",
            "not_yet_supported",
        }
        assert spec.support_status in {
            "structured",
            "structured_plus_context",
            "internet_manual",
            "not_yet_supported",
        }


def test_8b_effectiveness_questions_are_registered_as_manual_period_specs(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id.startswith("8B."))

    assert {spec.methodology_id for spec in specs} == {
        "8B.1",
        "8B.2",
        "8B.3",
        "8B.4",
        "8B.5",
        "8B.6",
        "8B.7",
        "8B.8",
        "8B.9",
        "8B.10",
    }
    for spec in specs:
        assert spec.category == "effectiveness"
        assert spec.answer_level == "ruler_period"
        assert spec.answer_type == "evidence_bundle"
        assert spec.evidence_strategy == "internet_manual"
        assert spec.support_status == "internet_manual"
        assert spec.acquisition_policy == "plan_only"
        assert spec.concept_keys == ("ruler_effectiveness_qualitative_evidence",)
        assert spec.text in methodology


def test_8b_effectiveness_concept_spec_is_registry_only_manual_evidence() -> None:
    concept = get_concept_spec("ruler_effectiveness_qualitative_evidence")

    assert concept is not None
    assert concept.expected_scope_keys == ("country", "leader", "period")
    assert concept.evidence_shape == "qualitative_cited"
    assert concept.acquisition_allowed is True


def test_1b_to_7b_ruler_quality_questions_are_registered_as_manual_period_specs(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_ids = {f"{chapter}B.{index}" for chapter in range(1, 8) for index in range(1, 11)}
    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.answer_level == "ruler_period"
        assert spec.answer_type == "evidence_bundle"
        assert spec.evidence_strategy == "internet_manual"
        assert spec.support_status == "internet_manual"
        assert spec.acquisition_policy == "plan_only"
        assert spec.concept_keys == ("ruler_quality_qualitative_evidence",)
        assert spec.text in methodology


def test_ruler_quality_concept_spec_is_registry_only_manual_evidence() -> None:
    concept = get_concept_spec("ruler_quality_qualitative_evidence")

    assert concept is not None
    assert concept.expected_scope_keys == ("country", "leader", "period")
    assert concept.evidence_shape == "qualitative_cited"
    assert concept.acquisition_allowed is True


def test_q2_1_classification_maps_to_registered_question() -> None:
    classification = QuestionClassification(
        question_key="state_based_armed_conflict",
        concept_keys=("ucdp_state_based_conflict",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("UKR",), role="entity"),
                DimensionFilter(key="year", values=(2023,), role="time"),
            )
        ),
    )

    spec = validate_question_classification(classification)
    question = question_from_classification(
        question_id="2.1",
        display_text=spec.text,
        classification=classification,
    )

    assert spec.methodology_id == "2.1"
    assert question.question_key == "state_based_armed_conflict"
    assert question.concepts == ("ucdp_state_based_conflict",)
    assert question.analyses == ("coverage",)
