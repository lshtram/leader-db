"""Diagnostic writer and deterministic checks for one trusted question packet."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

import tiktoken
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
)

from .control_flow import enforce_model_action
from .corpus_reader_runner import ModelCallCoordinator, execute_json_model
from .model_call_budget import RunUsageBudgetTracker, StageBudgetTracker
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_answer_validation import validate_question_answer
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_writer_prompt import (
    build_question_writer_prompt,
    project_predecessor_answer,
)


class AnswerEvidenceDisposition(BaseModel):
    """How one required exact record materially affected the answer."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    role: Literal["supporting", "contrary_or_qualifying", "limitation_only"]
    material_point: str = Field(min_length=20)


class _AnswerEvidenceDispositionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["supporting", "contrary_or_qualifying", "limitation_only"]
    material_point: str = Field(min_length=20)


def _reject_evidence_id_text(value: str) -> str:
    if re.search(r"\b(?:BATCH-[A-Z0-9-]+|E-[A-Z0-9]+|SRC:[A-Z0-9]+)\b", value):
        raise ValueError("transport prose must not contain evidence IDs")
    return value


_EvidenceFreeText = Annotated[str, AfterValidator(_reject_evidence_id_text)]


class _TransportEvidenceDispositionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["supporting", "contrary_or_qualifying", "limitation_only"]
    material_point: _EvidenceFreeText = Field(min_length=20)


class _TransportReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reason: _EvidenceFreeText = Field(min_length=20)


class EvidenceReopenRequest(BaseModel):
    """One compact candidate whose exact record may materially change the answer."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("reopen reason must contain at least 20 non-space characters")
        return stripped


class _DiagnosticQuestionAnswerBase(BaseModel):
    """Fields shared by the transport response and canonical saved answer."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: str = Field(min_length=30)
    limitations_and_gaps: tuple[str, ...] = ()
    reopen_requests: tuple[EvidenceReopenRequest, ...] = ()


class _DiagnosticQuestionAnswerTransportBase(BaseModel):
    """Non-prose fields shared by the current structured transport response."""

    model_config = ConfigDict(extra="forbid")

    question_id: str


class DiagnosticQuestionAnswer(_DiagnosticQuestionAnswerBase):
    """Canonical saved answer with an ordered evidence-disposition ledger."""

    evidence_dispositions: tuple[AnswerEvidenceDisposition, ...]


