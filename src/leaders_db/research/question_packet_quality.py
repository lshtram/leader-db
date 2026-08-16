"""Blind quality comparison for one diagnostic question-packet answer."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .control_flow import enforce_model_action
from .corpus_reader_runner import ModelCallCoordinator, execute_json_model
from .model_call_budget import RunUsageBudgetTracker, StageBudgetTracker
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_prompts import QuestionPacketPrompts, load_question_packet_prompts
from .question_packet_writer import DiagnosticQuestionAnswer, validate_question_answer


class BlindCandidateQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: Literal["A", "B"]
    factual_support: Literal["pass", "fail"]
    citation_entailment: Literal["pass", "fail"]
    material_coverage: Literal["pass", "fail"]
    balance_and_limits: Literal["pass", "fail"]
    attribution_and_period: Literal["pass", "fail"]
    judgeability: Literal["pass", "fail"]
    material_regressions: tuple[str, ...] = ()
    material_improvements: tuple[str, ...] = ()
    missed_evidence_ids: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    rationale: str = Field(min_length=30)

    @model_validator(mode="after")
    def reject_contradictory_blocking_findings(
        self, info: ValidationInfo
    ) -> BlindCandidateQuality:
        if info.context and info.context.get("allow_legacy_blocking_findings"):
            return self
        dimensions = (
            self.factual_support,
            self.citation_entailment,
            self.material_coverage,
            self.balance_and_limits,
            self.attribution_and_period,
            self.judgeability,
        )
        if self.material_regressions and all(value == "pass" for value in dimensions):
            raise ValueError("material regressions require a failed quality dimension")
        if self.unsupported_claims and (
            self.factual_support == "pass" and self.citation_entailment == "pass"
        ):
            raise ValueError("unsupported claims require factual or citation failure")
        return self


class BlindQuestionQualityReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    candidates: tuple[BlindCandidateQuality, ...] = Field(min_length=2, max_length=2)
    preferred_candidate: Literal["A", "B", "tie"]
    strongest_omitted_evidence_ids: tuple[str, ...] = ()
    overall_rationale: str = Field(min_length=30)

    @model_validator(mode="after")
    def validate_candidates(self) -> BlindQuestionQualityReview:
        if {item.candidate for item in self.candidates} != {"A", "B"}:
            raise ValueError("blind review requires candidates A and B exactly once")
        return self


def run_blind_question_quality_review(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    approved_answer: dict,
    experimental_answer: DiagnosticQuestionAnswer,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    budget_tracker: StageBudgetTracker | None = None,
    reasoning_effort: str | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
) -> Path:
    """Compare approved and experimental prose in deterministic blind order."""

    enforce_model_action(project_root, "question_review", role="independent_quality")

    profile_config_hash = sha256(profiles_path.read_bytes()).hexdigest()
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("blind question review requires the OpenAI Codex subscription surface")
    if validate_question_answer(packet, experimental_answer)["functional_gate"] != "pass":
        raise ValueError("blind review requires a deterministically valid experimental answer")
    labels = _blind_labels(packet.question_id)
    payloads = {
        "approved": approved_answer,
        "experimental": experimental_answer.model_dump(mode="json"),
    }
    prompts, prompt_config_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    prompt = _review_prompt(
        packet, {label: payloads[name] for label, name in labels.items()}, prompts.review_template
    )
    tokens = len(tiktoken.get_encoding("o200k_base").encode(prompt))
    if profile.context_window is None or tokens + 12_000 > int(profile.context_window * 0.9):
        raise ValueError("blind question review exceeds context safety margin")
    execution_kwargs = {}
    if budget_tracker is not None:
        execution_kwargs = {
            "budget_tracker": budget_tracker,
            "request_component": packet.question_id,
        }
    if reasoning_effort is not None:
        execution_kwargs["reasoning_effort"] = reasoning_effort
    if call_coordinator is not None:
        execution_kwargs["call_coordinator"] = call_coordinator
    if run_budget_tracker is not None:
        execution_kwargs["run_budget_tracker"] = run_budget_tracker
    try:
        review = execute_json_model(
            project_root,
            profile,
            prompt,
            BlindQuestionQualityReview,
            output_dir,
            **execution_kwargs,
        )
        _validate_review_identity_and_evidence(review, packet)
        _validate_review_conclusion(review, labels)
    except Exception:
        if call_coordinator is not None:
            call_coordinator.publish_failure()
        raise
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "diagnostic_question_blind_review_v4",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "profile_config_sha256": profile_config_hash,
        "prompt_config_version": prompts.version,
        "prompt_config_sha256": prompt_config_hash,
        "question_id": packet.question_id,
        "estimated_input_tokens": tokens,
        "randomization": labels,
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "approved_answer_sha256": _payload_hash(approved_answer),
        "experimental_answer_sha256": _payload_hash(experimental_answer.model_dump(mode="json")),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "review_sha256": _payload_hash(review.model_dump(mode="json")),
        "response_schema_sha256": _saved_schema_hash(output_dir),
        "preferred_source": (
            labels.get(review.preferred_candidate, "tie")
            if review.preferred_candidate != "tie"
            else "tie"
        ),
        "quality_gate": "pass" if _experimental_passes(review, labels) else "fail",
    }
    path = output_dir / "blind-review-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if manifest["quality_gate"] != "pass" and call_coordinator is not None:
        call_coordinator.publish_failure()
    return path


def validate_blind_review_artifacts(
    *,
    packet: QuestionEvidencePacket,
    approved_answer: dict,
    experimental_answer: DiagnosticQuestionAnswer,
    output_dir: Path,
    project_root: Path,
    profile_name: str,
    profiles_path: Path,
    manifest_name: str = "blind-review-manifest.json",
    reasoning_effort: str | None = None,
) -> dict:
    """Reload and bind a saved review to the exact current inputs."""

    manifest = json.loads((output_dir / manifest_name).read_text())
    prompts, prompt_config_hash = _load_saved_prompt_contract(project_root, manifest)
    review = BlindQuestionQualityReview.model_validate_json(
        (output_dir / "output.json").read_text(),
        context={"allow_legacy_blocking_findings": prompts.version < 11},
    )
    labels = _blind_labels(packet.question_id)
    profile_config_hash = sha256(profiles_path.read_bytes()).hexdigest()
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    prompt = _review_prompt(
        packet,
        {
            label: (
                approved_answer
                if source == "approved"
                else experimental_answer.model_dump(mode="json")
            )
            for label, source in labels.items()
        },
        prompts.review_template,
    )
    _validate_saved_prompt(output_dir, prompt)
    _validate_review_identity_and_evidence(review, packet)
    _validate_review_conclusion(review, labels)
    expected = {
        "schema_version": "diagnostic_question_blind_review_v4",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "profile_config_sha256": profile_config_hash,
        "prompt_config_version": prompts.version,
        "prompt_config_sha256": prompt_config_hash,
        "question_id": packet.question_id,
        "estimated_input_tokens": len(tiktoken.get_encoding("o200k_base").encode(prompt)),
        "randomization": labels,
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "approved_answer_sha256": _payload_hash(approved_answer),
        "experimental_answer_sha256": _payload_hash(experimental_answer.model_dump(mode="json")),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "review_sha256": _payload_hash(review.model_dump(mode="json")),
        "response_schema_sha256": _saved_schema_hash(output_dir),
        "preferred_source": (
            labels.get(review.preferred_candidate, "tie")
            if review.preferred_candidate != "tie"
            else "tie"
        ),
        "quality_gate": "pass" if _experimental_passes(review, labels) else "fail",
    }
    if manifest != expected:
        raise ValueError("blind review artifacts do not match their current inputs")
    if validate_question_answer(packet, experimental_answer)["functional_gate"] != "pass":
        raise ValueError("saved review uses an invalid experimental answer")
    return manifest


def _load_saved_prompt_contract(
    project_root: Path, manifest: dict
) -> tuple[QuestionPacketPrompts, str]:
    current_path = project_root / "configs/question-packet-prompts.yaml"
    current, current_hash = load_question_packet_prompts(current_path)
    version = manifest.get("prompt_config_version")
    if version == current.version:
        return current, current_hash
    legacy_path = project_root / f"configs/question-packet-prompts-v{version}.yaml"
    if not legacy_path.is_file():
        raise ValueError("saved review prompt version is unavailable")
    return load_question_packet_prompts(legacy_path)


def _blind_labels(question_id: str) -> dict[str, str]:
    ordering = sorted(
        ("approved", "experimental"),
        key=lambda item: sha256(f"{question_id}:{item}:v1".encode()).hexdigest(),
    )
    return dict(zip(("A", "B"), ordering, strict=True))


def _validate_saved_prompt(output_dir: Path, reconstructed: str) -> None:
    if (output_dir / "prompt.txt").read_bytes() != reconstructed.encode():
        raise ValueError("saved blind-review prompt differs from reconstructed prompt")


def _saved_schema_hash(output_dir: Path) -> str:
    saved = json.loads((output_dir / "schema.json").read_text())
    expected = BlindQuestionQualityReview.model_json_schema()
    make_strict_response_schema(expected)
    if saved != expected:
        raise ValueError("saved blind-review schema differs from the current contract")
    return _payload_hash(saved)


def _validate_review_identity_and_evidence(
    review: BlindQuestionQualityReview, packet: QuestionEvidencePacket
) -> None:
    if review.question_id != packet.question_id:
        raise ValueError("blind reviewer changed question identity")
    allowed = {item.evidence_id for item in packet.candidate_index}
    claimed = {
        evidence_id for item in review.candidates for evidence_id in item.missed_evidence_ids
    } | set(review.strongest_omitted_evidence_ids)
    if not claimed.issubset(allowed):
        raise ValueError("blind reviewer introduced an unknown evidence ID")


def _validate_review_conclusion(review: BlindQuestionQualityReview, labels: dict[str, str]) -> None:
    _experimental_passes(review, labels)


def _experimental_passes(review: BlindQuestionQualityReview, labels: dict[str, str]) -> bool:
    experimental_label = next(label for label, source in labels.items() if source == "experimental")
    experimental = next(item for item in review.candidates if item.candidate == experimental_label)
    dimensions = (
        experimental.factual_support,
        experimental.citation_entailment,
        experimental.material_coverage,
        experimental.balance_and_limits,
        experimental.attribution_and_period,
        experimental.judgeability,
    )
    return (
        all(value == "pass" for value in dimensions)
        and not experimental.unsupported_claims
        and not experimental.material_regressions
    )


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _review_prompt(packet: QuestionEvidencePacket, candidates: dict, template: str) -> str:
    exact = [item.model_dump(mode="json") for item in packet.priority_evidence]
    index = [item.model_dump(mode="json") for item in packet.candidate_index]
    return template.format(
        question_id=packet.question_id,
        question=packet.question,
        exact_evidence=json.dumps(exact, ensure_ascii=False),
        candidate_index=json.dumps(index, ensure_ascii=False),
        candidates=json.dumps(candidates, ensure_ascii=False),
    )


__all__ = ["run_blind_question_quality_review", "validate_blind_review_artifacts"]
