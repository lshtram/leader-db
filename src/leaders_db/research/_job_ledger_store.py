"""Private SQL and serialization helpers for the research job ledger."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def owned_update(
    engine: Engine,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    authorization_now: datetime,
    assignments: str,
    params: dict[str, Any],
    event_type: str,
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    """Update one active owned job and append its event atomically."""

    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE research_jobs SET {assignments}
                WHERE id = :job_id AND claimed_by = :worker_id
                  AND lease_token = :lease_token AND lease_expires_at > :authorization_now
                  AND status IN ('claimed', 'running')
                RETURNING *
                """
            ),
            params
            | {
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
                "authorization_now": authorization_now,
            },
        ).mappings().one_or_none()
        if result is None:
            raise ValueError("job is not actively leased by this worker")
        insert_event(
            conn,
            job_id=job_id,
            event_type=event_type,
            worker_id=worker_id,
            payload=event_payload,
        )
        return decode_job(dict(result))


def owned_job(
    conn: Any,
    *,
    job_id: int,
    worker_id: str,
    lease_token: str,
    authorization_now: datetime,
) -> dict[str, Any]:
    """Return an active owned job or fail closed."""

    row = conn.execute(
        text(
            """
            SELECT * FROM research_jobs
            WHERE id = :job_id AND claimed_by = :worker_id
              AND lease_token = :lease_token AND lease_expires_at > :authorization_now
              AND status IN ('claimed', 'running')
            """
        ),
        {
            "job_id": job_id,
            "worker_id": worker_id,
            "lease_token": lease_token,
            "authorization_now": authorization_now,
        },
    ).mappings().one_or_none()
    if row is None:
        raise ValueError("job is not actively leased by this worker")
    return dict(row)


def insert_event(
    conn: Any,
    *,
    job_id: int,
    event_type: str,
    payload: dict[str, Any],
    worker_id: str | None = None,
) -> None:
    """Append one immutable job event."""

    conn.execute(
        text(
            """
            INSERT INTO research_job_events (job_id, event_type, worker_id, payload_json)
            VALUES (:job_id, :event_type, :worker_id, :payload_json)
            """
        ),
        {
            "job_id": job_id,
            "event_type": event_type,
            "worker_id": worker_id,
            "payload_json": encode_json(payload),
        },
    )


def decode_job(record: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON columns in a returned ledger row."""

    decoded = dict(record)
    for key in ("checkpoint_json", "input_json", "error_json"):
        decoded[key.removesuffix("_json")] = json.loads(decoded.pop(key))
    return decoded


def encode_json(value: dict[str, Any]) -> str:
    """Encode deterministic compact JSON for ledger storage."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def utc_now(value: datetime | None) -> datetime:
    """Return a timezone-aware UTC timestamp."""

    now = value or datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


__all__ = ["decode_job", "encode_json", "insert_event", "owned_job", "owned_update", "utc_now"]
