"""Review and resume one direct-search researcher session before formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.engine import Engine

from ._codex_worker_setup import WorkerAttempt
from .codex_worker_command import (
    build_codex_exec_command,
    build_codex_resume_command,
    read_codex_thread_id,
)
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

ResearchCheckpoint = tuple[Path, str, Path, str, str]


@dataclass(frozen=True)
class NotebookContinuationResult:
    """Final notebook after zero or more reviewer-directed resumptions."""

    checkpoint: ResearchCheckpoint
    qa_reviewed: bool
    resume_count: int


def review_and_resume_notebook_if_needed(
    engine: Engine,
    *,
    checkpoint: ResearchCheckpoint,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    researcher_profile: ResearchModelProfile,
    reviewer_profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    workflow: ResearchWorkflow,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> NotebookContinuationResult:
    """Review all chapters and resume the same researcher up to the configured cap."""

    current = checkpoint
    reviewed = False
    resume_count = 0
    completed_reports = _completed_review_reports(attempt)
    if completed_reports and not completed_reports[-1][1].needs_continuation:
        return NotebookContinuationResult(current, True, 0)
    if completed_reports:
        last_round = completed_reports[-1][0]
        recovered_continuation = _existing_continuation(attempt, last_round)
        if (
            recovered_continuation is not None
            and f"RESEARCH CONTINUATION ROUND {last_round}" not in current[1]
        ):
            current = _rehydrate_completed_continuation(
                checkpoint=current,
                report=completed_reports[-1][1],
                recovered=recovered_continuation,
                attempt=attempt,
                job=job,
                round_number=last_round,
            )
        start_round = (
            last_round + 1
            if recovered_continuation is not None
            else last_round
        )
    else:
        start_round = 1
    expected_review_ids = _initial_expected_review_ids(job)
    for round_number in range(start_round, workflow.max_review_rounds + 1):
        qa = assess_research_notebook(
            current[1],
            methodology_ids=tuple(job["input"]["question_ids"]),
            workflow=workflow,
        )
        report = _existing_review_report(attempt, round_number) or _run_evidence_review(
            engine,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            profile=reviewer_profile,
            attempt=attempt,
            notebook=current[1],
            qa=qa,
            round_number=round_number,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
        reviewed = True
        try:
            validate_review_scope(
                report,
                selected_chapter_ids=qa.selected_chapter_ids,
                expected_chapter_ids=expected_review_ids,
            )
        except ValueError:
            report = _repair_evidence_review_scope(
                engine,
                report=report,
                job=job,
                worker_id=worker_id,
                project_root=project_root,
                profile=reviewer_profile,
                attempt=attempt,
                notebook=current[1],
                qa=qa,
                round_number=round_number,
                expected_chapter_ids=expected_review_ids,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
            validate_review_scope(
                report,
                selected_chapter_ids=qa.selected_chapter_ids,
                expected_chapter_ids=expected_review_ids,
            )
        if not report.needs_continuation:
            break
        takeover = _should_use_supervisor_takeover(
            round_number=round_number, workflow=workflow
        )
        if takeover:
            if "dossier_researcher" not in reviewer_profile.roles:
                raise ValueError(
                    "supervisor takeover profile does not permit dossier research"
                )
            current = _run_supervisor_takeover(
                engine,
                checkpoint=current,
                report=report,
                job=job,
                worker_id=worker_id,
                project_root=project_root,
                profile=reviewer_profile,
                attempt=attempt,
                round_number=round_number,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
        else:
            current = _resume_researcher(
                engine,
                checkpoint=current,
                report=report,
                job=job,
                worker_id=worker_id,
                project_root=project_root,
                profile=researcher_profile,
                attempt=attempt,
                round_number=round_number,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
        resume_count += 1
    if reviewed and report.needs_continuation:
        qa = assess_research_notebook(
            current[1],
            methodology_ids=tuple(job["input"]["question_ids"]),
            workflow=workflow,
        )
        final_round = workflow.max_review_rounds + 1
        final_report = _existing_review_report(attempt, final_round) or _run_evidence_review(
            engine,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            profile=reviewer_profile,
            attempt=attempt,
            notebook=current[1],
            qa=qa,
            round_number=final_round,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
        try:
            validate_review_scope(
                final_report,
                selected_chapter_ids=qa.selected_chapter_ids,
                expected_chapter_ids=expected_review_ids,
            )
        except ValueError:
            final_report = _repair_evidence_review_scope(
                engine,
                report=final_report,
                job=job,
                worker_id=worker_id,
                project_root=project_root,
                profile=reviewer_profile,
                attempt=attempt,
                notebook=current[1],
                qa=qa,
                round_number=final_round,
                expected_chapter_ids=expected_review_ids,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
            validate_review_scope(
                final_report,
                selected_chapter_ids=qa.selected_chapter_ids,
                expected_chapter_ids=expected_review_ids,
            )
    return NotebookContinuationResult(
        checkpoint=current,
        qa_reviewed=reviewed,
        resume_count=resume_count,
    )


def _initial_expected_review_ids(job: dict[str, Any]) -> tuple[str, ...]:
    """Return selected chapters in first-seen order for the first review round."""

    return tuple(
        dict.fromkeys(
            str(methodology_id).split(".", maxsplit=1)[0]
            for methodology_id in job["input"]["question_ids"]
        )
    )


def _should_use_supervisor_takeover(
    *, round_number: int, workflow: ResearchWorkflow
) -> bool:
    """Return whether initial research plus continuations exhausted the cheap-model cap."""

    completed_research_attempts = round_number + 1
    return (
        workflow.supervisor_takeover_enabled
        and completed_research_attempts
        > workflow.supervisor_takeover_after_research_attempts
    )


def _run_evidence_review(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    notebook: str,
    qa: Any,
    round_number: int,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> EvidenceReviewReport:
    suffix = f"round-{round_number:02d}"
    schema_path = attempt.trusted_dir / f"evidence-review-{suffix}.schema.json"
    output_path = attempt.trusted_dir / f"evidence-review-{suffix}.json"
    events_path = attempt.trusted_dir / f"evidence-review-{suffix}.events.jsonl"
    if _has_indeterminate_review(attempt, round_number):
        from .codex_worker import WorkerOutputError

        raise WorkerOutputError(
            f"review round {round_number} has a prior paid call without recoverable output"
        )
    (attempt.trusted_dir / f"evidence-review-{suffix}.starting.json").write_text(
        json.dumps({"job_id": job["id"], "round": round_number}, sort_keys=True),
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps(evidence_review_json_schema(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    prompt = build_evidence_review_prompt(job=job, notebook=notebook, qa=qa)
    (attempt.trusted_dir / f"evidence-review-{suffix}.prompt.txt").write_text(
        prompt, encoding="utf-8"
    )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={"phase": "evidence_review", "round": round_number},
    )
    from .codex_worker import WorkerOutputError, _run_codex

    _run_codex(
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
    try:
        return EvidenceReviewReport.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise WorkerOutputError("evidence reviewer produced invalid output") from exc


def _repair_evidence_review_scope(
    engine: Engine,
    *,
    report: EvidenceReviewReport,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    notebook: str,
    qa: Any,
    round_number: int,
    expected_chapter_ids: tuple[str, ...],
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> EvidenceReviewReport:
    """Give Luna one bounded correction when a review omits immutable chapters."""

    recovered = _existing_review_repair(attempt, round_number)
    if recovered is not None:
        return recovered
    suffix = f"round-{round_number:02d}-repair"
    schema_path = attempt.trusted_dir / f"evidence-review-{suffix}.schema.json"
    output_path = attempt.trusted_dir / f"evidence-review-{suffix}.json"
    events_path = attempt.trusted_dir / f"evidence-review-{suffix}.events.jsonl"
    schema_path.write_text(
        json.dumps(evidence_review_json_schema(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    prompt = (
        build_evidence_review_prompt(job=job, notebook=notebook, qa=qa)
        + "\n\nYour prior review omitted or expanded immutable chapter scope. "
        + "Return exactly one chapter_reviews row for every chapter in this list: "
        + ", ".join(expected_chapter_ids)
        + ". selected_theme_ids may remain a narrower subset. Preserve substantive "
        + "judgments where valid and correct only the scope/completeness defect.\n\n"
        + "Prior invalid review:\n"
        + report.model_dump_json(indent=2)
    )
    (attempt.trusted_dir / f"evidence-review-{suffix}.prompt.txt").write_text(
        prompt, encoding="utf-8"
    )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={"phase": "evidence_review_repair", "round": round_number},
    )
    from .codex_worker import WorkerOutputError, _run_codex

    starting_path = attempt.trusted_dir / f"evidence-review-{suffix}.starting.json"
    if _has_indeterminate_review_repair(attempt, round_number):
        raise WorkerOutputError(
            f"evidence review repair round {round_number} has a prior paid call "
            "without recoverable output"
        )
    starting_path.write_text(
        json.dumps({"job_id": job["id"], "round": round_number}, sort_keys=True),
        encoding="utf-8",
    )
    _run_codex(
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
    try:
        return EvidenceReviewReport.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise WorkerOutputError("evidence review repair produced invalid output") from exc


def _resume_researcher(
    engine: Engine,
    *,
    checkpoint: ResearchCheckpoint,
    report: EvidenceReviewReport,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    round_number: int,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> ResearchCheckpoint:
    session_id = read_codex_thread_id(checkpoint[0])
    suffix = f"round-{round_number:02d}"
    output_path = attempt.attempt_dir / f"research-continuation-{suffix}.md"
    events_path = attempt.trusted_dir / f"research-continuation-{suffix}.events.jsonl"
    prompt = _build_resume_prompt(report, round_number=round_number)
    (attempt.trusted_dir / f"research-continuation-{suffix}.prompt.txt").write_text(
        prompt, encoding="utf-8"
    )
    recovered = _existing_continuation(attempt, round_number)
    if recovered is None and _has_indeterminate_continuation(attempt, round_number):
        from .codex_worker import WorkerOutputError

        raise WorkerOutputError(
            f"research continuation round {round_number} has a prior paid call "
            "without recoverable output"
        )
    command = build_codex_resume_command(
        profile=profile,
        session_id=session_id,
        project_root=project_root,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={
            "phase": "research_resume",
            "round": round_number,
            "session_id": session_id,
            "chapter_ids": list(report.selected_theme_ids),
        },
    )
    from .codex_worker import WorkerOutputError, _run_codex

    if recovered is None:
        (attempt.trusted_dir / f"research-continuation-{suffix}.starting.json").write_text(
            json.dumps({"job_id": job["id"], "round": round_number}, sort_keys=True),
            encoding="utf-8",
        )
        _run_codex(
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
    else:
        events_path, output_path = recovered
    if (
        not output_path.is_file()
        or output_path.stat().st_size == 0
        or output_path.stat().st_size > 5_000_000
    ):
        raise WorkerOutputError("researcher continuation produced no bounded handoff")
    continuation = output_path.read_text(encoding="utf-8")
    notebook = (
        f"{checkpoint[1]}\n\n--- EVIDENCE REVIEW ROUND {round_number} ---\n\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        f"--- RESEARCH CONTINUATION ROUND {round_number} ---\n\n{continuation}"
    )
    notebook_path = attempt.trusted_dir / f"research-notebook-{suffix}.md"
    notebook_path.write_text(notebook, encoding="utf-8")
    notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
    events_hash = sha256(events_path.read_bytes()).hexdigest()
    (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
        json.dumps(
            {
                "job_key": job["job_key"],
                "provider_profile": job["provider_profile"],
                "provider": job["provider"],
                "model": job["model"],
                "phase": "research_review_loop",
                "review_round": round_number,
                "session_id": session_id,
                "notebook_path": str(notebook_path),
                "notebook_sha256": notebook_hash,
                "events_path": str(events_path),
                "events_sha256": events_hash,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return events_path, notebook, notebook_path, notebook_hash, events_hash


def _run_supervisor_takeover(
    engine: Engine,
    *,
    checkpoint: ResearchCheckpoint,
    report: EvidenceReviewReport,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    round_number: int,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> ResearchCheckpoint:
    """Let the supervisor finish recoverable research after the cheap model stalls."""

    suffix = f"round-{round_number:02d}"
    output_path = attempt.attempt_dir / f"research-supervisor-takeover-{suffix}.md"
    events_path = attempt.trusted_dir / f"research-supervisor-takeover-{suffix}.events.jsonl"
    prompt_path = attempt.trusted_dir / f"research-supervisor-takeover-{suffix}.prompt.txt"
    identity = {
        key: job.get(key)
        for key in (
            "job_key",
            "iso3",
            "country_name",
            "ruler_name",
            "period_start_year",
            "period_end_year",
        )
    }
    prompt = f"""You are taking over an incomplete ruler-period evidence research run.

