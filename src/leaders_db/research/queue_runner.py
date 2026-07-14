"""Bounded subprocess supervisor for draining one research job queue."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QueueJobType = Literal["dossier_researcher", "question_judge"]


class QueueWorkerResult(BaseModel):
    """Normalized outcome of one isolated run-one subprocess."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    returncode: int
    status: str
    job_id: int | None = None
    result_path: str | None = None
    error: str | None = None


class QueueRunSummary(BaseModel):
    """Circuit-breaker and throughput summary for one bounded drain."""

    model_config = ConfigDict(extra="forbid")

    run_key: str
    job_type: QueueJobType
    concurrency: int = Field(ge=1)
    launched: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    queue_empty_workers: int = Field(ge=0)
    circuit_breaker_tripped: bool
    results: tuple[QueueWorkerResult, ...]


@dataclass(frozen=True)
class QueueRunnerConfig:
    """Validated immutable settings passed to every child process."""

    run_key: str
    job_type: QueueJobType
    concurrency: int
    max_jobs: int
    max_failures: int
    lease_seconds: int
    heartbeat_seconds: int
    timeout_seconds: int
    db_url: str | None = None
    model_profiles_path: Path | None = None
    executable: str = "leaders-db"

    def validate(self) -> None:
        if self.concurrency < 1 or self.max_jobs < 1 or self.max_failures < 1:
            raise ValueError("concurrency, max_jobs, and max_failures must be positive")


def run_bounded_queue(config: QueueRunnerConfig) -> QueueRunSummary:
    """Drain at most max_jobs with bounded concurrency and failure circuit break."""

    config.validate()
    results: list[QueueWorkerResult] = []
    launched = 0
    failures = 0
    empty_workers = 0
    generation = 0
    while launched < config.max_jobs and failures < config.max_failures:
        width = min(
            config.concurrency,
            config.max_jobs - launched,
            config.max_failures - failures,
        )
        worker_ids = tuple(
            f"{config.run_key}-{config.job_type}-{generation:03d}-{index:02d}"
            for index in range(width)
        )
        with ThreadPoolExecutor(max_workers=width) as executor:
            batch = tuple(
                executor.map(
                    lambda worker_id: _run_one(config, worker_id=worker_id),
                    worker_ids,
                )
            )
        results.extend(batch)
        launched += width
        failures += sum(item.status == "failed" for item in batch)
        empty = sum(item.status == "queue_empty" for item in batch)
        empty_workers += empty
        if empty == width:
            break
        generation += 1
    return QueueRunSummary(
        run_key=config.run_key,
        job_type=config.job_type,
        concurrency=config.concurrency,
        launched=launched,
        completed=sum(item.status == "completed" for item in results),
        failed=failures,
        queue_empty_workers=empty_workers,
        circuit_breaker_tripped=failures >= config.max_failures,
        results=tuple(results),
    )


def _run_one(config: QueueRunnerConfig, *, worker_id: str) -> QueueWorkerResult:
    command = [
        config.executable,
        "research",
        "jobs",
        "run-one",
        "--worker-id",
        worker_id,
        "--run-key",
        config.run_key,
        "--job-type",
        config.job_type,
        "--lease-seconds",
        str(config.lease_seconds),
        "--heartbeat-seconds",
        str(config.heartbeat_seconds),
        "--timeout-seconds",
        str(config.timeout_seconds),
        "--json",
    ]
    if config.db_url:
        command.extend(("--db-url", config.db_url))
    if config.model_profiles_path:
        command.extend(("--model-profiles", str(config.model_profiles_path)))
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds + 120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return QueueWorkerResult(
            worker_id=worker_id,
            returncode=-1,
            status="failed",
            error=str(exc)[-2_000:],
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode != 0:
        return QueueWorkerResult(
            worker_id=worker_id,
            returncode=completed.returncode,
            status="failed",
            error=(completed.stderr or completed.stdout or "worker failed")[-2_000:],
        )
    if payload.get("status") == "queue_empty":
        return QueueWorkerResult(
            worker_id=worker_id,
            returncode=0,
            status="queue_empty",
        )
    job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    status = str(payload.get("status", "unknown"))
    if status != "completed":
        return QueueWorkerResult(
            worker_id=worker_id,
            returncode=0,
            status="failed",
            error=f"worker returned unexpected status: {status}",
        )
    return QueueWorkerResult(
        worker_id=worker_id,
        returncode=0,
        status="completed",
        job_id=job.get("id") if isinstance(job.get("id"), int) else None,
        result_path=(
            str(payload["result_path"]) if payload.get("result_path") else None
        ),
    )


__all__ = ["QueueRunSummary", "QueueRunnerConfig", "run_bounded_queue"]
