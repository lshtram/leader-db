"""Deterministic validation for one canonical diagnostic question answer."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .question_evidence_packet_models import QuestionEvidencePacket

if TYPE_CHECKING:
    from .question_packet_writer import DiagnosticQuestionAnswer


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


__all__ = ["validate_question_answer"]
