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


def test_authoritative_ruler_questions_match_guides_and_collector_catalog(
    project_root: Path,
) -> None:
    matching_specs = [
        spec
        for spec in list_question_specs()
        if re.fullmatch(r"[1-8]B\.(?:10|[1-9])", spec.methodology_id)
    ]
    collector_items = questions()

    assert len(matching_specs) == 80
    assert len({spec.methodology_id for spec in matching_specs}) == 80
    assert len(collector_items) == 80
    assert len({item["id"] for item in collector_items}) == 80
    expected_questions = {spec.methodology_id: spec.text for spec in matching_specs}
    collector_questions = {item["id"]: item["text"] for item in collector_items}
    methodology_items = _extract_table_questions(_methodology_text(project_root))
    prompt_review_items = _extract_numbered_questions(
        (
            project_root / "docs" / "methodology" / "pipeline-agent-questions-and-prompts.md"
        ).read_text(encoding="utf-8")
    )

    _assert_exact_question_catalog(methodology_items, expected_count=80)
    _assert_exact_question_catalog(prompt_review_items, expected_count=80)
    assert collector_questions == expected_questions
    assert dict(methodology_items) == expected_questions
    assert dict(prompt_review_items) == expected_questions
    for chapter_index in range(1, 9):
        chapter_id = f"{chapter_index}B"
        guide = next(
            (project_root / "docs/methodology/chapter-guides").glob(f"{chapter_id.lower()}-*.md")
        ).read_text(encoding="utf-8")
        guide_items = [
            *_extract_table_questions(guide),
            *_extract_numbered_questions(guide),
        ]
        _assert_exact_question_catalog(guide_items, expected_count=10)
        assert dict(guide_items) == {
            methodology_id: text
            for methodology_id, text in expected_questions.items()
            if methodology_id.startswith(f"{chapter_id}.")
        }


def _assert_exact_question_catalog(
    items: list[tuple[str, str]],
    *,
    expected_count: int,
) -> None:
    assert len(items) == expected_count
    assert len({methodology_id for methodology_id, _ in items}) == expected_count


def _extract_table_questions(text: str) -> list[tuple[str, str]]:
    return re.findall(
        r"^\| \*\*([1-8]B\.(?:10|[1-9]))\*\* \| (.+?) \|$",
        text,
        flags=re.MULTILINE,
    )


def _extract_numbered_questions(text: str) -> list[tuple[str, str]]:
    return [
        (methodology_id, " ".join(question.split()))
        for methodology_id, question in re.findall(
            r"^\d+\. \*\*([1-8]B\.(?:10|[1-9])):?\*\* (?:—|-|:)?\s*(.+?)"
            r"(?=^\d+\. \*\*[1-8]B\.(?:10|[1-9]):?\*\*|^\s*$)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
    ]


def _methodology_text(project_root: Path) -> str:
    return (project_root / "docs" / "methodology" / "ranking-evaluation-criteria.md").read_text(
        encoding="utf-8"
    )
