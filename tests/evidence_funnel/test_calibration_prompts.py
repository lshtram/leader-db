from __future__ import annotations

import json

import pytest

from leaders_db.evidence_funnel.calibration_prompts import (
    citation_cli_instructions,
    question_text,
)


def test_question_text_limits_prompt_to_configured_chapter_lenses() -> None:
    payload = {
        "schema_version": "questions-v1",
        "chapter_ids": ["5B", "8B"],
        "chapters": [
            {
                "id": "5B",
                "questions": [
                    {"id": "5B.1", "text": "Economic policy?"},
                    {"id": "5B.2", "text": "Implementation?"},
                ],
            },
            {
                "id": "8B",
                "questions": [{"id": "8B.1", "text": "Effectiveness?"}],
            },
        ],
    }

    selected = json.loads(question_text(payload, ("5B.1", "5B.2")))

    assert selected["chapter_ids"] == ["5B"]
    assert [item["id"] for item in selected["chapters"][0]["questions"]] == [
        "5B.1",
        "5B.2",
    ]
    assert "8B.1" not in json.dumps(selected)


def test_question_text_rejects_missing_configured_lens() -> None:
    payload = {"chapters": [{"id": "5B", "questions": []}]}

    with pytest.raises(ValueError, match="lacks configured IDs"):
        question_text(payload, ("5B.1",))


def test_citation_cli_instructions_define_only_four_actions() -> None:
    prompt = citation_cli_instructions("evidence-tool --run RUN-1")

    assert "evidence-tool --run RUN-1" in prompt
    assert "1. inspect " in prompt
    assert "2. record --json 'ONE_COMPACT_JSON_OBJECT'" in prompt
    assert "3. revise PROPOSAL_ID START_SEGMENT_ID END_SEGMENT_ID" in prompt
    assert "4. finish " in prompt
    assert "Copy the CLI prefix exactly" in prompt
    assert "Never use a shell loop" in prompt
    assert "separate reviewer will verify semantic support" in prompt
    assert "emit an evidence batch" not in prompt


def test_extraction_tool_surface_requires_shell_safe_apostrophes() -> None:
    from leaders_db.evidence_funnel.calibration_prompts import (
        SHELL_SAFE_JSON_INSTRUCTION,
    )

    assert "encode every apostrophe" in SHELL_SAFE_JSON_INSTRUCTION
    assert r"\u0027" in SHELL_SAFE_JSON_INSTRUCTION
    assert r"\u0024" in SHELL_SAFE_JSON_INSTRUCTION
