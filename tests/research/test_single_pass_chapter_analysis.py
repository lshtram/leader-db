"""Tests for one-context self-reviewed chapter analysis."""

import pytest

from leaders_db.research.chapter_analysis_models import (
    AnswerCritiqueIssue,
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    ChapterEvidenceShard,
    CorrectedLensAnswer,
    LensAnswer,
    SelfReviewedChapterAnalysis,
)
from leaders_db.research.single_pass_chapter_analysis import (
    _normalize_audit_registries,
    _normalize_shard_registry,
    _partition_evidence,
    _validate_result,
)
from tests.research.test_corpus_mapping_review import _evidence


def _result() -> SelfReviewedChapterAnalysis:
    drafts = tuple(
        LensAnswer(
            question_id=f"1B.{number}",
            answer=f"A sufficiently detailed draft answer for question {number}.",
            supporting_evidence_ids=("E-1",),
            contrary_or_qualifying_evidence_ids=(),
        )
        for number in range(1, 11)
    )
    corrected = tuple(
        CorrectedLensAnswer(
            question_id=item.question_id,
            answer=item.answer,
            supporting_evidence_ids=item.supporting_evidence_ids,
            contrary_or_qualifying_evidence_ids=(),
        )
        for item in drafts
    )
    return SelfReviewedChapterAnalysis(
        chapter_id="1B",
        draft=ChapterAnalysisDraft(chapter_id="1B", answers=drafts),
        critique=ChapterAnalysisCritique(
            chapter_id="1B",
            issues=(),
            overall_assessment="The complete draft was checked against the packet.",
        ),
        corrected_answers=corrected,
    )


def test_self_reviewed_result_requires_all_ten_questions() -> None:
    result = _result()

    _validate_result(
        result,
        chapter_id="1B",
        expected_questions={f"1B.{number}" for number in range(1, 11)},
        evidence_ids={"E-1"},
    )


def test_self_reviewed_result_rejects_invented_corrected_id() -> None:
    result = _result()
    answers = list(result.corrected_answers)
    answers[0] = answers[0].model_copy(
        update={"supporting_evidence_ids": ("E-invented",)}
    )

    with pytest.raises(ValueError, match="invented"):
        _validate_result(
            result.model_copy(update={"corrected_answers": tuple(answers)}),
            chapter_id="1B",
            expected_questions={f"1B.{number}" for number in range(1, 11)},
            evidence_ids={"E-1"},
        )


def test_critique_registry_removes_unknown_audit_id_and_records_it() -> None:
    result = _result()
    issue = AnswerCritiqueIssue(
        question_id="1B.1",
        issue_type="material_omission",
        evidence_ids=("E-1", "E-invented"),
        explanation="The draft omitted qualifying material.",
    )
    result = result.model_copy(
        update={
            "critique": result.critique.model_copy(update={"issues": (issue,)})
        }
    )

    normalized = _normalize_audit_registries(result, {"E-1"})

    normalized_issue = normalized.critique.issues[0]
    assert normalized_issue.evidence_ids == ("E-1",)
    assert "E-invented" in normalized_issue.explanation


def test_draft_registry_removes_unknown_audit_id_and_records_it() -> None:
    result = _result()
    answers = list(result.draft.answers)
    answers[0] = answers[0].model_copy(
        update={"supporting_evidence_ids": ("E-1", "E-invented")}
    )

    normalized = _normalize_audit_registries(
        result.model_copy(
            update={"draft": result.draft.model_copy(update={"answers": tuple(answers)})}
        ),
        {"E-1"},
    )

    normalized_answer = normalized.draft.answers[0]
    assert normalized_answer.supporting_evidence_ids == ("E-1",)
    assert any("E-invented" in item for item in normalized_answer.limitations_and_gaps)


def test_corrected_registry_removes_unknown_id_and_records_it() -> None:
    result = _result()
    answers = list(result.corrected_answers)
    answers[0] = answers[0].model_copy(
        update={"supporting_evidence_ids": ("E-1", "E-invented")}
    )

    normalized = _normalize_audit_registries(
        result.model_copy(update={"corrected_answers": tuple(answers)}), {"E-1"}
    )

    normalized_answer = normalized.corrected_answers[0]
    assert normalized_answer.supporting_evidence_ids == ("E-1",)
    assert any("E-invented" in item for item in normalized_answer.corrections_made)


def test_evidence_partition_preserves_every_record_once() -> None:
    evidence = {
        f"E-{number}": _evidence(f"E-{number}", "A material fact " + "x" * 50)
        for number in range(1, 5)
    }

    shards = _partition_evidence(evidence, max_chars=700)

    flattened = [evidence_id for shard in shards for evidence_id in shard]
    assert flattened == list(evidence)
    assert len(shards) > 1


def test_out_of_shard_citation_is_removed_and_recorded() -> None:
    answer = _result().draft.answers[0].model_copy(
        update={"supporting_evidence_ids": ("E-1", "E-outside")}
    )
    shard = ChapterEvidenceShard(
        chapter_id="1B",
        shard_id="1B-S01",
        reviewed_evidence_ids=("E-1",),
        answers=(answer,),
    )

    normalized = _normalize_shard_registry(shard, {"E-1"})

    assert normalized.answers[0].supporting_evidence_ids == ("E-1",)
    assert "E-outside" in normalized.cross_shard_cautions[0]


def test_registry_owns_reviewed_id_list() -> None:
    shard = ChapterEvidenceShard(
        chapter_id="1B",
        shard_id="1B-S01",
        reviewed_evidence_ids=(),
        answers=(),
    )

    normalized = _normalize_shard_registry(shard, {"E-1", "E-2"})

    assert normalized.reviewed_evidence_ids == ("E-1", "E-2")
    assert "registry" in normalized.cross_shard_cautions[0]
