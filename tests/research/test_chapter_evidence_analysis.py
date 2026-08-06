"""Tests for question-complete chapter analysis integrity controls."""

import json
from pathlib import Path

import pytest

from leaders_db.research.chapter_analysis_integrity import (
    revision_context,
    strip_invalid_corrected_ids,
    strip_invalid_critique_ids,
    strip_invalid_draft_ids,
)
from leaders_db.research.chapter_analysis_models import (
    AnswerCritiqueIssue,
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    CorrectedLensAnswer,
    LensAnswer,
)
from leaders_db.research.chapter_evidence_analysis import (
    _chapter_evidence,
    _validate_analysis,
    _validate_corrected_answer,
    _validate_critique,
)
from tests.research.test_corpus_mapping_review import _evidence


def _answers() -> tuple[LensAnswer, ...]:
    return tuple(
        LensAnswer(
            question_id=f"8B.{number}",
            answer=f"A sufficiently detailed evidence answer for lens {number}.",
            supporting_evidence_ids=("E-1",),
            contrary_or_qualifying_evidence_ids=(),
        )
        for number in range(1, 11)
    )


def test_analysis_requires_exact_question_set() -> None:
    draft = ChapterAnalysisDraft(chapter_id="8B", answers=_answers())

    _validate_analysis(
        "8B", {f"8B.{number}" for number in range(1, 11)}, {"E-1"}, draft
    )


def test_analysis_rejects_invented_evidence_id() -> None:
    draft = ChapterAnalysisDraft(chapter_id="8B", answers=_answers())

    with pytest.raises(ValueError, match="invented"):
        _validate_analysis(
            "8B", {f"8B.{number}" for number in range(1, 11)}, set(), draft
        )


def test_critique_rejects_unknown_question() -> None:
    critique = ChapterAnalysisCritique(
        chapter_id="8B",
        overall_assessment="A sufficiently detailed independent assessment.",
        issues=(
            AnswerCritiqueIssue(
                question_id="7B.1",
                issue_type="material_omission",
                evidence_ids=("E-1",),
                explanation="Material evidence was omitted.",
            ),
        ),
    )

    with pytest.raises(ValueError, match="unknown question"):
        _validate_critique(
            "8B", {f"8B.{number}" for number in range(1, 11)}, {"E-1"}, critique
        )


def test_corrected_answer_rejects_evidence_not_reopened() -> None:
    answer = CorrectedLensAnswer(
        question_id="8B.1",
        answer="A sufficiently detailed corrected evidence answer for the lens.",
        supporting_evidence_ids=("E-not-opened",),
        contrary_or_qualifying_evidence_ids=(),
    )

    with pytest.raises(ValueError, match="not reopened"):
        _validate_corrected_answer(answer, "8B.1", {"E-1"})


def test_strip_invalid_corrected_ids_records_removed_reference() -> None:
    answer = CorrectedLensAnswer(
        question_id="8B.1",
        answer="A sufficiently detailed corrected evidence answer for the lens.",
        supporting_evidence_ids=("E-1", "E-not-opened"),
        contrary_or_qualifying_evidence_ids=(),
    )

    repaired = strip_invalid_corrected_ids(answer, {"E-1"})

    assert repaired.supporting_evidence_ids == ("E-1",)
    assert "E-not-opened" in repaired.corrections_made[-1]


def test_strip_invalid_draft_ids_records_removed_references() -> None:
    draft = ChapterAnalysisDraft(
        chapter_id="8B",
        answers=tuple(
            answer.model_copy(
                update={"supporting_evidence_ids": ("E-1", "E-invalid")}
            )
            for answer in _answers()
        ),
    )

    repaired = strip_invalid_draft_ids(draft, {"E-1"})

    assert all(answer.supporting_evidence_ids == ("E-1",) for answer in repaired.answers)
    assert "E-invalid" in repaired.cross_lens_observations[-1]


def test_strip_invalid_critique_ids_records_removed_references() -> None:
    critique = ChapterAnalysisCritique(
        chapter_id="8B",
        overall_assessment="A sufficiently detailed independent assessment.",
        issues=(
            AnswerCritiqueIssue(
                question_id="8B.1",
                issue_type="material_omission",
                evidence_ids=("E-1", "E-invalid"),
                explanation="Material evidence was omitted.",
            ),
        ),
    )

    repaired = strip_invalid_critique_ids(critique, {"E-1"})

    assert repaired.issues[0].evidence_ids == ("E-1",)
    assert "E-invalid" in repaired.overall_assessment


def test_chapter_analysis_receives_complete_ruler_evidence_ledger(
    tmp_path: Path,
) -> None:
    first = _evidence("E-1", "Fact routed to chapter one")
    second = _evidence("E-2", "Fact routed to chapter eight").model_copy(
        update={"question_ids": ("8B.1",)}
    )
    package = tmp_path / "judge-package.json"
    package.write_text(
        json.dumps(
            {
                "evidence": [
                    first.model_dump(mode="json"),
                    second.model_dump(mode="json"),
                ]
            }
        ),
        encoding="utf-8",
    )

    evidence = _chapter_evidence(package, "1B")

    assert set(evidence) == {"E-1", "E-2"}


def test_chapter_revision_requires_both_review_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires both"):
        revision_context(
            "1B",
            prior_analysis_path=tmp_path / "analysis.json",
            quality_review_path=None,
        )
