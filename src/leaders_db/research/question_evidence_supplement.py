"""Prospective, hash-bound additions to a trusted question evidence package."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .corpus_reader_models import BoundEvidence
from .question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    EvidenceDisposition,
    QuestionCoverageChecklist,
    _ids_digest,
)
from .question_evidence_packets import load_trusted_chapter_question_evidence_package


class EvidenceSupplementSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extracted_artifact_path: str
    extracted_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class QuestionEvidenceSupplement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_evidence_supplement_v1"] = (
        "question_evidence_supplement_v1"
    )
    base_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    question_id: str
    sources: tuple[EvidenceSupplementSource, ...] = Field(min_length=1)
    evidence: tuple[BoundEvidence, ...] = Field(min_length=1)
    independent_review_path: str
    independent_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_inventory(self) -> QuestionEvidenceSupplement:
        if not self.question_id.startswith(f"{self.chapter_id}."):
            raise ValueError("supplement question belongs to another chapter")
        source_ids = [item.source_id for item in self.sources]
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(source_ids) != len(set(source_ids)) or len(evidence_ids) != len(
            set(evidence_ids)
        ):
            raise ValueError("supplement source and evidence IDs must be unique")
        if set(source_ids) != {item.source_id for item in self.evidence}:
            raise ValueError("supplement evidence must use every bound source exactly")
        if any(
            self.question_id not in item.question_ids
            or item.verification_status != "accepted"
            or sha256(item.exact_excerpt.encode()).hexdigest() != item.excerpt_sha256
            for item in self.evidence
        ):
            raise ValueError("supplement evidence is not accepted and directly mapped")
        return self


class QuestionEvidenceSupplementReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["question_evidence_supplement_review_v1"] = (
        "question_evidence_supplement_review_v1"
    )
    base_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supplement_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_id: str
    reviewed_evidence_ids: tuple[str, ...] = Field(min_length=1)
    review_gate: Literal["pass"] = "pass"
    limitations_confirmed: Literal[True] = True


def build_supplemented_question_package(
    *,
    project_root: Path,
    base_package_path: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    supplement_path: Path,
    output_path: Path,
) -> Path:
    """Build a fresh package only after trusted base and supplement reconstruction."""

    result = _construct_supplemented_question_package(
        project_root=project_root,
        base_package_path=base_package_path,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
        supplement_path=supplement_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def load_trusted_supplemented_question_package(
    *,
    project_root: Path,
    package_path: Path,
    base_package_path: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    supplement_path: Path,
) -> ChapterQuestionEvidencePackage:
    """Reload a supplemented package by reconstructing it from all bound inputs."""

    saved = ChapterQuestionEvidencePackage.model_validate_json(package_path.read_bytes())
    expected = _construct_supplemented_question_package(
        project_root=project_root,
        base_package_path=base_package_path,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
        supplement_path=supplement_path,
    )
    if saved != expected:
        raise ValueError("supplemented question package differs from trusted reconstruction")
    return saved


def _construct_supplemented_question_package(
    *,
    project_root: Path,
    base_package_path: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    supplement_path: Path,
) -> ChapterQuestionEvidencePackage:

    base = load_trusted_chapter_question_evidence_package(
        project_root=project_root,
        package_path=base_package_path,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
    )
    raw = supplement_path.read_bytes()
    supplement = QuestionEvidenceSupplement.model_validate_json(raw)
    if supplement.base_package_sha256 != _digest(base_package_path):
        raise ValueError("evidence supplement differs from its trusted base package")
    if supplement.chapter_id != base.chapter_id:
        raise ValueError("evidence supplement differs from its trusted base chapter")
    _validate_dependencies(project_root, supplement, raw)
    additions = {item.evidence_id: item for item in supplement.evidence}
    existing_ids = {item.evidence_id for item in base.complete_ledger_dispositions}
    if existing_ids & set(additions):
        raise ValueError("evidence supplement reuses an existing evidence ID")
    packets = []
    for packet in base.packets:
        if packet.question_id != supplement.question_id:
            packets.append(packet)
            continue
        required = tuple(item.evidence_id for item in supplement.evidence)
        records = (*packet.priority_evidence, *supplement.evidence)
        candidates = (*packet.candidate_index, *(_compact(item) for item in supplement.evidence))
        items = (*packet.coverage.items, *(
            EvidenceCoverageItem(
                evidence_id=item.evidence_id,
                requirement="must_address",
                carries_attribution=bool(item.ruler_attribution.strip()),
                carries_period_fit=bool(item.period_fit.strip()),
                carries_limitations=bool(item.limitations),
            )
            for item in supplement.evidence
        ))
        packets.append(
            packet.model_copy(
                update={
                    "priority_evidence": records,
                    "source_routed_priority_evidence_ids": tuple(
                        item.evidence_id
                        for item in records
                        if packet.question_id in item.question_ids
                    ),
                    "selection_added_priority_evidence_ids": tuple(
                        item.evidence_id
                        for item in records
                        if packet.question_id not in item.question_ids
                    ),
                    "candidate_index": candidates,
                    "direct_evidence_count": packet.direct_evidence_count + len(additions),
                    "favorable_evidence_ids": tuple(
                        item.evidence_id
                        for item in candidates
                        if item.polarity.lower() == "favorable"
                    ),
                    "adverse_evidence_ids": tuple(
                        item.evidence_id
                        for item in candidates
                        if item.polarity.lower() == "adverse"
                    ),
                    "mixed_or_context_evidence_ids": tuple(
                        item.evidence_id
                        for item in candidates
                        if item.polarity.lower() not in {"favorable", "adverse"}
                    ),
                    "coverage": QuestionCoverageChecklist(
                        question_id=packet.question_id,
                        items=items,
                        required_evidence_ids=(
                            *packet.coverage.required_evidence_ids,
                            *required,
                        ),
                        reopenable_evidence_ids=packet.coverage.reopenable_evidence_ids,
                        adjudicated_nonmaterial_evidence_ids=(
                            packet.coverage.adjudicated_nonmaterial_evidence_ids
                        ),
                        favorable_available=any(
                            item.polarity.lower() == "favorable" for item in candidates
                        ),
                        adverse_available=any(
                            item.polarity.lower() == "adverse" for item in candidates
                        ),
                        mixed_or_context_available=any(
                            item.polarity.lower() not in {"favorable", "adverse"}
                            for item in candidates
                        ),
                    ),
                }
            )
        )
    all_ids = (*existing_ids, *additions)
    result = base.model_copy(
        update={
            "schema_version": "chapter_question_evidence_package_v2",
            "base_package_sha256": _digest(base_package_path),
            "evidence_supplement_sha256": sha256(raw).hexdigest(),
            "complete_ledger_evidence_count": len(all_ids),
            "complete_ledger_ids_sha256": _ids_digest(all_ids),
            "packets": tuple(packets),
            "chapter_candidate_ids": tuple(
                sorted((*base.chapter_candidate_ids, *additions))
            ),
            "complete_ledger_dispositions": (
                *base.complete_ledger_dispositions,
                *(
                    EvidenceDisposition(
                        evidence_id=item.evidence_id,
                        direct_question_ids=(supplement.question_id,),
                        sibling_chapter_question_ids=tuple(
                            qid for qid in item.question_ids if qid != supplement.question_id
                        ),
                        disposition="direct",
                    )
                    for item in supplement.evidence
                ),
            ),
        }
    )
    return ChapterQuestionEvidencePackage.model_validate(result.model_dump())


def _validate_dependencies(
    project_root: Path, supplement: QuestionEvidenceSupplement, raw: bytes
) -> None:
    root = project_root.resolve()
    for source in supplement.sources:
        path = (root / source.artifact_path).resolve()
        if not path.is_relative_to(root) or _digest(path) != source.artifact_sha256:
            raise ValueError("evidence supplement source artifact differs")
        extracted_path = (root / source.extracted_artifact_path).resolve()
        if (
            not extracted_path.is_relative_to(root)
            or _digest(extracted_path) != source.extracted_artifact_sha256
        ):
            raise ValueError("evidence supplement extracted source artifact differs")
        extracted_text = extracted_path.read_text(encoding="utf-8")
        for evidence in (
            item for item in supplement.evidence if item.source_id == source.source_id
        ):
            if evidence.raw_sha256 != source.artifact_sha256:
                raise ValueError("evidence record raw hash differs from its source artifact")
            if evidence.exact_excerpt not in extracted_text:
                raise ValueError("evidence excerpt is absent from its bound source extraction")
    review_path = (root / supplement.independent_review_path).resolve()
    if (
        not review_path.is_relative_to(root)
        or _digest(review_path) != supplement.independent_review_sha256
    ):
        raise ValueError("evidence supplement review artifact differs")
    review = QuestionEvidenceSupplementReview.model_validate_json(review_path.read_text())
    payload = json.loads(raw)
    payload.pop("independent_review_path")
    payload.pop("independent_review_sha256")
    payload_hash = sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        review.base_package_sha256 != supplement.base_package_sha256
        or review.supplement_payload_sha256 != payload_hash
        or review.question_id != supplement.question_id
        or review.reviewed_evidence_ids
        != tuple(item.evidence_id for item in supplement.evidence)
    ):
        raise ValueError("evidence supplement review does not bind the exact evidence")


def _compact(item: BoundEvidence) -> CompactEvidenceCandidate:
    return CompactEvidenceCandidate(
        evidence_id=item.evidence_id,
        fact_summary=item.fact_summary,
        publisher=item.publisher,
        polarity=item.polarity,
        period_fit=item.period_fit,
        ruler_attribution=item.ruler_attribution,
        limitations=item.limitations,
        question_ids=item.question_ids,
    )


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "EvidenceSupplementSource",
    "QuestionEvidenceSupplement",
    "QuestionEvidenceSupplementReview",
    "build_supplemented_question_package",
]
