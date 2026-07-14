from pathlib import Path

from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.codex_worker import (
    _events_show_failed_turn,
    _has_indeterminate_formatter_call,
    _recover_completed_initial_research,
    _review_report_paths,
)
from leaders_db.research.evidence_review import ChapterEvidenceReview, EvidenceReviewReport
from leaders_db.research.notebook_continuation import (
    _completed_review_reports,
    _existing_continuation,
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
