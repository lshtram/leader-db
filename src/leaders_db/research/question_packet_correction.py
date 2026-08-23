"""One bounded answer correction after independent question review."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .control_flow import enforce_model_action, load_question_correction_policy
from .corpus_reader_runner import ModelCallCoordinator, execute_json_model
from .model_call_budget import RunUsageBudgetTracker, StageBudgetTracker
from .model_profiles import load_research_model_profiles
from .question_correction_ledger import CorrectionPhaseLedger, claim_phase_action
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_answer_validation import validate_question_answer
from .question_packet_chapter_models import QuestionUnavailableArtifact
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_quality import (
    BlindQuestionQualityReview,
    _blind_labels,
    _review_prompt,
    build_blind_review_response_schema,
    run_blind_question_quality_review,
    validate_blind_review_artifacts,
)
from .question_packet_writer import (
    DiagnosticQuestionAnswer,
    _canonical_question_answer,
    _question_answer_response_model,
)
from .question_packet_writer_prompt import _writer_evidence_payload
from .question_review_preflight import QuestionReviewInputSnapshot, require_trusted_snapshot

_CORRECTION_EXECUTION_CAPABILITY = object()
_FINAL_REVIEW_EXECUTION_CAPABILITY = object()


class QuestionCorrectionPrompts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    correction_template: str = Field(min_length=500)


class ResidualQuestionConcern(BaseModel):
    """Final-review limitations carried into chapter judgment."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["residual_question_concern_v1"] = "residual_question_concern_v1"
    question_id: str
    final_quality_gate: Literal["pass", "fail"]
    confidence_treatment: Literal["unchanged", "lower"]
    failed_dimensions: tuple[str, ...]
    material_regressions: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    missed_evidence_ids: tuple[str, ...]
    strongest_omitted_evidence_ids: tuple[str, ...]
    reviewer_rationale: str
    overall_rationale: str


def load_question_correction_prompts(path: Path) -> tuple[QuestionCorrectionPrompts, str]:
    """Load the exact correction prompt contract and its hash."""

    raw = path.read_bytes()
    return QuestionCorrectionPrompts.model_validate(yaml.safe_load(raw)), sha256(raw).hexdigest()


def experimental_review_findings(manifest: dict, review: BlindQuestionQualityReview) -> dict:
    """Deblind and retain only findings about the experimental answer."""

    labels = manifest.get("randomization")
    if not isinstance(labels, dict):
        raise ValueError("question review manifest lacks randomization binding")
    experimental = next(
        (item for item in review.candidates if labels.get(item.candidate) == "experimental"),
        None,
    )
    if experimental is None:
        raise ValueError("question review does not identify the experimental candidate")
    return {
        "failed_dimensions": [
            name
            for name in (
                "factual_support",
                "citation_entailment",
                "material_coverage",
                "balance_and_limits",
                "attribution_and_period",
                "judgeability",
            )
            if getattr(experimental, name) == "fail"
        ],
        "material_regressions": list(experimental.material_regressions),
        "unsupported_claims": list(experimental.unsupported_claims),
        "missed_evidence_ids": list(experimental.missed_evidence_ids),
        "candidate_rationale": experimental.rationale,
        "strongest_omitted_evidence_ids": list(review.strongest_omitted_evidence_ids),
        "overall_rationale": review.overall_rationale,
    }


def build_question_correction_prompt(
    *,
    packet: QuestionEvidencePacket,
    predecessor: DiagnosticQuestionAnswer,
    findings: dict,
    prompts: QuestionCorrectionPrompts,
) -> str:
    """Serialize one correction request from exact evidence and review findings."""

    exact = [
        _writer_evidence_payload(item, compact_table_citations=False, source_units=None)
        for item in packet.priority_evidence
    ]
    return prompts.correction_template.format(
        question_id=packet.question_id,
        question=packet.question,
        predecessor_answer=predecessor.model_dump_json(),
        review_findings=json.dumps(findings, ensure_ascii=False),
        exact_evidence=json.dumps(exact, ensure_ascii=False),
    )


