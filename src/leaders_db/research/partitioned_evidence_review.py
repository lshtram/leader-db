"""Resumable one-chapter-at-a-time evidence-review orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.engine import Engine

from ._codex_worker_setup import WorkerAttempt
from .codex_worker_command import build_codex_exec_command
from .compact_handoff import build_chapter_research_handoff
from .evidence_review import (
    EvidenceReviewReport,
    assess_research_notebook,
    build_evidence_review_prompt,
    evidence_review_json_schema,
    validate_review_scope,
)
from .job_ledger import checkpoint_job
from .model_profiles import ResearchModelProfile
from .research_workflow import ResearchWorkflow

CodexRunner = Callable[..., None]


def run_partitioned_evidence_review(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    notebook: str,
    round_number: int,
    terminal: bool,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
    codex_runner: CodexRunner,
) -> EvidenceReviewReport:
    """Review each selected chapter independently and merge validated reports."""

    chapter_ids = tuple(
        dict.fromkeys(
            str(question_id).split(".", maxsplit=1)[0]
            for question_id in job["input"]["question_ids"]
        )
    )
    reports = [
        _load_or_run_chapter_review(
            engine,
            job=job,
            chapter_id=chapter_id,
            worker_id=worker_id,
            project_root=project_root,
            profile=profile,
            attempt=attempt,
            notebook=notebook,
            round_number=round_number,
            terminal=terminal,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
            codex_runner=codex_runner,
        )
        for chapter_id in chapter_ids
    ]
    merged = _merge_chapter_reviews(reports)
    output_path = attempt.trusted_dir / f"evidence-review-round-{round_number:02d}.json"
    output_path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
    return merged


def _load_or_run_chapter_review(
    engine: Engine,
    *,
    job: dict[str, Any],
    chapter_id: str,
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    notebook: str,
    round_number: int,
    terminal: bool,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
    codex_runner: CodexRunner,
) -> EvidenceReviewReport:
    suffix = f"round-{round_number:02d}-{chapter_id}"
    output_path = attempt.trusted_dir / f"evidence-review-{suffix}.json"
    recovered = _recover_chapter_review(attempt, output_path.name, chapter_id)
    if recovered is not None:
        return recovered
    chapter_notebook = build_chapter_research_handoff(
        attempt_dir=attempt.attempt_dir,
        fallback_notebook=notebook,
        chapter_id=chapter_id,
    )
    chapter_job = dict(job)
    chapter_job["input"] = dict(job["input"])
    chapter_job["input"]["question_ids"] = [
        question_id
        for question_id in job["input"]["question_ids"]
        if str(question_id).startswith(f"{chapter_id}.")
    ]
    workflow = ResearchWorkflow.model_validate(job["input"]["research_workflow"])
    qa = assess_research_notebook(
        chapter_notebook,
        methodology_ids=tuple(chapter_job["input"]["question_ids"]),
        workflow=workflow,
    )
    schema_path = attempt.trusted_dir / f"evidence-review-{suffix}.schema.json"
    events_path = attempt.trusted_dir / f"evidence-review-{suffix}.events.jsonl"
    schema_path.write_text(
        json.dumps(evidence_review_json_schema(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    prompt = build_evidence_review_prompt(
        job=chapter_job, notebook=chapter_notebook, qa=qa, terminal=terminal
    )
    (attempt.trusted_dir / f"evidence-review-{suffix}.prompt.txt").write_text(
        prompt, encoding="utf-8"
    )
    (attempt.trusted_dir / f"evidence-review-{suffix}.starting.json").write_text(
        json.dumps(
            {"job_id": job["id"], "round": round_number, "chapter_id": chapter_id},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={
            "phase": "evidence_review",
            "round": round_number,
            "chapter_id": chapter_id,
        },
    )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
    )
    codex_runner(
        engine,
        command=command,
        prompt=prompt,
        events_path=events_path,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    report = _read_report(output_path)
    _validate_chapter_report(report, chapter_id)
    return report


def _recover_chapter_review(
    attempt: WorkerAttempt, name: str, chapter_id: str
) -> EvidenceReviewReport | None:
    for trusted_dir in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        path = trusted_dir / name
        if not path.is_file():
            continue
        try:
            report = _read_report(path)
            _validate_chapter_report(report, chapter_id)
            return report
        except (OSError, UnicodeError, ValueError, ValidationError):
            continue
    return None


def _read_report(path: Path) -> EvidenceReviewReport:
    return EvidenceReviewReport.model_validate_json(path.read_text(encoding="utf-8"))


def _validate_chapter_report(
    report: EvidenceReviewReport, chapter_id: str
) -> None:
    validate_review_scope(
        report,
        selected_chapter_ids=(chapter_id,),
        expected_chapter_ids=(chapter_id,),
    )
    if len(report.chapter_reviews) != 1:
        raise ValueError(f"evidence review must contain exactly one {chapter_id} row")


def _merge_chapter_reviews(
    reports: list[EvidenceReviewReport],
) -> EvidenceReviewReport:
    selected = tuple(
        review.chapter_id
        for report in reports
        if report.needs_continuation
        for review in report.chapter_reviews
    )
    return EvidenceReviewReport(
        schema_version="ruler_evidence_review_v1",
        needs_continuation=bool(selected),
        selected_theme_ids=selected,
        chapter_reviews=tuple(
            review for report in reports for review in report.chapter_reviews
        ),
        global_findings=tuple(
            finding for report in reports for finding in report.global_findings
        ),
        reviewer_summary=" ".join(report.reviewer_summary for report in reports),
    )


__all__ = ["run_partitioned_evidence_review"]
