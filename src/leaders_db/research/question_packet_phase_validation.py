"""Validation and input binding for chapter question phases."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .chapter_analysis_models import ResolvedChapterAnalysis
from .control_flow import load_question_review_experiment_policy
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import (
    ChapterQuestionArtifact,
    ChapterQuestionPhaseManifest,
    QuestionUnavailableArtifact,
)
from .question_packet_prompts import (
    load_question_packet_prompts,
    load_versioned_question_packet_prompts,
)
from .question_packet_quality import validate_blind_review_artifacts
from .question_packet_writer import (
    DiagnosticQuestionAnswer,
    build_question_writer_prompt,
    load_normalized_question_answer,
    validate_question_answer,
)
from .question_packet_writer_prompt import project_predecessor_answer
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
    prompt_hashes: set[str] = set()
    for artifact in manifest.artifacts:
        path = inside(output_dir, artifact.artifact_path)
        packet = packets[artifact.question_id]
        if artifact.status == "unavailable":
            _validate_unavailable_question(
                project_root=project_root,
                packet=packet,
                artifact=artifact,
                path=path,
            )
            continue
        answer = (
            load_normalized_question_answer(packet, path.parent)
            if path.name == "accepted-output.json"
            else DiagnosticQuestionAnswer.model_validate_json(path.read_text())
        )
        request = json.loads((path.parent / "request-manifest.json").read_bytes())
        prompts, prompt_hash = load_versioned_question_packet_prompts(
            project_root, request.get("prompt_config_version")
        )
        if packet.evidence_discovery_complete and prompts.version < 14:
            raise ValueError("closed evidence discovery requires prompt version 14 or later")
        if request.get("prompt_config_sha256") != prompt_hash:
            raise ValueError("saved question-writer prompt configuration hash differs")
        if prompts.version >= 12:
            projected, excluded = project_predecessor_answer(
                packet, predecessor[artifact.question_id]
            )
            if request.get("predecessor_answer_included") != bool(projected) or request.get(
                "predecessor_excluded_evidence_ids"
            ) != list(excluded):
                raise ValueError("saved predecessor projection metadata differs")
        if prompts.version >= 14 and (
            request.get("evidence_discovery_complete") is not packet.evidence_discovery_complete
            or request.get("reopenable_evidence_ids")
            != (
                []
                if packet.evidence_discovery_complete
                else list(packet.coverage.reopenable_evidence_ids)
            )
        ):
            raise ValueError("saved writer evidence-discovery metadata differs")
        prompt_hashes.add(prompt_hash)
        expected_prompt = prompt_builder(packet, prompts, predecessor[artifact.question_id])
        if (path.parent / "prompt.txt").read_bytes() != expected_prompt.encode():
            raise ValueError("saved question-writer prompt differs from current writer input")
        if sha256_file(path) != artifact.artifact_sha256 or (
            question_validator(packet, answer)["functional_gate"] != "pass"
        ):
            raise ValueError("chapter writing child artifact is invalid")
    if prompt_hashes and prompt_hashes != {manifest.prompt_config_sha256}:
        raise ValueError("chapter writing manifest mixes prompt configurations")
    return manifest


def _validate_unavailable_question(*, project_root, packet, artifact, path) -> None:
    unavailable = QuestionUnavailableArtifact.model_validate_json(path.read_text())
    if (
        unavailable.question_id != artifact.question_id
        or packet.candidate_index
        or packet.coverage.required_evidence_ids
        or unavailable.packet_sha256 != payload_hash(packet.model_dump(mode="json"))
        or sha256_file(path) != artifact.artifact_sha256
    ):
        raise ValueError("unavailable question artifact is not justified by its packet")
    adjudication = inside(project_root, unavailable.adjudication_path)
    if sha256_file(adjudication) != unavailable.adjudication_sha256:
        raise ValueError("unavailable question adjudication hash differs")
    from .question_packet_chapter import load_trusted_unavailable_adjudication

    load_trusted_unavailable_adjudication(
        project_root=project_root, path=adjudication, packet=packet
    )


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
    experiment_policy_path: Path | None = None,
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
    policy_path = _resolve_review_policy_path(
        project_root, actual.experiment_policy_sha256, experiment_policy_path
    )
    policy = load_question_review_experiment_policy(policy_path) if policy_path else None
    carries_reopens = (
        policy is not None
        and policy.writer_reopen_behavior == "carry_to_review_and_bounded_correction"
    )
    if any(answer.reopen_requests for answer in snapshot.answers.values()) and not carries_reopens:
        raise ValueError("question review cannot consume unresolved writer reopen requests")
    analysis_hash = sha256_file(approved_analysis_path)
    if analysis_hash != package.selected_analysis_sha256:
        raise ValueError("approved analysis hash does not match the question package")
    analysis = ResolvedChapterAnalysis.model_validate_json(approved_analysis_path.read_text())
    approved = {item.question_id: item.model_dump(mode="json") for item in analysis.answers}
    packets = {item.question_id: item for item in package.packets}
    artifacts = []
    review_prompt_hashes: set[str] = set()
    for written in writing.artifacts:
        if written.status == "unavailable":
            source = inside(writing_dir, written.artifact_path)
            child = inside(output_dir, written.artifact_path)
            unavailable = QuestionUnavailableArtifact.model_validate_json(child.read_text())
            if (
                unavailable.question_id != written.question_id
                or child.read_bytes() != source.read_bytes()
            ):
                raise ValueError("review unavailable artifact differs from trusted writing gap")
            artifacts.append(
                ChapterQuestionArtifact(
                    question_id=written.question_id,
                    artifact_path=written.artifact_path,
                    artifact_sha256=sha256_file(child),
                    status="unavailable",
                )
            )
            continue
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
        review_prompt_hashes.add(review["prompt_config_sha256"])
        child = review_dir / "blind-review-manifest.json"
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=written.question_id,
                artifact_path=str(child.relative_to(output_dir)),
                artifact_sha256=sha256_file(child),
                status=review["quality_gate"],
            )
        )
    model, profile_hash, _ = configuration_binding(project_root, profile_name, profiles_path)
    if review_prompt_hashes and len(review_prompt_hashes) != 1:
        raise ValueError("chapter review mixes prompt configurations")
    prompt_hash = next(iter(review_prompt_hashes), actual.prompt_config_sha256)
    experiment_policy_sha256 = None
    if policy_path is not None:
        experiment_policy_sha256 = sha256_file(policy_path)
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
        experiment_policy_sha256=experiment_policy_sha256,
        question_count=10,
        artifacts=tuple(artifacts),
        phase_gate=(
            "pass"
            if all(item.status in {"pass", "unavailable"} for item in artifacts)
            else "fail"
        ),
    )
    if actual != expected:
        raise ValueError("chapter review manifest differs from trusted child reviews")
    return actual


def _resolve_review_policy_path(
    project_root: Path, expected_sha256: str | None, supplied: Path | None
) -> Path | None:
    if expected_sha256 is None:
        if supplied is not None:
            raise ValueError("review manifest does not bind an experiment policy")
        return None
    candidates = tuple(
        path
        for path in (
            supplied,
            project_root / "configs/research-question-review-experiment.yaml",
            project_root / "configs/research-question-review-experiment-v1.yaml",
        )
        if path is not None and path.is_file()
    )
    matches = {path.resolve() for path in candidates if sha256_file(path) == expected_sha256}
    if len(matches) != 1:
        raise ValueError("saved review experiment policy is unavailable or ambiguous")
    return next(iter(matches))


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