def run_question_correction(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    predecessor: DiagnosticQuestionAnswer,
    findings: dict,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    prompts_path: Path,
    reasoning_effort: str,
    policy_path: Path,
    phase_ledger_path: Path,
    correction_ordinal: Literal[1] = 1,
    budget_tracker: StageBudgetTracker | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    execution_capability: object | None = None,
) -> Path:
    """Write exactly one corrected answer and persist its complete binding."""

    enforce_model_action(project_root, "question_writing", role="production")
    if (
        execution_capability is not _CORRECTION_EXECUTION_CAPABILITY
        or run_budget_tracker is None
    ):
        raise ValueError("question correction requires trusted budgeted authorization")
    policy = load_question_correction_policy(policy_path)
    if correction_ordinal != policy.maximum_corrections_per_failed_question:
        raise ValueError("correction ordinal violates the frozen correction policy")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("question correction output directory is already in use")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.provider != "openai" or profile.execution_surface != "codex":
        raise ValueError("question correction requires the OpenAI Codex subscription")
    prompts, prompts_hash = load_question_correction_prompts(prompts_path)
    prompt = build_question_correction_prompt(
        packet=packet, predecessor=predecessor, findings=findings, prompts=prompts
    )
    response_model = _question_answer_response_model(
        packet.coverage.required_evidence_ids, allow_reopen=False
    )
    complete = prompt + json.dumps(
        response_model.model_json_schema(), ensure_ascii=False, sort_keys=True
    )
    response = execute_json_model(
        project_root,
        profile,
        prompt,
        response_model,
        output_dir,
        budget_tracker=budget_tracker,
        request_component=packet.question_id,
        reasoning_effort=reasoning_effort,
        call_coordinator=call_coordinator,
        run_budget_tracker=run_budget_tracker,
    )
    answer = _canonical_question_answer(response, packet.coverage.required_evidence_ids)
    validation = validate_question_answer(packet, answer)
    if answer.reopen_requests or validation["functional_gate"] != "pass":
        if call_coordinator is not None:
            call_coordinator.publish_failure()
        raise ValueError("corrected question answer failed deterministic validation")
    answer_path = output_dir / "accepted-output.json"
    answer_path.write_text(answer.model_dump_json(indent=2) + "\n", encoding="utf-8")
    raw_path = output_dir / "output.json"
    schema = json.loads((output_dir / "schema.json").read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "question_answer_correction_v1",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "question_id": packet.question_id,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "correction_ordinal": correction_ordinal,
        "policy_sha256": sha256(policy_path.read_bytes()).hexdigest(),
        "profile_config_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "prompt_config_sha256": prompts_hash,
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "predecessor_sha256": _payload_hash(predecessor.model_dump(mode="json")),
        "review_findings_sha256": _payload_hash(findings),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "estimated_prompt_tokens": len(tiktoken.get_encoding("o200k_base").encode(prompt)),
        "raw_output_sha256": sha256(raw_path.read_bytes()).hexdigest(),
        "answer_sha256": sha256(answer_path.read_bytes()).hexdigest(),
        "response_schema_sha256": _payload_hash(schema),
        "functional_gate": "pass",
    }
    manifest_path = output_dir / "correction-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    claim_phase_action(
        ledger_path=phase_ledger_path,
        policy_path=policy_path,
        question_id=packet.question_id,
        action="correct",
        request_sha256=sha256(complete.encode()).hexdigest(),
    )
    return manifest_path


