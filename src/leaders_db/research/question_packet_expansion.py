"""Deterministically promote selected compact candidates to exact question evidence."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .corpus_reader_models import BoundEvidence
from .question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    QuestionEvidencePacket,
)
from .question_evidence_packets import load_trusted_chapter_question_evidence_package


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


class QuestionPacketExpansionConfig(BaseModel):
    """A small, review-bound list of candidates promoted to exact evidence."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    source_review: str
    source_review_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chapters: dict[str, dict[str, tuple[str, ...]]]

    @field_validator("chapters")
    @classmethod
    def validate_additions(
        cls, chapters: dict[str, dict[str, tuple[str, ...]]]
    ) -> dict[str, dict[str, tuple[str, ...]]]:
        for chapter_id, questions in chapters.items():
            expected = {f"{chapter_id}.{number}" for number in range(1, 11)}
            if set(questions) != expected:
                raise ValueError("expansion must cover the chapter's ten questions")
            if any(not ids or len(ids) != len(set(ids)) for ids in questions.values()):
                raise ValueError("each question expansion must contain unique IDs")
        return chapters


def load_question_packet_expansion(
    *, project_root: Path, config_path: Path, chapter_id: str
) -> dict[str, tuple[str, ...]]:
    """Load additions only when their source review manifest is unchanged."""

    config = QuestionPacketExpansionConfig.model_validate(
        yaml.safe_load(config_path.read_bytes())
    )
    review_dir = (project_root / "research/runs" / config.source_review).resolve()
    runs_root = (project_root / "research/runs").resolve()
    manifest_path = review_dir / "review-manifest.json"
    if (
        not review_dir.is_relative_to(runs_root)
        or not manifest_path.is_file()
        or sha256(manifest_path.read_bytes()).hexdigest()
        != config.source_review_manifest_sha256
    ):
        raise ValueError("question expansion source review is missing or changed")
    try:
        additions = config.chapters[chapter_id]
    except KeyError as exc:
        raise ValueError(f"question expansion does not contain {chapter_id}") from exc
    outer = json.loads(manifest_path.read_text())
    artifacts = {item["question_id"]: item for item in outer["artifacts"]}
    if set(artifacts) != set(additions):
        raise ValueError("source review does not contain the expansion questions")
    for question_id, expected_ids in additions.items():
        child_path = review_dir / artifacts[question_id]["artifact_path"]
        if sha256(child_path.read_bytes()).hexdigest() != artifacts[question_id][
            "artifact_sha256"
        ]:
            raise ValueError("source review child manifest changed")
        child = json.loads(child_path.read_text())
        output_path = child_path.parent / "output.json"
        review = json.loads(output_path.read_text())
        if (
            child["question_id"] != question_id
            or _payload_hash(review) != child["review_sha256"]
            or tuple(review["strongest_omitted_evidence_ids"]) != expected_ids
        ):
            raise ValueError("expansion differs from the source review recommendation")
    return additions


def load_expanded_question_evidence_package(
    *,
    project_root: Path,
    base_package_path: Path,
    expanded_package_path: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    config_path: Path,
) -> ChapterQuestionEvidencePackage:
    """Reconstruct and compare an expanded package before it is used."""

    base = load_trusted_chapter_question_evidence_package(
        project_root=project_root,
        package_path=base_package_path,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
    )
    additions = load_question_packet_expansion(
        project_root=project_root,
        config_path=config_path,
        chapter_id=base.chapter_id,
    )
    expected = expand_question_evidence_package(
        package=base,
        judge_package_path=judge_package_path,
        additions_by_question=additions,
    )
    actual = ChapterQuestionEvidencePackage.model_validate_json(
        expanded_package_path.read_text()
    )
    if actual != expected:
        raise ValueError("expanded question package differs from its exact derivation")
    return actual


def expand_question_evidence_package(
    *,
    package: ChapterQuestionEvidencePackage,
    judge_package_path: Path,
    additions_by_question: dict[str, tuple[str, ...]],
) -> ChapterQuestionEvidencePackage:
    """Return the same chapter package with named candidates reopened exactly."""

    raw = json.loads(judge_package_path.read_text())
    if sha256(judge_package_path.read_bytes()).hexdigest() != package.source_package_sha256:
        raise ValueError("judge package does not match the base question package")
    rows = [BoundEvidence.model_validate(item) for item in raw["evidence"]]
    ids = [item.evidence_id for item in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("judge package contains duplicate evidence IDs")
    ledger = {item.evidence_id: item for item in rows}
    packets = tuple(
        _expand_packet(packet, ledger, additions_by_question.get(packet.question_id, ()))
        for packet in package.packets
    )
    return package.model_copy(update={"packets": packets})


def _expand_packet(
    packet: QuestionEvidencePacket,
    ledger: dict[str, BoundEvidence],
    additions: tuple[str, ...],
) -> QuestionEvidencePacket:
    candidate_ids = {item.evidence_id for item in packet.candidate_index}
    existing = {item.evidence_id for item in packet.priority_evidence}
    if len(additions) != len(set(additions)) or not set(additions).issubset(candidate_ids):
        raise ValueError("expanded evidence must be unique question candidates")
    new_ids = tuple(item for item in additions if item not in existing)
    priority = packet.priority_evidence + tuple(ledger[item] for item in new_ids)
    required = tuple(item.evidence_id for item in priority)
    required_set = set(required)
    coverage = packet.coverage.model_copy(
        update={
            "items": tuple(
                item.model_copy(
                    update={
                        "requirement": (
                            "must_address"
                            if item.evidence_id in required_set
                            else "available_for_reopen"
                        )
                    }
                )
                for item in packet.coverage.items
            ),
            "required_evidence_ids": required,
            "reopenable_evidence_ids": tuple(
                item.evidence_id
                for item in packet.candidate_index
                if item.evidence_id not in required_set
            ),
        }
    )
    return QuestionEvidencePacket.model_validate(
        packet.model_copy(
            update={"priority_evidence": priority, "coverage": coverage}
        ).model_dump()
    )


__all__ = [
    "expand_question_evidence_package",
    "load_expanded_question_evidence_package",
    "load_question_packet_expansion",
]
