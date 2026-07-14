"""Query and dependency operations for the durable research job ledger."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ._job_ledger_store import decode_job


def list_jobs(
    engine: Engine,
    *,
    job_type: str | None = None,
    status: str | None = None,
    run_key: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """List ledger jobs using optional type and status filters."""

    clauses: list[str] = []
    params: dict[str, Any] = {}
    if job_type:
        clauses.append("job_type = :job_type")
        params["job_type"] = job_type
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if run_key:
        clauses.append("run_key = :run_key")
        params["run_key"] = run_key
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM research_jobs {where} ORDER BY priority, created_at, id"),
            params,
        ).mappings().all()
    return tuple(decode_job(dict(row)) for row in rows)


def add_job_dependencies(
    engine: Engine,
    *,
    job_id: int,
    depends_on_job_ids: tuple[int, ...],
) -> int:
    """Idempotently add dependency edges and return the number created."""

    with engine.begin() as conn:
        return insert_job_dependencies(conn, job_id, depends_on_job_ids)


def insert_job_dependencies(conn: Any, job_id: int, parent_ids: tuple[int, ...]) -> int:
    """Insert dependency edges using the caller's transaction."""

    created = 0
    for parent_id in dict.fromkeys(parent_ids):
        result = conn.execute(
            text(
                """
                INSERT INTO research_job_dependencies (job_id, depends_on_job_id)
                VALUES (:job_id, :parent_id)
                ON CONFLICT(job_id, depends_on_job_id) DO NOTHING
                """
            ),
            {"job_id": job_id, "parent_id": parent_id},
        )
        created += int(result.rowcount == 1)
    return created


def assert_existing_job_matches(engine_row: dict[str, Any], planned: dict[str, Any]) -> None:
    """Reject stable-key reuse when immutable planning inputs differ."""

    immutable_fields = (
        "run_key",
        "job_type",
        "target_year",
        "period_start_year",
        "period_end_year",
        "iso3",
        "ruler_id",
        "question_id",
        "provider_profile",
        "provider",
        "model",
        "input_json",
    )
    changed = [field for field in immutable_fields if engine_row[field] != planned[field]]
    if changed:
        raise ValueError(
            f"job_key {planned['job_key']!r} already exists with different immutable fields: "
            f"{changed}; use a new run_key"
        )


__all__ = [
    "add_job_dependencies",
    "assert_existing_job_matches",
    "insert_job_dependencies",
    "list_jobs",
]
