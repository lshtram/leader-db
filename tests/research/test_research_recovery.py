import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

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
    _existing_review_repair,
    _existing_supervisor_takeover,
    _has_indeterminate_review,
    _has_indeterminate_supervisor_takeover,
    _initial_expected_review_ids,
    _load_evidence_review,
    _rehydrate_completed_continuation,
    _should_use_supervisor_takeover,
)
from leaders_db.research.research_workflow import ResearchWorkflow


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


def test_scope_repair_review_is_recovered_across_attempts(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=False,
        selected_theme_ids=(),
        chapter_reviews=(),
        global_findings=(),
        reviewer_summary="Scope repaired.",
    )
    (prior.trusted_dir / "evidence-review-round-03-repair.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )

    assert _existing_review_repair(current, 3) == report


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


def test_completed_supervisor_takeover_is_recovered_without_new_call(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    events = prior.trusted_dir / "research-supervisor-takeover-round-02.events.jsonl"
    events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    output = prior.attempt_dir / "research-supervisor-takeover-round-02.md"
    output.write_text("Recovered Luna evidence.", encoding="utf-8")

    assert _existing_supervisor_takeover(current, 2) == (events, output)
    assert _has_indeterminate_supervisor_takeover(current, 2) is False


def test_failed_supervisor_takeover_is_safe_to_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    (prior.trusted_dir / "research-supervisor-takeover-round-02.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior.trusted_dir / "research-supervisor-takeover-round-02.events.jsonl").write_text(
        '{"type":"turn.failed"}\n', encoding="utf-8"
    )

    assert _existing_supervisor_takeover(current, 2) is None
    assert _has_indeterminate_supervisor_takeover(current, 2) is False


def test_started_supervisor_takeover_without_terminal_result_is_indeterminate(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    (prior.trusted_dir / "research-supervisor-takeover-round-02.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior.trusted_dir / "research-supervisor-takeover-round-02.events.jsonl").write_text(
        '{"type":"turn.started"}\n', encoding="utf-8"
    )

    assert _has_indeterminate_supervisor_takeover(current, 2) is True


def test_completed_invalid_review_is_safe_to_repair_on_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    (prior.trusted_dir / "evidence-review-round-01.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior.trusted_dir / "evidence-review-round-01.events.jsonl").write_text(
        '{"type":"turn.completed"}\n', encoding="utf-8"
    )
    (prior.trusted_dir / "evidence-review-round-01.json").write_text(
        '{"schema_version":"invalid"}', encoding="utf-8"
    )

    assert _has_indeterminate_review(current, 1) is False


def test_load_evidence_review_normalizes_question_ids_to_chapters(
    tmp_path: Path,
) -> None:
    path = tmp_path / "review.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_evidence_review_v1",
                "needs_continuation": True,
                "selected_theme_ids": ["1B.4", "1B.7", "2B.2"],
                "chapter_reviews": [
                    {
                        "chapter_id": chapter_id,
                        "defensible_evidence_estimate": 5,
                        "independent_source_family_estimate": 3,
                        "attribution_risk": "medium",
                        "substantive_issues": [],
                        "missing_themes": [],
                    }
                    for chapter_id in ("1B", "2B")
                ],
                "global_findings": [],
                "reviewer_summary": "Continue both chapters.",
            }
        ),
        encoding="utf-8",
    )

    report = _load_evidence_review(path)

    assert report.selected_theme_ids == ("1B", "2B")


def test_completed_review_recovery_normalizes_question_ids(tmp_path: Path) -> None:
    attempt = _attempt(tmp_path)
    review = {
        "schema_version": "ruler_evidence_review_v1",
        "needs_continuation": True,
        "selected_theme_ids": ["1B.4"],
        "chapter_reviews": [
            {
                "chapter_id": "1B",
                "defensible_evidence_estimate": 5,
                "independent_source_family_estimate": 3,
                "attribution_risk": "medium",
                "substantive_issues": [],
                "missing_themes": [],
            }
        ],
        "global_findings": [],
        "reviewer_summary": "Continue.",
    }
    (attempt.trusted_dir / "evidence-review-round-01.json").write_text(
        json.dumps(review), encoding="utf-8"
    )

    recovered = _completed_review_reports(attempt)

    assert recovered[0][1].selected_theme_ids == ("1B",)


@pytest.mark.parametrize("payload", ["[]", "null", '"review"'])
def test_load_evidence_review_rejects_non_object_json(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "review.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValidationError):
        _load_evidence_review(path)


@pytest.mark.parametrize("theme_id", ["1B.hallucinated", "1B-primary-records"])
def test_load_evidence_review_normalizes_descriptive_theme_suffix(
    tmp_path: Path, theme_id: str
) -> None:
    path = tmp_path / "review.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_evidence_review_v1",
                "needs_continuation": True,
                "selected_theme_ids": [theme_id],
                "chapter_reviews": [
                    {
                        "chapter_id": "1B",
                        "defensible_evidence_estimate": 5,
                        "independent_source_family_estimate": 3,
                        "attribution_risk": "medium",
                        "substantive_issues": [],
                        "missing_themes": [],
                    }
                ],
                "global_findings": [],
                "reviewer_summary": "Continue.",
            }
        ),
        encoding="utf-8",
    )

    report = _load_evidence_review(path)

    assert report.selected_theme_ids == ("1B",)


