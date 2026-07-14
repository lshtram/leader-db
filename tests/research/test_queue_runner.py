from __future__ import annotations

import json
import subprocess

from leaders_db.research.queue_runner import QueueRunnerConfig, run_bounded_queue


def test_queue_runner_drains_with_bounded_concurrency(monkeypatch) -> None:
    calls: list[list[str]] = []
    outcomes = iter(
        (
            _completed("completed", job_id=1),
            _completed("completed", job_id=2),
            _completed("queue_empty"),
            _completed("queue_empty"),
        )
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return next(outcomes)

    monkeypatch.setattr("leaders_db.research.queue_runner.subprocess.run", fake_run)
    summary = run_bounded_queue(_config(concurrency=2, max_jobs=8))

    assert summary.launched == 4
    assert summary.completed == 2
    assert summary.queue_empty_workers == 2
    assert summary.circuit_breaker_tripped is False
    assert all("--run-key" in command and "batch" in command for command in calls)


def test_queue_runner_stops_after_failure_circuit_breaker(monkeypatch) -> None:
    monkeypatch.setattr(
        "leaders_db.research.queue_runner.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr="provider unavailable"
        ),
    )

    summary = run_bounded_queue(
        _config(concurrency=2, max_jobs=20, max_failures=2)
    )

    assert summary.launched == 2
    assert summary.failed == 2
    assert summary.circuit_breaker_tripped is True
    assert all("provider unavailable" in (item.error or "") for item in summary.results)


def _completed(status: str, *, job_id: int | None = None) -> subprocess.CompletedProcess[str]:
    job = {"id": job_id} if job_id is not None else None
    return subprocess.CompletedProcess(
        args=["leaders-db"],
        returncode=0,
        stdout=json.dumps(
            {
                "status": status,
                "job": job,
                "result_path": f"result-{job_id}.json" if job_id else None,
            }
        ),
        stderr="",
    )


def _config(
    *, concurrency: int, max_jobs: int, max_failures: int = 2
) -> QueueRunnerConfig:
    return QueueRunnerConfig(
        run_key="batch",
        job_type="dossier_researcher",
        concurrency=concurrency,
        max_jobs=max_jobs,
        max_failures=max_failures,
        lease_seconds=900,
        heartbeat_seconds=60,
        timeout_seconds=7200,
    )