def validate_question_correction(
    *,
    packet: QuestionEvidencePacket,
    predecessor: DiagnosticQuestionAnswer,
    findings: dict,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    prompts_path: Path,
    reasoning_effort: str,
    policy_path: Path,
    phase_ledger_path: Path,
    correction_ordinal: Literal[1] = 1,
) -> tuple[DiagnosticQuestionAnswer, dict]:
    """Trusted-reload one correction from its exact inputs and transport artifacts."""

    policy = load_question_correction_policy(policy_path)
    if not phase_ledger_path.is_file():
        raise ValueError("correction phase ledger is missing")
    if correction_ordinal != policy.maximum_corrections_per_failed_question:
        raise ValueError("correction ordinal violates the frozen correction policy")
    manifest = json.loads((output_dir / "correction-manifest.json").read_text())
    prompts, prompts_hash = load_question_correction_prompts(prompts_path)
    prompt = build_question_correction_prompt(
        packet=packet, predecessor=predecessor, findings=findings, prompts=prompts
    )
    if (output_dir / "prompt.txt").read_bytes() != prompt.encode():
        raise ValueError("saved correction prompt differs from reconstructed prompt")
    response_model = _question_answer_response_model(
        packet.coverage.required_evidence_ids, allow_reopen=False
    )
    expected_schema = response_model.model_json_schema()
    make_strict_response_schema(expected_schema)
    saved_schema = json.loads((output_dir / "schema.json").read_text())
    if saved_schema != expected_schema:
        raise ValueError("saved correction schema differs from reconstructed schema")
    raw_path = output_dir / "output.json"
    response = response_model.model_validate_json(raw_path.read_text(encoding="utf-8"))
    answer = _canonical_question_answer(response, packet.coverage.required_evidence_ids)
    answer_path = output_dir / "accepted-output.json"
    if DiagnosticQuestionAnswer.model_validate_json(answer_path.read_text()) != answer:
        raise ValueError("saved corrected answer differs from immutable raw output")
    validation = validate_question_answer(packet, answer)
    if answer.reopen_requests or validation["functional_gate"] != "pass":
        raise ValueError("saved corrected answer fails deterministic validation")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    expected = {
        "schema_version": "question_answer_correction_v1",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "question_id": packet.question_id,
        "profile": profile_name,
        "model": profile.model,
        "reasoning_effort": reasoning_effort,
        "correction_ordinal": correction_ordinal,
        "policy_sha256": sha256(policy_path.read_bytes()).hexdigest(),
        "profile_config_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "prompt_config_sha256": prompts_hash,
        "packet_sha256": _payload_hash(packet.model_dump(mode="json")),
        "predecessor_sha256": _payload_hash(predecessor.model_dump(mode="json")),
        "review_findings_sha256": _payload_hash(findings),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "estimated_prompt_tokens": len(tiktoken.get_encoding("o200k_base").encode(prompt)),
        "raw_output_sha256": sha256(raw_path.read_bytes()).hexdigest(),
        "answer_sha256": sha256(answer_path.read_bytes()).hexdigest(),
        "response_schema_sha256": _payload_hash(saved_schema),
        "functional_gate": "pass",
    }
    if manifest != expected:
        raise ValueError("correction manifest differs from reconstructed inputs")
    return answer, manifest


def residual_question_concern(
    *, manifest: dict, review: BlindQuestionQualityReview
) -> ResidualQuestionConcern:
    """Convert the one final review into a judge-visible confidence input."""

    findings = experimental_review_findings(manifest, review)
    failed = tuple(str(item) for item in findings["failed_dimensions"])
    has_concern = bool(
        failed
        or findings["material_regressions"]
        or findings["unsupported_claims"]
        or findings["missed_evidence_ids"]
        or findings["strongest_omitted_evidence_ids"]
    )
    return ResidualQuestionConcern(
        question_id=review.question_id,
        final_quality_gate=(
            "fail" if has_concern else "pass"
        ),
        confidence_treatment="lower" if has_concern else "unchanged",
        failed_dimensions=failed,
        material_regressions=tuple(str(item) for item in findings["material_regressions"]),
        unsupported_claims=tuple(str(item) for item in findings["unsupported_claims"]),
        missed_evidence_ids=tuple(str(item) for item in findings["missed_evidence_ids"]),
        strongest_omitted_evidence_ids=tuple(
            str(item) for item in findings["strongest_omitted_evidence_ids"]
        ),
        reviewer_rationale=str(findings["candidate_rationale"]),
        overall_rationale=str(findings["overall_rationale"]),
    )


