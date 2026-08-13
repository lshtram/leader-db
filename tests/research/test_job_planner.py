from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.job_ledger import claim_next_job, complete_job, list_jobs
from leaders_db.research.job_planner import (
    _validate_dossier_cohort_identity,
    plan_all_chapter_judge_jobs,
    plan_chapter_judge_job,
    plan_dossier_jobs,
)
from leaders_db.research.local_prior_slice import LocalPriorSliceCase


def test_dossier_cohort_allows_only_append_only_manifest_expansion(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="expandable",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    expanded_manifest = SimpleNamespace(
        year=2020,
        batch_id="expanded",
        resolved_content_sha256="new-hash",
    )
    monkeypatch.setattr(
        "leaders_db.research.job_planner.load_batch_manifest",
        lambda path: expanded_manifest,
    )
    monkeypatch.setattr(
        "leaders_db.research.job_planner.validate_batch_manifest_cases",
        lambda engine, manifest: (
            _cases()[0],
            _cases()[0].model_copy(
                update={
                    "iso3": "CAN",
                    "country_name": "Canada",
                    "leader_name": "Jean Chrétien",
                    "leader_id": 2,
                    "ruler_year_id": 20,
                }
            ),
        ),
    )
    expanded = plan_dossier_jobs(
        engine,
        year=2020,
        run_key="expandable",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
        batch_manifest_path=tmp_path / "expanded.yaml",
    )
    assert expanded.write_result.model_dump() == {
        "created": 1,
        "existing": 0,
        "total": 1,
    }
    assert len(list_jobs(engine, run_key="expandable")) == 2
    judge = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="expanded-judge",
        dossier_run_key="expandable",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )
    assert judge.dossier_dependency_count == 2
    judge_job = next(
        job for job in list_jobs(engine, run_key="expanded-judge")
    )
    assert judge_job["input"]["batch_id"].startswith("append-only:")
    assert judge_job["input"]["dossier_job_keys"] == [
        "dossier:expandable:2020:USA:10",
        "dossier:expandable:2020:CAN:20",
    ]

    _validate_dossier_cohort_identity(
        engine,
        run_key="expandable",
        year=2020,
        batch_manifest_sha256="new-hash",
        included_ruler_year_ids={10, 20},
    )
    with pytest.raises(ValueError, match="different dossier batch"):
        _validate_dossier_cohort_identity(
            engine,
            run_key="expandable",
            year=2020,
            batch_manifest_sha256="new-hash",
            included_ruler_year_ids={20},
        )


def test_planner_creates_one_dossier_per_case_and_one_judge_per_chapter(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases(),
    )

    dossiers = plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    repeated = plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    judge = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

    assert dossiers.model_dump() == {
        "write_result": {"created": 2, "existing": 0, "total": 2},
        "eligible_jobs": 1,
        "quarantined_jobs": 1,
        "batch_id": None,
        "batch_manifest_sha256": None,
    }
    assert repeated.write_result.model_dump() == {"created": 0, "existing": 2, "total": 2}
    assert judge.write_result.created == 1
    assert judge.dossier_dependency_count == 1
    jobs = list_jobs(engine)
    assert len(jobs) == 3
    assert [job["status"] for job in jobs].count("quarantined") == 1
    dossier_job = next(job for job in jobs if job["job_type"] == "dossier_researcher")
    workflow = dossier_job["input"]["research_workflow"]
    assert workflow["chapter_order"] == [f"{index}B" for index in range(1, 9)]
    assert workflow["max_review_rounds"] == 3


