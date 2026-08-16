"""Deterministic question-level evidence packets from a frozen corpus ledger."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .corpus_reader_models import BoundEvidence
from .question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    EvidenceDisposition,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
    _ids_digest,
)
from .question_packet_approval import load_approved_selection


def build_chapter_question_evidence_package(
    *,
    project_root: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    chapter_id: str,
    output_path: Path,
) -> Path:
    """Build exact question packets without model selection or scientific mutation."""

    package = _construct_chapter_question_evidence_package(
        project_root=project_root,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
        chapter_id=chapter_id,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _construct_chapter_question_evidence_package(
    *,
    project_root: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
    chapter_id: str,
) -> ChapterQuestionEvidencePackage:
    """Construct one packet in memory from its validated sources."""

    raw_bytes = judge_package_path.read_bytes()
    source = json.loads(raw_bytes)
    evidence_rows = [BoundEvidence.model_validate(raw) for raw in source["evidence"]]
    _reject_duplicates([item.evidence_id for item in evidence_rows], "evidence")
    evidence = {item.evidence_id: item for item in evidence_rows}
    question_rows = [
        item
        for item in source["questions"]
        if str(item.get("methodology_id", "")).startswith(f"{chapter_id}.")
    ]
    _reject_duplicates([str(item["methodology_id"]) for item in question_rows], "question")
    questions = {str(item["methodology_id"]): item for item in question_rows}
    expected = tuple(f"{chapter_id}.{number}" for number in range(1, 11))
    if set(questions) != set(expected):
        raise ValueError(f"source package does not contain ten questions for {chapter_id}")
    selection_bytes, selected_bytes, selected = load_approved_selection(
        project_root,
        selection_manifest_path,
        judge_package_path,
        chapter_id,
    )
    catalogue_path = project_root / "src/leaders_db/conversational_evidence/data/questions.json"
    catalogue_bytes = catalogue_path.read_bytes()
    catalogue = json.loads(catalogue_bytes)
    chapter_rows = [item for item in catalogue["chapters"] if item["id"] == chapter_id]
    if len(chapter_rows) != 1:
        raise ValueError("question catalogue must contain the chapter exactly once")
    catalogue_chapter = chapter_rows[0]
    catalogue_ids = [str(item["id"]) for item in catalogue_chapter["questions"]]
    _reject_duplicates(catalogue_ids, "catalogue question")
    if set(catalogue_ids) != set(expected) or len(catalogue_ids) != 10:
        raise ValueError("question catalogue must contain exactly ten chapter questions")
    question_text = {
        str(item["id"]): str(item["text"])
        for item in catalogue_chapter["questions"]
    }
    answer_rows = selected["answers"]
    _reject_duplicates([str(answer["question_id"]) for answer in answer_rows], "answer")
    priority_by_question = {
        str(answer["question_id"]): tuple(
            dict.fromkeys(
                [
                    *answer.get("supporting_evidence_ids", []),
                    *answer.get("contrary_or_qualifying_evidence_ids", []),
                ]
            )
        )
        for answer in selected["answers"]
    }
    if set(priority_by_question) != set(expected):
        raise ValueError("selected analysis does not contain the chapter's ten answers")
    packets = tuple(
        _packet(
            question_id,
            question_text[question_id],
            questions[question_id],
            evidence,
            priority_by_question[question_id],
        )
        for question_id in expected
    )
    chapter_candidates = tuple(
        sorted(
            evidence_id
            for evidence_id, item in evidence.items()
            if any(qid.startswith(f"{chapter_id}.") for qid in item.question_ids)
        )
    )
    chapter_priority_ids = {item for values in priority_by_question.values() for item in values}
    dispositions = tuple(
        _disposition(item, chapter_id, chapter_priority_ids)
        for item in sorted(evidence.values(), key=lambda row: row.evidence_id)
    )
    return ChapterQuestionEvidencePackage(
        chapter_id=chapter_id,
        source_package_sha256=sha256(raw_bytes).hexdigest(),
        selection_manifest_sha256=sha256(selection_bytes).hexdigest(),
        selected_analysis_sha256=sha256(selected_bytes).hexdigest(),
        question_catalogue_sha256=sha256(catalogue_bytes).hexdigest(),
        complete_ledger_evidence_count=len(evidence),
        complete_ledger_ids_sha256=_ids_digest(evidence),
        packets=packets,
        chapter_candidate_ids=chapter_candidates,
        complete_ledger_dispositions=dispositions,
    )


def load_trusted_chapter_question_evidence_package(
    *,
    project_root: Path,
    package_path: Path,
    judge_package_path: Path,
    selection_manifest_path: Path,
) -> ChapterQuestionEvidencePackage:
    """Reload a packet only after rechecking every bound source hash."""

    package = ChapterQuestionEvidencePackage.model_validate_json(
        package_path.read_text(encoding="utf-8")
    )
    selection_bytes, analysis_bytes, _ = load_approved_selection(
        project_root,
        selection_manifest_path,
        judge_package_path,
        package.chapter_id,
    )
    catalogue_path = (
        project_root / "src/leaders_db/conversational_evidence/data/questions.json"
    )
    actual = (
        sha256(judge_package_path.read_bytes()).hexdigest(),
        sha256(selection_bytes).hexdigest(),
        sha256(analysis_bytes).hexdigest(),
        sha256(catalogue_path.read_bytes()).hexdigest(),
    )
    claimed = (
        package.source_package_sha256,
        package.selection_manifest_sha256,
        package.selected_analysis_sha256,
        package.question_catalogue_sha256,
    )
    if actual != claimed:
        raise ValueError("question evidence package provenance hashes are stale")
    expected = _construct_chapter_question_evidence_package(
        project_root=project_root,
        judge_package_path=judge_package_path,
        selection_manifest_path=selection_manifest_path,
        chapter_id=package.chapter_id,
    )
    if package != expected:
        raise ValueError("question evidence package differs from its approved sources")
    return package


def _packet(
    question_id: str,
    question_text: str,
    question: dict,
    evidence: dict[str, BoundEvidence],
    priority_ids: tuple[str, ...],
) -> QuestionEvidencePacket:
    routed_ids = tuple(str(item) for item in question.get("evidence_ids", []))
    if len(routed_ids) != len(set(routed_ids)) or not set(routed_ids).issubset(evidence):
        raise ValueError(f"invalid or duplicate evidence routing for {question_id}")
    if not set(priority_ids).issubset(evidence):
        raise ValueError(f"selected answer cites unknown evidence for {question_id}")
    reverse_ids = {
        item.evidence_id
        for item in evidence.values()
        if question_id in item.question_ids
    }
    if set(routed_ids) != reverse_ids:
        raise ValueError(
            f"question routing is not complete in both directions: {question_id}"
        )
    candidate_ids = tuple(dict.fromkeys([*priority_ids, *routed_ids]))
    records = tuple(evidence[item] for item in candidate_ids)
    for record in tuple(evidence[item] for item in routed_ids):
        if question_id not in record.question_ids:
            raise ValueError(f"question mapping disagrees with evidence record: {question_id}")
    polarity = {item.evidence_id: item.polarity.lower() for item in records}
    direct_ids = tuple(
        item.evidence_id for item in records if question_id in item.question_ids
    )
    favorable = tuple(item for item in direct_ids if polarity[item] == "favorable")
    adverse = tuple(item for item in direct_ids if polarity[item] == "adverse")
    mixed = tuple(item for item in direct_ids if item not in {*favorable, *adverse})
    return QuestionEvidencePacket(
        question_id=question_id,
        question=question_text,
        priority_evidence=tuple(evidence[item] for item in priority_ids),
        candidate_index=tuple(_compact(item) for item in records),
        direct_evidence_count=len(direct_ids),
        favorable_evidence_ids=favorable,
        adverse_evidence_ids=adverse,
        mixed_or_context_evidence_ids=mixed,
        coverage=_coverage(question_id, records, priority_ids),
    )


def _coverage(
    question_id: str,
    records: tuple[BoundEvidence, ...],
    priority_ids: tuple[str, ...],
) -> QuestionCoverageChecklist:
    required = set(priority_ids)
    items = tuple(
        EvidenceCoverageItem(
            evidence_id=item.evidence_id,
            requirement=(
                "must_address" if item.evidence_id in required else "available_for_reopen"
            ),
            carries_attribution=bool(item.ruler_attribution.strip()),
            carries_period_fit=bool(item.period_fit.strip()),
            carries_limitations=bool(item.limitations),
        )
        for item in records
    )
    return QuestionCoverageChecklist(
        question_id=question_id,
        items=items,
        required_evidence_ids=priority_ids,
        reopenable_evidence_ids=tuple(
            item.evidence_id for item in records if item.evidence_id not in required
        ),
        favorable_available=any(item.polarity.lower() == "favorable" for item in records),
        adverse_available=any(item.polarity.lower() == "adverse" for item in records),
        mixed_or_context_available=any(
            item.polarity.lower() not in {"favorable", "adverse"} for item in records
        ),
    )


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


def _disposition(
    item: BoundEvidence, chapter_id: str, chapter_priority_ids: set[str]
) -> EvidenceDisposition:
    direct = tuple(
        sorted(qid for qid in item.question_ids if qid.startswith(f"{chapter_id}."))
    )
    sibling = tuple(
        sorted(
            qid for qid in item.question_ids if not qid.startswith(f"{chapter_id}.")
        )
    )
    disposition = (
        "direct"
        if direct
        else "chapter_context"
        if item.evidence_id in chapter_priority_ids
        else "outside_chapter"
    )
    return EvidenceDisposition(
        evidence_id=item.evidence_id,
        direct_question_ids=direct,
        sibling_chapter_question_ids=sibling,
        disposition=disposition,
    )


def _reject_duplicates(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} IDs are not allowed")


__all__ = [
    "ChapterQuestionEvidencePackage",
    "CompactEvidenceCandidate",
    "EvidenceCoverageItem",
    "EvidenceDisposition",
    "QuestionCoverageChecklist",
    "QuestionEvidencePacket",
    "build_chapter_question_evidence_package",
    "load_trusted_chapter_question_evidence_package",
]
