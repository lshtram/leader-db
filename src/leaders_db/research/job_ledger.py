"""Durable, lease-based job ledger for research workers and judges."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ._job_ledger_store import (
    decode_job as _decode_job,
)
from ._job_ledger_store import (
    encode_json as _json,
)
from ._job_ledger_store import (
    insert_event as _insert_event,
)
from ._job_ledger_store import (
    owned_job as _owned_job,
)
from ._job_ledger_store import (
    owned_update as _owned_update,
)
from ._job_ledger_store import (
    utc_now as _utc_now,
)
from .job_ledger_admin import (
    authorize_additional_retry,
    invalidate_completed_job,
    quarantine_job,
    retry_failed_job,
)
from .job_ledger_queries import (
    add_job_dependencies,
    assert_existing_job_matches,
    insert_job_dependencies,
    list_jobs,
)

JobType = Literal["dossier_researcher", "question_judge"]
JobStatus = Literal[
    "pending",
    "claimed",
    "running",
    "completed",
    "failed",
    "retryable",
    "quarantined",
    "cancelled",
]

ACTIVE_STATUSES = ("claimed", "running")
TERMINAL_STATUSES = ("completed", "quarantined", "cancelled")


class ResearchJobSpec(BaseModel):
    """Idempotent creation contract for one durable research job."""

    model_config = ConfigDict(extra="forbid")

    job_key: str = Field(min_length=1)
    run_key: str = Field(min_length=1)
    job_type: JobType
    target_year: int
    period_start_year: int | None = None
    period_end_year: int | None = None
    iso3: str | None = None
    country_name: str | None = None
    ruler_id: str | None = None
    ruler_name: str | None = None
    question_id: str | None = None
    provider_profile: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    status: JobStatus = "pending"
    priority: int = 100
    max_attempts: int = Field(default=3, ge=1)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    quarantine_reason: str | None = None


class JobWriteResult(BaseModel):
    """Creation/idempotency summary for a planned job set."""

    created: int
    existing: int
    total: int


def create_jobs(
    engine: Engine,
    specs: tuple[ResearchJobSpec, ...],
    *,
    dependencies_by_job_key: dict[str, tuple[int, ...]] | None = None,
) -> JobWriteResult:
    """Insert jobs by stable key without overwriting existing work."""

    created = 0
    existing = 0
    with engine.begin() as conn:
        for spec in specs:
            params = _spec_params(spec)
            result = conn.execute(
                text(
                    """
                    INSERT INTO research_jobs (
                        job_key, run_key, job_type, target_year, period_start_year, period_end_year,
                        iso3, country_name, ruler_id, ruler_name, question_id,
                        provider_profile, provider, model, status, priority, max_attempts,
                        input_json, quarantine_reason
                    ) VALUES (
                        :job_key, :run_key, :job_type, :target_year,
                        :period_start_year, :period_end_year,
                        :iso3, :country_name, :ruler_id, :ruler_name, :question_id,
                        :provider_profile, :provider, :model, :status, :priority, :max_attempts,
                        :input_json, :quarantine_reason
                    )
                    ON CONFLICT(job_key) DO NOTHING
                    """
                ),
                params,
            )
            if result.rowcount == 1:
                created += 1
                job_id = conn.execute(
                    text("SELECT id FROM research_jobs WHERE job_key = :job_key"),
                    {"job_key": spec.job_key},
                ).scalar_one()
                _insert_event(
                    conn,
                    job_id=job_id,
                    event_type="planned" if spec.status == "pending" else spec.status,
                    payload={"provider_profile": spec.provider_profile},
                )
            else:
                existing_row = conn.execute(
                    text("SELECT * FROM research_jobs WHERE job_key = :job_key"),
                    {"job_key": spec.job_key},
                ).mappings().one()
                assert_existing_job_matches(dict(existing_row), params)
                existing += 1
                job_id = int(existing_row["id"])
            parent_ids = (dependencies_by_job_key or {}).get(spec.job_key, ())
            insert_job_dependencies(conn, int(job_id), parent_ids)
    return JobWriteResult(created=created, existing=existing, total=len(specs))


def claim_next_job(
    engine: Engine,
    *,
    worker_id: str,
    lease_seconds: int,
    job_type: JobType | None = None,
    run_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically claim one available or expired-lease job."""

    if not worker_id.strip():
        raise ValueError("worker_id must not be empty")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    claimed_at = _utc_now(now)
    lease_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    lease_token = str(uuid4())
    type_clause = "AND job_type = :job_type" if job_type else ""
    run_clause = "AND run_key = :run_key" if run_key else ""
    lock_clause = _claim_lock_clause(engine.dialect.name)
    statement = text(
        f"""
        UPDATE research_jobs
        SET status = 'claimed', claimed_by = :worker_id, claimed_at = :claimed_at,
            heartbeat_at = :claimed_at, lease_expires_at = :lease_expires_at,
            lease_token = :lease_token, attempt_count = attempt_count + 1,
            updated_at = :claimed_at
        WHERE id = (
            SELECT id FROM research_jobs
            WHERE attempt_count < max_attempts
              AND (
                status IN ('pending', 'retryable')
                OR (status IN ('claimed', 'running') AND lease_expires_at <= :claimed_at)
              )
              AND NOT EXISTS (
                SELECT 1
                FROM research_job_dependencies d
                JOIN research_jobs parent ON parent.id = d.depends_on_job_id
                WHERE d.job_id = research_jobs.id
                  AND parent.status NOT IN ('completed', 'failed', 'quarantined', 'cancelled')
              )
              {type_clause}
              {run_clause}
            ORDER BY priority ASC, created_at ASC, id ASC
            LIMIT 1
            {lock_clause}
        )
          AND attempt_count < max_attempts
          AND (
            status IN ('pending', 'retryable')
            OR (status IN ('claimed', 'running') AND lease_expires_at <= :claimed_at)
          )
          AND NOT EXISTS (
            SELECT 1
            FROM research_job_dependencies outer_d
            JOIN research_jobs outer_parent ON outer_parent.id = outer_d.depends_on_job_id
            WHERE outer_d.job_id = research_jobs.id
              AND outer_parent.status NOT IN ('completed', 'failed', 'quarantined', 'cancelled')
          )
        RETURNING *
        """
    )
    params = {
        "worker_id": worker_id,
        "claimed_at": claimed_at,
        "lease_expires_at": lease_expires_at,
        "lease_token": lease_token,
        "job_type": job_type,
        "run_key": run_key,
    }
    with engine.begin() as conn:
        exhausted = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'failed', claimed_by = NULL, lease_expires_at = NULL,
                    lease_token = NULL, updated_at = :claimed_at,
                    error_json = :exhausted_error
                WHERE status IN ('claimed', 'running')
                  AND lease_expires_at <= :claimed_at
                  AND attempt_count >= max_attempts
                RETURNING id
                """
            ),
            {
                "claimed_at": claimed_at,
                "exhausted_error": _json(
                    {
                        "error_type": "LeaseExpiredAfterFinalAttempt",
                        "message": "final worker lease expired before terminal publication",
                    }
                ),
            },
        ).scalars()
        for exhausted_job_id in exhausted:
            _insert_event(
                conn,
                job_id=int(exhausted_job_id),
                event_type="failed",
                payload={"reason": "lease_expired_after_final_attempt"},
            )
        row = conn.execute(statement, params).mappings().one_or_none()
        if row is None:
            return None
        record = dict(row)
        decoded = _decode_job(record)
        if record["job_type"] == "question_judge":
            unavailable = conn.execute(
                text(
                    """
                    SELECT parent.job_key, parent.status, parent.iso3, parent.ruler_name
                    FROM research_job_dependencies dependency
                    JOIN research_jobs parent ON parent.id = dependency.depends_on_job_id
                    WHERE dependency.job_id = :job_id
                      AND parent.status IN ('failed', 'quarantined', 'cancelled')
                    ORDER BY parent.id
                    """
                ),
                {"job_id": int(record["id"])},
            ).mappings()
            input_payload = dict(decoded["input"])
            existing = {
                str(item.get("job_key")): item
                for item in input_payload.get("unavailable_dossiers", [])
                if isinstance(item, dict)
            }
            for parent in unavailable:
                item = dict(parent)
                existing[str(item["job_key"])] = item
            input_payload["unavailable_dossiers"] = list(existing.values())
            unavailable_keys = set(existing)
            input_payload["dossier_job_keys"] = [
                key
                for key in input_payload.get("dossier_job_keys", [])
                if str(key) not in unavailable_keys
            ]
            conn.execute(
                text("UPDATE research_jobs SET input_json = :input_json WHERE id = :job_id"),
                {"input_json": _json(input_payload), "job_id": int(record["id"])},
            )
            decoded["input"] = input_payload
        _insert_event(
            conn,
            job_id=int(record["id"]),
            event_type="claimed",
            worker_id=worker_id,
            payload={"attempt_count": record["attempt_count"], "lease_seconds": lease_seconds},
        )
    return decoded


def heartbeat_job(
    engine: Engine,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
    progress: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Renew an owned active job lease and append progress metadata."""

    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    heartbeat_at = _utc_now(now)
    return _owned_update(
        engine,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        authorization_now=heartbeat_at,
        assignments=(
            "status = 'running', heartbeat_at = :now, "
            "lease_expires_at = :lease_expires_at, updated_at = :now"
        ),
        params={
            "now": heartbeat_at,
            "lease_expires_at": heartbeat_at + timedelta(seconds=lease_seconds),
        },
        event_type="heartbeat",
        event_payload=progress or {},
    )


