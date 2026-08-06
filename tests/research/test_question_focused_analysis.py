"""Tests for cache-friendly question-focused analysis controls."""

from leaders_db.research.chapter_analysis_models import (
    LensAnswer,
    QuestionWorkflowTurn,
)
from leaders_db.research.question_focused_analysis import (
    _answer_task,
    _run_stage,
    _shared_prefix,
    _turn_error,
)
from tests.research.test_corpus_mapping_review import _evidence


def _answer(evidence_id: str) -> LensAnswer:
    return LensAnswer(
        question_id="8B.1",
        answer="A sufficiently detailed evidence-based answer for this question.",
        supporting_evidence_ids=(evidence_id,),
        contrary_or_qualifying_evidence_ids=(),
    )


def test_shared_prefix_is_identical_across_question_suffixes() -> None:
    evidence = _evidence("E-1", "One material fact")
    prefix = _shared_prefix("8B", "Guide text", (evidence,))
    first = prefix + _answer_task({"id": "8B.1", "text": "First question"})
    second = prefix + _answer_task({"id": "8B.2", "text": "Second question"})

    assert first[: len(prefix)] == second[: len(prefix)] == prefix
    assert first[len(prefix) :] != second[len(prefix) :]


def test_turn_validation_rejects_invented_evidence() -> None:
    turn = QuestionWorkflowTurn(
        stage="answer",
        question_id="8B.1",
        answer=_answer("E-invented"),
    )

    assert _turn_error(turn, "answer", "8B.1", {"E-1"}) == (
        "turn invented an evidence ID"
    )


def test_turn_validation_accepts_exact_stage_question_and_ids() -> None:
    turn = QuestionWorkflowTurn(
        stage="answer",
        question_id="8B.1",
        answer=_answer("E-1"),
    )

    assert _turn_error(turn, "answer", "8B.1", {"E-1"}) is None


def test_serial_stage_preserves_question_order() -> None:
    visited = []
    questions = ({"id": "1B.1"}, {"id": "1B.2"}, {"id": "1B.3"})

    results = _run_stage(
        questions=questions,
        first_sequential=True,
        parallel_questions=1,
        worker=lambda item: visited.append(item["id"]) or item["id"],
    )

    assert visited == ["1B.1", "1B.2", "1B.3"]
    assert results == {item["id"]: item["id"] for item in questions}

