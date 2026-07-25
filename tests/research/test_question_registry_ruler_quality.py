from __future__ import annotations

import re
from pathlib import Path

from leaders_db.conversational_evidence.data import questions
from leaders_db.research.registry import get_concept_spec, list_question_specs


def test_8b_effectiveness_questions_are_registered_as_manual_period_specs(
    project_root: Path,
) -> None:
    methodology = _methodology_text(project_root)
    specs = tuple(spec for spec in list_question_specs() if spec.methodology_id.startswith("8B."))

    assert {spec.methodology_id for spec in specs} == {f"8B.{index}" for index in range(1, 11)}
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
    methodology = _methodology_text(project_root)
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


def test_ruler_question_catalog_matches_runtime_registry() -> None:
    matching_specs = [
        spec
        for spec in list_question_specs()
        if re.fullmatch(r"[1-8]B\.(?:10|[1-9])", spec.methodology_id)
    ]
    collector_items = questions()

    expected_questions = {spec.methodology_id: spec.text for spec in matching_specs}
    collector_questions = {item["id"]: item["text"] for item in collector_items}
    assert len(expected_questions) == len(matching_specs)
    assert len(collector_questions) == len(collector_items)
    assert collector_questions == expected_questions


def _methodology_text(project_root: Path) -> str:
    return (project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md").read_text(
        encoding="utf-8"
    )
