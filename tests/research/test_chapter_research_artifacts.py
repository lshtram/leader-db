"""Boundary tests for chapter research inspection and recovery artifacts."""

import json
from pathlib import Path

import pytest

from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.chapter_research_artifacts import validate_chapter_inspection
from leaders_db.research.chapter_research_sequence import (
    _chapter_resource_index,
    _existing_chapter_turn,
)


def _attempt(attempt_dir: Path, trusted_dir: Path) -> WorkerAttempt:
    return WorkerAttempt(
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


def test_chapter_inspection_treats_depth_as_target_not_gate() -> None:
    candidate = {
        "url": "https://example.test/report",
        "title": "Report",
        "publisher": "Publisher",
        "document_type": "report",
        "access_status": "opened",
        "chapter_ids": ["5B"],
    }

    validate_chapter_inspection(
        "SOURCE_CANDIDATE_JSON: " + json.dumps(candidate),
        chapter_id="5B",
        minimum=12,
    )


def test_chapter_inspection_accepts_source_claim_as_opened_evidence() -> None:
    claim = {
        "url": "https://example.test/report",
        "claim": "A concrete claim",
        "locator": "p. 4",
        "provisional_id": "WEB-5B-001",
        "canonical_fact_key": "fact-1",
        "disposition": "final_evidence",
        "chapter_ids": ["5B"],
        "methodology_ids": ["5B.1"],
    }

    validate_chapter_inspection(
        "SOURCE_CLAIM_JSON: " + json.dumps(claim), chapter_id="5B", minimum=12
    )


def test_chapter_inspection_accepts_prior_claim_before_prose_only_delta() -> None:
    claim = {
        "url": "https://example.test/report",
        "claim": "A concrete claim",
        "locator": "p. 4",
        "provisional_id": "WEB-5B-001",
        "canonical_fact_key": "fact-1",
        "disposition": "final_evidence",
        "chapter_ids": ["5B"],
        "methodology_ids": ["5B.1"],
    }
    cumulative_notebook = (
        "SOURCE_CLAIM_JSON: " + json.dumps(claim)
        + "\n--- RESUMED CHAPTER DELTA ---\nNo additional source was needed."
    )

    validate_chapter_inspection(cumulative_notebook, chapter_id="5B", minimum=12)


def test_chapter_inspection_accepts_structured_access_blocker() -> None:
    blocker = {
        "chapter_id": "5B",
        "documents_attempted": ["https://example.test/report"],
        "limitation": "provider access failed",
    }

    validate_chapter_inspection(
        "INSPECTION_SATURATION_BLOCKER_JSON: " + json.dumps(blocker),
        chapter_id="5B",
        minimum=12,
    )


def test_chapter_inspection_rejects_null_attempted_documents() -> None:
    blocker = {
        "chapter_id": "5B",
        "documents_attempted": [None],
        "limitation": "provider access failed",
    }

    with pytest.raises(RuntimeError, match="inspected no candidate"):
        validate_chapter_inspection(
            "INSPECTION_SATURATION_BLOCKER_JSON: " + json.dumps(blocker),
            chapter_id="5B",
            minimum=12,
        )


def test_candidate_resource_index_fails_closed_for_corrupt_catalogue(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "job" / "attempts" / "001-current"
    trusted_dir = tmp_path / "job" / "trusted" / "001-current"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    attempt = _attempt(attempt_dir, trusted_dir)
    (attempt_dir / "source-candidate-catalog.json").write_text(
        "not-json", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="existing source candidate catalogue"):
        _chapter_resource_index(attempt, "5B")


def test_chapter_recovery_requires_same_session_mode(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    current_attempt = job_dir / "attempts" / "002-current"
    current_trusted = job_dir / "trusted" / "002-current"
    prior_attempt = job_dir / "attempts" / "001-prior"
    prior_trusted = job_dir / "trusted" / "001-prior"
    for path in (current_attempt, current_trusted, prior_attempt, prior_trusted):
        path.mkdir(parents=True)
    attempt = _attempt(current_attempt, current_trusted)
    events = prior_trusted / "research-chapter-1B.events.jsonl"
    events.write_text(
        '{"type":"thread.started","thread_id":"wrong-thread"}\n{"type":"turn.completed"}\n',
        encoding="utf-8",
    )
    starting = prior_trusted / "research-chapter-1B.starting.json"
    common = {
        "chapter_id": "1B",
        "job_id": 7,
        "prompt_sha256": "prompt-hash",
        "provider_profile": "profile",
    }
    starting.write_text(
        json.dumps({**common, "chapter_session_mode": "legacy_persistent"}),
        encoding="utf-8",
    )
    output = prior_attempt / "research-chapter-1B.md"
    output.write_text("completed", encoding="utf-8")

    assert _existing_chapter_turn(
        attempt, "1B", job_id=7, chapter_session_mode="fresh_compact_context",
        prompt_hash="prompt-hash", provider_profile="profile",
    ) is None

    starting.write_text(
        json.dumps({**common, "chapter_session_mode": "fresh_compact_context"}),
        encoding="utf-8",
    )
    ledger = prior_trusted / "research-ledger-before-1B.json"
    ledger.write_text(
        '{"schema_version":"ruler_research_ledger_manifest_v1","entries":[]}',
        encoding="utf-8",
    )
    assert _existing_chapter_turn(
        attempt, "1B", job_id=7, chapter_session_mode="fresh_compact_context",
        prompt_hash="prompt-hash", provider_profile="profile",
    ) == (events, output, ledger)
