"""Strict transport and canonical contracts for focused question verification."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from .question_evidence_packet_models import QuestionEvidencePacket


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
    unresolved_reopen_request_ids: tuple[str, ...] = ()
    additional_omitted_evidence_ids: tuple[str, ...] = ()
    final_gate: Literal["pass", "fail"]
    rationale: str = Field(min_length=30)

    @model_validator(mode="after")
    def validate_gate(self) -> FocusedQuestionVerification:
        blocking = self.chronology_status != "pass"
        blocking = blocking or bool(
            self.unresolved_reopen_request_ids or self.additional_omitted_evidence_ids
        )
        blocking = blocking or any(
            item.status == "materially_omitted" for item in self.priority_evidence_checks
        )
        blocking = blocking or any(
            item.verdict != "rejected" for item in self.proposed_finding_checks
        )
        if self.final_gate != ("fail" if blocking else "pass"):
            raise ValueError("focused verifier final gate contradicts its checks")
        return self


def verification_response_model(
    packet: QuestionEvidencePacket,
    finding_ids: tuple[str, ...],
    *,
    contract_version: int = 2,
    unresolved_reopen_ids: tuple[str, ...] = (),
) -> type[BaseModel]:
    reopenable_ids = tuple(
        item
        for item in packet.coverage.reopenable_evidence_ids
        if contract_version == 1 or item not in unresolved_reopen_ids
    )
    identity = (
        (packet.question_id, *packet.coverage.required_evidence_ids, *reopenable_ids, *finding_ids)
        if contract_version == 1
        else (
            str(contract_version),
            packet.question_id,
            *packet.coverage.required_evidence_ids,
            *reopenable_ids,
            *finding_ids,
        )
    )
    digest = sha256("\n".join(identity).encode()).hexdigest()[:12]
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
    fields: dict[str, tuple[object, object]] = {
        "question_id": (str, ...),
        "chronology_status": (Literal["pass", "fail", "uncertain"], ...),
        "chronology_finding": (str, Field(min_length=20)),
        "priority_evidence_checks": (evidence_ledger, ...),
        "proposed_finding_checks": (finding_ledger, ...),
        "additional_omitted_evidence_ids": omission_field,
    }
    if contract_version == 1:
        fields["final_gate"] = (Literal["pass", "fail"], ...)
    fields["rationale"] = (str, Field(min_length=30))
    return create_model(
        f"FocusedQuestionVerificationResponse_{digest}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def canonical_verification(
    response: BaseModel,
    packet: QuestionEvidencePacket,
    finding_ids: tuple[str, ...],
    *,
    contract_version: int = 2,
    unresolved_reopen_ids: tuple[str, ...] = (),
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
    payload["unresolved_reopen_request_ids"] = (
        list(unresolved_reopen_ids) if contract_version >= 2 else []
    )
    if contract_version >= 2:
        blocking = payload["chronology_status"] != "pass"
        blocking = blocking or bool(
            payload["unresolved_reopen_request_ids"]
            or payload["additional_omitted_evidence_ids"]
        )
        blocking = blocking or any(
            item["status"] == "materially_omitted"
            for item in payload["priority_evidence_checks"]
        )
        blocking = blocking or any(
            item["verdict"] != "rejected" for item in payload["proposed_finding_checks"]
        )
        payload["final_gate"] = "fail" if blocking else "pass"
    return FocusedQuestionVerification.model_validate(payload)


__all__ = ["FocusedQuestionVerification", "canonical_verification", "verification_response_model"]
