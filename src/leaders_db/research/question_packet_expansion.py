"""Deterministically promote selected compact candidates to exact question evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .corpus_reader_models import BoundEvidence
from .question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    QuestionEvidencePacket,
)
from .question_evidence_packets import (
    _upgrade_legacy_provenance,
    load_trusted_chapter_question_evidence_package,
)
from .question_packet_expansion_legacy import load_question_packet_expansion


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


class MaterialDefectAddition(BaseModel):
    """One failed review's exact, hash-bound evidence recommendation."""

    model_config = ConfigDict(extra="forbid")

    review_manifest: str
    review_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def reject_duplicate_ids(cls, evidence_ids: tuple[str, ...]) -> tuple[str, ...]:
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("material-defect evidence IDs must be unique")
        return evidence_ids


class MaterialDefectReturnConfig(BaseModel):
    """One explicit, user-authorized return from review to evidence selection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_material_defect_return_v1"]
    source_run: str
    source_release_id: str
    source_preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_return_count: Literal[0]
    return_ordinal: Literal[1]
    user_authorized: Literal[True]
    chapters: dict[str, dict[str, MaterialDefectAddition]]

    @field_validator("chapters")
    @classmethod
    def validate_questions(
        cls, chapters: dict[str, dict[str, MaterialDefectAddition]]
    ) -> dict[str, dict[str, MaterialDefectAddition]]:
        if not chapters or any(not questions for questions in chapters.values()):
            raise ValueError("material-defect return must contain reviewed questions")
        for chapter_id, questions in chapters.items():
            expected = {f"{chapter_id}.{number}" for number in range(1, 11)}
            if not set(questions).issubset(expected):
                raise ValueError("material-defect return contains an invalid question")
        return chapters


@dataclass(frozen=True)
class _ReviewSnapshot:
    manifest_path: Path
    manifest_sha256: str
    output_path: Path
    output_sha256: str
    manifest: dict
    review: dict
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class MaterialDefectReturnReceipt:
    """One stable return snapshot shared by every chapter in a preflight."""

    config_path: Path
    config_sha256: str
    source_run: Path
    source_preflight_path: Path
    source_preflight_sha256: str
    source_release_id: str
    reviews: dict[str, _ReviewSnapshot]

    def additions_for(
        self, package: ChapterQuestionEvidencePackage
    ) -> dict[str, tuple[str, ...]]:
        additions = {}
        packets = {item.question_id: item for item in package.packets}
        for question_id, snapshot in self.reviews.items():
            if not question_id.startswith(f"{package.chapter_id}."):
                continue
            packet = packets[question_id]
            reopenable = set(packet.coverage.reopenable_evidence_ids)
            if (
                snapshot.manifest.get("packet_sha256")
                != _payload_hash(packet.model_dump(mode="json"))
                or not set(snapshot.evidence_ids).issubset(reopenable)
            ):
                raise ValueError("material-defect return differs from its question packet")
            additions[question_id] = snapshot.evidence_ids
        return additions

    def verify_unchanged(self) -> None:
        paths = {
            self.config_path: self.config_sha256,
            self.source_preflight_path: self.source_preflight_sha256,
        }
        for snapshot in self.reviews.values():
            paths[snapshot.manifest_path] = snapshot.manifest_sha256
            paths[snapshot.output_path] = snapshot.output_sha256
        if any(sha256(path.read_bytes()).hexdigest() != digest for path, digest in paths.items()):
            raise ValueError("material-defect return source changed during preflight")

    def manifest_details(self) -> list[dict]:
        return [
            {
                "question_id": question_id,
                "evidence_ids": list(snapshot.evidence_ids),
                "review_manifest": str(snapshot.manifest_path),
                "review_manifest_sha256": snapshot.manifest_sha256,
                "review_output_sha256": snapshot.output_sha256,
            }
            for question_id, snapshot in sorted(self.reviews.items())
        ]


def load_material_defect_return(
    *,
    project_root: Path,
    config_path: Path,
    active_chapters: tuple[str, ...],
) -> MaterialDefectReturnReceipt:
    """Verify one explicit return against immutable failed-review artifacts."""

    project_root = project_root.resolve()
    config_path = config_path.resolve()
    if not config_path.is_relative_to(project_root) or not config_path.is_file():
        raise ValueError("material-defect return config is outside the project")
    config_bytes = config_path.read_bytes()
    config = MaterialDefectReturnConfig.model_validate(yaml.safe_load(config_bytes))
    if not set(config.chapters).issubset(active_chapters):
        raise ValueError("material-defect return contains a chapter outside the active run")
    source_run = (project_root / "research/runs" / config.source_run).resolve()
    runs_root = (project_root / "research/runs").resolve()
    if not source_run.is_relative_to(runs_root) or not source_run.is_dir():
        raise ValueError("material-defect source run is outside the run store")
    preflight_path = (source_run / "preflight-manifest.json").resolve()
    if not preflight_path.is_relative_to(source_run) or not preflight_path.is_file():
        raise ValueError("material-defect source preflight is missing")
    preflight_bytes = preflight_path.read_bytes()
    if sha256(preflight_bytes).hexdigest() != config.source_preflight_sha256:
        raise ValueError("material-defect source preflight changed")
    preflight = json.loads(preflight_bytes)
    prior_count = preflight.get("material_defect_return_count") or 0
    if preflight.get("release_id") != config.source_release_id or prior_count != 0:
        raise ValueError("material-defect return exceeds its permitted source lineage")
    reviews = {}
    for questions in config.chapters.values():
        for question_id, addition in questions.items():
            manifest_path = (source_run / addition.review_manifest).resolve()
            if not manifest_path.is_relative_to(source_run) or not manifest_path.is_file():
                raise ValueError("material-defect review manifest is outside its source run")
            manifest_bytes = manifest_path.read_bytes()
            if sha256(manifest_bytes).hexdigest() != addition.review_manifest_sha256:
                raise ValueError("material-defect review manifest changed")
            manifest = json.loads(manifest_bytes)
            output_path = (manifest_path.parent / "output.json").resolve()
            if not output_path.is_relative_to(source_run) or not output_path.is_file():
                raise ValueError("material-defect review output is outside its source run")
            output_bytes = output_path.read_bytes()
            review = json.loads(output_bytes)
            if (
                manifest.get("question_id") != question_id
                or manifest.get("quality_gate") != "fail"
                or manifest.get("review_sha256") != _payload_hash(review)
                or tuple(review.get("strongest_omitted_evidence_ids", ()))
                != addition.evidence_ids
            ):
                raise ValueError("material-defect return differs from its failed review")
            reviews[question_id] = _ReviewSnapshot(
                manifest_path=manifest_path,
                manifest_sha256=sha256(manifest_bytes).hexdigest(),
                output_path=output_path,
                output_sha256=sha256(output_bytes).hexdigest(),
                manifest=manifest,
                review=review,
                evidence_ids=addition.evidence_ids,
            )
    return MaterialDefectReturnReceipt(
        config_path=config_path,
        config_sha256=sha256(config_bytes).hexdigest(),
        source_run=source_run,
        source_preflight_path=preflight_path,
        source_preflight_sha256=sha256(preflight_bytes).hexdigest(),
        source_release_id=config.source_release_id,
        reviews=reviews,
    )


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
    actual = ChapterQuestionEvidencePackage.model_validate_json(expanded_package_path.read_text())
    normalized = _upgrade_legacy_provenance(actual, expected)
    if normalized != expected:
        raise ValueError("expanded question package differs from its exact derivation")
    return normalized


def expand_question_evidence_package(
    *,
    package: ChapterQuestionEvidencePackage,
    judge_package_path: Path,
    additions_by_question: dict[str, tuple[str, ...]],
    retained_by_question: dict[str, tuple[str, ...]] | None = None,
    close_evidence_discovery: bool = False,
) -> ChapterQuestionEvidencePackage:
    """Return the same chapter package with named candidates reopened exactly."""

    raw_bytes = judge_package_path.read_bytes()
    if sha256(raw_bytes).hexdigest() != package.source_package_sha256:
        raise ValueError("judge package does not match the base question package")
    raw = json.loads(raw_bytes)
    rows = [BoundEvidence.model_validate(item) for item in raw["evidence"]]
    ids = [item.evidence_id for item in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("judge package contains duplicate evidence IDs")
    ledger = {item.evidence_id: item for item in rows}
    packets = tuple(
        _expand_packet(
            packet,
            ledger,
            additions_by_question.get(packet.question_id, ()),
            (retained_by_question or {}).get(packet.question_id, ()),
            close_evidence_discovery,
        )
        for packet in package.packets
    )
    return ChapterQuestionEvidencePackage.model_validate(
        package.model_copy(update={"packets": packets}).model_dump()
    )


def _expand_packet(
    packet: QuestionEvidencePacket,
    ledger: dict[str, BoundEvidence],
    additions: tuple[str, ...],
    retained: tuple[str, ...] = (),
    close_evidence_discovery: bool = False,
) -> QuestionEvidencePacket:
    candidate_ids = {item.evidence_id for item in packet.candidate_index}
    existing = {item.evidence_id for item in packet.priority_evidence}
    if (
        len(additions) != len(set(additions))
        or len(retained) != len(set(retained))
        or set(additions) & set(retained)
        or not {*additions, *retained}.issubset(candidate_ids)
    ):
        raise ValueError("expanded evidence must be unique question candidates")
    new_ids = tuple(item for item in additions if item not in existing)
    priority = packet.priority_evidence + tuple(ledger[item] for item in new_ids)
    required = tuple(item.evidence_id for item in priority)
    required_set = set(required)
    retained_set = (
        set(packet.coverage.adjudicated_nonmaterial_evidence_ids) | set(retained)
    ) - set(additions)
    source_routed = tuple(
        item.evidence_id for item in priority if packet.question_id in item.question_ids
    )
    selection_added = tuple(
        item.evidence_id for item in priority if item.evidence_id not in set(source_routed)
    )
    coverage = packet.coverage.model_copy(
        update={
            "items": tuple(
                item.model_copy(
                    update={
                        "requirement": (
                            "must_address"
                            if item.evidence_id in required_set
                            else (
                                "adjudicated_nonmaterial"
                                if item.evidence_id in retained_set
                                else "available_for_reopen"
                            )
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
                and item.evidence_id not in retained_set
            ),
            "adjudicated_nonmaterial_evidence_ids": tuple(
                item.evidence_id
                for item in packet.candidate_index
                if item.evidence_id in retained_set
            ),
        }
    )
    return QuestionEvidencePacket.model_validate(
        packet.model_copy(
            update={
                "priority_evidence": priority,
                "evidence_discovery_complete": (
                    packet.evidence_discovery_complete or close_evidence_discovery
                ),
                "source_routed_priority_evidence_ids": source_routed,
                "selection_added_priority_evidence_ids": selection_added,
                "coverage": coverage,
            }
        ).model_dump()
    )


__all__ = [
    "MaterialDefectReturnReceipt",
    "expand_question_evidence_package",
    "load_expanded_question_evidence_package",
    "load_material_defect_return",
    "load_question_packet_expansion",
]
