from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.chapter_judge_worker import (
    _prepare_batch,
)
from leaders_db.research.chapter_score_store import persist_chapter_batch_and_complete
from leaders_db.research.dossier_models import RulerEvidenceDossier
from leaders_db.research.job_ledger import (
    ResearchJobSpec,
    claim_next_job,
    create_jobs,
)
from tests.research.test_chapter_judge_worker import (
    _batch_for_store,
    _dossier_payload,
    _evaluation,
    _fixture_dossier_job,
    _fixture_judge_job,
    _judge_candidate,
    _projections,
    _unknown_usage,
)


def test_chapter_score_persistence_rejects_expired_lease_without_partial_rows(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'expired.sqlite'}"
    init_database(database_url)
    engine = create_engine(database_url)
    now = datetime(2020, 1, 1, tzinfo=UTC)
    create_jobs(
        engine,
        (
            ResearchJobSpec(
                job_key="chapter-judge:expired:2020:4B",
                run_key="expired",
                job_type="question_judge",
                target_year=2020,
                question_id="4B",
                provider_profile="fixture",
                provider="openai",
                model="fixture",
                input_payload={
                    "chapter_id": "4B",
                    "rubric_version": "chapter_4b_v1",
                    "dossier_job_keys": ["dossier:fixture"],
                },
            ),
        ),
    )
    judge = claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=1,
        job_type="question_judge",
        now=now,
    )
    assert judge is not None
    batch = _batch_for_store(job_key=judge["job_key"])

    with pytest.raises(ValueError, match="scope differs"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch.model_copy(update={"target_year": 2021}),
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "wrong-scope.json",
            now=now,
        )
    with pytest.raises(ValueError, match="scope differs"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch.model_copy(update={"rubric_version": "chapter_4b_untrusted"}),
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "wrong-rubric.json",
            now=now,
        )

    with pytest.raises(ValueError, match="stale, expired"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch,
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "result.json",
            now=now + timedelta(seconds=2),
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chapter_scores")).scalar_one() == 0


def test_prepare_batch_rejects_self_only_calibration_and_discovery_only_evidence(
    tmp_path: Path,
) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    judge = _fixture_judge_job(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        methodology_ids=methodology_ids,
    )
    candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    candidate["evaluations"][0]["calibrated_against"] = [dossier_jobs[0]["job_key"]]

    with pytest.raises(ValueError, match="another ruler"):
        _prepare_batch(
            candidate,
            job=judge,
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )

    discovery_payload = _dossier_payload(dossier_jobs[0], methodology_ids=methodology_ids)
    discovery_payload["evidence"][0]["final_evidence_use"] = "discovery_only"
    discovery_dossier = RulerEvidenceDossier.model_validate(discovery_payload)
    single_job = _fixture_judge_job(
        dossier_job_keys=[str(dossier_jobs[0]["job_key"])],
        methodology_ids=methodology_ids,
    )
    single_candidate = {
        "evaluations": [_evaluation(job_key=str(dossier_jobs[0]["job_key"]), iso3="AAA", score=5)],
        "batch_notes": [],
        "run_profile": {"usage": _unknown_usage()},
    }
    with pytest.raises(ValueError, match="discovery-only"):
        _prepare_batch(
            single_candidate,
            job=single_job,
            dossiers=((tmp_path / "discovery.json", discovery_dossier),),
            projections=_projections(
                ((tmp_path / "discovery.json", discovery_dossier),), chapter_id="4B"
            ),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )


def test_prepare_batch_accepts_singleton_no_peer_calibration_sentinel(
    tmp_path: Path,
) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_job = _fixture_dossier_job(index=1, iso3="AAA", methodology_ids=methodology_ids)
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(dossier_job, methodology_ids=methodology_ids)
    )
    candidate = {
        "evaluations": [_evaluation(job_key=str(dossier_job["job_key"]), iso3="AAA", score=5)],
        "batch_notes": [],
        "run_profile": {"usage": _unknown_usage()},
    }
    candidate["evaluations"][0]["calibrated_against"] = ["no_other_available_dossier_in_manifest"]

    batch = _prepare_batch(
        candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(dossier_job["job_key"])],
            methodology_ids=methodology_ids,
        ),
        dossiers=((tmp_path / "singleton.json", dossier),),
        projections=_projections(((tmp_path / "singleton.json", dossier),), chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert batch.evaluations[0].calibrated_against == ()
