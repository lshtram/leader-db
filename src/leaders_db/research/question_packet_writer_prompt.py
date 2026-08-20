"""Prompt construction for one diagnostic question writer call."""

from __future__ import annotations

import json
import re

from .citation_table_rows import TableLineSpan, resolve_table_line
from .corpus_reader_models import BoundEvidence
from .question_evidence_packet_models import QuestionEvidencePacket
from .question_packet_prompts import QuestionPacketPrompts

_EVIDENCE_ID = re.compile(r"\b(?:BATCH-[A-Z0-9-]+|E-[A-Z0-9]+|SRC:[A-Z0-9]+)\b")


def build_question_writer_prompt(
    packet: QuestionEvidencePacket,
    prompts: QuestionPacketPrompts,
    predecessor_answer: dict | None = None,
    *,
    compact_table_citations: bool = False,
    source_units: dict[tuple[str, int], str] | None = None,
) -> str:
    """Serialize one question without unavailable predecessor evidence."""

    if packet.evidence_discovery_complete and prompts.version < 14:
        raise ValueError("closed evidence discovery requires prompt version 14 or later")
    exact = [
        _writer_evidence_payload(
            item,
            compact_table_citations=compact_table_citations,
            source_units=source_units,
        )
        for item in packet.priority_evidence
    ]
    reopenable = (
        set()
        if packet.evidence_discovery_complete
        else set(packet.coverage.reopenable_evidence_ids)
    )
    candidates = [
        item.model_dump(mode="json")
        for item in packet.candidate_index
        if item.evidence_id in reopenable
    ]
    projected_predecessor = (
        project_predecessor_answer(packet, predecessor_answer)[0]
        if prompts.version >= 12
        else predecessor_answer or {}
    )
    template = (
        prompts.final_writer_template
        if packet.evidence_discovery_complete and prompts.version >= 14
        else prompts.writer_template
    )
    if template is None:
        raise ValueError("post-completion writing requires a final writer prompt")
    return template.format(
        question_id=packet.question_id,
        question=packet.question,
        predecessor_answer=json.dumps(projected_predecessor, ensure_ascii=False),
        exact_evidence=json.dumps(exact, ensure_ascii=False),
        candidate_index=json.dumps(candidates, ensure_ascii=False),
    )


def project_predecessor_answer(
    packet: QuestionEvidencePacket, predecessor_answer: dict | None
) -> tuple[dict, tuple[str, ...]]:
    """Exclude a predecessor that references evidence unavailable in exact form."""

    if predecessor_answer is None:
        return {}, ()
    referenced = _evidence_references(predecessor_answer)
    unavailable = tuple(
        sorted(referenced - set(packet.coverage.required_evidence_ids))
    )
    return ({}, unavailable) if unavailable else (predecessor_answer, ())


def _evidence_references(value: object) -> set[str]:
    if isinstance(value, str):
        return set(_EVIDENCE_ID.findall(value))
    if isinstance(value, dict):
        return {
            evidence_id
            for nested in value.values()
            for evidence_id in _evidence_references(nested)
        }
    if isinstance(value, (list, tuple)):
        return {
            evidence_id
            for nested in value
            for evidence_id in _evidence_references(nested)
        }
    return set()


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


__all__ = ["build_question_writer_prompt", "project_predecessor_answer"]
