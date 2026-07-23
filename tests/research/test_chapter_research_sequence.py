import json
from pathlib import Path

from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.chapter_research_sequence import (
    _existing_chapter_turn,
    build_chapter_research_prompt,
)
from leaders_db.research.research_workflow import ResearchWorkflow


def _workflow() -> ResearchWorkflow:
    return ResearchWorkflow(
        version=1,
        chapter_order=tuple(f"{index}B" for index in range(1, 9)),
        researcher_session_scope="segmented_ruler_period",
        chapter_session_mode="fresh_compact_context",
    )


def test_chapter_prompt_requires_measurable_opened_source_research() -> None:
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {
                "question_ids": ["3B.1", "3B.2", "4B.1"],
            },
        },
        chapter_id="3B",
        guide="Guide text",
        workflow=_workflow(),
        resource_index=(
            {
                "provisional_id": "R01",
                "url": "https://example.test/source",
                "claim": "Known lead",
            },
        ),
    )

    assert "about 30 plausible documents" in prompt
    assert "open at least 12 promising underlying" in prompt
    assert "Selected lenses: [\"3B.1\", \"3B.2\"]" in prompt
    assert "Do not stop at search snippets" in prompt
    assert "SOURCE_CLAIM_JSON:" in prompt
    assert "Known lead" in prompt
    assert "fresh compact chapter session" in prompt
    assert "WEB-3B-001" in prompt
    assert len(prompt) < 15_000


def test_chapter_prompt_requires_cumulative_manifest_and_residual_gap_audit() -> None:
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {"question_ids": ["7B.1"]},
        },
        chapter_id="7B",
        guide="Guide text",
        workflow=_workflow(),
    )

    assert "cumulative `research-ledger-manifest.json`" in prompt
    assert "chapter-only fragment" in prompt
    assert "exact residual gaps" in prompt
    assert "why another chapter-specific search wave would or would not" in prompt


def test_chapter_prompt_excludes_judge_only_guide_sections() -> None:
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {"question_ids": ["5B.1"]},
        },
        chapter_id="5B",
        guide=(
            "## Ten Evidence Lenses\n1. **5B.1** — Research question.\n\n"
            "## Researcher Evidence Plan\nUse primary records.\n\n"
            "## Chapter Judge and Lens Weighting\nJudge-only token hog."
        ),
        workflow=_workflow(),
    )

    assert "Research question" in prompt
    assert "Use primary records" in prompt
    assert "Judge-only token hog" not in prompt


def test_chapter_recovery_requires_same_session_mode(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    current_attempt = job_dir / "attempts" / "002-current"
    current_trusted = job_dir / "trusted" / "002-current"
    prior_attempt = job_dir / "attempts" / "001-prior"
    prior_trusted = job_dir / "trusted" / "001-prior"
    for path in (current_attempt, current_trusted, prior_attempt, prior_trusted):
        path.mkdir(parents=True)
    attempt = WorkerAttempt(
        attempt_dir=current_attempt,
        trusted_dir=current_trusted,
        result_path=current_attempt / "dossier.json",
        schema_path=current_trusted / "schema.json",
        prompt_path=current_attempt / "prompt.txt",
        pending_path=current_attempt / "pending.json",
        events_path=current_trusted / "events.jsonl",
        existing_candidate=None,
        local_priors=(),
        local_prior_provenance=(),
    )
    events = prior_trusted / "research-chapter-1B.events.jsonl"
    events.write_text(
        '{"type":"thread.started","thread_id":"wrong-thread"}\n'
        '{"type":"turn.completed"}\n',
        encoding="utf-8",
    )
    (prior_trusted / "research-chapter-1B.starting.json").write_text(
        json.dumps(
            {
                "chapter_id": "1B",
                "job_id": 7,
                "chapter_session_mode": "legacy_persistent",
                "prompt_sha256": "prompt-hash",
                "provider_profile": "profile",
            }
        ),
        encoding="utf-8",
    )
    output = prior_attempt / "research-chapter-1B.md"
    output.write_text("completed", encoding="utf-8")

    assert (
        _existing_chapter_turn(
            attempt,
            "1B",
            job_id=7,
            chapter_session_mode="fresh_compact_context",
            prompt_hash="prompt-hash",
            provider_profile="profile",
        )
        is None
    )

    (prior_trusted / "research-chapter-1B.starting.json").write_text(
        json.dumps(
            {
                "chapter_id": "1B",
                "job_id": 7,
                "chapter_session_mode": "fresh_compact_context",
                "prompt_sha256": "prompt-hash",
                "provider_profile": "profile",
            }
        ),
        encoding="utf-8",
    )
    (prior_trusted / "research-ledger-before-1B.json").write_text(
        '{"schema_version":"ruler_research_ledger_manifest_v1","entries":[]}',
        encoding="utf-8",
    )
    assert _existing_chapter_turn(
        attempt,
        "1B",
        job_id=7,
        chapter_session_mode="fresh_compact_context",
        prompt_hash="prompt-hash",
        provider_profile="profile",
    ) == (
        events,
        output,
        prior_trusted / "research-ledger-before-1B.json",
    )