def test_planner_creates_eight_judges_over_one_full_dossier_cohort(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    eligible = _cases()[0]
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: (eligible,),
    )
    all_ids = tuple(
        f"{chapter}B.{question}"
        for chapter in range(1, 9)
        for question in range(1, 11)
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="full-batch",
        methodology_ids=all_ids,
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    planned = plan_all_chapter_judge_jobs(
        engine,
        year=2020,
        run_key="full-batch",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

    assert planned.judge_jobs == 8
    assert planned.dossier_dependency_count_per_judge == 1
    jobs = list_jobs(engine, job_type="question_judge")
    assert [job["question_id"] for job in jobs] == [f"{index}B" for index in range(1, 9)]


def test_judge_run_can_reuse_dossiers_from_another_run_key(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="dossier-v2",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    result = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="judge-v3",
        dossier_run_key="dossier-v2",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

    assert result.dossier_dependency_count == 1
    judge = next(job for job in list_jobs(engine) if job["run_key"] == "judge-v3")
    assert judge["input"]["dossier_run_key"] == "dossier-v2"
    assert judge["input"]["dossier_run_keys"] == ["dossier-v2"]
    assert judge["input"]["dossier_job_keys"] == ["dossier:dossier-v2:2020:USA:10"]


def test_judge_run_can_combine_distinct_dossier_run_keys(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    cases = (
        _cases()[0],
        _cases()[0].model_copy(
            update={
                "iso3": "CAN",
                "country_name": "Canada",
                "leader_name": "Justin Trudeau",
                "leader_id": 2,
                "ruler_year_id": 20,
            }
        ),
    )
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: cases[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="first-dossiers",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: cases[1:],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="second-dossiers",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_jobs SET status = 'completed' "
                "WHERE run_key IN ('first-dossiers', 'second-dossiers')"
            )
        )

    result = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="combined-judge",
        dossier_run_key=("first-dossiers", "second-dossiers"),
        completed_dossiers_only=True,
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

    assert result.dossier_dependency_count == 2
    judge = next(job for job in list_jobs(engine) if job["run_key"] == "combined-judge")
    assert judge["input"]["dossier_run_key"] is None
    assert judge["input"]["dossier_run_keys"] == [
        "first-dossiers",
        "second-dossiers",
    ]
    assert judge["input"]["completed_dossiers_only"] is True
    assert judge["input"]["dossier_job_keys"] == [
        "dossier:first-dossiers:2020:USA:10",
        "dossier:second-dossiers:2020:CAN:20",
    ]


def test_v2_judge_rejects_a_cohort_without_approved_corpus_packages(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="deep-dossiers",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    with pytest.raises(ValueError, match="versioned deep-corpus release"):
        plan_chapter_judge_job(
            engine,
            year=2020,
            run_key="deep-judge",
            dossier_run_key="deep-dossiers",
            chapter_id="4B",
            provider_profile="judge",
            model_profiles_path=profiles,
            require_approved_corpus=True,
        )


def test_release_config_enforces_approved_corpus_without_shadow_flags(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    case = _cases()[0].model_copy(update={"year": 2023})
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: (case,),
    )
    plan_dossier_jobs(
        engine,
        year=2023,
        run_key="release-dossiers",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    with pytest.raises(ValueError, match="approved corpus package missing"):
        plan_chapter_judge_job(
            engine,
            year=2023,
            run_key="release-judge",
            dossier_run_key="release-dossiers",
            chapter_id="4B",
            provider_profile="judge",
            model_profiles_path=profiles,
            release_config_path=Path(
                "configs/evidence-funnel/production-2023-v4.yaml"
            ),
        )


def test_production_judge_requires_a_release_even_with_strict_flag(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="strict-dossiers",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    with pytest.raises(ValueError, match="versioned deep-corpus release"):
        plan_chapter_judge_job(
            engine,
            year=2020,
            run_key="strict-judge",
            dossier_run_key="strict-dossiers",
            require_approved_corpus=True,
            chapter_id="4B",
            provider_profile="judge",
            model_profiles_path=profiles,
        )


def test_judge_run_rejects_duplicate_ruler_across_dossier_runs(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    for run_key in ("first-dossiers", "duplicate-dossiers"):
        plan_dossier_jobs(
            engine,
            year=2020,
            run_key=run_key,
            methodology_ids=_chapter_ids("4B"),
            provider_profile="researcher",
            model_profiles_path=profiles,
        )

    with pytest.raises(ValueError, match="duplicate ruler identity"):
        plan_chapter_judge_job(
            engine,
            year=2020,
            run_key="invalid-judge",
            dossier_run_key=("first-dossiers", "duplicate-dossiers"),
            chapter_id="4B",
            provider_profile="judge",
            model_profiles_path=profiles,
        )


def test_judge_claim_waits_until_planned_dossier_completes(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

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
    result = tmp_path / "dossier.json"
    result.write_text("{}", encoding="utf-8")
    complete_job(
        engine,
        job_id=dossier["id"],
        worker_id="researcher",
        lease_token=dossier["lease_token"],
        result_path=str(result),
    )
    judge = claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=60,
        job_type="question_judge",
    )
    assert judge is not None


def test_dependency_edges_are_idempotent_on_replanned_judge(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )

    first = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )
    second = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )

    assert first.write_result.created == 1
    assert second.write_result.existing == 1
    with engine.connect() as conn:
        dependency_count = conn.execute(
            text("SELECT COUNT(*) FROM research_job_dependencies")
        ).scalar_one()
    assert dependency_count == 1


def test_chapter_judge_records_cancelled_dossier_as_unavailable(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot-cancelled",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_jobs SET status = 'cancelled' "
                "WHERE run_key = 'pilot-cancelled' AND job_type = 'dossier_researcher'"
            )
        )

    result = plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot-cancelled",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )
    judge = next(
        job
        for job in list_jobs(engine, job_type="question_judge")
        if job["run_key"] == "pilot-cancelled"
    )

    assert result.dossier_dependency_count == 0
    assert judge["input"]["dossier_job_keys"] == []
    assert judge["input"]["unavailable_dossiers"][0]["status"] == "cancelled"


def test_chapter_judge_reconciles_dossier_that_fails_after_planning(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    profiles = _profiles(tmp_path)
    monkeypatch.setattr(
        "leaders_db.research.job_planner.list_local_prior_slice_cases",
        lambda engine, *, year: _cases()[:1],
    )
    plan_dossier_jobs(
        engine,
        year=2020,
        run_key="pilot-late-failure",
        methodology_ids=_chapter_ids("4B"),
        provider_profile="researcher",
        model_profiles_path=profiles,
    )
    plan_chapter_judge_job(
        engine,
        year=2020,
        run_key="pilot-late-failure",
        chapter_id="4B",
        provider_profile="judge",
        model_profiles_path=profiles,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_jobs SET status = 'failed' "
                "WHERE run_key = 'pilot-late-failure' AND job_type = 'dossier_researcher'"
            )
        )

    judge = claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=60,
        job_type="question_judge",
        run_key="pilot-late-failure",
    )

    assert judge is not None
    assert judge["input"]["dossier_job_keys"] == []
    assert judge["input"]["unavailable_dossiers"][0]["status"] == "failed"


def _cases() -> tuple[LocalPriorSliceCase, ...]:
    return (
        LocalPriorSliceCase(
            iso3="USA",
            country_name="United States",
            year=2020,
            leader_name="Donald Trump",
            leader_id=1,
            ruler_year_id=10,
            identity_classification="resolved_auto_single_candidate",
            identity_review_status="resolved",
            identity_research_eligible=True,
        ),
        LocalPriorSliceCase(
            iso3="XKX",
            country_name="Kosovo",
            year=2020,
            identity_classification="missing_no_identity_observation",
            identity_review_status="needs_review",
            identity_research_eligible=False,
            identity_block_reason="identity_classification:missing_no_identity_observation",
        ),
    )


def _chapter_ids(chapter_id: str) -> tuple[str, ...]:
    return tuple(f"{chapter_id}.{index}" for index in range(1, 11))


def _profiles(tmp_path: Path) -> Path:
    config = tmp_path / "codex.toml"
    credential = tmp_path / "auth.json"
    config.write_text('model = "fixture"\n', encoding="utf-8")
    credential.write_text("{}", encoding="utf-8")
    path = tmp_path / "profiles.yaml"
    path.write_text(
        f"""version: 1
profiles:
  researcher:
    provider: openai
    model: gpt-5.6-luna
    execution_surface: codex
    roles: [dossier_researcher, dossier_evidence_reviewer, dossier_formatter]
    cost_class: low_cost_candidate
    context_window: 372000
    codex_config_path: {config}
    credential_path: {credential}
    notes: fixture
  judge:
    provider: openai
    model: gpt-5.6-terra
    execution_surface: codex
    roles: [chapter_judge]
    cost_class: low_cost_candidate
    context_window: 372000
    codex_config_path: {config}
    credential_path: {credential}
    notes: fixture
""",
        encoding="utf-8",
    )
    return path