Use direct iterative internet search. Repair the selected recoverable gaps and append
defensible source-claim units with precise locators, source summaries, period fit,
ruler attribution, contrary evidence, and chapter/lens links. Preserve usable evidence
from the accumulated notebook. Do not score the ruler. Return a permissive research
handoff, not strict JSON. Do not merely describe what should be researched: perform it.

Immutable ruler-period:
{json.dumps(identity, indent=2)}

Latest evidence review:
{report.model_dump_json(indent=2)}

Accumulated notebook:
---
{checkpoint[1]}
---
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    recovered = _existing_supervisor_takeover(attempt, round_number)
    if recovered is None and _has_indeterminate_supervisor_takeover(attempt, round_number):
        raise RuntimeError(
            f"supervisor takeover round {round_number} has a prior paid call "
            "without recoverable output"
        )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=None,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={
            "phase": "supervisor_research_takeover",
            "round": round_number,
            "chapter_ids": list(report.selected_theme_ids),
            "provider_profile": str(job["input"]["reviewer_profile"]),
        },
    )
    from .codex_worker import WorkerOutputError, _run_codex

    if recovered is None:
        starting_path = (
            attempt.trusted_dir / f"research-supervisor-takeover-{suffix}.starting.json"
        )
        starting_path.write_text(
            json.dumps({"job_id": job["id"], "round": round_number}, sort_keys=True),
            encoding="utf-8",
        )
        _run_codex(
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
    else:
        events_path, output_path = recovered
    if not output_path.is_file() or output_path.stat().st_size > 5_000_000:
        raise WorkerOutputError("supervisor takeover produced no bounded handoff")
    continuation = output_path.read_text(encoding="utf-8")
    notebook = (
        f"{checkpoint[1]}\n\n--- EVIDENCE REVIEW ROUND {round_number} ---\n\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        f"--- SUPERVISOR RESEARCH TAKEOVER ROUND {round_number} ---\n\n{continuation}"
    )
    notebook_path = attempt.trusted_dir / f"research-notebook-{suffix}.md"
    notebook_path.write_text(notebook, encoding="utf-8")
    notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
    events_hash = sha256(events_path.read_bytes()).hexdigest()
    (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
        json.dumps(
            {
                "job_key": job["job_key"],
                "provider_profile": job["provider_profile"],
                "provider": job["provider"],
                "model": job["model"],
                "takeover_provider_profile": job["input"]["reviewer_profile"],
                "takeover_provider": profile.provider,
                "takeover_model": profile.model,
                "phase": "supervisor_research_takeover",
                "review_round": round_number,
                "notebook_path": str(notebook_path),
                "notebook_sha256": notebook_hash,
                "events_path": str(events_path),
                "events_sha256": events_hash,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return events_path, notebook, notebook_path, notebook_hash, events_hash


def _existing_supervisor_takeover(
    attempt: WorkerAttempt, round_number: int
) -> tuple[Path, Path] | None:
    """Recover a completed supervisor handoff without purchasing another call."""

    suffix = f"round-{round_number:02d}"
    job_dir = attempt.attempt_dir.parent.parent
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        events_path = trusted / f"research-supervisor-takeover-{suffix}.events.jsonl"
        output_path = (
            job_dir
            / "attempts"
            / trusted.name
            / f"research-supervisor-takeover-{suffix}.md"
        )
        if events_path.is_file() and output_path.is_file():
            from .codex_worker import _events_show_completed_turn

            if _events_show_completed_turn(events_path):
                return events_path, output_path
    return None


def _has_indeterminate_supervisor_takeover(
    attempt: WorkerAttempt, round_number: int
) -> bool:
    """Detect a paid takeover call whose outcome cannot be safely inferred."""

    suffix = f"round-{round_number:02d}"
    for trusted in attempt.trusted_dir.parent.glob("*"):
        if trusted == attempt.trusted_dir:
            continue
        starting = trusted / f"research-supervisor-takeover-{suffix}.starting.json"
        events = trusted / f"research-supervisor-takeover-{suffix}.events.jsonl"
        if starting.is_file() and _existing_supervisor_takeover(attempt, round_number) is None:
            from .codex_worker import _events_show_failed_turn

            if not _events_show_failed_turn(events):
                return True
    return False


def _completed_review_reports(
    attempt: WorkerAttempt,
) -> list[tuple[int, EvidenceReviewReport]]:
    reports: dict[int, EvidenceReviewReport] = {}
    for directory in sorted(attempt.trusted_dir.parent.glob("*")):
        for path in directory.glob("evidence-review-round-*.json"):
            try:
                round_number = int(path.stem.rsplit("-", maxsplit=1)[-1])
                reports[round_number] = EvidenceReviewReport.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, ValidationError):
                continue
    return sorted(reports.items())


def _existing_review_report(
    attempt: WorkerAttempt, round_number: int
) -> EvidenceReviewReport | None:
    return dict(_completed_review_reports(attempt)).get(round_number)


def _existing_review_repair(
    attempt: WorkerAttempt, round_number: int
) -> EvidenceReviewReport | None:
    """Recover a completed scope-repair review from any prior attempt."""

    name = f"evidence-review-round-{round_number:02d}-repair.json"
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        path = trusted / name
        if not path.is_file():
            continue
        try:
            return EvidenceReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
    return None


def _has_indeterminate_review_repair(attempt: WorkerAttempt, round_number: int) -> bool:
    """Detect a paid review-repair call without a recoverable terminal result."""

    suffix = f"round-{round_number:02d}-repair"
    for trusted in attempt.trusted_dir.parent.glob("*"):
        if trusted == attempt.trusted_dir:
            continue
        starting = trusted / f"evidence-review-{suffix}.starting.json"
        events = trusted / f"evidence-review-{suffix}.events.jsonl"
        if not starting.is_file() or _existing_review_repair(attempt, round_number):
            continue
        from .codex_worker import _events_show_failed_turn

        if not _events_show_failed_turn(events):
            return True
    return False


def _existing_continuation(
    attempt: WorkerAttempt, round_number: int
) -> tuple[Path, Path] | None:
    suffix = f"round-{round_number:02d}"
    job_dir = attempt.attempt_dir.parent.parent
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        events_path = trusted / f"research-continuation-{suffix}.events.jsonl"
        output_path = job_dir / "attempts" / trusted.name / f"research-continuation-{suffix}.md"
        if (
            events_path.is_file()
            and output_path.is_file()
            and output_path.stat().st_size <= 5_000_000
        ):
            from .codex_worker import _events_show_completed_turn

            if _events_show_completed_turn(events_path):
                return events_path, output_path
    return None


def _rehydrate_completed_continuation(
    *,
    checkpoint: ResearchCheckpoint,
    report: EvidenceReviewReport,
    recovered: tuple[Path, Path],
    attempt: WorkerAttempt,
    job: dict[str, Any],
    round_number: int,
) -> ResearchCheckpoint:
    """Rebuild the durable notebook after a paid continuation completed pre-checkpoint."""

    events_path, output_path = recovered
    continuation = output_path.read_text(encoding="utf-8")
    notebook = (
        f"{checkpoint[1]}\n\n--- EVIDENCE REVIEW ROUND {round_number} ---\n\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        f"--- RESEARCH CONTINUATION ROUND {round_number} ---\n\n{continuation}"
    )
    suffix = f"round-{round_number:02d}"
    notebook_path = attempt.trusted_dir / f"research-notebook-{suffix}.md"
    notebook_path.write_text(notebook, encoding="utf-8")
    notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
    events_hash = sha256(events_path.read_bytes()).hexdigest()
    (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
        json.dumps(
            {
                "job_key": job["job_key"],
                "provider_profile": job["provider_profile"],
                "provider": job["provider"],
                "model": job["model"],
                "phase": "research_review_loop",
                "review_round": round_number,
                "session_id": read_codex_thread_id(checkpoint[0]),
                "notebook_path": str(notebook_path),
                "notebook_sha256": notebook_hash,
                "events_path": str(events_path),
                "events_sha256": events_hash,
                "recovered_without_provider_call": True,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return events_path, notebook, notebook_path, notebook_hash, events_hash


def _has_indeterminate_review(attempt: WorkerAttempt, round_number: int) -> bool:
    suffix = f"round-{round_number:02d}"
    for directory in attempt.trusted_dir.parent.glob("*"):
        if not (directory / f"evidence-review-{suffix}.starting.json").is_file():
            continue
        output = directory / f"evidence-review-{suffix}.json"
        events = directory / f"evidence-review-{suffix}.events.jsonl"
        from .codex_worker import _events_show_completed_turn, _events_show_failed_turn

        if _events_show_failed_turn(events):
            continue
        if not output.is_file():
            if _events_show_completed_turn(events):
                continue
            return True
        try:
            EvidenceReviewReport.model_validate_json(output.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            if _events_show_completed_turn(events):
                continue
            return True
    return False


def _has_indeterminate_continuation(
    attempt: WorkerAttempt, round_number: int
) -> bool:
    suffix = f"round-{round_number:02d}"
    job_dir = attempt.attempt_dir.parent.parent
    for directory in attempt.trusted_dir.parent.glob("*"):
        if not (directory / f"research-continuation-{suffix}.starting.json").is_file():
            continue
        events = directory / f"research-continuation-{suffix}.events.jsonl"
        output = job_dir / "attempts" / directory.name / f"research-continuation-{suffix}.md"
        if not events.is_file() or not output.is_file():
            return True
        from .codex_worker import _events_show_completed_turn

        if not _events_show_completed_turn(events):
            return True
    return False


def _build_resume_prompt(report: EvidenceReviewReport, *, round_number: int) -> str:
    return f"""Resume the same ruler research session for review round {round_number}.

The independent evidence reviewer identified the chapters and gaps below. Search the
internet directly and iteratively for every selected chapter. Follow event-specific
and source-specific leads; do not rely on one omnibus query. Add traceable source-claim
units and summaries to the existing evidence register, preserve contrary evidence and
attribution limits, and explain when a gap cannot be improved or the chapter is
saturated. Work only on the immutable ruler-period and do not score.

Reviewer brief:
{report.model_dump_json(indent=2)}
"""


__all__ = ["NotebookContinuationResult", "review_and_resume_notebook_if_needed"]
