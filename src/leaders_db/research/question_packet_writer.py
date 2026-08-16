"""Diagnostic writer and deterministic checks for one trusted question packet."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
)

from .citation_table_rows import TableLineSpan, resolve_table_line
from .control_flow import enforce_model_action
from .corpus_reader_models import BoundEvidence
from .corpus_reader_runner import ModelCallCoordinator, execute_json_model
from .model_call_budget import RunUsageBudgetTracker, StageBudgetTracker
from .model_profiles import load_research_model_profiles
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_prompts import QuestionPacketPrompts, load_question_packet_prompts


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
    """Build a strict object schema with one required key per evidence ID."""

    digest = sha256("\n".join(required_evidence_ids).encode()).hexdigest()[:12]
    fields = {
        f"item_{index:04d}": (
            _AnswerEvidenceDispositionDetail,
            Field(alias=evidence_id),
        )
        for index, evidence_id in enumerate(required_evidence_ids, start=1)
    }
    ledger = create_model(
        f"RequiredEvidenceLedger_{digest}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return create_model(
        f"DiagnosticQuestionAnswerResponse_{digest}",
        __base__=_DiagnosticQuestionAnswerBase,
        evidence_dispositions=(ledger, ...),
    )


def _canonical_question_answer(
    response: BaseModel, required_evidence_ids: tuple[str, ...]
) -> DiagnosticQuestionAnswer:
    """Convert the keyed transport ledger to the stable canonical tuple."""

    payload = response.model_dump(mode="json", by_alias=True)
    raw_ledger = payload.pop("evidence_dispositions")
    if not isinstance(raw_ledger, dict):
        raise ValueError("question response evidence ledger must be an object")
    payload["evidence_dispositions"] = [
        {"evidence_id": evidence_id, **raw_ledger[evidence_id]}
        for evidence_id in required_evidence_ids
    ]
    return DiagnosticQuestionAnswer.model_validate(payload)


def normalize_optional_reopen_requests(
    packet: QuestionEvidencePacket, answer: DiagnosticQuestionAnswer
) -> tuple[DiagnosticQuestionAnswer, dict[str, object]]:
    """Discard only advisory reopen IDs outside the immutable candidate index."""

    allowed = {item.evidence_id for item in packet.candidate_index}
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
    response_model = _question_answer_response_model(packet.coverage.required_evidence_ids)
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


def build_question_writer_prompt(
    packet: QuestionEvidencePacket,
    prompts: QuestionPacketPrompts,
    predecessor_answer: dict | None = None,
    *,
    compact_table_citations: bool = False,
    source_units: dict[tuple[str, int], str] | None = None,
) -> str:
    """Serialize a single-question writing task without the full ruler ledger."""

    exact = [
        _writer_evidence_payload(
            item,
            compact_table_citations=compact_table_citations,
            source_units=source_units,
        )
        for item in packet.priority_evidence
    ]
    reopenable = set(packet.coverage.reopenable_evidence_ids)
    candidates = [
        item.model_dump(mode="json")
        for item in packet.candidate_index
        if item.evidence_id in reopenable
    ]
    return prompts.writer_template.format(
        question_id=packet.question_id,
        question=packet.question,
        predecessor_answer=json.dumps(predecessor_answer or {}, ensure_ascii=False),
        exact_evidence=json.dumps(exact, ensure_ascii=False),
        candidate_index=json.dumps(candidates, ensure_ascii=False),
    )


def _writer_evidence_payload(
    evidence: BoundEvidence,
    *,
    compact_table_citations: bool,
    source_units: dict[tuple[str, int], str] | None,
) -> dict:
    payload = evidence.model_dump(mode="json")
    if not compact_table_citations:
        return payload
    table_citations = [
        citation for citation in evidence.citations if isinstance(citation.span, TableLineSpan)
    ]
    if not table_citations or len(table_citations) != len(evidence.citations):
        raise ValueError("compact table transport requires only exact table citations")
    if source_units is None:
        raise ValueError("compact table transport requires frozen source units")
    for citation in table_citations:
        key = (evidence.source_id, citation.span.unit)
        if key not in source_units:
            raise ValueError("compact table transport source unit is unavailable")
        exact = resolve_table_line(
            source_units[key],
            citation.span,
            expected_source_id=evidence.source_id,
            expected_unit=citation.span.unit,
        )
        if exact != citation.exact_excerpt:
            raise ValueError("compact table citation differs from frozen source")
    payload.pop("exact_excerpt")
    payload.pop("excerpt_sha256")
    return payload


def validate_question_answer(
    packet: QuestionEvidencePacket, answer: DiagnosticQuestionAnswer
) -> dict:
    """Require a complete ledger and reject foreign inline citations before review."""

    required = set(packet.coverage.required_evidence_ids)
    reopenable = set(packet.coverage.reopenable_evidence_ids)
    reopen_ids = [item.evidence_id for item in answer.reopen_requests]
    reopened = set(reopen_ids)
    duplicate_reopen_requests = sorted({item for item in reopen_ids if reopen_ids.count(item) > 1})
    disposition_ids = [item.evidence_id for item in answer.evidence_dispositions]
    duplicate_dispositions = sorted(
        {item for item in disposition_ids if disposition_ids.count(item) > 1}
    )
    missing_dispositions = sorted(required - set(disposition_ids))
    unknown_dispositions = sorted(set(disposition_ids) - required)
    cited = set(disposition_ids)
    inline_ids = {
        evidence_id.strip()
        for group in re.findall(r"\[([^\[\]\r\n]+)\]", answer.answer)
        for evidence_id in group.split(";")
        if evidence_id.strip()
    }
    missing_inline_citations = sorted(required - inline_ids)
    unknown_inline_citations = sorted(inline_ids - required)
    unknown_citations = sorted(cited - required)
    missing_required = sorted(required - cited)
    unknown_reopen_requests = sorted(reopened - reopenable)
    return {
        "question_id": packet.question_id,
        "identity_matches": answer.question_id == packet.question_id,
        "required_evidence_count": len(required),
        "cited_evidence_count": len(cited),
        "missing_required_evidence_ids": missing_required,
        "unknown_citation_ids": unknown_citations,
        "inline_citation_count": len(inline_ids),
        "missing_inline_citation_ids": missing_inline_citations,
        "unknown_inline_citation_ids": unknown_inline_citations,
        "unknown_reopen_request_ids": unknown_reopen_requests,
        "duplicate_reopen_request_ids": duplicate_reopen_requests,
        "missing_evidence_disposition_ids": missing_dispositions,
        "unknown_evidence_disposition_ids": unknown_dispositions,
        "duplicate_evidence_disposition_ids": duplicate_dispositions,
        "functional_gate": (
            "pass"
            if answer.question_id == packet.question_id
            and not missing_required
            and not unknown_citations
            and not unknown_inline_citations
            and not unknown_reopen_requests
            and not duplicate_reopen_requests
            and not missing_dispositions
            and not unknown_dispositions
            and not duplicate_dispositions
            else "fail"
        ),
    }


__all__ = [
    "AnswerEvidenceDisposition",
    "DiagnosticQuestionAnswer",
    "EvidenceReopenRequest",
    "build_question_writer_prompt",
    "validate_question_answer",
    "write_diagnostic_question_answer",
]
