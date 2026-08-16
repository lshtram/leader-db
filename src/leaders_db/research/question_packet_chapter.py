"""Straight-through chapter writing and review from trusted question packets."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path

from .chapter_analysis_models import ResolvedChapterAnalysis
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
)
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_quality import (
    run_blind_question_quality_review,
    validate_blind_review_artifacts,
)
from .question_packet_writer import (
    DiagnosticQuestionAnswer,
    build_question_writer_prompt,
    load_normalized_question_answer,
    validate_question_answer,
    write_diagnostic_question_answer,
)


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
) -> Path:
    """Review each completed question once in a phase separate from writing."""

    _require_unused_output_dir(output_dir)
    writing_path = writing_dir / "writing-manifest.json"
    writing = validate_chapter_question_writing(
        project_root=project_root,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=approved_analysis_path,
        profile_name=writing_profile_name,
        profiles_path=profiles_path,
    )
    analysis = _load_approved_analysis(package, approved_analysis_path)
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
        answer_path = _inside(writing_dir, written.artifact_path)
        if _sha256(answer_path) != written.artifact_sha256:
            raise ValueError("written question answer changed after the writing phase")
        packet = packets[written.question_id]
        answer = DiagnosticQuestionAnswer.model_validate_json(answer_path.read_text())
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
        if review["quality_gate"] != "pass":
            raise RuntimeError(f"question review failed its quality gate: {written.question_id}")
    passed = all(item.status == "pass" for item in artifacts)
    manifest = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_review_v1",
        chapter_id=package.chapter_id,
        profile=profile_name,
        model=model,
        package_sha256=_payload_hash(package.model_dump(mode="json")),
        profile_config_sha256=profile_hash,
        prompt_config_sha256=prompt_hash,
        approved_analysis_sha256=analysis_hash,
        writing_manifest_sha256=_sha256(writing_path),
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
) -> tuple[Path, ...]:
    """Review chapters concurrently and prohibit calls after a material failure."""

    if not packages or max_workers < 1:
        raise ValueError("concurrent chapter review requires packages and workers")
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


def validate_chapter_question_writing(
    *,
    project_root: Path,
    package: ChapterQuestionEvidencePackage,
    output_dir: Path,
    approved_analysis_path: Path,
    profile_name: str,
    profiles_path: Path,
) -> ChapterQuestionPhaseManifest:
    """Reload a writing phase and verify its exact inputs and child answers."""

    manifest = ChapterQuestionPhaseManifest.model_validate_json(
        (output_dir / "writing-manifest.json").read_text()
    )
    analysis = _load_approved_analysis(package, approved_analysis_path)
    predecessor = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    model, profile_hash, _ = _configuration_binding(project_root, profile_name, profiles_path)
    if (
        manifest.schema_version != "diagnostic_chapter_question_writing_v1"
        or manifest.chapter_id != package.chapter_id
        or manifest.profile != profile_name
        or manifest.model != model
        or manifest.package_sha256 != _payload_hash(package.model_dump(mode="json"))
        or manifest.profile_config_sha256 != profile_hash
        or manifest.approved_analysis_sha256 != _sha256(approved_analysis_path)
        or manifest.writing_manifest_sha256 is not None
        or manifest.phase_gate != "pass"
    ):
        raise ValueError("chapter writing manifest does not match current inputs")
    packets = {item.question_id: item for item in package.packets}
    prompts, _ = load_question_packet_prompts(project_root / "configs/question-packet-prompts.yaml")
    for artifact in manifest.artifacts:
        path = _inside(output_dir, artifact.artifact_path)
        packet = packets[artifact.question_id]
        answer = (
            load_normalized_question_answer(packet, path.parent)
            if path.name == "accepted-output.json"
            else DiagnosticQuestionAnswer.model_validate_json(path.read_text())
        )
        expected_prompt = build_question_writer_prompt(
            packet, prompts, predecessor[artifact.question_id]
        )
        if (path.parent / "prompt.txt").read_bytes() != expected_prompt.encode():
            raise ValueError("saved question-writer prompt differs from current writer input")
        if _sha256(path) != artifact.artifact_sha256 or (
            validate_question_answer(packet, answer)["functional_gate"] != "pass"
        ):
            raise ValueError("chapter writing child artifact is invalid")
    return manifest


def validate_chapter_question_review(
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
) -> ChapterQuestionPhaseManifest:
    """Reload a review phase and reconstruct its result from trusted children."""

    actual = ChapterQuestionPhaseManifest.model_validate_json(
        (output_dir / "review-manifest.json").read_text()
    )
    writing_path = writing_dir / "writing-manifest.json"
    writing = validate_chapter_question_writing(
        project_root=project_root,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=approved_analysis_path,
        profile_name=writing_profile_name,
        profiles_path=profiles_path,
    )
    analysis_hash = _sha256(approved_analysis_path)
    if analysis_hash != package.selected_analysis_sha256:
        raise ValueError("approved analysis hash does not match the question package")
    analysis = ResolvedChapterAnalysis.model_validate_json(approved_analysis_path.read_text())
    approved = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    packets = {item.question_id: item for item in package.packets}
    artifacts = []
    for written in writing.artifacts:
        answer = DiagnosticQuestionAnswer.model_validate_json(
            _inside(writing_dir, written.artifact_path).read_text()
        )
        review_dir = output_dir / "questions" / written.question_id
        review = validate_blind_review_artifacts(
            packet=packets[written.question_id],
            approved_answer=approved[written.question_id],
            experimental_answer=answer,
            output_dir=review_dir,
            project_root=project_root,
            profile_name=profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
        )
        child = review_dir / "blind-review-manifest.json"
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=written.question_id,
                artifact_path=str(child.relative_to(output_dir)),
                artifact_sha256=_sha256(child),
                status=review["quality_gate"],
            )
        )
    model, profile_hash, prompt_hash = _configuration_binding(
        project_root, profile_name, profiles_path
    )
    expected = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_review_v1",
        chapter_id=package.chapter_id,
        profile=profile_name,
        model=model,
        package_sha256=_payload_hash(package.model_dump(mode="json")),
        profile_config_sha256=profile_hash,
        prompt_config_sha256=prompt_hash,
        approved_analysis_sha256=analysis_hash,
        writing_manifest_sha256=_sha256(writing_path),
        question_count=10,
        artifacts=tuple(artifacts),
        phase_gate=("pass" if all(item.status == "pass" for item in artifacts) else "fail"),
    )
    if actual != expected:
        raise ValueError("chapter review manifest differs from trusted child reviews")
    return actual


def _write_manifest(output_dir: Path, name: str, manifest: ChapterQuestionPhaseManifest) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return path


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _configuration_binding(
    project_root: Path, profile_name: str, profiles_path: Path
) -> tuple[str, str, str]:
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("chapter question phases require the OpenAI Codex subscription")
    _, prompt_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    return profile.model, _sha256(profiles_path), prompt_hash


def _load_approved_analysis(
    package: ChapterQuestionEvidencePackage, path: Path
) -> ResolvedChapterAnalysis:
    if _sha256(path) != package.selected_analysis_sha256:
        raise ValueError("approved analysis hash does not match the question package")
    analysis = ResolvedChapterAnalysis.model_validate_json(path.read_text())
    expected = {f"{package.chapter_id}.{number}" for number in range(1, 11)}
    actual = [item.question_id for item in analysis.answers]
    if (
        analysis.chapter_id != package.chapter_id
        or len(actual) != len(set(actual))
        or set(actual) != expected
    ):
        raise ValueError("approved analysis must contain the chapter's ten questions")
    return analysis


def _require_unused_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("chapter phase output directory is already in use")


def _inside(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError("chapter artifact path escapes its phase directory")
    return path


__all__ = [
    "ChapterQuestionPhaseManifest",
    "run_all_chapter_question_review",
    "run_all_chapter_question_writing",
    "run_chapter_question_review",
    "run_chapter_question_writing",
]
