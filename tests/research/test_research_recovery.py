import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from leaders_db.research._codex_worker_artifacts import (
    candidate_has_valid_references,
    find_previous_candidate,
)
from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.codex_worker import (
    WorkerOutputError,
    _events_show_failed_turn,
    _evidence_preservation_floors,
    _has_indeterminate_formatter_call,
    _has_indeterminate_initial_research,
    _recover_completed_initial_research,
    _review_report_paths,
    _validate_formatter_evidence_yield,
)
from leaders_db.research.evidence_review import ChapterEvidenceReview, EvidenceReviewReport
from leaders_db.research.notebook_continuation import (
    _completed_review_reports,
    _existing_continuation,
    _initial_expected_review_ids,
    _rehydrate_completed_continuation,
)


def _attempt(tmp_path: Path, name: str = "002-current") -> WorkerAttempt:
    job_dir = tmp_path / "job"
    attempt_dir = job_dir / "attempts" / name
    trusted_dir = job_dir / "trusted" / name
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
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


def _candidate_evidence(index: int) -> dict[str, object]:
    return {
        "evidence_id": f"E{index:03d}",
        "claim": f"Claim {index}",
        "url": f"https://example.test/{index}",
        "title": f"Source {index}",
        "publisher": "Fixture publisher",
        "publication_date": "2020-01-01",
        "excerpt": "Fixture excerpt.",
        "source_type": "fixture",
        "source_confidence": "medium",
        "source_confidence_reason": "Fixture confidence.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target period",
        "ruler_attribution": "direct",
        "contrary_evidence": [],
    }


