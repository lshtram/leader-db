import json
from pathlib import Path

from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.chapter_research_sequence import (
    _existing_chapter_turn,
    build_chapter_research_prompt,
)
from leaders_db.research.codex_worker import (
    _checkpoint_covers_chapters,
    _recover_consumer_materials,
)
from leaders_db.research.notebook_continuation import (
    _append_current_ledger_manifest,
)
from leaders_db.research.research_workflow import ResearchWorkflow


def _workflow() -> ResearchWorkflow:
    return ResearchWorkflow(
        version=1,
        chapter_order=tuple(f"{index}B" for index in range(1, 9)),
        researcher_session_scope="segmented_ruler_period",
        chapter_session_mode="fresh_compact_context",
    )


def test_chapter_prompt_uses_natural_saturation_based_research() -> None:
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

    assert "There is no document or evidence-record quota." in prompt
    assert (
        "Use only `final_evidence`, `context`, or `discovery_only` for both "
        "`disposition` and" in prompt
    )
    assert "one machine record for one source supporting one material claim" in prompt
    assert "shared `underlying_fact_key`" in prompt
    assert "Do not bundle them into an omnibus" in prompt
    assert "Continue while research produces a materially new fact" in prompt
    assert "exact supported question IDs from\n[\"3B.1\", \"3B.2\"]" in prompt
    assert "Open an underlying source before using it" in prompt
    assert "SOURCE_CLAIM_JSON:" in prompt
    assert "Known lead" in prompt
    assert "WEB-3B-" in prompt
    assert "structured local-data package is prepared and retained separately" in prompt
    assert "Earlier web reconnaissance" in prompt
    assert len(prompt) < 15_000


def test_chapter_prompt_requires_parent_merge_and_residual_gap_audit() -> None:
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

    assert "parent workflow merges these append-only records" in prompt
    assert "disposition for every selected question" in prompt
    assert "whether more research is likely to add material information" in prompt
    assert "complete ledger" in prompt


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


def test_d_style_machine_record_survives_parent_ledger_merge(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "job" / "attempts" / "001-current"
    trusted_dir = tmp_path / "job" / "trusted" / "001-current"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    attempt = WorkerAttempt(
        attempt_dir=attempt_dir,
        trusted_dir=trusted_dir,
        result_path=attempt_dir / "dossier.json",
        schema_path=trusted_dir / "schema.json",
        prompt_path=attempt_dir / "prompt.txt",
        pending_path=attempt_dir / "pending.json",
        events_path=trusted_dir / "events.jsonl",
        existing_candidate=None,
        local_priors=(),
        local_prior_provenance=(),
    )
    record = {
        "title": "Primary record",
        "publisher": "Example Court",
        "publication_date": "2022-06-01",
        "url": "https://example.test/judgment",
        "claim": "The court issued a final finding.",
        "locator": "paragraph 42",
        "provisional_id": "WEB-7B-001",
        "canonical_fact_key": (
            "https://example.test/judgment|paragraph 42|final finding"
        ),
        "underlying_fact_key": "example-final-finding",
        "disposition": "final_evidence",
        "chapter_ids": ["7B"],
        "methodology_ids": ["7B.1", "7B.6"],
        "source_type": "legal",
        "source_confidence": "high",
        "source_confidence_reason": "Opened final judgment.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target period",
        "ruler_attribution": "direct",
        "contrary_evidence": [],
        "lenses": ["7B.1", "7B.6"],
    }
    notebook = "SOURCE_CLAIM_JSON: " + json.dumps(record, separators=(",", ":"))

    merged = _append_current_ledger_manifest(notebook, attempt)

    manifest = json.loads(
        (attempt_dir / "research-ledger-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["entries"] == [record]
    assert record["canonical_fact_key"] in merged
    assert record["locator"] in merged
    assert record["methodology_ids"] == manifest["entries"][0]["methodology_ids"]


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


def test_completed_chapter_checkpoint_prevents_research_replay(tmp_path: Path) -> None:
    notebook = (
        "initial\n\n--- CHAPTER RESEARCH 1B ---\nfirst"
        "\n\n--- CHAPTER RESEARCH 2B ---\nsecond"
    )
    checkpoint = (
        tmp_path / "events.jsonl",
        notebook,
        tmp_path / "notebook.md",
        "notebook-hash",
        "events-hash",
    )
    workflow = _workflow()
    job = {"input": {"question_ids": ["1B.1", "2B.1"]}}

    assert _checkpoint_covers_chapters(checkpoint, job=job, workflow=workflow)
    assert not _checkpoint_covers_chapters(
        (checkpoint[0], notebook.replace("2B", "3B"), *checkpoint[2:]),
        job=job,
        workflow=workflow,
    )


def test_recovered_checkpoint_copies_consumer_materials(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    prior_attempt = job_dir / "attempts" / "001-prior"
    current_attempt = job_dir / "attempts" / "002-current"
    prior_trusted = job_dir / "trusted" / "001-prior"
    current_trusted = job_dir / "trusted" / "002-current"
    for path in (prior_attempt, current_attempt, prior_trusted, current_trusted):
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
    checkpoint = (
        prior_trusted / "events.jsonl",
        (
            "notebook\n\n--- CHAPTER RESEARCH 1B ---\nchapter\n\n"
            "--- RESEARCH LEDGER MANIFEST ---\n"
            '{"schema_version":"ruler_research_ledger_manifest_v1",'
            '"entries":[{"canonical_fact_key":"fact-1"}]}'
        ),
        prior_trusted / "research-notebook-8B.md",
        "notebook-hash",
        "events-hash",
    )

    _recover_consumer_materials(checkpoint, attempt=attempt)

    assert (current_attempt / "research-ledger-manifest.json").is_file()
    assert (current_attempt / "research-chapter-1B.md").read_text() == "chapter"
