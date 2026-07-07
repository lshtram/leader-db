from __future__ import annotations

from pathlib import Path

from leaders_db.research.registry import get_concept_spec, list_question_specs


def test_chapter_5_economic_wellbeing_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {
        "5.1",
        "5.2",
        "5.3",
        "5.4",
        "5.11",
        "5.12",
        "5.13",
        "5.14",
    }
    expected_manual_ids = {
        "5.5",
        "5.6",
        "5.7",
        "5.8",
        "5.9",
        "5.10",
        "5.15",
        "5.16",
    }
    expected_not_supported_ids = {"5.17"}
    expected_ids = expected_structured_ids | expected_manual_ids | expected_not_supported_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "economic_wellbeing"
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

def test_chapter_6_social_wellbeing_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {"6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7"}
    expected_manual_ids = {"6.8", "6.9"}
    expected_not_supported_ids = {"6.10"}
    expected_ids = expected_structured_ids | expected_manual_ids | expected_not_supported_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "social_wellbeing"
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


def test_chapter_7_integrity_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_structured_ids = {"7.1", "7.2", "7.3", "7.4"}
    expected_context_ids = {"7.5"}
    expected_manual_ids = {"7.6", "7.7"}
    expected_not_supported_ids = {"7.8"}
    expected_ids = (
        expected_structured_ids
        | expected_context_ids
        | expected_manual_ids
        | expected_not_supported_ids
    )

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "integrity"
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


def test_chapter_8_effectiveness_country_condition_questions_are_registered(
    project_root: Path,
) -> None:
    methodology = (
        project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md"
    ).read_text(encoding="utf-8")
    expected_manual_ids = {
        "8.1",
        "8.2",
        "8.3",
        "8.4",
        "8.5",
        "8.6",
        "8.7",
        "8.8",
        "8.9",
        "8.10",
    }
    expected_context_ids = {"8.11"}
    expected_not_supported_ids = {"8.12"}
    expected_ids = expected_manual_ids | expected_context_ids | expected_not_supported_ids

    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id in expected_ids)

    assert {spec.methodology_id for spec in specs} == expected_ids
    for spec in specs:
        assert spec.category == "effectiveness"
        assert spec.text in methodology
        for concept_key in spec.concept_keys:
            assert get_concept_spec(concept_key) is not None

    for spec in specs:
        if spec.methodology_id in expected_manual_ids:
            assert spec.answer_level == "ruler_period"
            assert spec.evidence_strategy == "internet_manual"
            assert spec.support_status == "internet_manual"
            assert spec.acquisition_policy == "plan_only"
        elif spec.methodology_id in expected_context_ids:
            assert spec.answer_level == "country_year"
            assert spec.evidence_strategy == "structured_plus_context"
            assert spec.support_status == "structured_plus_context"
            assert spec.acquisition_policy == "plan_only"
        else:
            assert spec.answer_level == "country_year"
            assert spec.evidence_strategy == "not_yet_supported"
            assert spec.support_status == "not_yet_supported"
            assert spec.acquisition_policy == "none"