def checkpoint_job(
    engine: Engine,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    checkpoint: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist the latest resumable checkpoint and retain an audit event."""

    timestamp = _utc_now(now)
    return _owned_update(
        engine,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        authorization_now=timestamp,
        assignments="status = 'running', checkpoint_json = :checkpoint_json, updated_at = :now",
        params={"now": timestamp, "checkpoint_json": _json(checkpoint)},
        event_type="checkpoint",
        event_payload=checkpoint,
    )


def complete_job(
    engine: Engine,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    result_path: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Complete an owned job exactly once."""

    timestamp = _utc_now(now)
    return _owned_update(
        engine,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        authorization_now=timestamp,
        assignments=(
            "status = 'completed', result_path = :result_path, completed_at = :now, "
            "error_json = '{}', lease_expires_at = NULL, lease_token = NULL, updated_at = :now"
        ),
        params={"now": timestamp, "result_path": result_path},
        event_type="completed",
        event_payload={"result_path": result_path},
    )


def fail_job(
    engine: Engine,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    error: dict[str, Any],
    retryable: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail an owned job, making it retryable only when attempts remain."""

    timestamp = _utc_now(now)
    with engine.begin() as conn:
        row = _owned_job(
            conn,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            authorization_now=timestamp,
        )
        attempts_remain = row["attempt_count"] < row["max_attempts"]
        status = "retryable" if retryable and attempts_remain else "failed"
        result = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = :status, error_json = :error_json, lease_expires_at = NULL,
                    lease_token = NULL, updated_at = :now
                WHERE id = :job_id AND claimed_by = :worker_id
                  AND lease_token = :lease_token AND lease_expires_at > :now
                  AND status IN ('claimed', 'running')
                RETURNING *
                """
            ),
            {
                "status": status,
                "error_json": _json(error),
                "now": timestamp,
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
            },
        ).mappings().one()
        _insert_event(
            conn,
            job_id=job_id,
            event_type=status,
            worker_id=worker_id,
            payload=error,
        )
        return _decode_job(dict(result))


def _spec_params(spec: ResearchJobSpec) -> dict[str, Any]:
    return spec.model_dump(exclude={"input_payload"}) | {
        "input_json": _json(spec.input_payload),
    }


def _claim_lock_clause(dialect_name: str) -> str:
    """Avoid PostgreSQL head-of-queue contention without breaking SQLite."""

    return "FOR UPDATE SKIP LOCKED" if dialect_name == "postgresql" else ""


__all__ = [
    "JobWriteResult",
    "ResearchJobSpec",
    "add_job_dependencies",
    "authorize_additional_retry",
    "checkpoint_job",
    "claim_next_job",
    "complete_job",
    "create_jobs",
    "fail_job",
    "heartbeat_job",
    "invalidate_completed_job",
    "list_jobs",
    "quarantine_job",
    "retry_failed_job",
]
