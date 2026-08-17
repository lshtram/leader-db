"""Focused second-pass verification for one diagnostic question answer."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .control_flow import enforce_model_action
from .corpus_reader_runner import ModelCallCoordinator, execute_json_model
from .model_call_budget import RunUsageBudgetTracker, StageBudgetTracker
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_quality import BlindQuestionQualityReview, _blind_labels
from .question_packet_writer import DiagnosticQuestionAnswer, validate_question_answer


class PriorityEvidenceVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "covered", "qualification_included", "immaterial_duplicate", "materially_omitted"
    ]
    rationale: str = Field(min_length=20)


class ProposedFindingVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["confirmed", "rejected", "uncertain"]
    rationale: str = Field(min_length=20)


class CanonicalPriorityEvidenceVerification(PriorityEvidenceVerification):
    evidence_id: str

class CanonicalProposedFindingVerification(ProposedFindingVerification):
    finding_id: str


class FocusedQuestionVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    chronology_status: Literal["pass", "fail", "uncertain"]
    chronology_finding: str = Field(min_length=20)
    priority_evidence_checks: tuple[CanonicalPriorityEvidenceVerification, ...]
    proposed_finding_checks: tuple[CanonicalProposedFindingVerification, ...]
    additional_omitted_evidence_ids: tuple[str, ...] = ()
    final_gate: Literal["pass", "fail"]
    rationale: str = Field(min_length=30)

    @model_validator(mode="after")
    def validate_gate(self) -> FocusedQuestionVerification:
        blocking = self.chronology_status != "pass" or bool(self.additional_omitted_evidence_ids)
        blocking = blocking or any(
            item.status == "materially_omitted" for item in self.priority_evidence_checks
        )
        blocking = blocking or any(
            item.verdict != "rejected" for item in self.proposed_finding_checks
        )
        if self.final_gate != ("fail" if blocking else "pass"):
            raise ValueError("focused verifier final gate contradicts its checks")
        return self


class _VerifierPromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    verifier_template: str = Field(min_length=100)

    @model_validator(mode="after")
    def validate_placeholders(self) -> _VerifierPromptConfig:
        required = {
            "{question_id}",
            "{question}",
            "{experimental_answer}",
            "{exact_evidence}",
            "{candidate_index}",
            "{proposed_findings}",
        }
        if not required.issubset({item for item in required if item in self.verifier_template}):
            raise ValueError("verifier prompt omits a required placeholder")
        return self


def run_focused_question_verification(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    experimental_answer: DiagnosticQuestionAnswer,
    first_review: BlindQuestionQualityReview,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    budget_tracker: StageBudgetTracker | None = None,
    reasoning_effort: str | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
) -> Path:
    """Run and persist a focused second-pass verification."""

    enforce_model_action(project_root, "question_review", role="independent_quality")
    profile_hash = sha256(profiles_path.read_bytes()).hexdigest()
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    _validate_inputs(packet, experimental_answer, first_review, profile)
    prompt_config, prompt_hash = _load_prompt_config(
        project_root / "configs/question-review-verifier-prompts.yaml"
    )
    findings = _proposed_blocking_findings(first_review, packet.question_id)
    prompt = _verifier_prompt(
        packet, experimental_answer, findings, prompt_config.verifier_template
    )
    response_model = _verification_response_model(packet, tuple(findings))
    tokens = _estimated_tokens(prompt, response_model)
    if profile.context_window is None or tokens + 12_000 > int(profile.context_window * 0.9):
        raise ValueError("focused verification exceeds context safety margin")
    kwargs: dict[str, object] = {}
    if budget_tracker is not None:
        kwargs.update(budget_tracker=budget_tracker, request_component=packet.question_id)
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if run_budget_tracker is not None:
        kwargs["run_budget_tracker"] = run_budget_tracker
    if call_coordinator is not None:
        kwargs["call_coordinator"] = call_coordinator
    try:
        response = execute_json_model(
            project_root, profile, prompt, response_model, output_dir, **kwargs
        )
        verification = _canonical_verification(response, packet, tuple(findings))
    except Exception:
        if call_coordinator is not None:
            call_coordinator.publish_failure()
        raise
    accepted_path = output_dir / "accepted-verification.json"
    accepted_path.write_text(verification.model_dump_json(indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "diagnostic_focused_question_verification_v1",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "profile_config_sha256": profile_hash,
        "prompt_config_version": prompt_config.version,
        "prompt_config_sha256": prompt_hash,
        "question_id": packet.question_id,
        "estimated_input_tokens": tokens,
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "experimental_answer_sha256": _payload_hash(experimental_answer.model_dump(mode="json")),
        "first_review_sha256": _payload_hash(first_review.model_dump(mode="json")),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "raw_output_sha256": sha256((output_dir / "output.json").read_bytes()).hexdigest(),
        "response_schema_sha256": _saved_schema_hash(output_dir, response_model),
        "accepted_verification_sha256": sha256(accepted_path.read_bytes()).hexdigest(),
        "quality_gate": verification.final_gate,
    }
    path = output_dir / "focused-verification-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if verification.final_gate != "pass" and call_coordinator is not None:
        call_coordinator.publish_failure()
    return path


def validate_focused_question_verification(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    experimental_answer: DiagnosticQuestionAnswer,
    first_review: BlindQuestionQualityReview,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str | None = None,
) -> dict:
    """Reconstruct and validate all focused-verification artifacts."""

    profile_hash = sha256(profiles_path.read_bytes()).hexdigest()
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    _validate_inputs(packet, experimental_answer, first_review, profile)
    prompt_config, prompt_hash = _load_prompt_config(
        project_root / "configs/question-review-verifier-prompts.yaml"
    )
    findings = _proposed_blocking_findings(first_review, packet.question_id)
    finding_ids = tuple(findings)
    response_model = _verification_response_model(packet, finding_ids)
    prompt = _verifier_prompt(
        packet, experimental_answer, findings, prompt_config.verifier_template
    )
    if (output_dir / "prompt.txt").read_bytes() != prompt.encode():
        raise ValueError("saved focused-verifier prompt differs from reconstruction")
    raw_path = output_dir / "output.json"
    response = response_model.model_validate_json(raw_path.read_text(encoding="utf-8"))
    verification = _canonical_verification(response, packet, finding_ids)
    accepted_path = output_dir / "accepted-verification.json"
    expected_accepted = verification.model_dump_json(indent=2) + "\n"
    if accepted_path.read_bytes() != expected_accepted.encode():
        raise ValueError("accepted focused verification differs from raw output")
    expected = {
        "schema_version": "diagnostic_focused_question_verification_v1",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "profile_config_sha256": profile_hash,
        "prompt_config_version": prompt_config.version,
        "prompt_config_sha256": prompt_hash,
        "question_id": packet.question_id,
        "estimated_input_tokens": _estimated_tokens(prompt, response_model),
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "experimental_answer_sha256": _payload_hash(experimental_answer.model_dump(mode="json")),
        "first_review_sha256": _payload_hash(first_review.model_dump(mode="json")),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "raw_output_sha256": sha256(raw_path.read_bytes()).hexdigest(),
        "response_schema_sha256": _saved_schema_hash(output_dir, response_model),
        "accepted_verification_sha256": sha256(accepted_path.read_bytes()).hexdigest(),
        "quality_gate": verification.final_gate,
    }
    manifest = json.loads((output_dir / "focused-verification-manifest.json").read_text())
    if manifest != expected:
        raise ValueError("focused-verification manifest differs from reconstructed artifacts")
    return manifest


def _load_prompt_config(path: Path) -> tuple[_VerifierPromptConfig, str]:
    raw = path.read_bytes()
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid focused verifier prompt YAML: {path}") from exc
    return _VerifierPromptConfig.model_validate(payload), sha256(raw).hexdigest()


def _validate_inputs(
    packet: QuestionEvidencePacket,
    answer: DiagnosticQuestionAnswer,
    review: BlindQuestionQualityReview,
    profile,
) -> None:
    if validate_question_answer(packet, answer)["functional_gate"] != "pass":
        raise ValueError("focused verification requires a valid experimental answer")
    if review.question_id != packet.question_id:
        raise ValueError("first review question identity differs from the packet")
    if (
        profile.execution_surface != "codex"
        or profile.provider != "openai"
        or profile.model != "gpt-5.6-luna"
    ):
        raise ValueError("focused verification requires Luna on the Codex subscription surface")


def _proposed_blocking_findings(
    review: BlindQuestionQualityReview, question_id: str
) -> dict[str, str]:
    labels = _blind_labels(question_id)
    experimental_label = next(key for key, value in labels.items() if value == "experimental")
    candidate = next(item for item in review.candidates if item.candidate == experimental_label)
    findings = list(candidate.material_regressions) + list(candidate.unsupported_claims)
    dimensions = {
        "factual_support": candidate.factual_support,
        "citation_entailment": candidate.citation_entailment,
        "material_coverage": candidate.material_coverage,
        "balance_and_limits": candidate.balance_and_limits,
        "attribution_and_period": candidate.attribution_and_period,
        "judgeability": candidate.judgeability,
    }
    findings.extend(
        f"Pass one failed {name}: {candidate.rationale}"
        for name, value in dimensions.items()
        if value == "fail"
    )
    return {f"finding_{index:03d}": text for index, text in enumerate(dict.fromkeys(findings), 1)}


def _verification_response_model(
    packet: QuestionEvidencePacket, finding_ids: tuple[str, ...]
) -> type[BaseModel]:
    reopenable_ids = packet.coverage.reopenable_evidence_ids
    digest = sha256(
        "\n".join(
            (
                packet.question_id,
                *packet.coverage.required_evidence_ids,
                *reopenable_ids,
                *finding_ids,
            )
        ).encode()
    ).hexdigest()[:12]
    evidence_ledger = create_model(
        f"PriorityEvidenceVerificationLedger_{digest}",
        __config__=ConfigDict(extra="forbid"),
        **{
            f"item_{index:04d}": (PriorityEvidenceVerification, Field(alias=evidence_id))
            for index, evidence_id in enumerate(packet.coverage.required_evidence_ids, 1)
        },
    )
    finding_ledger = create_model(
        f"ProposedFindingVerificationLedger_{digest}",
        __config__=ConfigDict(extra="forbid"),
        **{
            f"item_{index:04d}": (ProposedFindingVerification, Field(alias=finding_id))
            for index, finding_id in enumerate(finding_ids, 1)
        },
    )
    omission_field = (
        (tuple[Literal.__getitem__(reopenable_ids), ...], ())
        if reopenable_ids
        else (tuple[str, ...], Field(default=(), max_length=0))
    )
    return create_model(
        f"FocusedQuestionVerificationResponse_{digest}",
        __config__=ConfigDict(extra="forbid"),
        question_id=(str, ...),
        chronology_status=(Literal["pass", "fail", "uncertain"], ...),
        chronology_finding=(str, Field(min_length=20)),
        priority_evidence_checks=(evidence_ledger, ...),
        proposed_finding_checks=(finding_ledger, ...),
        additional_omitted_evidence_ids=omission_field,
        final_gate=(Literal["pass", "fail"], ...),
        rationale=(str, Field(min_length=30)),
    )


def _canonical_verification(
    response: BaseModel,
    packet: QuestionEvidencePacket,
    finding_ids: tuple[str, ...],
) -> FocusedQuestionVerification:
    payload = response.model_dump(mode="json", by_alias=True)
    if payload["question_id"] != packet.question_id:
        raise ValueError("focused verifier changed question identity")
    evidence = payload.pop("priority_evidence_checks")
    findings = payload.pop("proposed_finding_checks")
    payload["priority_evidence_checks"] = [
        {"evidence_id": evidence_id, **evidence[evidence_id]}
        for evidence_id in packet.coverage.required_evidence_ids
    ]
    payload["proposed_finding_checks"] = [
        {"finding_id": finding_id, **findings[finding_id]} for finding_id in finding_ids
    ]
    return FocusedQuestionVerification.model_validate(payload)


def _verifier_prompt(
    packet: QuestionEvidencePacket,
    answer: DiagnosticQuestionAnswer,
    findings: dict[str, str],
    template: str,
) -> str:
    reopenable = set(packet.coverage.reopenable_evidence_ids)
    return template.format(
        question_id=packet.question_id,
        question=packet.question,
        experimental_answer=answer.model_dump_json(),
        exact_evidence=json.dumps(
            [item.model_dump(mode="json") for item in packet.priority_evidence],
            ensure_ascii=False,
        ),
        candidate_index=json.dumps(
            [
                item.model_dump(mode="json")
                for item in packet.candidate_index
                if item.evidence_id in reopenable
            ],
            ensure_ascii=False,
        ),
        proposed_findings=json.dumps(findings, ensure_ascii=False),
    )


def _estimated_tokens(prompt: str, model: type[BaseModel]) -> int:
    schema = json.dumps(model.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return len(tiktoken.get_encoding("o200k_base").encode(prompt + schema))


def _saved_schema_hash(output_dir: Path, model: type[BaseModel]) -> str:
    saved = json.loads((output_dir / "schema.json").read_text())
    expected = model.model_json_schema()
    make_strict_response_schema(expected)
    if saved != expected:
        raise ValueError("saved focused-verifier schema differs from current contract")
    return _payload_hash(saved)


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()

__all__ = [
    "FocusedQuestionVerification",
    "run_focused_question_verification",
    "validate_focused_question_verification",
]
