"""One-shot Codex worker command for durable dossier jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import typer
from pydantic import ValidationError

from .research_common import fail


def register_worker_commands(jobs_app: typer.Typer) -> None:
    jobs_app.command("plan-case")(plan_case_cmd)
    jobs_app.command("run-one")(run_one_job_cmd)
    jobs_app.command("run-queue")(run_queue_cmd)


def plan_case_cmd(
    year: int = typer.Option(..., "--year"),
    ruler_year_id: int = typer.Option(..., "--ruler-year-id"),
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
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Plan one exact ruler-year dossier for a model comparison or pilot."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..paths import project_root
    from ..research.job_planner import plan_single_dossier_job
    from ..research.readiness import all_ruler_quality_question_ids

    selected = tuple(dict.fromkeys(item.strip() for item in question_ids or ()))
    if not selected:
        selected = all_ruler_quality_question_ids()
    project = project_root()
    profiles = model_profiles_path or project / "configs/research-models.yaml"
    engine = build_engine(db_url or default_sqlite_url())
    from .research_job_commands import _require_ready

    _require_ready(
        engine,
        project_root=project,
        mode="dossier_researcher",
        year=year,
        methodology_ids=selected,
        provider_profile=provider_profile,
        reviewer_profile=reviewer_profile,
        formatter_profile=formatter_profile,
        output_dir=output_root,
        model_profiles_path=profiles,
        research_workflow_path=research_workflow_path,
        output_json=output_json,
    )
    try:
        result = plan_single_dossier_job(
            engine,
            year=year,
            ruler_year_id=ruler_year_id,
            run_key=run_key,
            methodology_ids=selected,
            provider_profile=provider_profile,
            reviewer_profile=reviewer_profile,
            formatter_profile=formatter_profile,
            model_profiles_path=profiles,
            output_root=output_root,
            research_workflow_path=research_workflow_path,
            max_attempts=max_attempts,
        )
    except ValueError as exc:
        fail(str(exc), output_json=output_json)
    _emit(result.model_dump(mode="json"), output_json=output_json)


def run_one_job_cmd(
    worker_id: str = typer.Option(..., "--worker-id"),
    run_key: str = typer.Option(..., "--run-key"),
    job_type: Literal["dossier_researcher", "question_judge"] = typer.Option(
        "dossier_researcher", "--job-type"
    ),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=240),
    heartbeat_seconds: int = typer.Option(60, "--heartbeat-seconds", min=1),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds", min=1),
    db_url: str | None = typer.Option(None, "--db-url"),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Claim, execute, validate, and finish one dossier or chapter-judge job."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..paths import project_root
    from ..research.chapter_judge_worker import execute_claimed_chapter_judge_job
    from ..research.chapter_score_store import persist_chapter_batch_and_complete
    from ..research.codex_worker import execute_claimed_dossier_job
    from ..research.job_ledger import claim_next_job, complete_job, fail_job

    project = project_root()
    profiles = model_profiles_path or project / "configs/research-models.yaml"
    engine = build_engine(db_url or default_sqlite_url())
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
    if job is None:
        _emit({"job": None, "status": "queue_empty"}, output_json=output_json)
        return
    token = str(job["lease_token"])
    result_path: Path | None = None
    try:
        if job_type == "question_judge":
            result_path, batch = execute_claimed_chapter_judge_job(
                engine,
                job=job,
                worker_id=worker_id,
                project_root=project,
                model_profiles_path=profiles,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
            completed = persist_chapter_batch_and_complete(
                engine,
                batch=batch,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=token,
                result_path=result_path,
            )
        else:
            result_path = execute_claimed_dossier_job(
                engine,
                job=job,
                worker_id=worker_id,
                project_root=project,
                model_profiles_path=profiles,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
            completed = complete_job(
                engine,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=token,
                result_path=str(result_path),
            )
    except Exception as exc:  # worker boundary: convert into durable job failure
        if result_path is not None and result_path.exists():
            result_path.replace(result_path.with_suffix(".orphaned.json"))
        error = {"error_type": type(exc).__name__, "message": str(exc)}
        try:
            failed_job = fail_job(
                engine,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=token,
                error=error,
                retryable=_is_retryable(exc),
            )
        except ValueError:
            failed_job = None
        fail(
            json.dumps({"job_id": job["id"], "failure": error, "job": failed_job}),
            output_json=output_json,
        )
    _emit(
        {"status": "completed", "job": completed, "result_path": str(result_path)},
        output_json=output_json,
    )


def run_queue_cmd(
    run_key: str = typer.Option(..., "--run-key"),
    job_type: Literal["dossier_researcher", "question_judge"] = typer.Option(
        "dossier_researcher", "--job-type"
    ),
    concurrency: int = typer.Option(2, "--concurrency", min=1, max=20),
    max_jobs: int = typer.Option(..., "--max-jobs", min=1),
    max_failures: int = typer.Option(2, "--max-failures", min=1),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=240),
    heartbeat_seconds: int = typer.Option(60, "--heartbeat-seconds", min=1),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds", min=1),
    db_url: str | None = typer.Option(None, "--db-url"),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Drain a bounded queue with isolated workers and a failure circuit breaker."""

    from ..research.queue_runner import QueueRunnerConfig, run_bounded_queue

    result = run_bounded_queue(
        QueueRunnerConfig(
            run_key=run_key,
            job_type=job_type,
            concurrency=concurrency,
            max_jobs=max_jobs,
            max_failures=max_failures,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
            db_url=db_url,
            model_profiles_path=model_profiles_path,
        )
    )
    _emit(result.model_dump(mode="json"), output_json=output_json)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, RuntimeError, OSError, ValidationError))


def _emit(payload: dict[str, object], *, output_json: bool) -> None:
    typer.echo(json.dumps(payload, indent=2 if output_json else None, sort_keys=True, default=str))


__all__ = [
    "plan_case_cmd",
    "register_worker_commands",
    "run_one_job_cmd",
    "run_queue_cmd",
]
