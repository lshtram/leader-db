"""Validation and input binding for chapter question phases."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .chapter_analysis_models import ResolvedChapterAnalysis
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import (
    ChapterQuestionArtifact,
    ChapterQuestionPhaseManifest,
)
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_quality import validate_blind_review_artifacts
from .question_packet_writer import (
    DiagnosticQuestionAnswer,
    build_question_writer_prompt,
    load_normalized_question_answer,
    validate_question_answer,
)
from .question_review_preflight import load_review_input_snapshot


def validate_chapter_question_writing(
    *,
    project_root: Path,
    package: ChapterQuestionEvidencePackage,
    output_dir: Path,
    approved_analysis_path: Path,
    profile_name: str,
    profiles_path: Path,
    question_validator=validate_question_answer,
    prompt_builder=build_question_writer_prompt,
) -> ChapterQuestionPhaseManifest:
    """Reload a writing phase and verify its exact inputs and child answers."""

    manifest = ChapterQuestionPhaseManifest.model_validate_json(
        (output_dir / "writing-manifest.json").read_text()
    )
    analysis = load_approved_analysis(package, approved_analysis_path)
    predecessor = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    model, profile_hash, _ = configuration_binding(project_root, profile_name, profiles_path)
    if (
        manifest.schema_version != "diagnostic_chapter_question_writing_v1"
        or manifest.chapter_id != package.chapter_id
        or manifest.profile != profile_name
        or manifest.model != model
        or manifest.package_sha256 != payload_hash(package.model_dump(mode="json"))
        or manifest.profile_config_sha256 != profile_hash
        or manifest.approved_analysis_sha256 != sha256_file(approved_analysis_path)
        or manifest.writing_manifest_sha256 is not None
        or manifest.phase_gate != "pass"
    ):
        raise ValueError("chapter writing manifest does not match current inputs")
    packets = {item.question_id: item for item in package.packets}
    prompts, _ = load_question_packet_prompts(project_root / "configs/question-packet-prompts.yaml")
    for artifact in manifest.artifacts:
        path = inside(output_dir, artifact.artifact_path)
        packet = packets[artifact.question_id]
        answer = (
            load_normalized_question_answer(packet, path.parent)
            if path.name == "accepted-output.json"
            else DiagnosticQuestionAnswer.model_validate_json(path.read_text())
        )
        expected_prompt = prompt_builder(
            packet, prompts, predecessor[artifact.question_id]
        )
        if (path.parent / "prompt.txt").read_bytes() != expected_prompt.encode():
            raise ValueError("saved question-writer prompt differs from current writer input")
        if sha256_file(path) != artifact.artifact_sha256 or (
            question_validator(packet, answer)["functional_gate"] != "pass"
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
    blind_review_validator=validate_blind_review_artifacts,
    question_validator=validate_question_answer,
    prompt_builder=build_question_writer_prompt,
) -> ChapterQuestionPhaseManifest:
    """Reload a review phase and reconstruct its result from trusted children."""

    actual = ChapterQuestionPhaseManifest.model_validate_json(
        (output_dir / "review-manifest.json").read_text()
    )
    writing = validate_chapter_question_writing(
        project_root=project_root,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=approved_analysis_path,
        profile_name=writing_profile_name,
        profiles_path=profiles_path,
        question_validator=question_validator,
        prompt_builder=prompt_builder,
    )
    snapshot = load_review_input_snapshot(writing_dir, writing)
    if any(answer.reopen_requests for answer in snapshot.answers.values()):
        raise ValueError("question review cannot consume unresolved writer reopen requests")
    analysis_hash = sha256_file(approved_analysis_path)
    if analysis_hash != package.selected_analysis_sha256:
        raise ValueError("approved analysis hash does not match the question package")
    analysis = ResolvedChapterAnalysis.model_validate_json(approved_analysis_path.read_text())
    approved = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    packets = {item.question_id: item for item in package.packets}
    artifacts = []
    for written in writing.artifacts:
        answer = snapshot.answers[written.question_id]
        review_dir = output_dir / "questions" / written.question_id
        review = blind_review_validator(
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
                artifact_sha256=sha256_file(child),
                status=review["quality_gate"],
            )
        )
    model, profile_hash, prompt_hash = configuration_binding(
        project_root, profile_name, profiles_path
    )
    expected = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_review_v1",
        chapter_id=package.chapter_id,
        profile=profile_name,
        model=model,
        package_sha256=payload_hash(package.model_dump(mode="json")),
        profile_config_sha256=profile_hash,
        prompt_config_sha256=prompt_hash,
        approved_analysis_sha256=analysis_hash,
        writing_manifest_sha256=snapshot.writing_manifest_sha256,
        question_count=10,
        artifacts=tuple(artifacts),
        phase_gate=("pass" if all(item.status == "pass" for item in artifacts) else "fail"),
    )
    if actual != expected:
        raise ValueError("chapter review manifest differs from trusted child reviews")
    return actual




def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def configuration_binding(
    project_root: Path, profile_name: str, profiles_path: Path
) -> tuple[str, str, str]:
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("chapter question phases require the OpenAI Codex subscription")
    _, prompt_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    return profile.model, sha256_file(profiles_path), prompt_hash


def load_approved_analysis(
    package: ChapterQuestionEvidencePackage, path: Path
) -> ResolvedChapterAnalysis:
    if sha256_file(path) != package.selected_analysis_sha256:
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


def inside(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError("chapter artifact path escapes its phase directory")
    return path
