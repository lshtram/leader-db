"""Durable research job-ledger CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import typer
from sqlalchemy.engine import Engine

from .research_common import fail

jobs_app = typer.Typer(help="Plan and operate durable research jobs.", no_args_is_help=True)
JobTypeOption = Literal["dossier_researcher", "question_judge"]
ReadinessModeOption = Literal["dossier_researcher", "chapter_judge"]
JobStatusOption = Literal[
    "pending",
    "claimed",
    "running",
    "completed",
    "failed",
    "retryable",
    "quarantined",
    "cancelled",
]


def register_job_commands(research_app: typer.Typer) -> None:
    research_app.add_typer(jobs_app, name="jobs")


@jobs_app.command("plan-dossiers")
def plan_dossiers_cmd(
    year: int = typer.Option(..., "--year"),
    run_key: str = typer.Option(..., "--run-key"),
    question_ids: list[str] | None = typer.Option(None, "--question-id"),
    provider_profile: str = typer.Option(..., "--provider-profile"),
    reviewer_profile: str = typer.Option("openai-luna-candidate", "--reviewer-profile"),
    formatter_profile: str = typer.Option("openai-luna-candidate", "--formatter-profile"),
    output_root: Path = typer.Option(..., "--output-root"),
    max_attempts: int = typer.Option(3, "--max-attempts", min=1),
    db_url: str | None = typer.Option(None, "--db-url"),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    research_workflow_path: Path | None = typer.Option(None, "--research-workflow"),
    batch_manifest_path: Path | None = typer.Option(
        None, "--batch-manifest", exists=True, dir_okay=False
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Plan one dossier job per included ruler/country-year."""

    selected_ids = tuple(dict.fromkeys(value.strip() for value in question_ids or ()))
    if not selected_ids:
        from ..research.readiness import all_ruler_quality_question_ids

        selected_ids = all_ruler_quality_question_ids()
    engine, project, profiles = _runtime(db_url, model_profiles_path)
    from ..research.job_planner import plan_dossier_jobs

    _require_ready(
        engine,
        project_root=project,
        mode="dossier_researcher",
        year=year,
        methodology_ids=selected_ids,
        provider_profile=provider_profile,
        reviewer_profile=reviewer_profile,
        formatter_profile=formatter_profile,
        output_dir=output_root,
        model_profiles_path=profiles,
        research_workflow_path=research_workflow_path,
        output_json=output_json,
    )
    try:
        result = plan_dossier_jobs(
            engine,
            year=year,
            run_key=run_key,
            methodology_ids=selected_ids,
            provider_profile=provider_profile,
            reviewer_profile=reviewer_profile,
            formatter_profile=formatter_profile,
            model_profiles_path=profiles,
            output_root=output_root,
            research_workflow_path=research_workflow_path,
            batch_manifest_path=batch_manifest_path,
            max_attempts=max_attempts,
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit(result.model_dump(mode="json"), output_json=output_json)


@jobs_app.command("plan-chapter-judge")
def plan_chapter_judge_cmd(
    year: int = typer.Option(..., "--year"),
    run_key: str = typer.Option(..., "--run-key"),
    dossier_run_key: list[str] | None = typer.Option(
        None,
        "--dossier-run-key",
        help="Reuse dossiers from one or more run keys; repeat this option.",
    ),
    completed_dossiers_only: bool = typer.Option(
        False,
        "--completed-dossiers-only",
        help="Compose the cohort only from completed dossier jobs.",
    ),
    chapter_id: str | None = typer.Option(None, "--chapter-id"),
    all_chapters: bool = typer.Option(False, "--all-chapters"),
    provider_profile: str = typer.Option(
        "openai-sol-supervisor", "--provider-profile"
    ),
    output_root: Path = typer.Option(..., "--output-root"),
    max_attempts: int = typer.Option(3, "--max-attempts", min=1),
    db_url: str | None = typer.Option(None, "--db-url"),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Plan one chapter-year judge job with ruler-dossier dependencies."""

    engine, project, profiles = _runtime(db_url, model_profiles_path)
    from ..research.job_planner import (
        plan_all_chapter_judge_jobs,
        plan_chapter_judge_job,
    )

    if all_chapters == (chapter_id is not None):
        fail(
            "provide exactly one of --chapter-id or --all-chapters",
            output_json=output_json,
        )
    normalized_chapter = chapter_id.strip().upper() if chapter_id else None
    methodology_ids = (
        tuple(f"{chapter}B.{index}" for chapter in range(1, 9) for index in range(1, 11))
        if all_chapters
        else tuple(f"{normalized_chapter}.{index}" for index in range(1, 11))
    )
    _require_ready(
        engine,
        project_root=project,
        mode="chapter_judge",
        year=year,
        methodology_ids=methodology_ids,
        provider_profile=provider_profile,
        output_dir=output_root,
        model_profiles_path=profiles,
        output_json=output_json,
    )
    try:
        common = {
            "year": year,
            "run_key": run_key,
            "dossier_run_key": dossier_run_key,
            "completed_dossiers_only": completed_dossiers_only,
            "provider_profile": provider_profile,
            "model_profiles_path": profiles,
            "output_root": output_root,
            "max_attempts": max_attempts,
        }
        result = (
            plan_all_chapter_judge_jobs(engine, **common)
            if all_chapters
            else plan_chapter_judge_job(engine, chapter_id=str(normalized_chapter), **common)
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit(result.model_dump(mode="json"), output_json=output_json)


@jobs_app.command("list")
def list_jobs_cmd(
    job_type: JobTypeOption | None = typer.Option(None, "--job-type"),
    status: JobStatusOption | None = typer.Option(None, "--status"),
    run_key: str | None = typer.Option(None, "--run-key"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List durable jobs with optional type and status filters."""

    from ..research.job_ledger import list_jobs

    engine, _, _ = _runtime(db_url, None)
    try:
        jobs = list_jobs(engine, job_type=job_type, status=status, run_key=run_key)
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job_count": len(jobs), "jobs": list(jobs)}, output_json=output_json)


@jobs_app.command("claim")
def claim_job_cmd(
    worker_id: str = typer.Option(..., "--worker-id"),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=1),
    job_type: JobTypeOption | None = typer.Option(None, "--job-type"),
    run_key: str | None = typer.Option(None, "--run-key"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Atomically claim the next dependency-ready job."""

    from ..research.job_ledger import claim_next_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = claim_next_job(
            engine,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            job_type=job_type,
            run_key=run_key,
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("heartbeat")
def heartbeat_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    worker_id: str = typer.Option(..., "--worker-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=1),
    progress_json: str = typer.Option("{}", "--progress-json"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Renew an active lease and append a progress event."""

    from ..research.job_ledger import heartbeat_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = heartbeat_job(
            engine,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            progress=_json_object(progress_json),
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("checkpoint")
def checkpoint_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    worker_id: str = typer.Option(..., "--worker-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    checkpoint_path: Path = typer.Option(..., "--checkpoint", exists=True, dir_okay=False),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Persist a worker-owned resumable checkpoint JSON object."""

    from ..research.job_ledger import checkpoint_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = checkpoint_job(
            engine,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            checkpoint=_json_file(checkpoint_path),
        )
    except (OSError, ValueError) as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("complete")
def complete_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    worker_id: str = typer.Option(..., "--worker-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    result_path: Path = typer.Option(..., "--result", exists=True),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Mark an owned job complete with a verified result path."""

    from ..research.job_ledger import complete_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = complete_job(
            engine,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            result_path=str(result_path),
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("fail")
def fail_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    worker_id: str = typer.Option(..., "--worker-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    error_json: str = typer.Option(..., "--error-json"),
    retryable: bool = typer.Option(False, "--retryable/--no-retryable"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Fail an owned job and optionally return it to the retry queue."""

    from ..research.job_ledger import fail_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = fail_job(
            engine,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error=_json_object(error_json),
            retryable=retryable,
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("retry")
def retry_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Manually requeue a failed job when attempts remain."""

    from ..research.job_ledger import retry_failed_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = retry_failed_job(engine, job_id=job_id)
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("authorize-retry")
def authorize_retry_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    reason: str = typer.Option(..., "--reason"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Grant one audited recovery attempt to an exhausted or invalidated job."""

    from ..research.job_ledger import authorize_additional_retry

    engine, _, _ = _runtime(db_url, None)
    try:
        job = authorize_additional_retry(engine, job_id=job_id, reason=reason)
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("quarantine")
def quarantine_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    reason: str = typer.Option(..., "--reason"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Remove a nonterminal job from the claim queue with a reason."""

    from ..research.job_ledger import quarantine_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = quarantine_job(engine, job_id=job_id, reason=reason)
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


@jobs_app.command("invalidate-completed")
def invalidate_completed_job_cmd(
    job_id: int = typer.Option(..., "--job-id"),
    reason: str = typer.Option(..., "--reason"),
    db_url: str | None = typer.Option(None, "--db-url"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Quarantine a completed result that failed post-run quality control."""

    from ..research.job_ledger import invalidate_completed_job

    engine, _, _ = _runtime(db_url, None)
    try:
        job = invalidate_completed_job(engine, job_id=job_id, reason=reason)
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit({"job": job}, output_json=output_json)


def _runtime(db_url: str | None, model_profiles_path: Path | None) -> tuple[Engine, Path, Path]:
    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..paths import project_root

    project = project_root()
    profiles = model_profiles_path or project / "configs/research-models.yaml"
    return build_engine(db_url or default_sqlite_url()), project, profiles


def _require_ready(
    engine: Engine,
    *,
    project_root: Path,
    mode: ReadinessModeOption,
    year: int,
    methodology_ids: tuple[str, ...],
    provider_profile: str,
    reviewer_profile: str | None = None,
    formatter_profile: str | None = None,
    output_dir: Path,
    model_profiles_path: Path,
    research_workflow_path: Path | None = None,
    output_json: bool,
) -> None:
    from ..research.readiness import build_research_readiness_report

    report = build_research_readiness_report(
        engine,
        project_root=project_root,
        mode=mode,
        year=year,
        methodology_ids=methodology_ids,
        provider_profile=provider_profile,
        reviewer_profile=reviewer_profile,
        formatter_profile=formatter_profile,
        output_dir=output_dir,
        model_profiles_path=model_profiles_path,
        research_workflow_path=research_workflow_path,
    )
    if not report.ready:
        failures = [
            check.model_dump(mode="json") for check in report.checks if check.status == "fail"
        ]
        fail(json.dumps({"readiness_failures": failures}, sort_keys=True), output_json=output_json)


def _json_object(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _json_file(path: Path) -> dict[str, Any]:
    return _json_object(path.read_text(encoding="utf-8"))


def _emit(payload: dict[str, Any], *, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    typer.echo(json.dumps(payload, sort_keys=True, default=str))


__all__ = ["jobs_app", "register_job_commands"]
