"""Capability-bound execution for a preflighted question-review ruler phase."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .control_flow import load_question_review_experiment_policy
from .model_call_budget import load_stage_budget_tracker
from .model_call_coordinator import ModelCallCoordinator
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter import (
    run_chapter_question_review,
    validate_chapter_question_writing,
)
from .question_packet_phase_validation import load_approved_analysis, sha256_file
from .question_packet_prompts import load_question_packet_prompts
from .question_phase_import import QuestionPhaseImportPreflight, _construct_preflight
from .question_review_preflight import (
    build_question_review_preflight_manifest,
    load_review_input_snapshot,
)
from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

_REVIEW_AUTHORIZATION_CAPABILITY = object()


@dataclass(frozen=True)
class QuestionReviewAuthorization:
    preflight_path: Path
    preflight_sha256: str
    run_dir: Path
    ruler_id: str
    chapter_ids: tuple[str, ...]
    request_sha256s: frozenset[str]
    limits: dict[str, int]
    profile_name: str
    profiles_path: Path
    profiles_sha256: str
    reasoning_effort: str
    experiment_policy_path: Path
    experiment_policy_sha256: str
    _capability: object


def load_question_review_authorization(
    *,
    project_root: Path,
    run_dir: Path,
    ruler_id: str,
    packages: tuple[ChapterQuestionEvidencePackage, ...],
    approved_analysis_paths: dict[str, Path],
    preflight_path: Path,
    cohort_preflight_path: Path,
    import_preflight_path: Path,
    source_run: Path,
    cohort_packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    cohort_approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    reasoning_effort: str,
    approved_limits: dict[str, int],
    profiles_path: Path,
    experiment_policy_path: Path,
) -> QuestionReviewAuthorization:
    """Reconstruct an eligible preflight and issue its exact launch capability."""

    if (
        cohort_preflight_path.resolve() != (run_dir / "cohort-preflight.json").resolve()
        or import_preflight_path.resolve()
        != (run_dir / "preflight/question-phase-import.json").resolve()
    ):
        raise ValueError("question review authorization requires canonical lineage inputs")
    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    saved_import = QuestionPhaseImportPreflight.model_validate_json(
        import_preflight_path.read_bytes()
    )
    expected_import = _construct_preflight(
        project_root=project_root,
        source_run=source_run,
        target_run=run_dir,
        packages=cohort_packages,
        approved_analysis_paths=cohort_approved_analysis_paths,
        profile_name=profile_name,
        writing_profile_name=writing_profile_name,
        profiles_path=profiles_path,
        experiment_policy_path=experiment_policy_path,
    )
    if saved_import != expected_import or saved_import.status != "eligible":
        raise ValueError("question review authorization import differs from reconstruction")
    required_chapters = tuple(
        row.chapter_id
        for row in saved_import.rows
        if row.ruler_id == ruler_id and row.review_action == "execute"
    )
    supplied_chapters = tuple(package.chapter_id for package in packages)
    if not required_chapters or supplied_chapters != required_chapters:
        raise ValueError("question review authorization requires the exact import remainder")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    prompts, prompt_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    policy = load_question_review_experiment_policy(experiment_policy_path)
    stage = load_stage_budget_tracker(
        project_root / "configs/research-stage-budgets.yaml", "question_review"
    ).budget
    analyses = {
        package.chapter_id: load_approved_analysis(
            package, approved_analysis_paths[package.chapter_id]
        )
        for package in packages
    }
    snapshots = tuple(
        load_review_input_snapshot(
            run_dir / f"model-output/{ruler_id}/question-writing/{package.chapter_id}",
            validate_chapter_question_writing(
                project_root=project_root,
                package=package,
                output_dir=(
                    run_dir
                    / f"model-output/{ruler_id}/question-writing/{package.chapter_id}"
                ),
                approved_analysis_path=approved_analysis_paths[package.chapter_id],
                profile_name=profile_name,
                profiles_path=profiles_path,
            ),
        )
        for package in packages
    )
    scratch = preflight_path.with_name(f".{preflight_path.name}.trusted-reconstruction")
    try:
        build_question_review_preflight_manifest(
            run_dir=run_dir,
            packages=packages,
            approved_analyses=analyses,
            snapshots=snapshots,
            prompts=prompts,
            profile_name=profile_name,
            profile=profile,
            reasoning_effort=reasoning_effort,
            stage_budget=stage,
            run_limits=approved_limits,
            run_ledger=(),
            input_bindings={
                "cohort_preflight_sha256": sha256_file(cohort_preflight_path),
                "import_preflight_sha256": sha256_file(import_preflight_path),
                "prompt_config_sha256": prompt_hash,
            },
            output_path=scratch,
            downstream_roots=tuple(
                run_dir
                / f"model-output/{ruler_id}/question-review/{package.chapter_id}"
                for package in packages
            ),
            experiment_policy=policy,
        )
        expected = json.loads(scratch.read_text(encoding="utf-8"))
    finally:
        scratch.unlink(missing_ok=True)
    if saved != expected or saved.get("status") != "eligible":
        raise ValueError("question review preflight differs from trusted reconstruction")
    return QuestionReviewAuthorization(
        preflight_path=preflight_path,
        preflight_sha256=sha256_file(preflight_path),
        run_dir=run_dir,
        ruler_id=ruler_id,
        chapter_ids=tuple(package.chapter_id for package in packages),
        request_sha256s=frozenset(
            item["complete_request_sha256"] for item in saved["requests"]
        ),
        limits={
            "maximum_calls": int(approved_limits["max_calls"]),
            "maximum_input_tokens": int(approved_limits["max_input_tokens"]),
            "maximum_output_tokens": int(approved_limits["max_output_tokens"]),
        },
        profile_name=profile_name,
        profiles_path=profiles_path,
        profiles_sha256=sha256_file(profiles_path),
        reasoning_effort=reasoning_effort,
        experiment_policy_path=experiment_policy_path,
        experiment_policy_sha256=sha256_file(experiment_policy_path),
        _capability=_REVIEW_AUTHORIZATION_CAPABILITY,
    )


def run_authorized_question_reviews(
    *,
    authorization: QuestionReviewAuthorization,
    project_root: Path,
    packages: tuple[ChapterQuestionEvidencePackage, ...],
    approved_analysis_paths: dict[str, Path],
) -> tuple[Path, ...]:
    """Run all eight chapters using only the capability's request inventory and limits."""

    if authorization._capability is not _REVIEW_AUTHORIZATION_CAPABILITY:
        raise ValueError("question review execution lacks trusted authorization")
    if (
        sha256_file(authorization.preflight_path) != authorization.preflight_sha256
        or sha256_file(authorization.profiles_path) != authorization.profiles_sha256
        or sha256_file(authorization.experiment_policy_path)
        != authorization.experiment_policy_sha256
    ):
        raise ValueError("question review authorization input changed before execution")
    chapter_ids = tuple(package.chapter_id for package in packages)
    canonical = tuple(f"{number}B" for number in range(1, 9))
    if chapter_ids != authorization.chapter_ids or chapter_ids != tuple(
        chapter for chapter in canonical if chapter in set(chapter_ids)
    ):
        raise ValueError("question review authorization requires its exact ordered chapters")
    limits = RunUsageLimits(
        max_calls=authorization.limits["maximum_calls"],
        max_input_tokens=authorization.limits["maximum_input_tokens"],
        max_output_tokens=authorization.limits["maximum_output_tokens"],
    )
    tracker = RunUsageBudgetTracker(
        ledger_path=authorization.run_dir
        / f"stage-budgets/{authorization.ruler_id}-question-review-usage.json",
        limits=limits,
        config_sha256=authorization.preflight_sha256,
        allowed_request_sha256s=authorization.request_sha256s,
    )
    policy = load_question_review_experiment_policy(
        authorization.experiment_policy_path
    )
    policy_hash = sha256_file(authorization.experiment_policy_path)
    coordinator = ModelCallCoordinator()
    results = []
    for package in packages:
        results.append(
            run_chapter_question_review(
                project_root=project_root,
                package=package,
                approved_analysis_path=approved_analysis_paths[package.chapter_id],
                writing_dir=authorization.run_dir
                / (
                    f"model-output/{authorization.ruler_id}/question-writing/"
                    f"{package.chapter_id}"
                ),
                output_dir=authorization.run_dir
                / (
                    f"model-output/{authorization.ruler_id}/question-review/"
                    f"{package.chapter_id}"
                ),
                profile_name=authorization.profile_name,
                writing_profile_name=authorization.profile_name,
                profiles_path=authorization.profiles_path,
                reasoning_effort=authorization.reasoning_effort,
                call_coordinator=coordinator,
                run_budget_tracker=tracker,
                experiment_policy=policy,
                experiment_policy_sha256=policy_hash,
            )
        )
    return tuple(results)


__all__ = [
    "QuestionReviewAuthorization",
    "load_question_review_authorization",
    "run_authorized_question_reviews",
]
