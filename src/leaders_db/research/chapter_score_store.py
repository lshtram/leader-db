"""Lease-fenced persistence for validated chapter judgment batches."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ._job_ledger_store import decode_job, encode_json, insert_event
from .chapter_judge_models import ChapterJudgmentBatch


def persist_chapter_batch_and_complete(
    engine: Engine,
    *,
    batch: ChapterJudgmentBatch,
    job_id: int,
    worker_id: str,
    lease_token: str,
    result_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Upsert every score and complete its owned job in one transaction."""

    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM research_jobs
                WHERE id = :job_id AND claimed_by = :worker_id
                  AND lease_token = :lease_token AND lease_expires_at > :now
                  AND status IN ('claimed', 'running')
                """
            ),
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
                "now": timestamp,
            },
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("job lease is stale, expired, or not owned by this worker")
        job = decode_job(dict(row))
        if job["job_type"] != "question_judge" or job["job_key"] != batch.job_key:
            raise ValueError("chapter batch does not match the owned judge job")
        expected_batch = {
            "run_key": job["run_key"],
            "target_year": job["target_year"],
            "chapter_id": job["input"]["chapter_id"],
            "calibration_batch_id": job["job_key"],
            "rubric_version": job["input"]["rubric_version"],
        }
        actual_batch = {key: getattr(batch, key) for key in expected_batch}
        if actual_batch != expected_batch:
            raise ValueError("chapter batch scope differs from the owned judge job")
        if (
            batch.run_profile.provider_profile,
            batch.run_profile.provider,
            batch.run_profile.model,
        ) != (job["provider_profile"], job["provider"], job["model"]):
            raise ValueError("chapter batch run profile differs from the owned judge job")
        expected_dossiers = set(job["input"].get("dossier_job_keys", []))
        actual_dossiers = {
            evaluation.dossier_job_key for evaluation in batch.evaluations
        }
        if actual_dossiers != expected_dossiers:
            raise ValueError("chapter batch dossier set differs from the owned judge job")
        if batch.run_profile.dossier_count != len(expected_dossiers):
            raise ValueError("chapter batch dossier count differs from the owned judge job")
        for evaluation in batch.evaluations:
            if (
                evaluation.chapter_id != batch.chapter_id
                or evaluation.rubric_version != batch.rubric_version
                or evaluation.calibration_batch_id != batch.calibration_batch_id
            ):
                raise ValueError("chapter evaluation scope differs from its batch")

        for evaluation in batch.evaluations:
            payload = evaluation.model_dump(mode="json")
            conn.execute(
                text(
                    """
                    INSERT INTO chapter_scores (
                        id, chapter_id, year, iso3, ruler_id, ruler_year_id, ruler_name,
                        score_1_to_10, confidence_score, answer_count, answered_count,
                        missing_count, direct_count, proxy_count, method_version,
                        run_key, job_key, calibration_batch_id, plausible_score_lower,
                        plausible_score_upper, manual_review_required, judgment_json,
                        created_at, updated_at
                    ) VALUES (
                        :id, :chapter_id, :year, :iso3, :ruler_id, :ruler_year_id, :ruler_name,
                        :score, :confidence, 10, :answered_count, :missing_count, 0, 0,
                        :method_version, :run_key, :job_key, :calibration_batch_id,
                        :range_lower, :range_upper, :manual_review_required,
                        :judgment_json, :now, :now
                    )
                    ON CONFLICT(chapter_id, year, ruler_year_id, method_version) DO UPDATE SET
                        ruler_id = excluded.ruler_id,
                        ruler_year_id = excluded.ruler_year_id,
                        ruler_name = excluded.ruler_name,
                        score_1_to_10 = excluded.score_1_to_10,
                        confidence_score = excluded.confidence_score,
                        answer_count = excluded.answer_count,
                        answered_count = excluded.answered_count,
                        missing_count = excluded.missing_count,
                        direct_count = excluded.direct_count,
                        proxy_count = excluded.proxy_count,
                        run_key = excluded.run_key,
                        job_key = excluded.job_key,
                        calibration_batch_id = excluded.calibration_batch_id,
                        plausible_score_lower = excluded.plausible_score_lower,
                        plausible_score_upper = excluded.plausible_score_upper,
                        manual_review_required = excluded.manual_review_required,
                        judgment_json = excluded.judgment_json,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "id": _stable_chapter_score_id(
                        chapter_id=evaluation.chapter_id,
                        year=batch.target_year,
                        ruler_year_id=evaluation.ruler_year_id,
                        method_version=evaluation.rubric_version,
                    ),
                    "chapter_id": evaluation.chapter_id,
                    "year": batch.target_year,
                    "iso3": evaluation.iso3,
                    "ruler_id": evaluation.ruler_id,
                    "ruler_year_id": evaluation.ruler_year_id,
                    "ruler_name": evaluation.ruler_name,
                    "score": evaluation.score_1_to_10,
                    "confidence": evaluation.confidence_score,
                    "answered_count": len(evaluation.supported_lenses),
                    "missing_count": len(evaluation.missing_or_weak_lenses),
                    "method_version": evaluation.rubric_version,
                    "run_key": batch.run_key,
                    "job_key": batch.job_key,
                    "calibration_batch_id": evaluation.calibration_batch_id,
                    "range_lower": evaluation.plausible_score_range.lower,
                    "range_upper": evaluation.plausible_score_range.upper,
                    "manual_review_required": evaluation.manual_review_required,
                    "judgment_json": encode_json(payload),
                    "now": timestamp,
                },
            )

        completed = conn.execute(
            text(
                """
                UPDATE research_jobs
                SET status = 'completed', result_path = :result_path,
                    completed_at = :now, error_json = '{}', lease_expires_at = NULL,
                    lease_token = NULL, updated_at = :now
                WHERE id = :job_id AND claimed_by = :worker_id
                  AND lease_token = :lease_token AND lease_expires_at > :now
                  AND status IN ('claimed', 'running')
                RETURNING *
                """
            ),
            {
                "result_path": str(result_path),
                "now": timestamp,
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
            },
        ).mappings().one_or_none()
        if completed is None:
            raise ValueError("judge job ownership changed before completion")
        insert_event(
            conn,
            job_id=job_id,
            event_type="completed",
            payload={
                "result_path": str(result_path),
                "chapter_score_count": len(batch.evaluations),
            },
            worker_id=worker_id,
        )
        return decode_job(dict(completed))


def _stable_chapter_score_id(
    *, chapter_id: str, year: int, ruler_year_id: int, method_version: str
) -> int:
    """Return a portable positive integer key for SQLite and PostgreSQL inserts."""

    value = f"{chapter_id}:{year}:{ruler_year_id}:{method_version}".encode()
    return int(sha256(value).hexdigest()[:15], 16)


__all__ = ["persist_chapter_batch_and_complete"]
