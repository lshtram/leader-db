"""Straight-through chapter writing and review from trusted question packets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .control_flow import (
    QuestionReviewExperimentPolicy,
    load_question_review_experiment_policy,
)
from .corpus_reader_runner import ModelCallCoordinator
from .model_call_budget import (
    RunUsageBudgetTracker,
    load_stage_budget_tracker,
    resolve_integrated_run_budget,
)
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import (
    ChapterQuestionArtifact,
    ChapterQuestionPhaseManifest,
    QuestionEvidenceUnavailableAdjudication,
    QuestionResearchInventory,
    QuestionTargetedSearchManifest,
    QuestionUnavailableArtifact,
    QuestionUnavailableIndependentReview,
)
from .question_packet_phase_validation import (
    configuration_binding as _configuration_binding,
)
from .question_packet_phase_validation import inside as _inside
from .question_packet_phase_validation import (
    load_approved_analysis as _load_approved_analysis,
)
from .question_packet_phase_validation import (
    payload_hash as _payload_hash,
)
from .question_packet_phase_validation import (
    sha256_file as _sha256,
)
from .question_packet_phase_validation import (
    validate_chapter_question_review as _validate_chapter_question_review,
)
from .question_packet_phase_validation import (
    validate_chapter_question_writing as _validate_chapter_question_writing,
)
from .question_packet_quality import (
    run_blind_question_quality_review,
    validate_blind_review_artifacts,
)
from .question_packet_writer import (
    build_question_writer_prompt,
    validate_question_answer,
    write_diagnostic_question_answer,
)
from .question_review_preflight import (
    QuestionReviewInputSnapshot,
    load_review_input_snapshot,
    require_trusted_snapshot,
    stop_for_reopen_requests,
)

_UNAVAILABLE_REVIEW_CAPABILITY = object()


@dataclass(frozen=True)
class TrustedUnavailableAdjudication:
    """Capability issued only after deterministic independent-input validation."""

    path: Path
    artifact: QuestionEvidenceUnavailableAdjudication
    _capability: object


def run_chapter_question_writing(
    *,
    project_root: Path,
    package: ChapterQuestionEvidencePackage,
    output_dir: Path,
    approved_analysis_path: Path,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    unavailable_adjudications: dict[str, TrustedUnavailableAdjudication] | None = None,
) -> Path:
    """Write each chapter question once and stop on the first invalid result."""

    _require_unused_output_dir(output_dir)
    analysis = _load_approved_analysis(package, approved_analysis_path)
    predecessor = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    model, profile_hash, prompt_hash = _configuration_binding(
        project_root, profile_name, profiles_path
    )
    artifacts = []
    budget = load_stage_budget_tracker(
        project_root / "configs/research-stage-budgets.yaml", "question_writer"
    )
    for packet in sorted(package.packets, key=lambda item: int(item.question_id.rsplit(".", 1)[1])):
        question_dir = output_dir / "questions" / packet.question_id
        empty_packet = (
            getattr(packet, "candidate_index", None) == ()
            and not packet.coverage.required_evidence_ids
        )
        if empty_packet:
            trusted_adjudication = (unavailable_adjudications or {}).get(packet.question_id)
            if trusted_adjudication is None:
                raise ValueError(
                    f"{packet.question_id} has no evidence and no trusted saturation adjudication"
                )
            require_trusted_unavailable_adjudication(trusted_adjudication)
            adjudication_path = trusted_adjudication.path
            current = load_trusted_unavailable_adjudication(
                project_root=project_root,
                path=adjudication_path,
                packet=packet,
            )
            if current.artifact != trusted_adjudication.artifact:
                raise ValueError("trusted unavailable adjudication changed before execution")
            question_dir.mkdir(parents=True, exist_ok=False)
            unavailable_path = question_dir / "unavailable.json"
            unavailable_path.write_text(
                QuestionUnavailableArtifact(
                    question_id=packet.question_id,
                    packet_sha256=_payload_hash(packet.model_dump(mode="json")),
                    adjudication_path=str(adjudication_path.resolve().relative_to(project_root.resolve())),
                    adjudication_sha256=_sha256(adjudication_path),
                ).model_dump_json(indent=2)
                + "\n",
                encoding="utf-8",
            )
            artifacts.append(
                ChapterQuestionArtifact(
                    question_id=packet.question_id,
                    artifact_path=str(unavailable_path.relative_to(output_dir)),
                    artifact_sha256=_sha256(unavailable_path),
                    status="unavailable",
                )
            )
            continue
        write_diagnostic_question_answer(
            project_root=project_root,
            packet=packet,
            output_dir=question_dir,
            profile_name=profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
            predecessor_answer=predecessor[packet.question_id],
            budget_tracker=budget,
            call_coordinator=call_coordinator,
            run_budget_tracker=run_budget_tracker,
        )
        accepted_path = question_dir / "accepted-output.json"
        answer_path = accepted_path if accepted_path.is_file() else question_dir / "output.json"
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=packet.question_id,
                artifact_path=str(answer_path.relative_to(output_dir)),
                artifact_sha256=_sha256(answer_path),
                status="pass",
            )
        )
    manifest = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_writing_v1",
        chapter_id=package.chapter_id,
        profile=profile_name,
        model=model,
        package_sha256=_payload_hash(package.model_dump(mode="json")),
        profile_config_sha256=profile_hash,
        prompt_config_sha256=prompt_hash,
        approved_analysis_sha256=_sha256(approved_analysis_path),
        question_count=len(artifacts),
        artifacts=tuple(artifacts),
        phase_gate="pass",
    )
    return _write_manifest(output_dir, "writing-manifest.json", manifest)


def run_all_chapter_question_writing(
    *,
    project_root: Path,
    packages: tuple[ChapterQuestionEvidencePackage, ...],
    output_root: Path,
    approved_analysis_paths: dict[str, Path],
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str | None = None,
    max_workers: int = 8,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    unavailable_adjudications: dict[str, TrustedUnavailableAdjudication] | None = None,
) -> tuple[Path, ...]:
    """Run chapters concurrently and stop new calls after one material failure."""

    if not packages or max_workers < 1:
        raise ValueError("concurrent chapter writing requires packages and workers")
    chapter_ids = [package.chapter_id for package in packages]
    if len(chapter_ids) != len(set(chapter_ids)) or set(chapter_ids) != set(
        approved_analysis_paths
    ):
        raise ValueError("chapter packages and approved analyses must match exactly")
    run_budget_tracker = resolve_integrated_run_budget(output_root, run_budget_tracker)
    if run_budget_tracker is not None:
        model = load_research_model_profiles(profiles_path).profiles[profile_name].model
        max_workers = min(max_workers, run_budget_tracker.safe_parallel_calls(model))
    coordinator = ModelCallCoordinator()

    def run(package: ChapterQuestionEvidencePackage) -> Path:
        return run_chapter_question_writing(
            project_root=project_root,
            package=package,
            output_dir=output_root / package.chapter_id,
            approved_analysis_path=approved_analysis_paths[package.chapter_id],
            profile_name=profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
            call_coordinator=coordinator,
            run_budget_tracker=run_budget_tracker,
            unavailable_adjudications=unavailable_adjudications,
        )

    results: list[Path] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(packages))) as executor:
        futures = {executor.submit(run, package): package.chapter_id for package in packages}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # collect after all in-flight calls have settled
                coordinator.publish_failure()
                failures.append(exc)
    if failures:
        raise RuntimeError(
            f"chapter writing stopped after material failure: {failures[0]}"
        ) from failures[0]
    return tuple(sorted(results))


def load_trusted_unavailable_adjudication(
    *, project_root: Path, path: Path, packet
) -> TrustedUnavailableAdjudication:
    root = project_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("unavailable adjudication must remain inside the project")
    item = QuestionEvidenceUnavailableAdjudication.model_validate_json(
        resolved.read_text(encoding="utf-8")
    )
    packet_hash = _payload_hash(packet.model_dump(mode="json"))
    if item.question_id != packet.question_id or item.packet_sha256 != packet_hash:
        raise ValueError("unavailable adjudication differs from the exact question packet")
    inventory_path = (root / item.research_inventory_path).resolve()
    search_path = (root / item.targeted_search_manifest_path).resolve()
    review_path = (root / item.independent_review_path).resolve()
    if (
        not inventory_path.is_relative_to(root)
        or not search_path.is_relative_to(root)
        or not review_path.is_relative_to(root)
        or _sha256(inventory_path) != item.research_inventory_sha256
        or _sha256(search_path) != item.targeted_search_manifest_sha256
        or _sha256(review_path) != item.independent_review_sha256
    ):
        raise ValueError("unavailable adjudication dependency is missing or differs")
    inventory = QuestionResearchInventory.model_validate_json(
        inventory_path.read_text(encoding="utf-8")
    )
    search = QuestionTargetedSearchManifest.model_validate_json(
        search_path.read_text(encoding="utf-8")
    )
    review = QuestionUnavailableIndependentReview.model_validate_json(
        review_path.read_text(encoding="utf-8")
    )
    if (
        inventory.question_id != packet.question_id
        or search.question_id != packet.question_id
        or len(search.queries) != item.targeted_query_count
        or len(search.inspected_urls) != item.inspected_source_count
        or set(inventory.source_ids) != set(search.inspected_urls)
        or review.question_id != packet.question_id
        or review.research_inventory_sha256 != item.research_inventory_sha256
        or review.targeted_search_manifest_sha256
        != item.targeted_search_manifest_sha256
    ):
        raise ValueError("unavailable adjudication does not reconcile its search inventory")
    return TrustedUnavailableAdjudication(
        path=resolved, artifact=item, _capability=_UNAVAILABLE_REVIEW_CAPABILITY
    )


def require_trusted_unavailable_adjudication(
    item: TrustedUnavailableAdjudication,
) -> None:
    if item._capability is not _UNAVAILABLE_REVIEW_CAPABILITY:
        raise ValueError("unavailable adjudication lacks trusted review capability")


def validate_chapter_question_writing(**kwargs) -> ChapterQuestionPhaseManifest:
    """Validate writing while preserving the original patchable facade hooks."""

    return _validate_chapter_question_writing(
        **kwargs,
        question_validator=validate_question_answer,
        prompt_builder=build_question_writer_prompt,
    )


def validate_chapter_question_review(**kwargs) -> ChapterQuestionPhaseManifest:
    """Validate review while preserving the original patchable facade hooks."""

    return _validate_chapter_question_review(
        **kwargs,
        blind_review_validator=validate_blind_review_artifacts,
        question_validator=validate_question_answer,
        prompt_builder=build_question_writer_prompt,
    )


def run_chapter_question_review(
    *,
    project_root: Path,
    package: ChapterQuestionEvidencePackage,
    approved_analysis_path: Path,
    writing_dir: Path,
    output_dir: Path,
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    reasoning_effort: str | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    input_snapshot: QuestionReviewInputSnapshot | None = None,
    experiment_policy: QuestionReviewExperimentPolicy | None = None,
    experiment_policy_sha256: str | None = None,
) -> Path:
    """Review each completed question once in a phase separate from writing."""

    _require_unused_output_dir(output_dir)
    if (experiment_policy is None) != (experiment_policy_sha256 is None):
        raise ValueError("review experiment policy and hash must be supplied together")
    collect_quality_failures = experiment_policy is not None
    analysis = _load_approved_analysis(package, approved_analysis_path)
    if input_snapshot is None:
        writing = validate_chapter_question_writing(
            project_root=project_root,
            package=package,
            output_dir=writing_dir,
            approved_analysis_path=approved_analysis_path,
            profile_name=writing_profile_name,
            profiles_path=profiles_path,
        )
        input_snapshot = load_review_input_snapshot(writing_dir, writing)
    else:
        require_trusted_snapshot(input_snapshot)
        writing = input_snapshot.writing
        if writing.chapter_id != package.chapter_id or input_snapshot.writing_dir != writing_dir:
            raise ValueError("review input snapshot differs from its chapter invocation")
    if (
        experiment_policy is None
        or experiment_policy.writer_reopen_behavior == "stop_before_review"
    ):
        stop_for_reopen_requests(output_dir, (input_snapshot,))
    trusted_answers = input_snapshot.answers
    analysis_hash = _sha256(approved_analysis_path)
    model, profile_hash, prompt_hash = _configuration_binding(
        project_root, profile_name, profiles_path
    )
    approved_by_id = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    packets = {item.question_id: item for item in package.packets}
    artifacts = []
    budget = load_stage_budget_tracker(
        project_root / "configs/research-stage-budgets.yaml", "question_review"
    )
    for written in writing.artifacts:
        if written.status == "unavailable":
            source = writing_dir / written.artifact_path
            review_dir = output_dir / "questions" / written.question_id
            review_dir.mkdir(parents=True, exist_ok=False)
            target = review_dir / "unavailable.json"
            target.write_bytes(source.read_bytes())
            artifacts.append(
                ChapterQuestionArtifact(
                    question_id=written.question_id,
                    artifact_path=str(target.relative_to(output_dir)),
                    artifact_sha256=_sha256(target),
                    status="unavailable",
                )
            )
            continue
        packet = packets[written.question_id]
        answer = trusted_answers[written.question_id]
        review_dir = output_dir / "questions" / written.question_id
        run_blind_question_quality_review(
            project_root=project_root,
            packet=packet,
            approved_answer=approved_by_id[written.question_id],
            experimental_answer=answer,
            output_dir=review_dir,
            profile_name=profile_name,
            profiles_path=profiles_path,
            budget_tracker=budget,
            reasoning_effort=reasoning_effort,
            call_coordinator=call_coordinator,
            run_budget_tracker=run_budget_tracker,
            publish_quality_failure=not collect_quality_failures,
        )
        review = validate_blind_review_artifacts(
            packet=packet,
            approved_answer=approved_by_id[written.question_id],
            experimental_answer=answer,
            output_dir=review_dir,
            project_root=project_root,
            profile_name=profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
        )
        manifest_path = review_dir / "blind-review-manifest.json"
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=written.question_id,
                artifact_path=str(manifest_path.relative_to(output_dir)),
                artifact_sha256=_sha256(manifest_path),
                status=review["quality_gate"],
            )
        )
        if review["quality_gate"] != "pass" and not collect_quality_failures:
            raise RuntimeError(f"question review failed its quality gate: {written.question_id}")
    passed = all(item.status in {"pass", "unavailable"} for item in artifacts)
    manifest = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_review_v1",
        chapter_id=package.chapter_id,
        profile=profile_name,
        model=model,
        package_sha256=_payload_hash(package.model_dump(mode="json")),
        profile_config_sha256=profile_hash,
        prompt_config_sha256=prompt_hash,
        approved_analysis_sha256=analysis_hash,
        writing_manifest_sha256=input_snapshot.writing_manifest_sha256,
        experiment_policy_sha256=experiment_policy_sha256,
        question_count=len(artifacts),
        artifacts=tuple(artifacts),
        phase_gate="pass" if passed else "fail",
    )
    return _write_manifest(output_dir, "review-manifest.json", manifest)


def run_all_chapter_question_review(
    *,
    project_root: Path,
    packages: tuple[ChapterQuestionEvidencePackage, ...],
    approved_analysis_paths: dict[str, Path],
    writing_root: Path,
    output_root: Path,
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    reasoning_effort: str | None = None,
    max_workers: int = 8,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    experiment_policy_path: Path | None = None,
) -> tuple[Path, ...]:
    """Review chapters concurrently and prohibit calls after a material failure."""

    if not packages or max_workers < 1:
        raise ValueError("concurrent chapter review requires packages and workers")
    _require_unused_output_dir(output_root)
    chapter_ids = [package.chapter_id for package in packages]
    if len(chapter_ids) != len(set(chapter_ids)) or set(chapter_ids) != set(
        approved_analysis_paths
    ):
        raise ValueError("chapter packages and approved analyses must match exactly")
    run_budget_tracker = resolve_integrated_run_budget(output_root, run_budget_tracker)
    if run_budget_tracker is not None:
        model = load_research_model_profiles(profiles_path).profiles[profile_name].model
        max_workers = min(max_workers, run_budget_tracker.safe_parallel_calls(model))
    coordinator = ModelCallCoordinator()
    experiment_policy = (
        load_question_review_experiment_policy(experiment_policy_path)
        if experiment_policy_path is not None
        else None
    )
    experiment_policy_sha256 = (
        _sha256(experiment_policy_path) if experiment_policy_path is not None else None
    )
    snapshots = tuple(
        load_review_input_snapshot(
            writing_root / package.chapter_id,
            validate_chapter_question_writing(
                project_root=project_root,
                package=package,
                output_dir=writing_root / package.chapter_id,
                approved_analysis_path=approved_analysis_paths[package.chapter_id],
                profile_name=writing_profile_name,
                profiles_path=profiles_path,
            ),
        )
        for package in packages
    )
    if (
        experiment_policy is None
        or experiment_policy.writer_reopen_behavior == "stop_before_review"
    ):
        stop_for_reopen_requests(output_root, snapshots)
    snapshots_by_chapter = {item.writing.chapter_id: item for item in snapshots}

    def run(package: ChapterQuestionEvidencePackage) -> Path:
        return run_chapter_question_review(
            project_root=project_root,
            package=package,
            approved_analysis_path=approved_analysis_paths[package.chapter_id],
            writing_dir=writing_root / package.chapter_id,
            output_dir=output_root / package.chapter_id,
            profile_name=profile_name,
            writing_profile_name=writing_profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
            call_coordinator=coordinator,
            run_budget_tracker=run_budget_tracker,
            input_snapshot=snapshots_by_chapter[package.chapter_id],
            experiment_policy=experiment_policy,
            experiment_policy_sha256=experiment_policy_sha256,
        )

    results: list[Path] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(packages))) as executor:
        futures = {executor.submit(run, package): package.chapter_id for package in packages}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # collect after all in-flight calls have settled
                coordinator.publish_failure()
                failures.append(exc)
    if failures:
        raise RuntimeError(
            f"chapter review stopped after material failure: {failures[0]}"
        ) from failures[0]
    return tuple(sorted(results))


def _write_manifest(output_dir: Path, name: str, manifest: ChapterQuestionPhaseManifest) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return path


def _require_unused_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("chapter phase output directory is already in use")


__all__ = [
    "ChapterQuestionPhaseManifest",
    "_inside",
    "run_all_chapter_question_review",
    "run_all_chapter_question_writing",
    "run_chapter_question_review",
    "run_chapter_question_writing",
    "validate_chapter_question_review",
    "validate_chapter_question_writing",
]
