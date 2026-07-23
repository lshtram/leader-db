import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from leaders_db.research._codex_worker_artifacts import find_previous_candidate
from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.codex_worker import (
    WorkerOutputError,
    _embedded_ledger_manifest,
    _events_show_failed_turn,
    _has_indeterminate_formatter_call,
    _has_indeterminate_initial_research,
    _load_or_recover_research_ledger_manifest,
    _load_research_ledger_manifest,
    _recover_completed_initial_research,
    _recover_explicit_markdown_evidence,
    _recover_markdown_ledger_entries,
    _restore_explicit_cited_bullets,
    _restore_formatter_ledger_evidence,
    _validate_formatter_ledger_accounting,
    _validate_recovered_candidate_references,
)
from leaders_db.research.evidence_review import ChapterEvidenceReview, EvidenceReviewReport
from leaders_db.research.notebook_continuation import (
    _append_current_ledger_manifest,
    _completed_review_reports,
    _existing_continuation,
    _existing_review_repair,
    _existing_supervisor_takeover,
    _has_indeterminate_review,
    _has_indeterminate_supervisor_takeover,
    _initial_expected_review_ids,
    _load_evidence_review,
    _rehydrate_completed_continuation,
    _require_terminal_review,
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


def test_audited_aborted_review_is_safe_to_retry(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    prior = _attempt(tmp_path, "001-prior")
    (prior.trusted_dir / "evidence-review-round-01.starting.json").write_text(
        "{}", encoding="utf-8"
    )
    (prior.trusted_dir / "evidence-review-round-01.events.jsonl").write_text(
        '{"type":"turn.started"}\n', encoding="utf-8"
    )
    (prior.trusted_dir / "evidence-review-round-01.aborted.json").write_text(
        '{"reason":"stuck process was explicitly terminated"}', encoding="utf-8"
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


def test_load_evidence_review_recovers_newline_joined_question_ids(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_evidence_review_v1",
                "needs_continuation": True,
                "selected_theme_ids": [
                    "1B.1",
                    "1B.72026-07-22 1B.8\\n2B.1\\n3B.4",
                ],
                "chapter_reviews": [
                    {
                        "chapter_id": chapter,
                        "defensible_evidence_estimate": 5,
                        "independent_source_family_estimate": 3,
                        "attribution_risk": "medium",
                        "substantive_issues": [],
                        "missing_themes": [],
                    }
                    for chapter in ("1B", "2B", "3B")
                ],
                "global_findings": [],
                "reviewer_summary": "Continue.",
            }
        ),
        encoding="utf-8",
    )

    report = _load_evidence_review(path)

    assert report.selected_theme_ids == ("1B", "2B", "3B")


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


def test_recovered_candidate_rejects_unmapped_evidence() -> None:
    dossier = SimpleNamespace(
        evidence=(SimpleNamespace(evidence_id="E001"),),
        mappings=(),
        coverage=(
            SimpleNamespace(methodology_id="1B.1", evidence_ids=()),
        ),
    )

    with pytest.raises(WorkerOutputError, match="unmapped evidence"):
        _validate_recovered_candidate_references(dossier)


def test_formatter_must_preserve_final_ledger_keys_and_chapter_routing() -> None:
    notebook = """Research notebook.

--- RESEARCH LEDGER MANIFEST ---

{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"I-1","canonical_fact_key":"fact-1","chapter_ids":["2B"],"disposition":"final_evidence"},
  {"provisional_id":"I-2","canonical_fact_key":"fact-2","disposition":"context"},
  {"provisional_id":"I-3","canonical_fact_key":"fact-3","chapter_ids":["2B"],"disposition":"final_evidence"},
  {"provisional_id":"R-1","canonical_fact_key":"rejected-1","disposition":"rejected","reason":"Duplicate."}
]}
"""
    collapsed = SimpleNamespace(
        evidence=(
            SimpleNamespace(
                canonical_fact_key="context-does-not-compensate",
                final_evidence_use="context",
            ),
            SimpleNamespace(
                canonical_fact_key="second-context-does-not-compensate",
                final_evidence_use="context",
            ),
        )
    )

    collapsed.mappings = ()
    with pytest.raises(WorkerOutputError, match="omitted accepted final evidence"):
        _validate_formatter_ledger_accounting(collapsed, notebook=notebook)

    rewritten = SimpleNamespace(
        evidence=(
            SimpleNamespace(
                canonical_fact_key="rewritten-fact-1",
                final_evidence_use="final_evidence",
            ),
            SimpleNamespace(canonical_fact_key="fact-3", final_evidence_use="final_evidence"),
        )
    )
    rewritten.mappings = ()
    with pytest.raises(WorkerOutputError, match="fact-1"):
        _validate_formatter_ledger_accounting(rewritten, notebook=notebook)

    preserved = SimpleNamespace(
        evidence=(
            SimpleNamespace(
                evidence_id="E001",
                canonical_fact_key="fact-1",
                final_evidence_use="final_evidence",
            ),
            SimpleNamespace(
                evidence_id="E002",
                canonical_fact_key="fact-3",
                final_evidence_use="final_evidence",
            ),
        ),
        mappings=(
            SimpleNamespace(evidence_id="E001", methodology_id="2B.1"),
            SimpleNamespace(evidence_id="E002", methodology_id="2B.2"),
        ),
    )
    _validate_formatter_ledger_accounting(
        preserved, notebook=notebook + "\nLater reviewer and continuation prose.\n"
    )

    downgraded_but_preserved = SimpleNamespace(
        evidence=(
            SimpleNamespace(
                evidence_id="E001",
                canonical_fact_key="fact-1",
                final_evidence_use="context",
            ),
            SimpleNamespace(
                evidence_id="E002",
                canonical_fact_key="fact-3",
                final_evidence_use="final_evidence",
            ),
        ),
        mappings=preserved.mappings,
    )
    _validate_formatter_ledger_accounting(
        downgraded_but_preserved,
        notebook=notebook,
    )


def test_previous_candidate_exposes_distinct_evidence_from_other_attempts(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "job"
    attempts = job_dir / "attempts"
    trusted = job_dir / "trusted"
    for attempt_name, evidence in (
        (
            "001-first",
                [
                    _candidate_evidence(1)
                    | {
                        "canonical_fact_key": "fact-from-first",
                        "source_locator": "paragraph 1",
                    }
                ],
        ),
        (
            "002-strong",
            [
                    _candidate_evidence(1)
                    | {"canonical_fact_key": "fact-a", "source_locator": "paragraph 1"},
                    _candidate_evidence(2)
                    | {"canonical_fact_key": "fact-b", "source_locator": "paragraph 2"},
            ],
        ),
    ):
        attempt = attempts / attempt_name
        attempt.mkdir(parents=True)
        (trusted / attempt_name).mkdir(parents=True)
        (trusted / attempt_name / "formatter-complete.marker").write_text("complete\n")
        (attempt / "dossier.pending.json").write_text(
            json.dumps(
                {
                    "evidence": evidence,
                    "mappings": [],
                    "coverage": [],
                    "methodology_ids": ["2B.1"],
                }
            )
        )

    candidate = find_previous_candidate(job_dir, attempt_dir=attempts / "003-new")

    assert candidate is not None
    assert [item["canonical_fact_key"] for item in candidate["evidence"]] == [
        "fact-a",
        "fact-b",
    ]
    assert [
        item["canonical_fact_key"]
        for item in candidate["recovery_evidence_catalog"]
    ] == ["fact-from-first"]


def test_previous_candidate_tolerates_one_malformed_evidence_record(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "job"
    attempts = job_dir / "attempts"
    trusted = job_dir / "trusted"
    rich_attempt = attempts / "001-rich"
    empty_attempt = attempts / "002-empty"
    for attempt in (rich_attempt, empty_attempt):
        attempt.mkdir(parents=True)
        marker = trusted / attempt.name / "formatter-complete.marker"
        marker.parent.mkdir(parents=True)
        marker.write_text("complete\n")
    evidence = _candidate_evidence(1) | {"canonical_fact_key": "fact-1"}
    (rich_attempt / "dossier.pending.json").write_text(
        json.dumps(
            {
                "evidence": [evidence, {"not": "valid evidence"}],
                "mappings": [
                    {
                        "evidence_id": evidence["evidence_id"],
                        "methodology_id": "1B.1",
                        "relation": "context",
                        "relevance": "Useful evidence survives a malformed sibling.",
                    }
                ],
                "coverage": [
                    {
                        "methodology_id": "1B.1",
                        "status": "partially_covered",
                        "evidence_ids": [evidence["evidence_id"]],
                        "reason": "One useful record is available.",
                    }
                ],
                "methodology_ids": ["1B.1"],
            }
        )
    )
    (empty_attempt / "dossier.pending.json").write_text(
        json.dumps(
            {
                "evidence": [],
                "mappings": [],
                "coverage": [],
                "methodology_ids": ["1B.1"],
            }
        )
    )

    candidate = find_previous_candidate(job_dir, attempt_dir=attempts / "003-new")

    assert candidate is not None
    assert candidate["evidence"][0]["canonical_fact_key"] == "fact-1"


def test_formatter_restores_exact_manifest_fact_from_recovery_catalog() -> None:
    candidate = {
        "evidence": [],
        "mappings": [],
        "coverage": [
            {
                "methodology_id": "1B.2",
                "status": "research_blocked",
                "evidence_ids": [],
                "reason": "Formatter omitted the reviewed fact.",
            }
        ],
        "methodology_ids": ["1B.2"],
        "normalization_warnings": [],
    }
    recovered_fact = _candidate_evidence(1) | {
        "canonical_fact_key": "reviewed-fact",
        "source_locator": "page 4",
    }
    notebook = """Notebook.
--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"R001","canonical_fact_key":"reviewed-fact",
   "chapter_ids":["1B"],"methodology_ids":["1B.2"],
   "disposition":"final_evidence"}
]}
"""

    restored = _restore_formatter_ledger_evidence(
        candidate,
        existing_candidate={"evidence": [], "recovery_evidence_catalog": [recovered_fact]},
        notebook=notebook,
    )

    assert restored["evidence"][0]["canonical_fact_key"] == "reviewed-fact"
    assert restored["evidence"][0]["evidence_id"] == "E001"
    assert restored["mappings"] == [
        {
            "evidence_id": "E001",
            "methodology_id": "1B.2",
            "relation": "context",
            "relevance": "Restored exact reviewed ledger routing.",
        }
    ]
    assert restored["coverage"][0]["status"] == "partially_covered"
    assert restored["coverage"][0]["evidence_ids"] == ["E001"]
    assert "1 canonical fact key(s)" in restored["normalization_warnings"][-1]


def test_formatter_recovers_explicit_cited_bullets_as_context_without_manifest() -> None:
    candidate = {
        "evidence": [],
        "mappings": [],
        "coverage": [],
        "methodology_ids": ["3B.3", "3B.6"],
        "normalization_warnings": [],
    }
    notebook = """Research handoff without a JSON manifest.

- **EV057** — GAO found that review boards generally found incidents aligned
  with policy, while federal standards were tightened. This supports safeguards,
  not population outcomes. Lens: `3B.3`, `3B.6`.
  [GAO-23-105927](https://www.gao.gov/products/gao-23-105927), lines 284–289.
- **RB058** — No complete target-year denominator was found.
"""

    restored = _restore_explicit_cited_bullets(candidate, notebook=notebook)

    assert len(restored["evidence"]) == 1
    assert restored["evidence"][0]["evidence_id"] == "EV057"
    assert restored["evidence"][0]["final_evidence_use"] == "context"
    assert restored["evidence"][0]["publication_date"] == "unknown_not_recorded"
    assert {
        mapping["methodology_id"] for mapping in restored["mappings"]
    } == {"3B.3", "3B.6"}


def test_cited_bullet_recovery_repairs_unresolvable_environment_support() -> None:
    candidate = {
        "evidence": [],
        "mappings": [],
        "coverage": [],
        "methodology_ids": ["3B.3"],
        "normalization_warnings": [],
        "evidence_environment": {"supporting_evidence_ids": ["E001"]},
    }
    notebook = """- **EV057** — GAO found a federal safeguard.
Lens: `3B.3`. [GAO](https://www.gao.gov/products/gao-23-105927), lines 284–289.
"""

    restored = _restore_explicit_cited_bullets(candidate, notebook=notebook)

    assert restored["evidence_environment"]["supporting_evidence_ids"] == ["EV057"]


def test_restored_manifest_fact_precedes_equivalent_rewritten_candidate() -> None:
    rewritten = _candidate_evidence(1) | {
        "canonical_fact_key": "formatter-rewritten-key",
        "source_locator": "page 4",
    }
    reviewed = rewritten | {
        "evidence_id": "E009",
        "canonical_fact_key": "reviewed-key",
    }
    candidate = {
        "evidence": [rewritten],
        "mappings": [],
        "coverage": [],
        "methodology_ids": ["1B.1"],
    }
    notebook = """--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"R001","canonical_fact_key":"reviewed-key",
   "chapter_ids":["1B"],"methodology_ids":["1B.1"],
   "disposition":"final_evidence"}
]}
"""

    restored = _restore_formatter_ledger_evidence(
        candidate,
        existing_candidate={"evidence": [reviewed]},
        notebook=notebook,
    )

    assert [item["canonical_fact_key"] for item in restored["evidence"]] == [
        "reviewed-key",
        "formatter-rewritten-key",
    ]


def test_formatter_restores_missing_exact_route_for_emitted_manifest_fact() -> None:
    evidence = _candidate_evidence(1) | {
        "canonical_fact_key": "reviewed-key",
        "source_locator": "page 4",
    }
    candidate = {
        "evidence": [evidence],
        "mappings": [],
        "coverage": [],
        "methodology_ids": ["1B.4", "1B.10"],
    }
    notebook = """--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"R001","canonical_fact_key":"reviewed-key",
   "chapter_ids":["1B"],"methodology_ids":["1B.4","1B.10"],
   "disposition":"final_evidence"}
]}
"""

    restored = _restore_formatter_ledger_evidence(
        candidate,
        existing_candidate=None,
        notebook=notebook,
    )

    assert {
        (item["evidence_id"], item["methodology_id"])
        for item in restored["mappings"]
    } == {("E001", "1B.4"), ("E001", "1B.10")}
    assert {item["methodology_id"] for item in restored["coverage"]} == {
        "1B.4",
        "1B.10",
    }


def test_complete_markdown_evidence_block_can_be_recovered_exactly() -> None:
    key = "https://example.test/report#L92-L150"
    notebook = f"""### P027 — Independent reporting

- Canonical fact key: `{key}`
- Source: Example News, 26 July 2022.
- Claim: Construction began after the safety-related concrete pour.
- Locator: HTML lines 92–108 and 116–128.
- Source type/confidence: independent reporting; medium for the event.
- Attribution: national project under executive authority, with agency implementation.
- Role: independent corroboration of project activity.
"""

    recovered = _recover_explicit_markdown_evidence(notebook, key)

    assert recovered is not None
    assert recovered["canonical_fact_key"] == key
    assert recovered["url"] == key
    assert recovered["source_locator"] == "HTML lines 92–108 and 116–128."
    assert recovered["source_confidence"] == "medium"
    assert recovered["publisher"] == "Example News"


def test_incomplete_markdown_evidence_block_is_not_recovered() -> None:
    key = "https://example.test/report#p4"
    notebook = f"""### P027 — Incomplete item
- Canonical fact key: `{key}`
- Claim: A claim without a precise producer record.
"""

    assert _recover_explicit_markdown_evidence(notebook, key) is None


def test_markdown_evidence_can_join_by_immutable_provisional_id() -> None:
    key = "https://example.test/canonical#L92-L150"
    notebook = """### P027 — Independent reporting
- Canonical fact key: `https://example.test/stale-display`
- Source: Example News, 26 July 2022.
- Claim: Construction began after the safety-related concrete pour.
- Locator: HTML lines 92–108 and 116–128.
- Source type/confidence: independent reporting; medium for the event.
- Attribution: national project under executive authority.
- Role: independent corroboration.
"""

    recovered = _recover_explicit_markdown_evidence(
        notebook,
        key,
        provisional_id="P027",
    )

    assert recovered is not None
    assert recovered["canonical_fact_key"] == key


def test_markdown_evidence_accepts_separate_title_publisher_and_date() -> None:
    key = "https://example.test/report.pdf#P2|dual-use risk"
    notebook = """### E034 — Dual-use biotechnology risk
- Canonical URL: https://example.test/report.pdf
- Title: National statement
- Publisher: Example Ministry
- Date: 2022
- Claim: The statement recognizes dual-use biotechnology risk.
- Locator: PDF p. 2
- Profile: `source_confidence=high`; `source_type=official_statement`.
- Attribution: State position; no direct ruler wording.
- Role: final evidence for the stated position.
"""

    recovered = _recover_explicit_markdown_evidence(
        notebook,
        key,
        provisional_id="E034",
    )

    assert recovered is not None
    assert recovered["title"] == "National statement"
    assert recovered["publisher"] == "Example Ministry"
    assert recovered["publication_date"] == "2022"


def test_markdown_manifest_recovery_accepts_bold_id_handoff_style() -> None:
    handoff = """## Chapter 2B

- **ID 2B-AFG-001** — *Citation:* Example, 2023. URL: https://example.org/a.
  *Claim:* A concrete diplomatic action. *Supported lenses:* 2B.1, 2B.7.

- **ID 2B-AFG-002** — *Citation:* Example, 2023. URL: https://example.org/b.
  *Claim:* A second action. *Role:* context. *Supported lenses:* 2B.5.
"""

    entries = _recover_markdown_ledger_entries(handoff)

    assert entries == [
        {
            "provisional_id": "2B-AFG-001",
            "canonical_fact_key": "recovered:https://example.org/a|2B-AFG-001",
            "disposition": "final_evidence",
            "chapter_ids": ["2B"],
            "methodology_ids": ["2B.1", "2B.7"],
        },
        {
            "provisional_id": "2B-AFG-002",
            "canonical_fact_key": "recovered:https://example.org/b|2B-AFG-002",
            "disposition": "context",
            "chapter_ids": ["2B"],
            "methodology_ids": ["2B.5"],
        },
    ]


def test_research_ledger_manifest_requires_rejection_reason(tmp_path: Path) -> None:
    path = tmp_path / "research-ledger-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "R-1",
                        "canonical_fact_key": "rejected-1",
                        "disposition": "rejected",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkerOutputError, match="requires a reason"):
        _load_research_ledger_manifest(path)


def test_markdown_manifest_recovers_exact_lens_mappings() -> None:
    handoff = """### E038 — Appeals court found coercion risk
- **Canonical fact key:** `https://example.test/ruling|p1|coercion`
- **Disposition:** final_evidence
- **Mappings:** 4B.2, 4B.6, 4B.9.
"""

    entries = _recover_markdown_ledger_entries(handoff)

    assert entries[0]["chapter_ids"] == ["4B"]
    assert entries[0]["methodology_ids"] == ["4B.2", "4B.6", "4B.9"]


def test_formatter_accounting_rejects_dropped_exact_lens_mapping() -> None:
    notebook = """Notebook.
--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"E038","canonical_fact_key":"fact-38",
   "chapter_ids":["4B"],"methodology_ids":["4B.2","4B.6"],
   "disposition":"final_evidence"}
]}
"""
    dossier = SimpleNamespace(
        evidence=(
            SimpleNamespace(
                evidence_id="E038",
                canonical_fact_key="fact-38",
                final_evidence_use="final_evidence",
            ),
        ),
        mappings=(
            SimpleNamespace(evidence_id="E038", methodology_id="4B.6"),
        ),
    )

    with pytest.raises(WorkerOutputError, match="dropped accepted lens routing"):
        _validate_formatter_ledger_accounting(dossier, notebook=notebook)


def test_embedded_research_ledger_manifest_is_recovered(tmp_path: Path) -> None:
    manifest_path = tmp_path / "research-ledger-manifest.json"
    handoff_path = tmp_path / "research-handoff.md"
    handoff_path.write_text(
        "Notebook prose.\n\n```json\n"
        '{"schema_version":"ruler_research_ledger_manifest_v1","entries":['
        '{"provisional_id":"E-1","canonical_fact_key":"fact-1",'
        '"disposition":"final_evidence"}]}\n```\nMore prose.\n',
        encoding="utf-8",
    )

    recovered = _load_or_recover_research_ledger_manifest(
        manifest_path, handoff_path=handoff_path
    )

    assert recovered["entries"][0]["canonical_fact_key"] == "fact-1"
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == recovered


def test_markdown_manifest_recovery_preserves_discovery_status_and_section_boundary() -> None:
    handoff = """### R027 — Inaccessible source

- Canonical fact key: `https://example.org/inaccessible|candidate`
- Status: `discovery_only`.
- Reason: Retrieval failed; no precise locator or excerpt was verified.
- Lens mappings suggested: `1B.1`, `1B.2`.

## Later chapter

This unrelated section discusses 2B.1 and must not expand R027 routing.
"""

    recovered = _recover_markdown_ledger_entries(handoff)

    assert recovered == [
        {
            "provisional_id": "R027",
            "canonical_fact_key": "https://example.org/inaccessible|candidate",
            "disposition": "discovery_only",
            "chapter_ids": ["1B"],
            "methodology_ids": ["1B.1", "1B.2"],
        }
    ]


def test_embedded_manifest_cannot_promote_explicit_discovery_only_item() -> None:
    notebook = """### R027 — Inaccessible source

- Canonical fact key: `https://example.org/inaccessible|candidate`
- Status: `discovery_only`.
- Reason: No precise locator or excerpt was verified.

--- RESEARCH LEDGER MANIFEST ---

{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"R027",
   "canonical_fact_key":"https://example.org/inaccessible|candidate",
   "chapter_ids":["1B"],"methodology_ids":["1B.1"],
   "disposition":"final_evidence"}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert manifest["entries"][0]["disposition"] == "discovery_only"


def test_embedded_manifest_discards_historical_heading_replay() -> None:
    notebook = """### P027 — Historical display entry
- Canonical fact key: `stale-display-url`
- Role: final_evidence.

--- RESEARCH LEDGER MANIFEST ---

{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"P027","canonical_fact_key":"canonical-url#L1-L3",
   "chapter_ids":["1B"],"methodology_ids":["1B.3"],
   "disposition":"final_evidence"},
  {"provisional_id":"P027-2","canonical_fact_key":"stale-display-url",
   "chapter_ids":["1B"],"methodology_ids":["1B.3"],
   "disposition":"final_evidence"}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert [item["canonical_fact_key"] for item in manifest["entries"]] == [
        "canonical-url#L1-L3"
    ]


def test_embedded_manifest_preserves_first_canonical_key_for_existing_id() -> None:
    notebook = """Initial research.
--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"P027","canonical_fact_key":"canonical-url#L92-L150",
   "chapter_ids":["1B"],"methodology_ids":["1B.3"],
   "disposition":"context"}
]}

Later continuation.
--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"P027","canonical_fact_key":"stale-display-url",
   "chapter_ids":["1B"],"methodology_ids":["1B.3","1B.7"],
   "disposition":"final_evidence"}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert manifest["entries"][0]["canonical_fact_key"] == "canonical-url#L92-L150"
    assert manifest["entries"][0]["methodology_ids"] == ["1B.3", "1B.7"]
    assert manifest["entries"][0]["disposition"] == "context"


def test_embedded_manifest_uses_earliest_fenced_handoff_before_separator() -> None:
    notebook = """Researcher handoff:
```json
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"P027","canonical_fact_key":"canonical-url#L92-L150",
   "chapter_ids":["1B"],"methodology_ids":["1B.3"],
   "disposition":"final_evidence"}
]}
```

--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"P027","canonical_fact_key":"stale-display-url",
   "chapter_ids":["1B"],"methodology_ids":["1B.3","1B.7"],
   "disposition":"final_evidence"}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert manifest["entries"][0]["canonical_fact_key"] == "canonical-url#L92-L150"


def test_embedded_manifest_preserves_first_explicit_update_for_later_id() -> None:
    notebook = """Initial manifest.
--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[]}

## Manifest update
```json
[
  {"provisional_id":"E032","canonical_fact_key":"precise-url#L15-L39|meeting",
   "chapter_ids":["1B"],"methodology_ids":["1B.7"],"disposition":"context"}
]
```

--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
  {"provisional_id":"E032","canonical_fact_key":"recovered:display-url|E032",
   "chapter_ids":["1B"],"methodology_ids":["1B.7"],
   "disposition":"final_evidence"}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert manifest["entries"][0]["canonical_fact_key"] == (
        "precise-url#L15-L39|meeting"
    )
    assert manifest["entries"][0]["disposition"] == "context"


def test_invalid_embedded_research_ledger_manifest_is_ignored(tmp_path: Path) -> None:
    handoff_path = tmp_path / "research-handoff.md"
    handoff_path.write_text(
        '{"schema_version":"wrong","entries":[]}', encoding="utf-8"
    )

    assert (
        _load_or_recover_research_ledger_manifest(
            tmp_path / "research-ledger-manifest.json", handoff_path=handoff_path
        )
        is None
    )


def test_markdown_research_ledger_is_recovered(tmp_path: Path) -> None:
    handoff_path = tmp_path / "research-handoff.md"
    handoff_path.write_text(
        """# Global evidence ledger

## E001 — First item
- **Canonical fact key:** `https://example.test/a|p2|claim a`
- **Final use:** `context` pending exact extraction.

## E002 — Second item
- **Canonical fact key:** `https://example.test/b|s1|claim b`
- **Final use:** `final_evidence`.
""",
        encoding="utf-8",
    )

    recovered = _load_or_recover_research_ledger_manifest(
        tmp_path / "research-ledger-manifest.json", handoff_path=handoff_path
    )

    assert recovered["entries"] == [
        {
            "provisional_id": "E001",
                "canonical_fact_key": "https://example.test/a|p2|claim a",
                "chapter_ids": [],
                "disposition": "context",
        },
        {
            "provisional_id": "E002",
                "canonical_fact_key": "https://example.test/b|s1|claim b",
                "chapter_ids": [],
                "disposition": "final_evidence",
        },
    ]


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
    (prior_attempt / "research-ledger-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "I-1",
                        "canonical_fact_key": "continued-fact",
                        "disposition": "final_evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
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
    assert "continued-fact" in recovered[1]
    assert (current.attempt_dir / "research-ledger-manifest.json").is_file()
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
    (prior_attempt / "research-ledger-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "I-1",
                        "canonical_fact_key": "initial-fact",
                        "disposition": "context",
                    }
                ],
            }
        ),
        encoding="utf-8",
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
    assert "initial-fact" in recovered[1]
    assert (current.attempt_dir / "research-ledger-manifest.json").is_file()


def test_initial_recovery_without_file_uses_embedded_manifest(tmp_path: Path) -> None:
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
    (prior_attempt / "research-handoff.md").write_text(
        "Research.\n```json\n"
        '{"schema_version":"ruler_research_ledger_manifest_v1","entries":['
        '{"provisional_id":"E-1","canonical_fact_key":"embedded-fact",'
        '"disposition":"final_evidence"}]}\n```\n',
        encoding="utf-8",
    )

    recovered = _recover_completed_initial_research(
        attempt=current,
        job={
            "job_key": "dossier:test",
            "provider_profile": "researcher",
            "provider": "openai",
            "model": "fixture",
        },
    )

    assert recovered is not None
    assert "embedded-fact" in recovered[1]
    assert (prior_attempt / "research-ledger-manifest.json").is_file()


def test_continuation_recovery_without_adjacent_manifest_uses_markdown_ledger(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_attempt.mkdir()

    notebook = _append_current_ledger_manifest(
        """Accumulated notebook.

## E101 — Continued fact
- **Canonical fact key:** `https://example.test/continued|p4|continued fact`
- **Final use:** `final_evidence`.
""",
        current,
        source_attempt_dir=prior_attempt,
    )

    assert "https://example.test/continued|p4|continued fact" in notebook
    assert (prior_attempt / "research-ledger-manifest.json").is_file()


def test_continuation_recovery_without_any_ledger_remains_permissive(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    prior_attempt = current.attempt_dir.parent / "001-prior"
    prior_attempt.mkdir()

    notebook = _append_current_ledger_manifest(
        "Unaccounted prose.", current, source_attempt_dir=prior_attempt
    )

    assert notebook == "Unaccounted prose."


def test_continuation_manifest_merges_new_notebook_entries(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    manifest_path = current.attempt_dir / "research-ledger-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "E100",
                        "canonical_fact_key": "old|p1|fact",
                        "disposition": "final_evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    notebook = _append_current_ledger_manifest(
        """## E101 — Continued fact
- **Canonical fact key:** `new|p2|fact`
- **Final use:** `final_evidence`.
""",
        current,
    )

    assert '"provisional_id": "E100"' in notebook
    assert '"provisional_id": "E101"' in notebook


def test_continuation_keeps_only_latest_embedded_manifest(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    notebook = _append_current_ledger_manifest(
        """## E101 — First fact
- **Canonical fact key:** `first|p1|fact`
- **Final use:** `final_evidence`.
""",
        current,
    )
    updated = _append_current_ledger_manifest(
        notebook
        + """

## E102 — Second fact
- **Canonical fact key:** `second|p2|fact`
- **Final use:** `final_evidence`.
""",
        current,
    )

    assert updated.count("--- RESEARCH LEDGER MANIFEST ---") == 1
    assert "first|p1|fact" in updated
    assert "second|p2|fact" in updated


def test_continuation_manifest_disposition_is_monotonic(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    manifest_path = current.attempt_dir / "research-ledger-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "E100",
                        "canonical_fact_key": "same|p1|fact",
                        "chapter_ids": ["1B"],
                        "methodology_ids": ["1B.1"],
                        "disposition": "discovery_only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    promoted = _append_current_ledger_manifest(
        'SOURCE_CLAIM_JSON: {"provisional_id":"E100","canonical_fact_key":'
        '"same|p1|fact","chapter_ids":["2B"],"methodology_ids":["2B.1"],'
        '"disposition":"final_evidence"}',
        current,
    )
    promoted_manifest = json.loads(
        promoted.rsplit("--- RESEARCH LEDGER MANIFEST ---", maxsplit=1)[1]
    )
    assert promoted_manifest["entries"][0]["disposition"] == "final_evidence"
    assert promoted_manifest["entries"][0]["chapter_ids"] == ["1B", "2B"]

    demoted = _append_current_ledger_manifest(
        'SOURCE_CLAIM_JSON: {"provisional_id":"E100","canonical_fact_key":'
        '"same|p1|fact","chapter_ids":["3B"],"methodology_ids":["3B.1"],'
        '"disposition":"rejected"}',
        current,
    )
    demoted_manifest = json.loads(
        demoted.rsplit("--- RESEARCH LEDGER MANIFEST ---", maxsplit=1)[1]
    )
    assert demoted_manifest["entries"][0]["disposition"] == "final_evidence"
    assert demoted_manifest["entries"][0]["chapter_ids"] == ["1B", "2B", "3B"]


def test_markdown_table_fallback_is_recovered_acceptingly() -> None:
    recovered = _recover_markdown_ledger_entries(
        """| ID | Material claim and locator | Limits | Period / methodology |
|---|---|---|---|
| AMLO22-R01 | Claim. [INE](https://example.test/ine), lines 1-4. | Limit. | 2022; 1B, 4B |
"""
    )

    assert recovered == [
        {
            "provisional_id": "AMLO22-R01",
            "canonical_fact_key": "recovered:https://example.test/ine|AMLO22-R01",
            "disposition": "final_evidence",
            "chapter_ids": ["1B", "4B"],
        }
    ]


def test_initial_claim_lines_normalize_disposition_and_routing(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.md"
    manifest = tmp_path / "manifest.json"
    handoff.write_text(
        'SOURCE_CLAIM_JSON: {"provisional_id":"R01","canonical_fact_key":"fact",'
        '"disposition":"accepted","chapter_ids":["4B","bad"],'
        '"methodology_ids":["authority_baseline","4B.2"],'
        '"url":"https://example.test","claim":"Claim","locator":"lines 1-2"}\n',
        encoding="utf-8",
    )

    recovered = _load_or_recover_research_ledger_manifest(
        manifest, handoff_path=handoff
    )

    assert recovered is not None
    assert recovered["entries"] == [
        {
            "provisional_id": "R01",
            "canonical_fact_key": "fact",
            "disposition": "final_evidence",
            "chapter_ids": ["4B"],
            "methodology_ids": ["4B.2"],
            "url": "https://example.test",
            "claim": "Claim",
            "locator": "lines 1-2",
        }
    ]


def test_continuation_manifest_renames_conflicting_id_reuse(tmp_path: Path) -> None:
    current = _attempt(tmp_path)
    (current.attempt_dir / "research-ledger-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "E101",
                        "canonical_fact_key": "old|p1|fact",
                        "disposition": "final_evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    notebook = _append_current_ledger_manifest(
        """## E101 — Different fact
- **Canonical fact key:** `new|p2|different`
- **Final use:** `final_evidence`.
""",
        current,
    )

    assert '"provisional_id": "E101"' in notebook
    assert '"provisional_id": "E101-2"' in notebook


def test_continuation_does_not_reparse_headings_before_authoritative_manifest(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    (current.attempt_dir / "research-ledger-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "P027",
                        "canonical_fact_key": "canonical-url#L92-L150",
                        "chapter_ids": ["1B"],
                        "methodology_ids": ["1B.3"],
                        "disposition": "final_evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    notebook = """### P027 — Historical display heading
- Canonical fact key: `stale-display-url`
- Role: final_evidence.

--- RESEARCH LEDGER MANIFEST ---

{"schema_version":"ruler_research_ledger_manifest_v1","entries":[]}

## Evidence review
No continuation was requested.
"""

    updated = _append_current_ledger_manifest(notebook, current)
    final_manifest = json.loads(
        updated.rsplit("--- RESEARCH LEDGER MANIFEST ---", maxsplit=1)[1]
    )

    assert [item["canonical_fact_key"] for item in final_manifest["entries"]] == [
        "canonical-url#L92-L150"
    ]


def test_continuation_manifest_recovers_from_invalid_optional_manifest(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    (current.attempt_dir / "research-ledger-manifest.json").write_text(
        '{"schema_version":"wrong","entries":[]}', encoding="utf-8"
    )

    notebook = _append_current_ledger_manifest(
        """## E201 — Recovered fact
- **Canonical fact key:** `recovered|p2|fact`
- **Final use:** `final_evidence`.
""",
        current,
    )

    assert '"provisional_id": "E201"' in notebook


def test_continuation_manifest_consolidates_duplicate_canonical_key(
    tmp_path: Path,
) -> None:
    current = _attempt(tmp_path)
    (current.attempt_dir / "research-ledger-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [
                    {
                        "provisional_id": "E100",
                        "canonical_fact_key": "same|p1|fact",
                        "disposition": "final_evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    notebook = _append_current_ledger_manifest(
        """## E101 — Duplicate fact
- **Canonical fact key:** `same|p1|fact`
- **Final use:** `final_evidence`.
""",
        current,
    )

    assert '"provisional_id": "E100"' in notebook
    assert '"provisional_id": "E101"' not in notebook


def test_terminal_review_cannot_request_more_research() -> None:
    report = EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=True,
        selected_theme_ids=("4B",),
        chapter_reviews=(
            ChapterEvidenceReview(
                chapter_id="4B",
                defensible_evidence_estimate=1,
                independent_source_family_estimate=1,
                attribution_risk="high",
                substantive_issues=("More research required.",),
                missing_themes=("Media freedom",),
            ),
        ),
        global_findings=("Not terminal.",),
        reviewer_summary="Continuation required.",
    )

    with pytest.raises(ValueError, match="final evidence review"):
        _require_terminal_review(report)


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


def test_explicit_failed_continuation_is_safe_to_retry(tmp_path: Path) -> None:
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
        '{"type":"turn.started"}\n'
        '{"type":"error","message":"Selected model is at capacity."}\n'
        '{"type":"turn.failed","error":{"message":"Selected model is at capacity."}}\n',
        encoding="utf-8",
    )

    assert _has_indeterminate_continuation(current, 1) is False


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