def test_review_reports_are_recovered_across_attempts(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=False,
        selected_theme_ids=(),
        chapter_reviews=(),
        global_findings=(),
        reviewer_summary="All selected chapters passed.",
    )
    (prior / "evidence-review-round-01.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )

    assert _completed_review_reports(current) == [(1, report)]


def test_completed_continuation_is_recovered_without_new_call(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior_trusted = current.trusted_dir.parent / "001-prior"
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_trusted.mkdir()
    prior_attempt.mkdir()
    events = prior_trusted / "research-continuation-round-01.events.jsonl"
    events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    output = prior_attempt / "research-continuation-round-01.md"
    output.write_text("Recovered evidence.", encoding="utf-8")

    assert _existing_continuation(current, 1) == (events, output)


def test_formatter_recovery_prefers_candidate_with_more_preserved_evidence(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path, "003-current")
    attempts = current.attempt_dir.parent
    trusted = current.trusted_dir.parent
    for name, count in (("001-richer", 8), ("002-newer-sparse", 3)):
        attempt_dir = attempts / name
        trusted_dir = trusted / name
        attempt_dir.mkdir()
        trusted_dir.mkdir()
        (trusted_dir / "formatter-complete.marker").write_text("complete\n", encoding="utf-8")
        evidence = [_candidate_evidence(index) for index in range(1, count + 1)]
        mappings = (
            []
            if name == "001-richer"
            else [
                {
                    "methodology_id": "2B.1",
                    "evidence_id": item["evidence_id"],
                    "relation": "supports",
                    "relevance": "Fixture relevance.",
                }
                for item in evidence
            ]
        )
        (attempt_dir / "dossier.pending.json").write_text(
            json.dumps(
                {
                    "evidence": evidence,
                    "mappings": mappings,
                    "coverage": [
                        {
                            "methodology_id": "2B.1",
                            "status": "covered",
                            "evidence_ids": [item["evidence_id"] for item in evidence],
                            "reason": "Fixture coverage.",
                        }
                    ],
                    "methodology_ids": ["2B.1"],
                }
            ),
            encoding="utf-8",
        )
    invalid_attempt = attempts / "000-invalid-high-count"
    invalid_trusted = trusted / "000-invalid-high-count"
    invalid_attempt.mkdir()
    invalid_trusted.mkdir()
    (invalid_trusted / "formatter-complete.marker").write_text("complete\n", encoding="utf-8")
    (invalid_attempt / "dossier.pending.json").write_text(
        json.dumps(
            {
                "evidence": [
                    {"evidence_id": f"E{index:03d}"} for index in range(1, 20)
                ],
                "mappings": [],
                "coverage": [],
                "methodology_ids": ["2B.1"],
            }
        ),
        encoding="utf-8",
    )

    candidate = find_previous_candidate(
        current.attempt_dir.parent.parent,
        attempt_dir=current.attempt_dir,
    )

    assert candidate is not None
    assert len(candidate["evidence"]) == 3


def test_broken_reference_candidate_is_retained_only_for_repair(tmp_path: Path) -> None:
    current = _attempt(tmp_path, "002-current")
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_trusted = current.trusted_dir.parent / "001-prior"
    prior_attempt.mkdir()
    prior_trusted.mkdir()
    (prior_trusted / "formatter-complete.marker").write_text(
        "complete\n", encoding="utf-8"
    )
    payload = {
        "evidence": [_candidate_evidence(1)],
        "mappings": [
            {
                "methodology_id": "2B.1",
                "evidence_id": "E999",
                "relation": "supports",
                "relevance": "Broken but repairable reference.",
            }
        ],
        "coverage": [
            {
                "methodology_id": "2B.1",
                "status": "covered",
                "evidence_ids": ["E999"],
                "reason": "Broken but repairable reference.",
            }
        ],
        "methodology_ids": ["2B.1"],
    }
    (prior_attempt / "dossier.pending.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    candidate = find_previous_candidate(
        current.attempt_dir.parent.parent, attempt_dir=current.attempt_dir
    )

    assert candidate == payload
    assert candidate_has_valid_references(candidate) is False


def test_first_review_scope_uses_only_job_selected_chapters() -> None:
    job = {"input": {"question_ids": ["2B.1", "2B.2", "5B.1"]}}

    assert _initial_expected_review_ids(job) == ("2B", "5B")


def test_formatter_must_preserve_reviewed_source_claim_units(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=False,
        selected_theme_ids=(),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="2B",
                defensible_evidence_estimate=10,
                independent_source_family_estimate=3,
                attribution_risk="medium",
                substantive_issues=(),
                missing_themes=(),
            ),
        ),
        global_findings=(),
        reviewer_summary="Formatting may proceed.",
    )
    (current.trusted_dir / "evidence-review-round-01.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )
    assert _evidence_preservation_floors(current.trusted_dir) == {"2B": 8}
    too_sparse = SimpleNamespace(
        mappings=tuple(
            SimpleNamespace(methodology_id="2B.1", evidence_id=f"E{index:03d}")
            for index in range(1, 8)
        )
    )

    with pytest.raises(WorkerOutputError, match="chapters: 2B"):
        _validate_formatter_evidence_yield(too_sparse, trusted_dir=current.trusted_dir)

    sufficient = SimpleNamespace(
        mappings=(
            *too_sparse.mappings,
            SimpleNamespace(methodology_id="2B.2", evidence_id="E008"),
        )
    )
    _validate_formatter_evidence_yield(sufficient, trusted_dir=current.trusted_dir)


def test_sparse_review_estimate_does_not_create_an_undocumented_floor(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=False,
        selected_theme_ids=(),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="1B",
                defensible_evidence_estimate=2,
                independent_source_family_estimate=1,
                attribution_risk="high",
                substantive_issues=(),
                missing_themes=("Direct ruler attribution",),
            ),
        ),
        global_findings=(),
        reviewer_summary="Sparse but honestly documented.",
    )
    (current.trusted_dir / "evidence-review-round-01.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )
    one_unit = SimpleNamespace(
        mappings=(SimpleNamespace(methodology_id="1B.1", evidence_id="E001"),)
    )
    two_units = SimpleNamespace(
        mappings=(
            *one_unit.mappings,
            SimpleNamespace(methodology_id="1B.2", evidence_id="E002"),
        )
    )

    with pytest.raises(WorkerOutputError, match="chapters: 1B"):
        _validate_formatter_evidence_yield(one_unit, trusted_dir=current.trusted_dir)
    _validate_formatter_evidence_yield(two_units, trusted_dir=current.trusted_dir)


def test_formatter_floors_retain_chapters_from_earlier_review_rounds(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    first = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=True,
        selected_theme_ids=("2B",),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="1B",
                defensible_evidence_estimate=6,
                independent_source_family_estimate=2,
                attribution_risk="low",
                substantive_issues=(),
                missing_themes=(),
            ),
            ChapterEvidenceReview(
                chapter_id="2B",
                defensible_evidence_estimate=8,
                independent_source_family_estimate=3,
                attribution_risk="medium",
                substantive_issues=(),
                missing_themes=("decision chronology",),
            ),
        ),
        global_findings=(),
        reviewer_summary="Continue 2B.",
    )
    second = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=False,
        selected_theme_ids=(),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="2B",
                defensible_evidence_estimate=10,
                independent_source_family_estimate=4,
                attribution_risk="low",
                substantive_issues=(),
                missing_themes=(),
            ),
        ),
        global_findings=(),
        reviewer_summary="Formatting may proceed.",
    )
    for number, report in ((1, first), (2, second)):
        (current.trusted_dir / f"evidence-review-round-{number:02d}.json").write_text(
            report.model_dump_json(), encoding="utf-8"
        )

    assert _evidence_preservation_floors(current.trusted_dir) == {"1B": 5, "2B": 8}


