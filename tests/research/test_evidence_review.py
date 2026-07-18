from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.codex_worker_command import (
    build_codex_resume_command,
    read_codex_thread_id,
)
from leaders_db.research.evidence_review import (
    EvidenceReviewReport,
    assess_research_notebook,
    build_evidence_review_prompt,
    evidence_review_json_schema,
    validate_review_scope,
)
from leaders_db.research.model_profiles import ResearchModelProfile
from leaders_db.research.research_workflow import ResearchWorkflow


def test_resume_command_targets_exact_session_and_preserves_sandbox(tmp_path: Path) -> None:
    command = build_codex_resume_command(
        profile=_profile(),
        session_id="0199a213-81c0-7800-8aa1-bbab2a035a53",
        project_root=tmp_path,
        final_message_path=tmp_path / "handoff.md",
        writable_dir=tmp_path / "attempt",
    )

    assert command[:2] == ("codex", "--cd")
    assert "--last" not in command
    assert command[command.index("resume") + 1] == ("0199a213-81c0-7800-8aa1-bbab2a035a53")
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--add-dir") + 1] == str(tmp_path / "attempt")


def test_thread_id_reader_requires_one_exact_thread(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"type": "thread.started", "thread_id": "thread-1"})
        + "\n"
        + json.dumps({"type": "turn.completed", "usage": {}})
        + "\n",
        encoding="utf-8",
    )

    assert read_codex_thread_id(events) == "thread-1"
    events.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        read_codex_thread_id(events)


def test_notebook_qa_flags_sparse_handoff_and_accepts_audited_one() -> None:
    methodology_ids = tuple(
        f"{chapter}B.{question}" for chapter in range(1, 9) for question in range(1, 11)
    )
    sparse = assess_research_notebook("short", methodology_ids=methodology_ids)
    assert sparse.needs_reviewer is True
    assert len(sparse.selected_chapter_ids) == 8

    locators = "\n".join(
        f"E{index:03d} https://source{index}.example/report" for index in range(1, 41)
    )
    chapters = "\n".join(f"## {chapter}B" for chapter in range(1, 9))
    audited = assess_research_notebook(
        f"{chapters}\n{locators}\nContrary evidence\nGap audit\n"
        f"Local-data audit\n{'substantive notes ' * 150}",
        methodology_ids=methodology_ids,
    )
    assert audited.needs_reviewer is False
    assert audited.approximate_locator_count == 40


def test_evidence_review_scope_and_strict_schema() -> None:
    report = EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": True,
            "selected_theme_ids": ["2B"],
            "chapter_reviews": [
                {
                    "chapter_id": chapter,
                    "defensible_evidence_estimate": 4,
                    "independent_source_family_estimate": 2,
                    "attribution_risk": "medium",
                    "substantive_issues": ["Ruler attribution needs support."],
                    "missing_themes": ["Decision chronology"],
                }
                for chapter in ("1B", "2B")
            ],
            "global_findings": ["Sparse but usable."],
            "reviewer_summary": "Continue only the peace chapter.",
        }
    )
    validate_review_scope(report, selected_chapter_ids=("1B", "2B"))
    schema = evidence_review_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema["$defs"].values():
        assert set(definition["required"]) == set(definition["properties"])


def test_evidence_review_scope_accepts_global_stop_without_chapter_rows() -> None:
    report = EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": False,
            "selected_theme_ids": [],
            "chapter_reviews": [],
            "global_findings": ["Further research is not actionable under the documented blocker."],
            "reviewer_summary": "Stop after the configured continuation attempts.",
        }
    )

    validate_review_scope(
        report,
        selected_chapter_ids=("1B", "2B"),
        expected_chapter_ids=(),
    )


def test_evidence_review_scope_rejects_first_round_omission() -> None:
    report = EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": False,
            "selected_theme_ids": [],
            "chapter_reviews": [],
            "global_findings": ["Incomplete review."],
            "reviewer_summary": "Stopped without reviewing chapters.",
        }
    )

    with pytest.raises(ValueError, match="selected chapter scope"):
        validate_review_scope(report, selected_chapter_ids=("1B", "2B"))


