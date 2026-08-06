"""Deterministic conversion from a bound citation draft to evidence."""

from __future__ import annotations

from .citation_models import BoundEvidenceDraft
from .deterministic import stable_evidence_id
from .models import EvidenceCandidate, SourceDescriptor


def candidate_from_draft(
    draft: BoundEvidenceDraft,
    source: SourceDescriptor,
) -> EvidenceCandidate:
    """Build the canonical pending candidate from one code-bound draft."""

    intent = draft.intent
    return EvidenceCandidate(
        schema_version="evidence_candidate_v2",
        evidence_id=stable_evidence_id(
            source.source_id,
            intent.citation.locator,
            draft.exact_excerpt,
            intent.claim,
        ),
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        source_family=source.source_family,
        source_dependencies=source.dependencies,
        claim=intent.claim,
        claim_type=intent.claim_type,
        polarity=intent.polarity,
        actor=intent.actor,
        action=intent.action,
        mechanism=intent.mechanism,
        outcome=intent.outcome,
        dates=intent.dates,
        quantities=intent.quantities,
        excerpt=draft.exact_excerpt,
        locator=intent.citation.locator,
        excerpt_start_char=draft.excerpt_start_char,
        excerpt_end_char=draft.excerpt_end_char,
        url=source.url,
        title=source.title,
        publisher=source.publisher,
        publication_date=source.publication_date,
        source_type=source.document_type,
        attribution=intent.attribution,
        period_fit=intent.period_fit,
        source_limitations=intent.source_limitations,
        question_ids=intent.question_ids,
        verification_status="pending",
        verification_notes=(
            "Exact citation copied by code from the hash-bound frozen source.",
        ),
        premium_verification_required=intent.premium_verification_required,
    )


__all__ = ["candidate_from_draft"]