def run_final_question_review(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    approved_answer: dict,
    corrected_answer: DiagnosticQuestionAnswer,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    policy_path: Path,
    reasoning_effort: str,
    phase_ledger_path: Path,
    final_review_ordinal: Literal[1] = 1,
    budget_tracker: StageBudgetTracker | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    execution_capability: object | None = None,
) -> Path:
    """Run the policy's sole final review without stopping on quality findings."""

    if (
        execution_capability is not _FINAL_REVIEW_EXECUTION_CAPABILITY
        or budget_tracker is None
        or run_budget_tracker is None
    ):
        raise ValueError("final review requires trusted budgeted authorization")
    policy = load_question_correction_policy(policy_path)
    if final_review_ordinal != policy.maximum_final_reviews_per_corrected_question:
        raise ValueError("final-review ordinal violates the frozen correction policy")
    prompts, _ = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    labels = _blind_labels(packet.question_id)
    prompt = _review_prompt(
        packet,
        {
            label: (
                approved_answer
                if source == "approved"
                else corrected_answer.model_dump(mode="json")
            )
            for label, source in labels.items()
        },
        prompts.review_template,
    )
    schema = build_blind_review_response_schema(packet)
    complete = prompt + json.dumps(schema, ensure_ascii=False, sort_keys=True)
    manifest_path = run_blind_question_quality_review(
        project_root=project_root,
        packet=packet,
        approved_answer=approved_answer,
        experimental_answer=corrected_answer,
        output_dir=output_dir,
        profile_name=profile_name,
        profiles_path=profiles_path,
        budget_tracker=budget_tracker,
        reasoning_effort=reasoning_effort,
        call_coordinator=call_coordinator,
        run_budget_tracker=run_budget_tracker,
        publish_quality_failure=False,
    )
    binding = {
        "schema_version": "question_final_review_policy_binding_v1",
        "question_id": packet.question_id,
        "final_review_ordinal": final_review_ordinal,
        "policy_sha256": sha256(policy_path.read_bytes()).hexdigest(),
        "review_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
    }
    (output_dir / "final-review-policy-binding.json").write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    claim_phase_action(
        ledger_path=phase_ledger_path,
        policy_path=policy_path,
        question_id=packet.question_id,
        action="review",
        request_sha256=sha256(complete.encode()).hexdigest(),
    )
    return manifest_path


def persist_residual_question_concern(
    *, manifest: dict, review: BlindQuestionQualityReview, output_path: Path
) -> Path:
    """Persist the final review's nonblocking, judge-visible confidence treatment."""

    concern = residual_question_concern(manifest=manifest, review=review)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(concern.model_dump_json(indent=2) + "\n")
    return output_path