@pytest.mark.parametrize("theme_id", ["1B-2B", "2B-primary-records"])
def test_load_evidence_review_rejects_ambiguous_or_unreviewed_theme_prefix(
    tmp_path: Path, theme_id: str
) -> None:
    path = tmp_path / "review.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_evidence_review_v1",
                "needs_continuation": True,
                "selected_theme_ids": [theme_id],
                "chapter_reviews": [
                    {
                        "chapter_id": "1B",
                        "defensible_evidence_estimate": 5,
                        "independent_source_family_estimate": 3,
                        "attribution_risk": "medium",
                        "substantive_issues": [],
                        "missing_themes": [],
                    }
                ],
                "global_findings": [],
                "reviewer_summary": "Continue.",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="selected continuation themes"):
        _load_evidence_review(path)


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


def test_luna_takeover_starts_after_two_cheap_research_attempts() -> None:
    workflow = ResearchWorkflow(
        version=1,
        chapter_order=tuple(f"{index}B" for index in range(1, 9)),
    )

    assert _should_use_supervisor_takeover(round_number=1, workflow=workflow) is False
    assert _should_use_supervisor_takeover(round_number=2, workflow=workflow) is True
    assert _should_use_supervisor_takeover(round_number=3, workflow=workflow) is True


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


def test_latest_review_can_lower_an_earlier_overestimate(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    for number, estimate in ((1, 10), (2, 6)):
        report = EvidenceReviewReport(
            schema_version="ruler_evidence_review_v1",
            needs_continuation=False,
            selected_theme_ids=(),
            chapter_reviews=(
                ChapterEvidenceReview(
                    chapter_id="2B",
                    defensible_evidence_estimate=estimate,
                    independent_source_family_estimate=3,
                    attribution_risk="medium",
                    substantive_issues=(),
                    missing_themes=(),
                ),
            ),
            global_findings=(),
            reviewer_summary="Formatting may proceed.",
        )
        (current.trusted_dir / f"evidence-review-round-{number:02d}.json").write_text(
            report.model_dump_json(), encoding="utf-8"
        )

    assert _evidence_preservation_floors(current.trusted_dir) == {"2B": 5}


def test_same_round_repair_supersedes_original_review_estimate(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    for suffix, estimate in (("", 10), ("-repair", 5)):
        report = EvidenceReviewReport(
            schema_version="ruler_evidence_review_v1",
            needs_continuation=False,
            selected_theme_ids=(),
            chapter_reviews=(
                ChapterEvidenceReview(
                    chapter_id="2B",
                    defensible_evidence_estimate=estimate,
                    independent_source_family_estimate=3,
                    attribution_risk="medium",
                    substantive_issues=(),
                    missing_themes=(),
                ),
            ),
            global_findings=(),
            reviewer_summary="Formatting may proceed.",
        )
        (current.trusted_dir / f"evidence-review-round-01{suffix}.json").write_text(
            report.model_dump_json(), encoding="utf-8"
        )

    assert _evidence_preservation_floors(current.trusted_dir) == {"2B": 4}


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
        payload = report.model_dump(mode="json")
        if number == 1:
            payload["selected_theme_ids"] = ["2B:decision-chronology"]
        (current.trusted_dir / f"evidence-review-round-{number:02d}.json").write_text(
            json.dumps(payload), encoding="utf-8"
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


def test_operator_terminated_initial_turn_is_safe_to_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    (prior / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior / "research-events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.started"}\n',
        encoding="utf-8",
    )
    (prior / "research-operator-terminated.json").write_text(
        json.dumps(
            {
                "reason": "repeated MCP timeouts",
                "operator": "test-operator",
                "thread_id": "thread-1",
                "terminated_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    assert _has_indeterminate_initial_research(current.trusted_dir) is False


@pytest.mark.parametrize(
    "marker",
    [
        {},
        {"reason": "missing audit fields"},
        {
            "reason": "stale",
            "operator": "test-operator",
            "thread_id": "thread-1",
            "terminated_at": "2000-01-01T00:00:00+00:00",
        },
    ],
)
def test_invalid_operator_termination_remains_indeterminate(
    tmp_path: Path, marker: dict[str, str]
) -> None:
    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    (prior / "research-starting.json").write_text("{}", encoding="utf-8")
    (prior / "research-events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.started"}\n',
        encoding="utf-8",
    )
    (prior / "research-operator-terminated.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )

    assert _has_indeterminate_initial_research(current.trusted_dir) is True


def test_explicit_failed_turn_is_safe_to_retry(tmp_path: Path) -> None:
    events = tmp_path / "codex-events.jsonl"
    events.write_text(
        '{"type":"error","message":"network unavailable"}\n'
        '{"type":"turn.failed","error":{"message":"network unavailable"}}\n',
        encoding="utf-8",
    )

    assert _events_show_failed_turn(events) is True


def test_operator_terminated_continuation_is_safe_to_retry(tmp_path: Path) -> None:
    from leaders_db.research.notebook_continuation import (
        _has_indeterminate_continuation,
    )

    current = _attempt(tmp_path)
    prior = current.trusted_dir.parent / "001-prior"
    prior.mkdir()
    suffix = "round-01"
    (prior / f"research-continuation-{suffix}.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior / f"research-continuation-{suffix}.events.jsonl").write_text(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.started"}\n',
        encoding="utf-8",
    )
    (prior / f"research-continuation-{suffix}.operator-terminated.json").write_text(
        json.dumps(
            {
                "reason": "operator interrupted the continuation",
                "operator": "test-operator",
                "thread_id": "thread-1",
                "terminated_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    assert _has_indeterminate_continuation(current, 1) is False


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