def test_recovered_continuation_is_merged_into_durable_checkpoint(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    initial_events = current.trusted_dir / "research-events.jsonl"
    initial_events.write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n', encoding="utf-8"
    )
    initial_notebook = current.trusted_dir / "initial.md"
    initial_notebook.write_text("Initial notebook.", encoding="utf-8")
    prior_trusted = current.trusted_dir.parent / "001-prior"
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_trusted.mkdir()
    prior_attempt.mkdir()
    continuation_events = prior_trusted / "research-continuation-round-01.events.jsonl"
    continuation_events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    continuation_output = prior_attempt / "research-continuation-round-01.md"
    continuation_output.write_text("Recovered evidence.", encoding="utf-8")
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=True,
        selected_theme_ids=("2B",),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="2B",
                defensible_evidence_estimate=1,
                independent_source_family_estimate=1,
                attribution_risk="low",
                substantive_issues=(),
                missing_themes=("peace events",),
            ),
        ),
        global_findings=(),
        reviewer_summary="Continue 2B.",
    )
    recovered = _rehydrate_completed_continuation(
        checkpoint=(initial_events, "Initial notebook.", initial_notebook, "x", "y"),
        report=report,
        recovered=(continuation_events, continuation_output),
        attempt=current,
        job={
            "job_key": "dossier:test",
            "provider_profile": "researcher",
            "provider": "openai",
            "model": "fixture",
        },
        round_number=1,
    )

    assert "Initial notebook." in recovered[1]
    assert "Recovered evidence." in recovered[1]
    assert (current.trusted_dir / "research-notebook-checkpoint.json").is_file()


def test_initial_recovery_preserves_materials_and_handoff(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior_trusted = current.trusted_dir.parent / "001-prior"
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_trusted.mkdir()
    prior_attempt.mkdir()
    (prior_trusted / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior_trusted / "research-events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.completed"}\n',
        encoding="utf-8",
    )
    (prior_attempt / "research-materials.md").write_text(
        "Detailed evidence register.", encoding="utf-8"
    )
    (prior_attempt / "research-handoff.md").write_text(
        "Research summary.", encoding="utf-8"
    )
    job = {
        "job_key": "dossier:test",
        "provider_profile": "researcher",
        "provider": "openai",
        "model": "fixture",
    }

    recovered = _recover_completed_initial_research(attempt=current, job=job)

    assert recovered is not None
    assert "Detailed evidence register." in recovered[1]
    assert "Research summary." in recovered[1]


def test_pre_session_mcp_failure_is_safe_to_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    (prior / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior / "research-events.jsonl").write_text(
        "ERROR required MCP server failed to initialize\n", encoding="utf-8"
    )

    assert _has_indeterminate_initial_research(current.trusted_dir) is False


def test_started_initial_thread_without_completion_is_indeterminate(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    (prior / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior / "research-events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.started"}\n',
        encoding="utf-8",
    )

    assert _has_indeterminate_initial_research(current.trusted_dir) is True


def test_explicitly_failed_initial_turn_is_safe_to_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    (prior / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior / "research-events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"turn.failed","error":{"message":"provider rejected"}}\n',
        encoding="utf-8",
    )

    assert _has_indeterminate_initial_research(current.trusted_dir) is False


def test_explicit_failed_turn_is_safe_to_retry(tmp_path: Path) -> None:
    events = tmp_path / "codex-events.jsonl"
    events.write_text(
        '{"type":"error","message":"network unavailable"}\n'
        '{"type":"turn.failed","error":{"message":"network unavailable"}}\n',
        encoding="utf-8",
    )

    assert _events_show_failed_turn(events) is True


def test_review_report_scan_excludes_start_and_schema_json(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted" / "002-current"
    prior = trusted.parent / "001-prior"
    trusted.mkdir(parents=True)
    prior.mkdir()
    report = prior / "evidence-review-round-03.json"
    report.write_text("{}", encoding="utf-8")
    (prior / "evidence-review-round-03.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior / "evidence-review-round-03.schema.json").write_text(
        "{}", encoding="utf-8"
    )

    assert _review_report_paths(trusted) == [report]


def test_explicit_failed_formatter_is_retryable_but_not_reusable(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior_trusted = current.trusted_dir.parent / "001-prior"
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_trusted.mkdir()
    prior_attempt.mkdir()
    (prior_trusted / "formatter-starting.json").write_text("{}", encoding="utf-8")
    (prior_trusted / "codex-events.jsonl").write_text(
        '{"type":"turn.failed","error":{"message":"network unavailable"}}\n',
        encoding="utf-8",
    )
    (prior_attempt / "dossier.pending.json").write_text("{}", encoding="utf-8")

    assert _has_indeterminate_formatter_call(current) is False
    assert not (prior_trusted / "formatter-complete.marker").exists()
