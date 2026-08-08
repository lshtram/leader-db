"""Plan ruler-dossier and question-judge jobs into the durable ledger."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine

from leaders_db.research.batch_manifest import (
    load_batch_manifest,
    validate_batch_manifest_cases,
)
from leaders_db.research.chapter_guides import load_chapter_guide
from leaders_db.research.job_ledger import (
    JobWriteResult,
    ResearchJobSpec,
    create_jobs,
    list_jobs,
)
from leaders_db.research.local_prior_slice import LocalPriorSliceCase, list_local_prior_slice_cases
from leaders_db.research.model_profiles import (
    ResearchModelProfile,
    load_research_model_profiles,
)
from leaders_db.research.registry import get_question_spec_by_methodology_id
from leaders_db.research.research_workflow import load_research_workflow


class DossierPlanResult(BaseModel):
    """Summary from planning one dossier job per included ruler/country-year."""

    model_config = ConfigDict(extra="forbid")

    write_result: JobWriteResult
    eligible_jobs: int
    quarantined_jobs: int
    batch_id: str | None = None
    batch_manifest_sha256: str | None = None


class JudgePlanResult(BaseModel):
    """Summary from planning one question judge and its dossier dependencies."""

    model_config = ConfigDict(extra="forbid")

    write_result: JobWriteResult
    judge_job_id: int
    dossier_dependency_count: int


class JudgeBatchPlanResult(BaseModel):
    """Planning summary for the complete eight-judge chapter batch."""

    model_config = ConfigDict(extra="forbid")

    chapter_results: tuple[JudgePlanResult, ...]
    judge_jobs: int
    dossier_dependency_count_per_judge: int


def plan_dossier_jobs(
    engine: Engine,
    *,
    year: int,
    run_key: str,
    methodology_ids: tuple[str, ...],
    provider_profile: str,
    reviewer_profile: str | None = None,
    formatter_profile: str | None = None,
    model_profiles_path: Path,
    output_root: Path | None = None,
    research_workflow_path: Path | None = None,
    batch_manifest_path: Path | None = None,
    max_attempts: int = 3,
) -> DossierPlanResult:
    """Create one idempotent dossier job per included country-year."""

    if not methodology_ids:
        raise ValueError("at least one methodology_id is required")
    for methodology_id in methodology_ids:
        spec = get_question_spec_by_methodology_id(methodology_id)
        if spec is None or spec.evidence_strategy != "internet_manual":
            raise ValueError(f"unsupported dossier methodology_id: {methodology_id!r}")
    profile = _profile_for_role(
        model_profiles_path,
        provider_profile=provider_profile,
        role="dossier_researcher",
    )
    formatter_profile_name = formatter_profile or provider_profile
    reviewer_profile_name = reviewer_profile or provider_profile
    reviewer = _profile_for_role(
        model_profiles_path,
        provider_profile=reviewer_profile_name,
        role="dossier_evidence_reviewer",
    )
    formatter = _profile_for_role(
        model_profiles_path,
        provider_profile=formatter_profile_name,
        role="dossier_formatter",
    )
    research_workflow = load_research_workflow(
        research_workflow_path or _default_research_workflow_path()
    ).model_dump(mode="json")
    manifest = load_batch_manifest(batch_manifest_path) if batch_manifest_path else None
    if manifest is not None and manifest.year != year:
        raise ValueError("batch manifest year differs from requested planning year")
    cases = (
        validate_batch_manifest_cases(engine, manifest)
        if manifest is not None
        else list_local_prior_slice_cases(engine, year=year)
    )
    _validate_dossier_cohort_identity(
        engine,
        run_key=run_key,
        year=year,
        batch_manifest_sha256=(
            manifest.resolved_content_sha256 if manifest is not None else None
        ),
        included_ruler_year_ids={
            case.ruler_year_id for case in cases if case.ruler_year_id is not None
        },
    )
    existing_jobs = tuple(
        job
        for job in list_jobs(engine, run_key=run_key, job_type="dossier_researcher")
        if job["target_year"] == year
    )
    existing_hashes = {
        job["input"].get("batch_manifest_sha256") for job in existing_jobs
    }
    expanding_manifest = bool(existing_jobs) and existing_hashes != {
        manifest.resolved_content_sha256 if manifest is not None else None
    }
    existing_ruler_year_ids = {
        int(job["input"]["ruler_year_id"])
        for job in existing_jobs
        if job["input"].get("ruler_year_id") is not None
    }
    cases_to_plan = (
        tuple(
            case
            for case in cases
            if case.ruler_year_id not in existing_ruler_year_ids
        )
        if expanding_manifest
        else cases
    )
    specs = tuple(
        _dossier_spec(
            case,
            methodology_ids=methodology_ids,
            run_key=run_key,
            profile_name=provider_profile,
            profile=profile,
            reviewer_profile_name=reviewer_profile_name,
            reviewer_profile=reviewer,
            formatter_profile_name=formatter_profile_name,
            formatter_profile=formatter,
            research_workflow=research_workflow,
            output_root=output_root,
            max_attempts=max_attempts,
            batch_id=manifest.batch_id if manifest else None,
            batch_manifest_sha256=(
                manifest.resolved_content_sha256 if manifest else None
            ),
        )
        for case in cases_to_plan
    )
    result = create_jobs(engine, specs)
    eligible = sum(spec.status == "pending" for spec in specs)
    return DossierPlanResult(
        write_result=result,
        eligible_jobs=eligible,
        quarantined_jobs=len(specs) - eligible,
        batch_id=manifest.batch_id if manifest else None,
        batch_manifest_sha256=manifest.resolved_content_sha256 if manifest else None,
    )


def plan_single_dossier_job(
    engine: Engine,
    *,
    year: int,
    ruler_year_id: int,
    run_key: str,
    methodology_ids: tuple[str, ...],
    provider_profile: str,
    reviewer_profile: str | None = None,
    formatter_profile: str | None = None,
    model_profiles_path: Path,
    output_root: Path,
    research_workflow_path: Path | None = None,
    source_catalog_seed_paths: tuple[Path, ...] = (),
    max_attempts: int = 3,
) -> DossierPlanResult:
    """Plan one comparison/pilot dossier for an exact eligible ruler-year."""

    if not methodology_ids:
        raise ValueError("at least one methodology_id is required")
    missing_seeds = [path for path in source_catalog_seed_paths if not path.is_file()]
    if missing_seeds:
        raise ValueError(f"source catalogue seed does not exist: {missing_seeds[0]}")
    for methodology_id in methodology_ids:
        spec = get_question_spec_by_methodology_id(methodology_id)
        if spec is None or spec.evidence_strategy != "internet_manual":
            raise ValueError(f"unsupported dossier methodology_id: {methodology_id!r}")
    profile = _profile_for_role(
        model_profiles_path,
        provider_profile=provider_profile,
        role="dossier_researcher",
    )
    formatter_profile_name = formatter_profile or provider_profile
    reviewer_profile_name = reviewer_profile or provider_profile
    reviewer = _profile_for_role(
        model_profiles_path,
        provider_profile=reviewer_profile_name,
        role="dossier_evidence_reviewer",
    )
    formatter = _profile_for_role(
        model_profiles_path,
        provider_profile=formatter_profile_name,
        role="dossier_formatter",
    )
    research_workflow = load_research_workflow(
        research_workflow_path or _default_research_workflow_path()
    ).model_dump(mode="json")
    case = next(
        (
            item
            for item in list_local_prior_slice_cases(engine, year=year)
            if item.ruler_year_id == ruler_year_id
        ),
        None,
    )
    if case is None or not case.identity_research_eligible:
        raise ValueError("ruler_year_id is unavailable or identity-quarantined")
    spec = _dossier_spec(
        case,
        methodology_ids=methodology_ids,
        run_key=run_key,
        profile_name=provider_profile,
        profile=profile,
        reviewer_profile_name=reviewer_profile_name,
        reviewer_profile=reviewer,
        formatter_profile_name=formatter_profile_name,
        formatter_profile=formatter,
        research_workflow=research_workflow,
        output_root=output_root,
        source_catalog_seed_paths=source_catalog_seed_paths,
        max_attempts=max_attempts,
    )
    result = create_jobs(engine, (spec,))
    return DossierPlanResult(
        write_result=result,
        eligible_jobs=1,
        quarantined_jobs=0,
    )


def plan_chapter_judge_job(
    engine: Engine,
    *,
    year: int,
    run_key: str,
    dossier_run_key: str | Sequence[str] | None = None,
    completed_dossiers_only: bool = False,
    approved_ruler_package_paths: Sequence[Path] = (),
    require_approved_corpus: bool = False,
    release_config_path: Path | None = None,
    chapter_id: str,
    provider_profile: str,
    model_profiles_path: Path,
    output_root: Path | None = None,
    max_attempts: int = 3,
) -> JudgePlanResult:
    """Create one chapter judge depending on every eligible ruler dossier."""

    normalized_chapter = chapter_id.strip().upper()
    if normalized_chapter not in {f"{index}B" for index in range(1, 9)}:
        raise ValueError(f"unsupported chapter_id: {chapter_id!r}")
    methodology_ids = tuple(f"{normalized_chapter}.{index}" for index in range(1, 11))
    if any(get_question_spec_by_methodology_id(item) is None for item in methodology_ids):
        raise ValueError(f"chapter question registry is incomplete for {normalized_chapter}")
    profile = _profile_for_role(
        model_profiles_path,
        provider_profile=provider_profile,
        role="chapter_judge",
    )
    _, rubric_version = load_chapter_guide(normalized_chapter)
    source_run_keys = _normalize_dossier_run_keys(dossier_run_key, fallback=run_key)
    scoped_dossier_jobs = tuple(
        job
        for job in list_jobs(engine, job_type="dossier_researcher")
        if job["target_year"] == year
        and job["run_key"] in source_run_keys
        and (not completed_dossiers_only or job["status"] == "completed")
        and set(methodology_ids).issubset(job["input"].get("question_ids", []))
    )
    if not scoped_dossier_jobs:
        raise ValueError(
            "no ruler dossier jobs cover this chapter and year "
            f"for dossier runs {source_run_keys!r}"
        )
    _reject_duplicate_dossier_identities(scoped_dossier_jobs)
    cohort_hashes = {
        job["input"].get("batch_manifest_sha256") for job in scoped_dossier_jobs
    }
    cohort_ids = {job["input"].get("batch_id") for job in scoped_dossier_jobs}
    cohort_hash, cohort_id = _judge_cohort_identity(cohort_hashes, cohort_ids)
    dossier_jobs = tuple(
        job
        for job in scoped_dossier_jobs
        if job["status"] not in {"failed", "cancelled", "quarantined"}
    )
    unavailable_jobs = tuple(
        job
        for job in scoped_dossier_jobs
        if job["status"] in {"failed", "cancelled", "quarantined"}
    )
    release_reference = None
    if release_config_path is not None:
        from .deep_corpus_release import (
            load_deep_corpus_release,
        )
        from .deep_corpus_release import (
            release_reference as build_release_reference,
        )

        release = load_deep_corpus_release(release_config_path)
        if release.target_year != year:
            raise ValueError("deep-corpus release target year differs from judge year")
        require_approved_corpus = release.judge_contract.require_approved_corpus_package
        release_reference = build_release_reference(release_config_path)
    approved_packages = _approved_package_map(
        approved_ruler_package_paths,
        expected_job_keys={job["job_key"] for job in dossier_jobs},
        require_complete=require_approved_corpus,
        target_year=year,
    )
    job_key = f"chapter-judge:{run_key}:{year}:{normalized_chapter}"
    write_result = create_jobs(
        engine,
        (
            ResearchJobSpec(
                job_key=job_key,
                run_key=run_key,
                job_type="question_judge",
                target_year=year,
                question_id=normalized_chapter,
                provider_profile=provider_profile,
                provider=profile.provider,
                model=profile.model,
                max_attempts=max_attempts,
                input_payload={
                    "chapter_id": normalized_chapter,
                    "rubric_version": rubric_version,
                    "methodology_ids": list(methodology_ids),
                    "dossier_run_key": (
                        source_run_keys[0] if len(source_run_keys) == 1 else None
                    ),
                    "dossier_run_keys": list(source_run_keys),
                    "completed_dossiers_only": completed_dossiers_only,
                    "dossier_job_keys": [job["job_key"] for job in dossier_jobs],
                    "require_approved_corpus": require_approved_corpus,
                    "approved_ruler_packages": approved_packages,
                    "deep_corpus_release": release_reference,
                    "batch_id": cohort_id,
                    "batch_manifest_sha256": cohort_hash,
                    "unavailable_dossiers": [
                        {
                            "job_key": job["job_key"],
                            "status": job["status"],
                            "iso3": job["iso3"],
                            "ruler_name": job["ruler_name"],
                        }
                        for job in unavailable_jobs
                    ],
                    "output_root": str(output_root) if output_root else None,
                },
            ),
        ),
        dependencies_by_job_key={
            job_key: tuple(int(job["id"]) for job in dossier_jobs),
        },
    )
    judge = next(
        job
        for job in list_jobs(engine, job_type="question_judge")
        if job["job_key"] == job_key
    )
    return JudgePlanResult(
        write_result=write_result,
        judge_job_id=int(judge["id"]),
        dossier_dependency_count=len(dossier_jobs),
    )


def _judge_cohort_identity(
    manifest_hashes: set[str | None], batch_ids: set[str | None]
) -> tuple[str | None, str | None]:
    """Represent a single manifest or its validated append-only lineage."""

    if len(manifest_hashes) == 1 and len(batch_ids) == 1:
        return next(iter(manifest_hashes)), next(iter(batch_ids))
    hashes = sorted(value or "unmanifested" for value in manifest_hashes)
    identifiers = sorted(value or "unmanifested" for value in batch_ids)
    lineage_hash = sha256("|".join(hashes).encode("utf-8")).hexdigest()
    return lineage_hash, "append-only:" + "+".join(identifiers)


def _normalize_dossier_run_keys(
    value: str | Sequence[str] | None,
    *,
    fallback: str,
) -> tuple[str, ...]:
    """Return a stable, non-empty ordered dossier-run selection."""

    raw_values = (value,) if isinstance(value, str) else tuple(value or (fallback,))
    normalized = tuple(dict.fromkeys(item.strip() for item in raw_values if item.strip()))
    if not normalized:
        raise ValueError("at least one non-empty dossier run key is required")
    return normalized


def _reject_duplicate_dossier_identities(jobs: Sequence[dict[str, Any]]) -> None:
    """Reject cohorts that select one ruler-year from more than one run."""

    seen: dict[tuple[str, ...], str] = {}
    for job in jobs:
        ruler_year_id = job["input"].get("ruler_year_id")
        identity = (
            ("ruler_year_id", str(ruler_year_id))
            if ruler_year_id is not None
            else (
                "legacy",
                str(job["iso3"]),
                str(job["ruler_id"]),
                str(job["target_year"]),
            )
        )
        prior = seen.setdefault(identity, str(job["run_key"]))
        if prior != str(job["run_key"]):
            raise ValueError(
                "duplicate ruler identity across dossier runs: "
                f"{'/'.join(identity)} appears in {prior!r} and "
                f"{job['run_key']!r}"
            )


def plan_all_chapter_judge_jobs(
    engine: Engine,
    *,
    year: int,
    run_key: str,
    dossier_run_key: str | Sequence[str] | None = None,
    completed_dossiers_only: bool = False,
    approved_ruler_package_paths: Sequence[Path] = (),
    require_approved_corpus: bool = False,
    release_config_path: Path | None = None,
    provider_profile: str,
    model_profiles_path: Path,
    output_root: Path | None = None,
    max_attempts: int = 3,
) -> JudgeBatchPlanResult:
    """Idempotently plan one comparative judge for every chapter."""

    results = tuple(
        plan_chapter_judge_job(
            engine,
            year=year,
            run_key=run_key,
            dossier_run_key=dossier_run_key,
            completed_dossiers_only=completed_dossiers_only,
            approved_ruler_package_paths=approved_ruler_package_paths,
            require_approved_corpus=require_approved_corpus,
            release_config_path=release_config_path,
            chapter_id=f"{chapter}B",
            provider_profile=provider_profile,
            model_profiles_path=model_profiles_path,
            output_root=output_root,
            max_attempts=max_attempts,
        )
        for chapter in range(1, 9)
    )
    dependency_counts = {item.dossier_dependency_count for item in results}
    if len(dependency_counts) != 1:
        raise ValueError("all chapter judges must share one dossier cohort")
    return JudgeBatchPlanResult(
        chapter_results=results,
        judge_jobs=len(results),
        dossier_dependency_count_per_judge=next(iter(dependency_counts)),
    )


def _approved_package_map(
    paths: Sequence[Path],
    *,
    expected_job_keys: set[str],
    require_complete: bool,
    target_year: int,
) -> dict[str, dict[str, str]]:
    from .approved_ruler_package import (
        ApprovedPackageReference,
        ApprovedRulerEvidencePackage,
    )

    mapped: dict[str, dict[str, str]] = {}
    for path in paths:
        package = ApprovedRulerEvidencePackage.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if package.dossier_job_key in mapped:
            raise ValueError("duplicate approved ruler package for dossier job")
        if package.dossier_job_key not in expected_job_keys:
            raise ValueError("approved ruler package is outside the judge cohort")
        if package.target_year != target_year:
            raise ValueError("approved ruler package target year differs from judge year")
        reference = ApprovedPackageReference(
            path=str(path),
            sha256=sha256(path.read_bytes()).hexdigest(),
        )
        mapped[package.dossier_job_key] = reference.model_dump(mode="json")
    if require_complete and set(mapped) != expected_job_keys:
        missing = ", ".join(sorted(expected_job_keys - set(mapped)))
        raise ValueError(f"approved corpus package missing for dossier jobs: {missing}")
    return mapped


def _validate_dossier_cohort_identity(
    engine: Engine,
    *,
    run_key: str,
    year: int,
    batch_manifest_sha256: str | None,
    included_ruler_year_ids: set[int],
) -> None:
    """Permit only explicit append-only expansion of a frozen ruler cohort."""

    existing = tuple(
        job
        for job in list_jobs(engine, run_key=run_key, job_type="dossier_researcher")
        if job["target_year"] == year
    )
    hashes = {job["input"].get("batch_manifest_sha256") for job in existing}
    existing_ids = {
        int(job["input"]["ruler_year_id"])
        for job in existing
        if job["input"].get("ruler_year_id") is not None
    }
    if (
        hashes
        and hashes != {batch_manifest_sha256}
        and not existing_ids.issubset(included_ruler_year_ids)
    ):
        raise ValueError(
            "run_key/year already belongs to a different dossier batch manifest"
        )


def _dossier_spec(
    case: LocalPriorSliceCase,
    *,
    methodology_ids: tuple[str, ...],
    run_key: str,
    profile_name: str,
    profile: ResearchModelProfile,
    reviewer_profile_name: str,
    reviewer_profile: ResearchModelProfile,
    formatter_profile_name: str,
    formatter_profile: ResearchModelProfile,
    research_workflow: dict[str, object],
    output_root: Path | None,
    max_attempts: int,
    source_catalog_seed_paths: tuple[Path, ...] = (),
    batch_id: str | None = None,
    batch_manifest_sha256: str | None = None,
) -> ResearchJobSpec:
    ruler_year_id = case.ruler_year_id
    leader_id = case.leader_id
    iso3 = case.iso3
    identity = str(ruler_year_id or leader_id or "unresolved")
    eligible = case.identity_research_eligible
    block_reason = case.identity_block_reason
    return ResearchJobSpec(
        job_key=f"dossier:{run_key}:{case.year}:{iso3}:{identity}",
        run_key=run_key,
        job_type="dossier_researcher",
        target_year=case.year,
        period_start_year=case.year,
        period_end_year=case.year,
        iso3=iso3,
        country_name=case.country_name,
        ruler_id=str(leader_id) if leader_id is not None else None,
        ruler_name=case.leader_name,
        provider_profile=profile_name,
        provider=profile.provider,
        model=profile.model,
        status="pending" if eligible else "quarantined",
        max_attempts=max_attempts,
        quarantine_reason=None if eligible else str(block_reason),
        input_payload={
            "question_ids": list(methodology_ids),
            "ruler_year_id": ruler_year_id,
            "identity_classification": case.identity_classification,
            "output_root": str(output_root) if output_root else None,
            "research_workflow": research_workflow,
            "source_catalog_seed_paths": [
                {
                    "path": str(path),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                }
                for path in source_catalog_seed_paths
            ],
            "workflow_mode": "direct_search_chapter_loop_v1",
            "evidence_review_mode": "always",
            "reviewer_profile": reviewer_profile_name,
            "reviewer_provider": reviewer_profile.provider,
            "reviewer_model": reviewer_profile.model,
            "batch_id": batch_id,
            "batch_manifest_sha256": batch_manifest_sha256,
            "formatter_profile": formatter_profile_name,
            "formatter_provider": formatter_profile.provider,
            "formatter_model": formatter_profile.model,
        },
    )


def _default_research_workflow_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs/research-workflow.yaml"


def _profile_for_role(
    path: Path,
    *,
    provider_profile: str,
    role: str,
) -> ResearchModelProfile:
    profile = load_research_model_profiles(path).profiles.get(provider_profile)
    if profile is None:
        raise ValueError(f"unknown provider profile: {provider_profile!r}")
    if role not in profile.roles:
        raise ValueError(f"provider profile {provider_profile!r} does not support {role}")
    return profile


__all__ = [
    "DossierPlanResult",
    "JudgeBatchPlanResult",
    "JudgePlanResult",
    "plan_all_chapter_judge_jobs",
    "plan_chapter_judge_job",
    "plan_dossier_jobs",
    "plan_single_dossier_job",
]
