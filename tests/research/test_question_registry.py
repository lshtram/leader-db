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


def test_chapter_1_nuclear_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {"1.1", "1.5", "1.6", "1.7", "1.8"}
    expected_context_ids = {"1.9"}
    expected_manual_ids = {
        "1.2",
        "1.3",
        "1.4",
        "1.10",
        "1.11",
        "1.12",
        "1.13",
        "1.14",
        "1.15",
    }
    expected_not_supported_ids = {"1.16"}
    expected_ids = (
        expected_structured_ids
        | expected_context_ids
        | expected_manual_ids
        | expected_not_supported_ids
    )

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "nuclear_risk"
        assert spec.text in methodology
        for concept_key in spec.concept_keys:
            assert get_concept_spec(concept_key) is not None

    for spec in specs:
        if spec.methodology_id in expected_structured_ids:
            assert spec.evidence_strategy == "structured"
            assert spec.support_status == "structured"
            assert spec.acquisition_policy == "none"
        elif spec.methodology_id in expected_context_ids:
            assert spec.evidence_strategy == "structured_plus_context"
            assert spec.support_status == "structured_plus_context"
            assert spec.acquisition_policy == "none"
        elif spec.methodology_id in expected_manual_ids:
            assert spec.evidence_strategy == "internet_manual"
            assert spec.support_status == "internet_manual"
            assert spec.acquisition_policy == "plan_only"
        else:
            assert spec.evidence_strategy == "not_yet_supported"
            assert spec.support_status == "not_yet_supported"
            assert spec.acquisition_policy == "none"


def test_chapter_2_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {"2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"}
    expected_manual_ids = {"2.8", "2.9", "2.10", "2.11", "2.12"}
    expected_context_ids = {"2.13"}
    expected_ids = expected_structured_ids | expected_manual_ids | expected_context_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "international_peace"
        assert spec.text in methodology
        for concept_key in spec.concept_keys:
            assert get_concept_spec(concept_key) is not None

    for spec in specs:
        if spec.methodology_id in expected_structured_ids:
            assert spec.answer_level == "country_year"
            assert spec.evidence_strategy == "structured"
            assert spec.support_status == "structured"
            assert spec.acquisition_policy == "none"
        elif spec.methodology_id in expected_manual_ids:
            assert spec.evidence_strategy == "internet_manual"
            assert spec.support_status == "internet_manual"
            assert spec.acquisition_policy == "plan_only"
        else:
            assert spec.evidence_strategy == "structured_plus_context"
            assert spec.support_status == "structured_plus_context"
            assert spec.acquisition_policy == "plan_only"


def test_chapter_2_generic_structured_questions_use_production_fact_contracts() -> None:
    expected_concept_keys = {
        "2.2": ("internationalized_conflict_events",),
        "2.3": ("state_based_conflict_fatalities",),
        "2.4": ("state_based_conflict_events",),
        "2.5": ("military_spend_share_gdp",),
        "2.6": ("military_spend_constant_usd", "military_spend_per_capita"),
        "2.7": ("military_spend_share_govt",),
    }

    for methodology_id, concept_keys in expected_concept_keys.items():
        spec = get_question_spec_by_methodology_id(methodology_id)
        assert spec is not None
        assert spec.concept_keys == concept_keys
        for concept_key in concept_keys:
            concept = get_concept_spec(concept_key)
            assert concept is not None
            assert concept.observation_families == ("international_peace_country_year",)
            assert concept.required_output_schema == "NormalizedObservation"

    q2_6 = get_question_spec_by_methodology_id("2.6")
    assert q2_6 is not None
    assert q2_6.answer_type == "evidence_bundle"
    assert q2_6.output_fields == (
        "military_spend_constant_usd",
        "military_spend_per_capita",
        "evidence_year",
        "coverage_status",
        "source_observation_ids",
        "warning_codes",
    )

    q2_2 = get_question_spec_by_methodology_id("2.2")
    assert q2_2 is not None
    assert q2_2.output_fields == (
        "answer",
        "internationalized_conflict_events",
        "evidence_year",
        "coverage_status",
        "source_observation_ids",
        "warning_codes",
    )


def test_chapter_3_domestic_safety_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {
        "3.1",
        "3.2",
        "3.3",
        "3.4",
        "3.5",
        "3.6",
        "3.7",
        "3.8",
        "3.9",
    }
    expected_manual_ids = {"3.10", "3.11"}
    expected_not_supported_ids = {"3.12"}
    expected_ids = expected_structured_ids | expected_manual_ids | expected_not_supported_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "domestic_safety"
        assert spec.text in methodology
        for concept_key in spec.concept_keys:
            assert get_concept_spec(concept_key) is not None

    for spec in specs:
        if spec.methodology_id in expected_structured_ids:
            assert spec.evidence_strategy == "structured"
            assert spec.support_status == "structured"
            assert spec.acquisition_policy == "none"
        elif spec.methodology_id in expected_manual_ids:
            assert spec.evidence_strategy == "internet_manual"
            assert spec.support_status == "internet_manual"
            assert spec.acquisition_policy == "plan_only"
        else:
            assert spec.evidence_strategy == "not_yet_supported"
            assert spec.support_status == "not_yet_supported"
            assert spec.acquisition_policy == "none"


def test_chapter_4_political_freedom_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "4.5",
        "4.6",
        "4.7",
        "4.8",
        "4.9",
        "4.10",
    }
    expected_not_supported_ids = {"4.11"}
    expected_ids = expected_structured_ids | expected_not_supported_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "political_freedom"
        assert spec.text in methodology
        for concept_key in spec.concept_keys:
            assert get_concept_spec(concept_key) is not None

    for spec in specs:
        if spec.methodology_id in expected_structured_ids:
            assert spec.evidence_strategy == "structured"
            assert spec.support_status == "structured"
            assert spec.acquisition_policy == "none"
        else:
            assert spec.evidence_strategy == "not_yet_supported"
            assert spec.support_status == "not_yet_supported"
            assert spec.acquisition_policy == "none"


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
