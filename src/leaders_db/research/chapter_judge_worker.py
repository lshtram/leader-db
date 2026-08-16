"""Execute one claimed comparative chapter-judge job through Codex."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import tiktoken
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from ._codex_worker_artifacts import (
    read_codex_usage,
)
from .chapter_judge_attempt import (
    ChapterJudgeAttempt,
    _initialize_attempt,
    _projection_hashes,
    _write_chapter_projections,  # noqa: F401
)
from .chapter_judge_candidate import (
    _prepare_batch,
    _read_candidate,
    _write_null_recovery_queue,
)
from .chapter_judge_models import (
    ChapterJudgmentBatch,
    codex_chapter_judgment_json_schema,
)
from .chapter_judge_normalize import (
    _ensure_bias_assessment,  # noqa: F401
    _normalize_calibration_references,  # noqa: F401
    _normalize_confidence_scale,  # noqa: F401
    _normalize_evidence_reference_lists,  # noqa: F401
    _normalize_judgment_envelope,  # noqa: F401
    _normalize_lens_lists,  # noqa: F401
    _normalize_local_evidence_reference_lists,  # noqa: F401
)
from .chapter_judge_prompt import build_chapter_judge_prompt
from .chapter_judge_recovery import (
    _find_previous_chapter_candidate,  # noqa: F401
    _recover_previous_chapter_batch,
)
from .codex_worker import WorkerOutputError, _run_codex
from .codex_worker_command import build_codex_exec_command, validate_worker_timing
from .control_flow import enforce_model_action
from .execution_profile import (
    finalize_execution,
    start_execution_profile,
    write_execution_profile,
)
from .job_ledger import checkpoint_job, heartbeat_job
from .model_call_budget import (
    RunUsageBudgetTracker,
    StageBudgetTracker,
    load_stage_budget_tracker,
    model_max_output_tokens,
    resolve_integrated_run_budget,
)
from .model_profiles import load_research_model_profiles

FILE_BACKED_PROMPT_THRESHOLD_BYTES = 850_000


def execute_claimed_chapter_judge_job(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    model_profiles_path: Path,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
) -> tuple[Path, ChapterJudgmentBatch]:
    """Run and validate one claimed chapter judge, without completing its lease."""

    enforce_model_action(project_root, "chapter_judging", role="production")
    validate_worker_timing(
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    if job["job_type"] != "question_judge" or job["status"] != "claimed":
        raise ValueError("worker can execute only a claimed chapter-judge job")
    lease_token = str(job["lease_token"])
    profile = load_research_model_profiles(model_profiles_path).profiles.get(
        job["provider_profile"]
    )
    if profile is None or "chapter_judge" not in profile.roles:
        raise ValueError("configured provider profile does not permit chapter judging")
    if (profile.provider, profile.model) != (job["provider"], job["model"]):
        raise ValueError("claimed job provider/model differs from the configured profile")

    if profile.context_window is None:
        raise ValueError("chapter judge profile must declare a context_window")
    attempt = _initialize_attempt(
        engine,
        job=job,
        project_root=project_root,
        context_window=profile.context_window,
    )
    run_budget_tracker = resolve_integrated_run_budget(attempt.attempt_dir, run_budget_tracker)
    batch, existing = _recover_previous_chapter_batch(attempt=attempt, job=job)
    if batch is not None:
        _write_null_recovery_queue(
            batch,
            projections=attempt.projections,
            path=attempt.attempt_dir / "null-recovery.json",
        )
        _publish_batch(
            engine,
            batch=batch,
            pending_path=attempt.pending_path,
            result_path=attempt.result_path,
            job=job,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
        )
        return attempt.result_path, batch
    previous_path = None
    if existing is not None:
        previous_path = attempt.attempt_dir / "previous-candidate.json"
        previous_path.write_text(json.dumps(existing), encoding="utf-8")

    candidate: dict[str, Any] | None = None
    if candidate is None:
        projection_bytes = sum(path.stat().st_size for path, _ in attempt.projections)
        embed_projections = projection_bytes <= FILE_BACKED_PROMPT_THRESHOLD_BYTES
        input_hashes = _projection_hashes(attempt.projections)
        prompt = build_chapter_judge_prompt(
            job,
            project_root=project_root,
            guide_text=attempt.guide_text,
            projections=attempt.projections,
            previous_candidate_path=previous_path,
            embed_projections=embed_projections,
        )
        attempt.prompt_path.write_text(prompt, encoding="utf-8")
        command = build_codex_exec_command(
            profile=profile,
            project_root=project_root if embed_projections else attempt.attempt_dir,
            schema_path=attempt.schema_path,
            final_message_path=attempt.pending_path,
            writable_dir=attempt.attempt_dir,
            sandbox_mode="read-only" if embed_projections else "danger-full-access",
        )
        budget = load_stage_budget_tracker(
            project_root / "configs/research-stage-budgets.yaml",
            "chapter_judge",
            ledger_path=(
                attempt.attempt_dir.parents[3] / "stage-budgets" / "chapter-judge-reservations.json"
            ),
        )
        additional_inputs = (
            ()
            if embed_projections
            else tuple(path.read_text(encoding="utf-8") for path, _ in attempt.projections)
        )
        _run_budgeted_judge(
            engine=engine,
            attempt=attempt,
            job=job,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
            command=command,
            prompt=prompt,
            additional_inputs=additional_inputs,
            stage_budget=budget,
            run_budget=run_budget_tracker,
            model_name=profile.model,
        )
        if _projection_hashes(attempt.projections) != input_hashes:
            raise ValueError("chapter projection changed while the judge was running")
        (attempt.attempt_dir / "judge-complete.marker").write_text("complete\n", encoding="utf-8")
        heartbeat_job(
            engine,
            job_id=int(job["id"]),
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            progress={"phase": "validating_chapter_output"},
        )
        candidate = _read_candidate(attempt.pending_path)

    try:
        batch = _prepare_batch(
            candidate,
            job=job,
            dossiers=attempt.dossiers,
            projections=attempt.projections,
            rubric_version=attempt.rubric_version,
            events_path=attempt.events_path,
        )
    except (ValidationError, ValueError) as exc:
        raise WorkerOutputError("Codex chapter judgment failed semantic validation") from exc
    _write_null_recovery_queue(
        batch,
        projections=attempt.projections,
        path=attempt.attempt_dir / "null-recovery.json",
    )
    _publish_batch(
        engine,
        batch=batch,
        pending_path=attempt.pending_path,
        result_path=attempt.result_path,
        job=job,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )
    return attempt.result_path, batch


def _run_budgeted_judge(
    *,
    engine: Engine,
    attempt: ChapterJudgeAttempt,
    job: dict[str, Any],
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
    command: list[str],
    prompt: str,
    additional_inputs: tuple[str, ...],
    stage_budget: StageBudgetTracker,
    run_budget: RunUsageBudgetTracker | None,
    model_name: str,
) -> None:
    schema = codex_chapter_judgment_json_schema()
    reservation = None
    launched = False
    started = None
    return_code = None
    complete = (
        prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True) + "".join(additional_inputs)
    )
    estimated_input_tokens = len(tiktoken.get_encoding("o200k_base").encode(complete))
    try:
        if run_budget is not None:
            reservation = run_budget.reserve(
                stage="chapter_judge",
                component=str(job["input"]["chapter_id"]),
                estimated_input_tokens=estimated_input_tokens,
                output_token_allowance=model_max_output_tokens(model_name),
                output_dir=attempt.attempt_dir,
            )
        stage_budget.reserve(
            component=str(job["input"]["chapter_id"]),
            prompt=prompt,
            response_schema=schema,
            output_dir=attempt.attempt_dir,
            additional_inputs=additional_inputs,
        )
        checkpoint_job(
            engine,
            job_id=int(job["id"]),
            worker_id=worker_id,
            lease_token=lease_token,
            checkpoint={
                "phase": "chapter_judge_starting",
                "attempt_dir": str(attempt.attempt_dir),
                "dossier_count": len(attempt.dossiers),
                "estimated_input_tokens": attempt.context_estimate.estimated_input_tokens,
            },
        )
        launched = True
        started = start_execution_profile()
        _run_judge(
            engine,
            command=command,
            prompt=prompt,
            events_path=attempt.events_path,
            job_id=int(job["id"]),
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
        return_code = 0
    finally:
        finalizers = []
        if run_budget is not None and reservation is not None:
            if launched:
                finalizers.append(
                    lambda: run_budget.reconcile(
                        reservation,
                        (
                            usage.model_dump(mode="json")
                            if (usage := read_codex_usage(attempt.events_path)) is not None
                            else None
                        ),
                    )
                )
            else:
                finalizers.append(lambda: run_budget.cancel_unlaunched(reservation))
        if launched and started is not None:
            finalizers.append(
                lambda: write_execution_profile(
                    output_dir=attempt.attempt_dir,
                    events_path=attempt.events_path,
                    model=model_name,
                    reasoning_effort="high",
                    started=started,
                    return_code=return_code,
                    request_characters=len(prompt) + sum(map(len, additional_inputs)),
                    response_schema_characters=len(
                        json.dumps(schema, ensure_ascii=False, sort_keys=True)
                    ),
                    estimated_input_tokens=estimated_input_tokens,
                    output_token_allowance=(
                        model_max_output_tokens(model_name) if run_budget is not None else None
                    ),
                    command=command,
                    extra={
                        "stage": "chapter_judging",
                        "component": str(job["input"]["chapter_id"]),
                    },
                )
            )
        finalize_execution(*finalizers)


def _run_judge(
    engine: Engine,
    *,
    command: tuple[str, ...],
    prompt: str,
    events_path: Path,
    job_id: int,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> None:
    """Execute a no-discovery judge; the complete projections are embedded."""

    _run_codex(
        engine,
        command=command,
        prompt=prompt,
        events_path=events_path,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )


def _publish_batch(
    engine: Engine,
    *,
    batch: ChapterJudgmentBatch,
    pending_path: Path,
    result_path: Path,
    job: dict[str, Any],
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> None:
    with pending_path.open("w", encoding="utf-8") as pending:
        pending.write(batch.model_dump_json(indent=2))
        pending.flush()
        os.fsync(pending.fileno())
    heartbeat_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        progress={"phase": "publishing_validated_chapter_output"},
    )
    os.replace(pending_path, result_path)
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={
            "phase": "validated",
            "result_path": str(result_path),
            "chapter_score_count": len(batch.evaluations),
        },
    )


__all__ = ["execute_claimed_chapter_judge_job"]