def write_diagnostic_question_answer(
    *,
    project_root: Path,
    packet: QuestionEvidencePacket,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    predecessor_answer: dict | None = None,
    budget_tracker: StageBudgetTracker | None = None,
    reasoning_effort: str | None = None,
    call_coordinator: ModelCallCoordinator | None = None,
    run_budget_tracker: RunUsageBudgetTracker | None = None,
) -> tuple[DiagnosticQuestionAnswer, dict]:
    """Write one diagnostic answer from exact priority evidence and a reopen index."""

    enforce_model_action(project_root, "question_writing", role="production")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("question writer requires the OpenAI Codex subscription surface")
    prompts, prompt_config_hash = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    projected_predecessor, excluded_predecessor_ids = project_predecessor_answer(
        packet, predecessor_answer
    )
    prompt = build_question_writer_prompt(packet, prompts, predecessor_answer)
    estimated_tokens = len(tiktoken.get_encoding("o200k_base").encode(prompt))
    if profile.context_window is None or estimated_tokens + 12_000 > int(
        profile.context_window * 0.9
    ):
        raise ValueError("question writer request exceeds context safety margin")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "request-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "diagnostic_question_writer_request_v1",
                "production_status": "diagnostic_only",
                "api_key_used": False,
                "profile": profile_name,
                "model": profile.model,
                "reasoning_effort": reasoning_effort,
                "prompt_config_version": prompts.version,
                "prompt_config_sha256": prompt_config_hash,
                "question_id": packet.question_id,
                "estimated_input_tokens": estimated_tokens,
                "required_evidence_ids": list(packet.coverage.required_evidence_ids),
                "reopenable_evidence_ids": list(packet.coverage.reopenable_evidence_ids),
                "predecessor_answer_included": bool(projected_predecessor),
                "predecessor_excluded_evidence_ids": list(excluded_predecessor_ids),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
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
        response_model = _question_answer_response_model(packet.coverage.required_evidence_ids)
        response = execute_json_model(
            project_root,
            profile,
            prompt,
            response_model,
            output_dir,
            **execution_kwargs,
        )
        answer = _canonical_question_answer(response, packet.coverage.required_evidence_ids)
    except Exception:
        if call_coordinator is not None:
            call_coordinator.publish_failure()
        raise
    accepted, normalization = normalize_optional_reopen_requests(packet, answer)
    raw_path = output_dir / "output.json"
    normalization["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
    accepted_path = output_dir / "accepted-output.json"
    accepted_path.write_text(accepted.model_dump_json(indent=2) + "\n", encoding="utf-8")
    normalization["accepted_output_sha256"] = sha256(accepted_path.read_bytes()).hexdigest()
    (output_dir / "normalization-ledger.json").write_text(
        json.dumps(normalization, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = validate_question_answer(packet, accepted)
    (output_dir / "deterministic-validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if validation["functional_gate"] != "pass":
        if call_coordinator is not None:
            call_coordinator.publish_failure()
        raise ValueError("diagnostic question answer failed deterministic validation")
    return accepted, validation


def _question_answer_response_model(
    required_evidence_ids: tuple[str, ...],
) -> type[BaseModel]:
    """Build a strict response whose prose citations are exact-ID enums."""

    if not required_evidence_ids:
        raise ValueError("question writer requires at least one exact evidence ID")
    digest = sha256("\n".join(required_evidence_ids).encode()).hexdigest()[:12]
    citation_id = Literal.__getitem__(required_evidence_ids)
    section = create_model(
        f"CitedAnswerSection_{digest}",
        __config__=ConfigDict(extra="forbid"),
        text=(
            _EvidenceFreeText,
            Field(min_length=20, max_length=1000, pattern=r"^[^\[\]\r\n]+$"),
        ),
        citation_ids=(tuple[citation_id, ...], Field(min_length=1)),
    )
    ledger = _required_evidence_ledger(
        required_evidence_ids, digest, _TransportEvidenceDispositionDetail
    )
    return create_model(
        f"DiagnosticQuestionAnswerResponse_{digest}",
        __base__=_DiagnosticQuestionAnswerTransportBase,
        answer_sections=(tuple[section, ...], Field(min_length=1)),
        limitation_sections=(tuple[section, ...], ...),
        reopen_requests=(tuple[_TransportReopenRequest, ...], ()),
        evidence_dispositions=(ledger, ...),
    )


def _legacy_question_answer_response_model(
    required_evidence_ids: tuple[str, ...],
) -> type[BaseModel]:
    """Reconstruct the keyed prompt-v10 through prompt-v12 transport."""

    digest = sha256("\n".join(required_evidence_ids).encode()).hexdigest()[:12]
    ledger = _required_evidence_ledger(required_evidence_ids, digest)
    return create_model(
        f"LegacyDiagnosticQuestionAnswerResponse_{digest}",
        __base__=_DiagnosticQuestionAnswerBase,
        evidence_dispositions=(ledger, ...),
    )


def _required_evidence_ledger(
    required_evidence_ids: tuple[str, ...],
    digest: str,
    detail_model: type[BaseModel] = _AnswerEvidenceDispositionDetail,
) -> type[BaseModel]:
    fields = {
        f"item_{index:04d}": (
            detail_model,
            Field(alias=evidence_id),
        )
        for index, evidence_id in enumerate(required_evidence_ids, start=1)
    }
    return create_model(
        f"RequiredEvidenceLedger_{digest}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _canonical_question_answer(
    response: BaseModel, required_evidence_ids: tuple[str, ...]
) -> DiagnosticQuestionAnswer:
    """Convert the keyed transport ledger to the stable canonical tuple."""

    payload = response.model_dump(mode="json", by_alias=True)
    raw_ledger = payload.pop("evidence_dispositions")
    if not isinstance(raw_ledger, dict):
        raise ValueError("question response evidence ledger must be an object")
    sections = payload.pop("answer_sections", None)
    if sections is not None:
        payload["answer"] = "\n\n".join(
            _render_cited_section(section["text"], section["citation_ids"])
            for section in sections
        )
        payload["limitations_and_gaps"] = [
            _render_cited_section(section["text"], section["citation_ids"])
            for section in payload.pop("limitation_sections")
        ]
    payload["evidence_dispositions"] = [
        {"evidence_id": evidence_id, **raw_ledger[evidence_id]}
        for evidence_id in required_evidence_ids
    ]
    return DiagnosticQuestionAnswer.model_validate(payload)


def _render_cited_section(text: str, citation_ids: list[str]) -> str:
    stripped = text.strip()
    citation = f"[{'; '.join(citation_ids)}]"
    if stripped[-1] in ".?!":
        return f"{stripped[:-1].rstrip()} {citation}{stripped[-1]}"
    return f"{stripped} {citation}"


def normalize_optional_reopen_requests(
    packet: QuestionEvidencePacket, answer: DiagnosticQuestionAnswer
) -> tuple[DiagnosticQuestionAnswer, dict[str, object]]:
    """Discard only advisory reopen IDs outside the immutable candidate index."""

    allowed = set(packet.coverage.reopenable_evidence_ids)
    rejected = tuple(item for item in answer.reopen_requests if item.evidence_id not in allowed)
    accepted = tuple(item for item in answer.reopen_requests if item.evidence_id in allowed)
    normalized = answer.model_copy(update={"reopen_requests": accepted})
    return normalized, {
        "schema_version": "optional_reopen_normalization_v1",
        "question_id": packet.question_id,
        "rule": "discard_unknown_advisory_reopen_ids_only",
        "normalization_applied": bool(rejected),
        "accepted_reopen_ids": [item.evidence_id for item in accepted],
        "rejected_reopen_ids": [item.evidence_id for item in rejected],
        "mandatory_evidence_dispositions_changed": False,
        "answer_text_changed": False,
    }


def load_normalized_question_answer(
    packet: QuestionEvidencePacket, output_dir: Path
) -> DiagnosticQuestionAnswer:
    """Reconstruct and verify the accepted answer from immutable raw output."""

    raw_path = output_dir / "output.json"
    accepted_path = output_dir / "accepted-output.json"
    ledger_path = output_dir / "normalization-ledger.json"
    raw_text = raw_path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    request = json.loads((output_dir / "request-manifest.json").read_bytes())
    prompt_version = request.get("prompt_config_version")
    if type(prompt_version) is not int or prompt_version < 1:
        raise ValueError("question writer request has an invalid prompt version")
    if prompt_version >= 13:
        if "answer_sections" not in payload or "answer" in payload:
            raise ValueError("current question writer raw output uses a legacy transport")
        response_model = _question_answer_response_model(
            packet.coverage.required_evidence_ids
        )
        response = response_model.model_validate_json(raw_text)
        raw = _canonical_question_answer(response, packet.coverage.required_evidence_ids)
    else:
        if "answer_sections" in payload:
            raise ValueError("legacy question writer raw output uses the current transport")
        response_model = _legacy_question_answer_response_model(
            packet.coverage.required_evidence_ids
        )
        try:
            response = response_model.model_validate_json(raw_text)
            raw = _canonical_question_answer(response, packet.coverage.required_evidence_ids)
        except ValidationError:
            raw = DiagnosticQuestionAnswer.model_validate_json(raw_text)
    expected, ledger = normalize_optional_reopen_requests(packet, raw)
    ledger["raw_output_sha256"] = sha256(raw_path.read_bytes()).hexdigest()
    ledger["accepted_output_sha256"] = sha256(accepted_path.read_bytes()).hexdigest()
    actual = DiagnosticQuestionAnswer.model_validate_json(accepted_path.read_text(encoding="utf-8"))
    saved_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if actual != expected or saved_ledger != ledger:
        raise ValueError("normalized question answer does not match immutable raw output")
    return actual


__all__ = [
    "AnswerEvidenceDisposition",
    "DiagnosticQuestionAnswer",
    "EvidenceReopenRequest",
    "build_question_writer_prompt",
    "validate_question_answer",
    "write_diagnostic_question_answer",
]