def test_evidence_review_scope_accepts_later_round_subset() -> None:
    report = EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": True,
            "selected_theme_ids": ["2B"],
            "chapter_reviews": [
                {
                    "chapter_id": "2B",
                    "defensible_evidence_estimate": 6,
                    "independent_source_family_estimate": 3,
                    "attribution_risk": "medium",
                    "substantive_issues": ["Ruler attribution needs support."],
                    "missing_themes": ["Decision chronology"],
                }
            ],
            "global_findings": ["Chapter 1B was closed in the prior round."],
            "reviewer_summary": "Continue only the peace chapter.",
        }
    )

    validate_review_scope(
        report,
        selected_chapter_ids=("1B", "2B"),
        expected_chapter_ids=("2B",),
    )


def test_evidence_review_scope_rejects_scope_expansion() -> None:
    report = EvidenceReviewReport.model_validate(
        {
            "schema_version": "ruler_evidence_review_v1",
            "needs_continuation": True,
            "selected_theme_ids": ["3B"],
            "chapter_reviews": [
                {
                    "chapter_id": "3B",
                    "defensible_evidence_estimate": 2,
                    "independent_source_family_estimate": 1,
                    "attribution_risk": "high",
                    "substantive_issues": ["Outside the immutable scope."],
                    "missing_themes": ["All lenses"],
                }
            ],
            "global_findings": ["Invalid expansion."],
            "reviewer_summary": "Invalid expansion.",
        }
    )

    with pytest.raises(ValueError, match="selected chapter scope"):
        validate_review_scope(report, selected_chapter_ids=("1B", "2B"))


def test_notebook_qa_and_reviewer_prompt_use_configured_yield_goals() -> None:
    workflow = ResearchWorkflow(
        version=1,
        chapter_order=tuple(f"{index}B" for index in range(1, 9)),
        minimum_source_claim_units_per_chapter=7,
        normal_source_claim_units_per_chapter=12,
        maximum_source_claim_units_per_chapter=20,
        minimum_independent_source_families_per_chapter=4,
    )
    notebook = (
        "## 1B\n"
        + "\n".join(f"E{index} https://same.example/report-{index}" for index in range(1, 7))
        + "\nContrary evidence\nGap audit\nLocal-data audit\n"
        + "substantive notes " * 150
    )

    qa = assess_research_notebook(
        notebook,
        methodology_ids=tuple(f"1B.{index}" for index in range(1, 11)),
        workflow=workflow,
    )
    prompt = build_evidence_review_prompt(
        job={
            "job_key": "dossier:test",
            "input": {
                "question_ids": [f"1B.{index}" for index in range(1, 11)],
                "research_workflow": workflow.model_dump(mode="json"),
            },
        },
        notebook=notebook,
        qa=qa,
    )

    assert "missing precise locator as a recoverable\nextraction task" in prompt
    assert "recreated under chapter-specific IDs" in prompt
    assert "any researcher-written score" in prompt
    assert "Do not use workflow exhaustion" in prompt
    assert "remain deterministic cleanup rather than web-research tasks" in prompt
    assert "formal responsibility" in prompt
    assert "Chapter 7B requires a personal-integrity" in prompt
    assert "Do not pass a chapter merely because it has several sources" in prompt

    assert qa.minimum_source_claim_units_per_chapter == 7
    assert qa.minimum_independent_source_families_per_chapter == 4
    assert qa.approximate_source_family_count == 1
    assert {finding.check_id for finding in qa.findings} >= {
        "low_locator_yield",
        "low_source_family_yield",
    }
    assert '"minimum_source_claim_units_per_chapter": 7' in prompt
    assert '"minimum_independent_source_families_per_chapter": 4' in prompt


def test_terminal_reviewer_records_residual_gaps_without_more_continuation() -> None:
    qa = assess_research_notebook(
        "## 4B\nSparse notebook.",
        methodology_ids=("4B.1",),
    )

    prompt = build_evidence_review_prompt(
        job={"job_key": "dossier:test", "input": {"question_ids": ["4B.1"]}},
        notebook="## 4B\nSparse notebook.",
        qa=qa,
        terminal=True,
    )

    assert "terminal review after all permitted research rounds" in prompt
    assert "Set `needs_continuation=false`" in prompt
    assert "not a claim that the dossier is complete" in prompt


def _profile() -> ResearchModelProfile:
    return ResearchModelProfile(
        provider="openai",
        model="gpt-5.6-luna",
        execution_surface="codex",
        roles=("dossier_researcher",),
        cost_class="low_cost_candidate",
        context_window=372000,
        codex_config_path="~/.codex/config.toml",
        credential_path="~/.codex/auth.json",
        notes="fixture",
    )
