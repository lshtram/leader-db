from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from leaders_db.db.engine import build_engine, init_database
from leaders_db.research.job_ledger import (
    JobStatus,
    ResearchJobSpec,
    _claim_lock_clause,
    add_job_dependencies,
    authorize_additional_retry,
    checkpoint_job,
    claim_next_job,
    complete_job,
    create_jobs,
    fail_job,
    heartbeat_job,
    invalidate_completed_job,
    list_jobs,
    quarantine_job,
    retry_failed_job,
)


def test_job_creation_is_idempotent_by_stable_key(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    specs = (_dossier_spec("dossier:2020:USA:1"),)

    first = create_jobs(engine, specs)
    second = create_jobs(engine, specs)

    assert first.model_dump() == {"created": 1, "existing": 0, "total": 1}
    assert second.model_dump() == {"created": 0, "existing": 1, "total": 1}
    assert len(list_jobs(engine)) == 1
    assert _event_types(engine) == ["planned"]


def test_stable_key_rejects_changed_model_or_input(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    original = _dossier_spec("dossier:2020:USA:1")
    create_jobs(engine, (original,))
    changed = original.model_copy(
        update={"model": "gpt-5.6-terra", "input_payload": {"question_ids": ["4B.3"]}}
    )

    with pytest.raises(ValueError, match="different immutable fields"):
        create_jobs(engine, (changed,))

    stored = list_jobs(engine)[0]
    assert stored["model"] == "MiniMax-M2.7"
    assert stored["input"] == {"question_ids": ["4B.2"]}


def test_claim_is_exclusive_and_checkpoint_is_resumable_after_expired_lease(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1"),))
    started = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)

    first = claim_next_job(
        engine,
        worker_id="worker-a",
        lease_seconds=60,
        now=started,
    )
    assert first is not None
    assert first["attempt_count"] == 1
    assert claim_next_job(
        engine,
        worker_id="worker-b",
        lease_seconds=60,
        now=started + timedelta(seconds=30),
    ) is None
    checkpoint_job(
        engine,
        job_id=first["id"],
        worker_id="worker-a",
        lease_token=first["lease_token"],
        checkpoint={"evidence_count": 7, "last_query": "fixture query"},
        now=started + timedelta(seconds=40),
    )

    reclaimed = claim_next_job(
        engine,
        worker_id="worker-b",
        lease_seconds=60,
        now=started + timedelta(seconds=61),
    )

    assert reclaimed is not None
    assert reclaimed["id"] == first["id"]
    assert reclaimed["attempt_count"] == 2
    assert reclaimed["checkpoint"] == {"evidence_count": 7, "last_query": "fixture query"}
    assert _event_types(engine) == ["planned", "claimed", "checkpoint", "claimed"]


def test_expired_final_attempt_becomes_terminal_failure(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(
        engine,
        (_dossier_spec("dossier:2020:USA:final", max_attempts=1),),
    )
    started = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    claimed = claim_next_job(
        engine, worker_id="worker", lease_seconds=10, now=started
    )
    assert claimed is not None

    assert (
        claim_next_job(
            engine,
            worker_id="replacement",
            lease_seconds=10,
            now=started + timedelta(seconds=11),
        )
        is None
    )
    stored = list_jobs(engine)[0]
    assert stored["status"] == "failed"
    assert stored["error"]["error_type"] == "LeaseExpiredAfterFinalAttempt"
    assert _event_types(engine) == ["planned", "claimed", "failed"]


def test_exhausted_failure_requires_audited_authorization_for_one_more_attempt(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:recovery", max_attempts=1),))
    claimed = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert claimed is not None
    fail_job(
        engine,
        job_id=claimed["id"],
        worker_id="worker",
        lease_token=claimed["lease_token"],
        error={"error_type": "WorkerOutputError"},
        retryable=True,
    )

    authorized = authorize_additional_retry(
        engine,
        job_id=claimed["id"],
        reason="recover completed formatter artifact",
    )

    assert authorized["status"] == "retryable"
    assert authorized["max_attempts"] == 2
    assert authorized["quarantine_reason"] is None
    recovered = claim_next_job(engine, worker_id="recovery", lease_seconds=60)
    assert recovered is not None
    assert recovered["attempt_count"] == 2
    assert "additional_retry_authorized" in _event_types(engine)


def test_concurrent_workers_cannot_claim_the_same_job(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1"),))
    barrier = Barrier(2)

    def claim(worker_id: str) -> dict[str, object] | None:
        barrier.wait()
        return claim_next_job(engine, worker_id=worker_id, lease_seconds=60)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0]["attempt_count"] == 1


def test_postgresql_claims_skip_rows_locked_by_other_workers() -> None:
    assert _claim_lock_clause("postgresql") == "FOR UPDATE SKIP LOCKED"
    assert _claim_lock_clause("sqlite") == ""


def test_claim_and_list_can_be_scoped_to_one_run(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    first = _dossier_spec("dossier:run-a:2020:USA:1")
    second = _dossier_spec("dossier:run-b:2020:USA:1").model_copy(update={"run_key": "run-b"})
    create_jobs(engine, (first, second))

    claimed = claim_next_job(
        engine,
        worker_id="worker",
        lease_seconds=60,
        run_key="run-b",
    )

    assert claimed is not None
    assert claimed["run_key"] == "run-b"
    assert [job["run_key"] for job in list_jobs(engine, run_key="pilot")] == ["pilot"]


def test_only_lease_owner_can_heartbeat_checkpoint_or_complete(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1"),))
    job = claim_next_job(engine, worker_id="owner", lease_seconds=60)
    assert job is not None

    with pytest.raises(ValueError, match="actively leased"):
        heartbeat_job(
            engine,
            job_id=job["id"],
            worker_id="intruder",
            lease_token=job["lease_token"],
            lease_seconds=60,
        )
    running = heartbeat_job(
        engine,
        job_id=job["id"],
        worker_id="owner",
        lease_token=job["lease_token"],
        lease_seconds=60,
        progress={"sources": 3},
    )
    assert running["status"] == "running"
    completed = complete_job(
        engine,
        job_id=job["id"],
        worker_id="owner",
        lease_token=job["lease_token"],
        result_path="data/outputs/research/dossier.json",
    )
    assert completed["status"] == "completed"
    assert claim_next_job(engine, worker_id="other", lease_seconds=60) is None


def test_expired_lease_and_stale_same_worker_token_cannot_mutate(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1"),))
    started = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    first = claim_next_job(
        engine, worker_id="worker", lease_seconds=10, now=started
    )
    assert first is not None

    with pytest.raises(ValueError, match="actively leased"):
        checkpoint_job(
            engine,
            job_id=first["id"],
            worker_id="worker",
            lease_token=first["lease_token"],
            checkpoint={"late": True},
            now=started + timedelta(seconds=11),
        )

    second = claim_next_job(
        engine,
        worker_id="worker",
        lease_seconds=60,
        now=started + timedelta(seconds=11),
    )
    assert second is not None
    assert second["lease_token"] != first["lease_token"]
    with pytest.raises(ValueError, match="actively leased"):
        heartbeat_job(
            engine,
            job_id=first["id"],
            worker_id="worker",
            lease_token=first["lease_token"],
            lease_seconds=60,
            now=started + timedelta(seconds=12),
        )
    heartbeat_job(
        engine,
        job_id=second["id"],
        worker_id="worker",
        lease_token=second["lease_token"],
        lease_seconds=60,
        now=started + timedelta(seconds=12),
    )


def test_job_and_dependencies_roll_back_together(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)

    def fail_dependency_insert(*args: object, **kwargs: object) -> int:
        raise RuntimeError("dependency insert failed")

    monkeypatch.setattr(
        "leaders_db.research.job_ledger.insert_job_dependencies",
        fail_dependency_insert,
    )
    with pytest.raises(RuntimeError, match="dependency insert failed"):
        create_jobs(
            engine,
            (_dossier_spec("dossier:2020:USA:1"),),
            dependencies_by_job_key={"dossier:2020:USA:1": (99,)},
        )

    assert list_jobs(engine) == ()


def test_retry_budget_and_manual_retry_are_enforced(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1", max_attempts=2),))
    first = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert first is not None
    retryable = fail_job(
        engine,
        job_id=first["id"],
        worker_id="worker",
        lease_token=first["lease_token"],
        error={"code": "rate_limit"},
        retryable=True,
    )
    assert retryable["status"] == "retryable"
    second = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert second is not None
    failed = fail_job(
        engine,
        job_id=second["id"],
        worker_id="worker",
        lease_token=second["lease_token"],
        error={"code": "repeated_failure"},
        retryable=True,
    )
    assert failed["status"] == "failed"
    with pytest.raises(ValueError, match="attempts remaining"):
        retry_failed_job(engine, job_id=second["id"])


def test_successful_completion_clears_prior_attempt_error(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(engine, (_dossier_spec("dossier:2020:USA:1"),))
    first = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert first is not None
    fail_job(
        engine,
        job_id=first["id"],
        worker_id="worker",
        lease_token=first["lease_token"],
        error={"code": "temporary"},
        retryable=True,
    )
    second = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert second is not None

    completed = complete_job(
        engine,
        job_id=second["id"],
        worker_id="worker",
        lease_token=second["lease_token"],
        result_path="dossier.json",
    )

    assert completed["error"] == {}


def test_quarantined_job_never_enters_claim_queue(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(
        engine,
        (
            _dossier_spec(
                "dossier:2020:XKX:missing",
                status="quarantined",
                quarantine_reason="missing_identity",
            ),
        ),
    )
    job = list_jobs(engine)[0]

    assert job["status"] == "quarantined"
    assert claim_next_job(engine, worker_id="worker", lease_seconds=60) is None
    with pytest.raises(ValueError, match="terminal"):
        quarantine_job(engine, job_id=job["id"], reason="again")


def test_completed_result_can_be_invalidated_after_quality_control(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(
        engine,
        (_dossier_spec("dossier:2020:USA:invalid", max_attempts=1),),
    )
    claimed = claim_next_job(engine, worker_id="worker", lease_seconds=60)
    assert claimed is not None
    complete_job(
        engine,
        job_id=claimed["id"],
        worker_id="worker",
        lease_token=claimed["lease_token"],
        result_path="invalid-dossier.json",
    )

    invalidated = invalidate_completed_job(
        engine,
        job_id=claimed["id"],
        reason="formatter discarded reviewed evidence",
    )

    assert invalidated["status"] == "quarantined"
    assert invalidated["quarantine_reason"] == "formatter discarded reviewed evidence"
    assert invalidated["completed_at"] is None
    assert invalidated["result_path"] == "invalid-dossier.json"
    assert _event_types(engine)[-1] == "completed_result_invalidated"
    with pytest.raises(ValueError, match="not completed"):
        invalidate_completed_job(engine, job_id=claimed["id"], reason="again")

    authorized = authorize_additional_retry(
        engine,
        job_id=claimed["id"],
        reason="repair the invalid formatter result",
    )
    assert authorized["status"] == "retryable"
    assert authorized["max_attempts"] == 2


def test_judge_job_waits_for_dossier_dependencies(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    create_jobs(
        engine,
        (
            _dossier_spec("dossier:2020:USA:1"),
            ResearchJobSpec(
                job_key="judge:2020:4B.2",
                run_key="pilot",
                job_type="question_judge",
                target_year=2020,
                question_id="4B.2",
                provider_profile="minimax-m3-long-context",
                provider="minimax",
                model="MiniMax-M3",
            ),
        ),
    )
    jobs = {job["job_key"]: job for job in list_jobs(engine)}
    assert add_job_dependencies(
        engine,
        job_id=jobs["judge:2020:4B.2"]["id"],
        depends_on_job_ids=(jobs["dossier:2020:USA:1"]["id"],),
    ) == 1

    assert claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=60,
        job_type="question_judge",
    ) is None
    dossier = claim_next_job(
        engine,
        worker_id="researcher",
        lease_seconds=60,
        job_type="dossier_researcher",
    )
    assert dossier is not None
    complete_job(
        engine,
        job_id=dossier["id"],
        worker_id="researcher",
        lease_token=dossier["lease_token"],
        result_path="dossier.json",
    )
    judge = claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=60,
        job_type="question_judge",
    )
    assert judge is not None


def _dossier_spec(
    key: str,
    *,
    max_attempts: int = 3,
    status: JobStatus = "pending",
    quarantine_reason: str | None = None,
) -> ResearchJobSpec:
    return ResearchJobSpec(
        job_key=key,
        run_key="pilot",
        job_type="dossier_researcher",
        target_year=2020,
        iso3="USA",
        country_name="United States",
        ruler_id="1",
        ruler_name="Donald Trump",
        provider_profile="minimax-m2.7-researcher",
        provider="minimax",
        model="MiniMax-M2.7",
        max_attempts=max_attempts,
        status=status,
        quarantine_reason=quarantine_reason,
        input_payload={"question_ids": ["4B.2"]},
    )


def _event_types(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(text("SELECT event_type FROM research_job_events ORDER BY id")).scalars()
        )
