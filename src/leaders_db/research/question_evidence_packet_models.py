"""Validated contracts for deterministic question-level evidence packets."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .corpus_reader_models import BoundEvidence


class EvidenceDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    direct_question_ids: tuple[str, ...]
    sibling_chapter_question_ids: tuple[str, ...]
    disposition: Literal["direct", "chapter_context", "outside_chapter"]


class CompactEvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    fact_summary: str
    publisher: str
    polarity: str
    period_fit: str
    ruler_attribution: str
    limitations: tuple[str, ...]
    question_ids: tuple[str, ...]


class EvidenceCoverageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    requirement: Literal["must_address", "available_for_reopen"]
    carries_attribution: bool
    carries_period_fit: bool
    carries_limitations: bool


class QuestionCoverageChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    items: tuple[EvidenceCoverageItem, ...]
    required_evidence_ids: tuple[str, ...]
    reopenable_evidence_ids: tuple[str, ...]
    favorable_available: bool
    adverse_available: bool
    mixed_or_context_available: bool

    @model_validator(mode="after")
    def validate_partition(self) -> QuestionCoverageChecklist:
        item_ids = [item.evidence_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("coverage checklist contains duplicate evidence")
        required = {item.evidence_id for item in self.items if item.requirement == "must_address"}
        reopenable = {
            item.evidence_id
            for item in self.items
            if item.requirement == "available_for_reopen"
        }
        if required != set(self.required_evidence_ids) or reopenable != set(
            self.reopenable_evidence_ids
        ):
            raise ValueError("coverage checklist partitions do not reconcile")
        return self


class QuestionEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question: str
    priority_evidence: tuple[BoundEvidence, ...]
    candidate_index: tuple[CompactEvidenceCandidate, ...]
    direct_evidence_count: int = Field(ge=0)
    favorable_evidence_ids: tuple[str, ...]
    adverse_evidence_ids: tuple[str, ...]
    mixed_or_context_evidence_ids: tuple[str, ...]
    coverage: QuestionCoverageChecklist


class ChapterQuestionEvidencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["chapter_question_evidence_package_v1"] = (
        "chapter_question_evidence_package_v1"
    )
    chapter_id: str
    source_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_catalogue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete_ledger_evidence_count: int = Field(ge=0)
    complete_ledger_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    packets: tuple[QuestionEvidencePacket, ...] = Field(min_length=10, max_length=10)
    chapter_candidate_ids: tuple[str, ...]
    complete_ledger_dispositions: tuple[EvidenceDisposition, ...]

    @model_validator(mode="after")
    def validate_complete_package(self) -> ChapterQuestionEvidencePackage:
        expected = {f"{self.chapter_id}.{number}" for number in range(1, 11)}
        if {item.question_id for item in self.packets} != expected:
            raise ValueError("package must contain exactly the chapter's ten questions")
        disposition_ids = [item.evidence_id for item in self.complete_ledger_dispositions]
        if len(disposition_ids) != len(set(disposition_ids)):
            raise ValueError("ledger evidence must receive exactly one disposition")
        if len(disposition_ids) != self.complete_ledger_evidence_count or (
            _ids_digest(disposition_ids) != self.complete_ledger_ids_sha256
        ):
            raise ValueError("complete ledger count or identity hash does not reconcile")
        direct = {
            item.evidence_id
            for item in self.complete_ledger_dispositions
            if item.disposition == "direct"
        }
        if set(self.chapter_candidate_ids) != direct:
            raise ValueError("chapter candidate IDs do not match direct dispositions")
        for packet in self.packets:
            _validate_packet(packet, set(disposition_ids))
        return self


def _ids_digest(values) -> str:
    return sha256("\n".join(sorted(values)).encode()).hexdigest()


def _validate_packet(packet: QuestionEvidencePacket, ledger_ids: set[str]) -> None:
    if packet.coverage.question_id != packet.question_id:
        raise ValueError("packet and coverage question identities differ")
    priority = tuple(item.evidence_id for item in packet.priority_evidence)
    candidates = tuple(item.evidence_id for item in packet.candidate_index)
    if len(priority) != len(set(priority)) or priority != packet.coverage.required_evidence_ids:
        raise ValueError("priority evidence does not match required coverage")
    if candidates != tuple(item.evidence_id for item in packet.coverage.items) or not set(
        candidates
    ).issubset(ledger_ids):
        raise ValueError("candidate index does not match coverage or ledger")
    if tuple(item for item in candidates if item not in set(priority)) != (
        packet.coverage.reopenable_evidence_ids
    ):
        raise ValueError("reopenable evidence does not match non-priority candidates")
    by_id = {item.evidence_id: item for item in packet.candidate_index}
    direct = tuple(item for item in candidates if packet.question_id in by_id[item].question_ids)
    expected = (
        tuple(item for item in direct if by_id[item].polarity.lower() == "favorable"),
        tuple(item for item in direct if by_id[item].polarity.lower() == "adverse"),
        tuple(
            item
            for item in direct
            if by_id[item].polarity.lower() not in {"favorable", "adverse"}
        ),
    )
    if expected != (
        packet.favorable_evidence_ids,
        packet.adverse_evidence_ids,
        packet.mixed_or_context_evidence_ids,
    ) or packet.direct_evidence_count != len(direct):
        raise ValueError("direct evidence polarity partitions do not reconcile")
    flags = (
        any(by_id[item].polarity.lower() == "favorable" for item in candidates),
        any(by_id[item].polarity.lower() == "adverse" for item in candidates),
        any(by_id[item].polarity.lower() not in {"favorable", "adverse"} for item in candidates),
    )
    if flags != (
        packet.coverage.favorable_available,
        packet.coverage.adverse_available,
        packet.coverage.mixed_or_context_available,
    ):
        raise ValueError("coverage polarity availability does not match candidates")


__all__ = [
    "ChapterQuestionEvidencePackage",
    "CompactEvidenceCandidate",
    "EvidenceCoverageItem",
    "EvidenceDisposition",
    "QuestionCoverageChecklist",
    "QuestionEvidencePacket",
]
