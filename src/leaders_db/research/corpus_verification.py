"""Deterministic passage-verification helpers for corpus reading."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .citation_spans import paragraph_spans, resolve_citation_span
from .corpus_extraction import load_validated_extraction
from .corpus_reader_models import BatchVerification, BoundEvidence, EvidenceCitation
from .corpus_reading_plan import CorpusReadingPlan

VERIFICATION_BATCH_CHARACTERS = 220_000


def verification_prompt(
    evidence: tuple[BoundEvidence, ...],
    candidates: dict[str, tuple[EvidenceCitation, ...]] | None = None,
) -> str:
    payload = [
        _verification_record(
            item, None if candidates is None else candidates[item.evidence_id]
        )
        for item in evidence
    ]
    return (
        "Freshly verify every proposed fact summary against its exact code-bound "
        "excerpt or excerpts. Reject unsupported attribution, dates, quantities, legal "
        "status, or causal wording. Correct only by narrowing the summary to what the "
        "excerpt supports; never add facts. When citation candidates are supplied, "
        "return every separately needed span_id in citation_span_ids. Return exactly "
        "one verdict per evidence_id.\n\n"
        f"EVIDENCE:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def partition_verification(
    evidence: tuple[BoundEvidence, ...],
    candidates: dict[str, tuple[EvidenceCitation, ...]] | None = None,
) -> tuple[tuple[BoundEvidence, ...], ...]:
    groups: list[tuple[BoundEvidence, ...]] = []
    current: list[BoundEvidence] = []
    for item in evidence:
        candidate = tuple([*current, item])
        if len(verification_prompt(candidate, candidates)) <= VERIFICATION_BATCH_CHARACTERS:
            current.append(item)
            continue
        if not current:
            raise ValueError("one evidence record exceeds verification transport budget")
        groups.append(tuple(current))
        current = [item]
        if len(verification_prompt(tuple(current), candidates)) > VERIFICATION_BATCH_CHARACTERS:
            raise ValueError("one evidence record exceeds verification transport budget")
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def build_verification_candidates(
    *, acquisition_dir: Path, plan: CorpusReadingPlan, evidence: tuple[BoundEvidence, ...]
) -> dict[str, tuple[EvidenceCitation, ...]]:
    documents = {item.source_id: item for item in plan.documents}
    extractions: dict[str, tuple[dict[str, object], ...]] = {}
    result = {}
    for item in evidence:
        document = documents[item.source_id]
        if item.source_id not in extractions:
            extractions[item.source_id] = load_validated_extraction(
                acquisition_dir / str(document.extracted_path),
                expected_source_id=item.source_id,
                expected_raw_sha256=str(document.raw_sha256),
            )
        citations = []
        for row in extractions[item.source_id]:
            unit = int(row["unit"])
            if not item.start_unit <= unit <= item.end_unit:
                continue
            text = str(row["text"])
            for number, span in enumerate(paragraph_spans(unit, text), start=1):
                excerpt = resolve_citation_span(text, span)
                citations.append(
                    EvidenceCitation(
                        span_id=f"U{unit}-P{number}",
                        span=span,
                        exact_excerpt=excerpt,
                        excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
                    )
                )
        if not citations:
            raise ValueError("verification evidence has no paragraph citation candidates")
        result[item.evidence_id] = tuple(citations)
    return result


def apply_verification(
    evidence: tuple[BoundEvidence, ...],
    verification: BatchVerification,
    candidates: dict[str, tuple[EvidenceCitation, ...]] | None = None,
) -> tuple[BoundEvidence, ...]:
    verdicts = {item.evidence_id: item for item in verification.verdicts}
    if len(verdicts) != len(verification.verdicts):
        raise ValueError("verification verdict IDs must be unique")
    if set(verdicts) != {item.evidence_id for item in evidence}:
        raise ValueError("verification verdict IDs do not reconcile with bound evidence")
    verified = []
    for item in evidence:
        verdict = verdicts[item.evidence_id]
        citations = item.citations
        if candidates is not None:
            by_id = {
                candidate.span_id: candidate for candidate in candidates[item.evidence_id]
            }
            if not verdict.citation_span_ids or not set(verdict.citation_span_ids) <= by_id.keys():
                raise ValueError("verification citation span IDs do not reconcile")
            citations = tuple(by_id[span_id] for span_id in verdict.citation_span_ids)
        verified.append(
            item.model_copy(
                update={
                    "fact_summary": verdict.corrected_fact_summary or item.fact_summary,
                    "verification_status": verdict.status,
                    "verification_notes": verdict.notes,
                    "citations": citations,
                }
            )
        )
    return tuple(verified)


def _verification_record(
    item: BoundEvidence, candidates: tuple[EvidenceCitation, ...] | None = None
) -> dict[str, object]:
    payload = item.model_dump(mode="json")
    if candidates is not None:
        payload.pop("citations")
        payload["citation_candidates"] = [
            candidate.model_dump(mode="json") for candidate in candidates
        ]
    if item.citations or candidates is not None:
        payload.pop("exact_excerpt")
        payload.pop("excerpt_sha256")
    return payload


__all__ = [
    "apply_verification",
    "build_verification_candidates",
    "partition_verification",
    "verification_prompt",
]