def build_question_judge_handoff(
    *,
    question_artifacts: dict[str, Path],
    residual_artifacts: dict[str, Path],
    final_review_dirs: dict[str, Path],
    phase_ledger_path: Path,
    policy_path: Path,
    packets: dict[str, QuestionEvidencePacket],
    approved_answers: dict[str, dict],
    corrected_answers: dict[str, DiagnosticQuestionAnswer],
    original_snapshots: tuple[QuestionReviewInputSnapshot, ...],
    project_root: Path,
    profile_name: str,
    profiles_path: Path,
    reasoning_effort: str,
    output_path: Path,
    unavailable_artifacts: dict[str, Path] | None = None,
    unavailable_packets: dict[str, QuestionEvidencePacket] | None = None,
) -> Path:
    """Bind all 80 selected answers and every corrected-answer residual for judging."""

    expected = {f"{chapter}B.{number}" for chapter in range(1, 9) for number in range(1, 11)}
    unavailable_artifacts = unavailable_artifacts or {}
    unavailable_packets = unavailable_packets or {}
    unavailable_ids = set(unavailable_artifacts)
    ledger = CorrectionPhaseLedger.model_validate_json(phase_ledger_path.read_text())
    reviewed = {
        item.split(":")[0]
        for item in ledger.claimed_actions
        if item.endswith(":review:1")
    }
    if reviewed != set(ledger.question_ids):
        raise ValueError("judge handoff requires every mandatory final review")
    if (
        set(question_artifacts) | unavailable_ids != expected
        or set(question_artifacts) & unavailable_ids
        or set(residual_artifacts) != reviewed
        or set(final_review_dirs) != reviewed
        or set(unavailable_packets) != unavailable_ids
    ):
        raise ValueError("judge handoff requires exactly the 80-question inventory")
    if ledger.policy_sha256 != sha256(policy_path.read_bytes()).hexdigest():
        raise ValueError("judge handoff policy differs from the correction phase")
    if set(packets) != reviewed or set(approved_answers) != reviewed or set(
        corrected_answers
    ) != reviewed:
        raise ValueError("judge handoff lacks trusted final-review inputs")
    for snapshot in original_snapshots:
        require_trusted_snapshot(snapshot)
    original_answers = {
        question_id: answer
        for snapshot in original_snapshots
        for question_id, answer in snapshot.answers.items()
        if question_id not in reviewed
    }
    if set(original_answers) != expected - reviewed - unavailable_ids:
        raise ValueError("judge handoff lacks trusted unchanged writing inputs")
    for question_id, artifact_path in question_artifacts.items():
        selected = DiagnosticQuestionAnswer.model_validate_json(artifact_path.read_text())
        trusted = (
            corrected_answers[question_id]
            if question_id in reviewed
            else original_answers[question_id]
        )
        if selected != trusted:
            raise ValueError("judge handoff selected answer differs from trusted writing")
    for question_id, artifact_path in unavailable_artifacts.items():
        unavailable = QuestionUnavailableArtifact.model_validate_json(
            artifact_path.read_text(encoding="utf-8")
        )
        if unavailable.question_id != question_id:
            raise ValueError("judge handoff unavailable artifact identity differs")
        from .question_packet_chapter import load_trusted_unavailable_adjudication

        load_trusted_unavailable_adjudication(
            project_root=project_root,
            path=(project_root / unavailable.adjudication_path),
            packet=unavailable_packets[question_id],
        )
    for question_id in sorted(reviewed):
        review_dir = final_review_dirs[question_id]
        validate_blind_review_artifacts(
            packet=packets[question_id],
            approved_answer=approved_answers[question_id],
            experimental_answer=corrected_answers[question_id],
            output_dir=review_dir,
            project_root=project_root,
            profile_name=profile_name,
            profiles_path=profiles_path,
            reasoning_effort=reasoning_effort,
        )
        review_manifest_path = review_dir / "blind-review-manifest.json"
        review_manifest = json.loads(review_manifest_path.read_text())
        binding = json.loads((review_dir / "final-review-policy-binding.json").read_text())
        review = BlindQuestionQualityReview.model_validate_json(
            (review_dir / "output.json").read_text()
        )
        residual = ResidualQuestionConcern.model_validate_json(
            residual_artifacts[question_id].read_text()
        )
        if (
            residual.question_id != question_id
            or residual != residual_question_concern(manifest=review_manifest, review=review)
            or binding.get("question_id") != question_id
            or binding.get("schema_version") != "question_final_review_policy_binding_v1"
            or binding.get("final_review_ordinal") != 1
            or binding.get("policy_sha256") != sha256(policy_path.read_bytes()).hexdigest()
            or binding.get("review_manifest_sha256")
            != sha256(review_manifest_path.read_bytes()).hexdigest()
        ):
            raise ValueError("judge handoff residual is not bound to its final review")
    payload = {
        "schema_version": "question_judge_handoff_v1",
        "question_count": 80,
        "questions": {
            question_id: {
                "answer_path": str(path),
                "answer_sha256": sha256(path.read_bytes()).hexdigest(),
                "residual_concern_path": (
                    str(residual_artifacts[question_id])
                    if question_id in residual_artifacts
                    else None
                ),
                "residual_concern_sha256": (
                    sha256(residual_artifacts[question_id].read_bytes()).hexdigest()
                    if question_id in residual_artifacts
                    else None
                ),
            }
            for question_id, path in sorted(question_artifacts.items())
        } | {
            question_id: {
                "answer_path": None,
                "answer_sha256": None,
                "unavailable_path": str(path),
                "unavailable_sha256": sha256(path.read_bytes()).hexdigest(),
                "residual_concern_path": None,
                "residual_concern_sha256": None,
            }
            for question_id, path in sorted(unavailable_artifacts.items())
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = [
    "QuestionCorrectionPrompts",
    "ResidualQuestionConcern",
    "build_question_correction_prompt",
    "build_question_judge_handoff",
    "experimental_review_findings",
    "load_question_correction_prompts",
    "persist_residual_question_concern",
    "residual_question_concern",
    "run_final_question_review",
    "run_question_correction",
    "validate_question_correction",
]
