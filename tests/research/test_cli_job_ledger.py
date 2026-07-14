from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.research.job_ledger import (
    ResearchJobSpec,
    claim_next_job,
    complete_job,
    create_jobs,
    fail_job,
)

runner = CliRunner()


def test_job_cli_exposes_chapter_judge_planner() -> None:
    result = runner.invoke(app, ["research", "jobs", "plan-chapter-judge", "--help"])

    assert result.exit_code == 0
    assert "--chapter-id" in result.stdout
    assert "--question-id" not in result.stdout


def test_job_cli_claim_checkpoint_heartbeat_and_complete(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_job_spec(),))

    claim = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "claim",
            "--worker-id",
            "worker-1",
            "--job-type",
            "dossier_researcher",
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert claim.exit_code == 0, claim.stdout
    claimed = json.loads(claim.stdout)["job"]

    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text('{"evidence_count": 12}', encoding="utf-8")
    checkpoint = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "checkpoint",
            "--job-id",
            str(claimed["id"]),
            "--worker-id",
            "worker-1",
            "--lease-token",
            claimed["lease_token"],
            "--checkpoint",
            str(checkpoint_path),
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert checkpoint.exit_code == 0, checkpoint.stdout
    assert json.loads(checkpoint.stdout)["job"]["checkpoint"] == {"evidence_count": 12}

    heartbeat = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "heartbeat",
            "--job-id",
            str(claimed["id"]),
            "--worker-id",
            "worker-1",
            "--lease-token",
            claimed["lease_token"],
            "--progress-json",
            '{"question_coverage": 20}',
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert heartbeat.exit_code == 0, heartbeat.stdout
    assert json.loads(heartbeat.stdout)["job"]["status"] == "running"

    result_path = tmp_path / "dossier.json"
    result_path.write_text("{}", encoding="utf-8")
    completed = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "complete",
            "--job-id",
            str(claimed["id"]),
            "--worker-id",
            "worker-1",
            "--lease-token",
            claimed["lease_token"],
            "--result",
            str(result_path),
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert completed.exit_code == 0, completed.stdout
    assert json.loads(completed.stdout)["job"]["status"] == "completed"


def test_job_cli_rejects_invalid_json_progress(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_job_spec(),))
    claimed = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "claim",
            "--worker-id",
            "worker-1",
            "--db-url",
            database_url,
            "--json",
        ],
    )
    claimed_job = json.loads(claimed.stdout)["job"]

    result = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "heartbeat",
            "--job-id",
            str(claimed_job["id"]),
            "--worker-id",
            "worker-1",
            "--lease-token",
            claimed_job["lease_token"],
            "--progress-json",
            "[]",
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "JSON payload must be an object" in result.stdout


def test_job_cli_invalidates_completed_result_and_authorizes_repair(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_job_spec().model_copy(update={"max_attempts": 1}),))
    claimed = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert claimed is not None
    complete_job(
        engine,
        job_id=claimed["id"],
        worker_id="worker",
        lease_token=claimed["lease_token"],
        result_path="bad-dossier.json",
    )

    invalidated = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "invalidate-completed",
            "--job-id",
            str(claimed["id"]),
            "--reason",
            "formatter discarded evidence",
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert invalidated.exit_code == 0, invalidated.stdout
    assert json.loads(invalidated.stdout)["job"]["status"] == "quarantined"

    authorized = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "authorize-retry",
            "--job-id",
            str(claimed["id"]),
            "--reason",
            "repair the invalid result",
            "--db-url",
            database_url,
            "--json",
        ],
    )
    assert authorized.exit_code == 0, authorized.stdout
    payload = json.loads(authorized.stdout)["job"]
    assert payload["status"] == "retryable"
    assert payload["max_attempts"] == 2


def test_job_cli_rejects_empty_additional_retry_reason(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_job_spec(),))
    claimed = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert claimed is not None
    fail_job(
        engine,
        job_id=claimed["id"],
        worker_id="worker",
        lease_token=claimed["lease_token"],
        error={"error_type": "fixture"},
        retryable=True,
    )

    result = runner.invoke(
        app,
        [
            "research",
            "jobs",
            "authorize-retry",
            "--job-id",
            str(claimed["id"]),
            "--reason",
            " ",
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "reason must not be empty" in result.stdout


def _job_spec() -> ResearchJobSpec:
    return ResearchJobSpec(
        job_key="dossier:2020:USA:1",
        run_key="pilot",
        job_type="dossier_researcher",
        target_year=2020,
        iso3="USA",
        ruler_id="1",
        provider_profile="openai-luna-candidate",
        provider="openai",
        model="gpt-5.6-luna",
        input_payload={"question_ids": ["4B.2"]},
    )
