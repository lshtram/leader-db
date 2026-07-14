"""Administrative transitions for durable research jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ._job_ledger_store import decode_job, insert_event, utc_now


def retry_failed_job(engine: Engine, *, job_id: int, now: datetime | None = None) -> dict[str, Any]:
    """Return a failed job to the queue when its attempt budget remains."""

    timestamp = utc_now(now)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'retryable', claimed_by = NULL, claimed_at = NULL,
                    heartbeat_at = NULL, lease_expires_at = NULL, lease_token = NULL,
                    updated_at = :now
                WHERE id = :job_id AND status = 'failed' AND attempt_count < max_attempts
                RETURNING *
                """
            ),
            {"job_id": job_id, "now": timestamp},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("job is not failed with retry attempts remaining")
        insert_event(conn, job_id=job_id, event_type="retry_requested", payload={})
        return decode_job(dict(row))


def authorize_additional_retry(
    engine: Engine,
    *,
    job_id: int,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Grant one audited recovery attempt to an exhausted or invalidated job."""

    if not reason.strip():
        raise ValueError("additional retry reason must not be empty")
    timestamp = utc_now(now)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'retryable',
                    max_attempts = CASE
                      WHEN attempt_count >= max_attempts THEN max_attempts + 1
                      ELSE max_attempts
                    END,
                    claimed_by = NULL, claimed_at = NULL, heartbeat_at = NULL,
                    lease_expires_at = NULL, lease_token = NULL,
                    quarantine_reason = NULL, updated_at = :now
                WHERE id = :job_id
                  AND (
                    (status = 'failed' AND attempt_count >= max_attempts)
                    OR (status = 'quarantined' AND result_path IS NOT NULL
                        AND quarantine_reason IS NOT NULL)
                  )
                RETURNING *
                """
            ),
            {"job_id": job_id, "now": timestamp},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("job is not an exhausted failed or invalidated job")
        insert_event(
            conn,
            job_id=job_id,
            event_type="additional_retry_authorized",
            payload={"reason": reason},
        )
        return decode_job(dict(row))


def quarantine_job(
    engine: Engine,
    *,
    job_id: int,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Quarantine any nonterminal job and remove it from the claim queue."""

    if not reason.strip():
        raise ValueError("quarantine reason must not be empty")
    timestamp = utc_now(now)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'quarantined', quarantine_reason = :reason,
                    lease_expires_at = NULL, lease_token = NULL, updated_at = :now
                WHERE id = :job_id AND status NOT IN ('completed', 'quarantined', 'cancelled')
                RETURNING *
                """
            ),
            {"job_id": job_id, "reason": reason, "now": timestamp},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("job is terminal or does not exist")
        insert_event(conn, job_id=job_id, event_type="quarantined", payload={"reason": reason})
        return decode_job(dict(row))


def invalidate_completed_job(
    engine: Engine,
    *,
    job_id: int,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Quarantine a completed result that failed post-run quality control."""

    if not reason.strip():
        raise ValueError("invalidation reason must not be empty")
    timestamp = utc_now(now)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'quarantined', quarantine_reason = :reason,
                    claimed_by = NULL, claimed_at = NULL, heartbeat_at = NULL,
                    lease_expires_at = NULL, lease_token = NULL,
                    completed_at = NULL, updated_at = :now
                WHERE id = :job_id AND status = 'completed'
                RETURNING *
                """
            ),
            {"job_id": job_id, "reason": reason, "now": timestamp},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("job is not completed or does not exist")
        insert_event(
            conn,
            job_id=job_id,
            event_type="completed_result_invalidated",
            payload={"reason": reason},
        )
        return decode_job(dict(row))


__all__ = [
    "authorize_additional_retry",
    "invalidate_completed_job",
    "quarantine_job",
    "retry_failed_job",
]
