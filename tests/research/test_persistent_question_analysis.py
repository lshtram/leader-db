"""Tests for persistent-thread question analysis helpers."""

import json

from leaders_db.research.persistent_question_analysis import (
    _analyst_instruction,
    _evidence_context,
    _parse_turn,
)
from tests.research.test_corpus_mapping_review import _evidence


def test_only_first_turn_contains_complete_evidence_context() -> None:
    evidence = _evidence("E-1", "Distinctive retained evidence summary")
    context = _evidence_context("8B", "Guide", (evidence,))
    later = _analyst_instruction({"id": "8B.2", "text": "Question"})

    assert "Distinctive retained evidence summary" in context
    assert "Distinctive retained evidence summary" not in later


def test_parse_turn_accepts_fenced_resume_output(tmp_path) -> None:
    path = tmp_path / "output.json"
    payload = {
        "stage": "answer",
        "question_id": "8B.1",
        "answer": {
            "question_id": "8B.1",
            "answer": "A sufficiently detailed evidence answer for the selected lens.",
            "supporting_evidence_ids": [],
            "contrary_or_qualifying_evidence_ids": [],
            "limitations_and_gaps": [],
        },
        "critique": None,
        "corrected": None,
    }
    path.write_text(f"```json\n{json.dumps(payload)}\n```\n", encoding="utf-8")

    turn = _parse_turn(path)

    assert turn.stage == "answer"
    assert turn.question_id == "8B.1"
