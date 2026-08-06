"""Deterministic passage-verification helpers for corpus reading."""

from __future__ import annotations

import json

from .corpus_reader_models import BatchVerification, BoundEvidence

VERIFICATION_BATCH_CHARACTERS = 220_000


def verification_prompt(evidence: tuple[BoundEvidence, ...]) -> str:
    payload = [item.model_dump(mode="json") for item in evidence]
    return (
        "Freshly verify every proposed fact summary against its exact code-bound "
        "excerpt. Reject unsupported attribution, dates, quantities, legal status, or "
        "causal wording. Correct only by narrowing the summary to what the excerpt "
        "supports; never add facts. Return exactly one verdict per evidence_id.\n\n"
        f"EVIDENCE:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def partition_verification(
    evidence: tuple[BoundEvidence, ...],
) -> tuple[tuple[BoundEvidence, ...], ...]:
    groups: list[tuple[BoundEvidence, ...]] = []
    current: list[BoundEvidence] = []
    characters = 0
    for item in evidence:
        size = len(item.model_dump_json())
        if current and characters + size > VERIFICATION_BATCH_CHARACTERS:
            groups.append(tuple(current))
            current, characters = [], 0
        current.append(item)
        characters += size
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def apply_verification(
    evidence: tuple[BoundEvidence, ...], verification: BatchVerification
) -> tuple[BoundEvidence, ...]:
    verdicts = {item.evidence_id: item for item in verification.verdicts}
    if set(verdicts) != {item.evidence_id for item in evidence}:
        raise ValueError("verification verdict IDs do not reconcile with bound evidence")
    return tuple(
        item.model_copy(
            update={
                "fact_summary": verdicts[item.evidence_id].corrected_fact_summary
                or item.fact_summary,
                "verification_status": verdicts[item.evidence_id].status,
                "verification_notes": verdicts[item.evidence_id].notes,
            }
        )
        for item in evidence
    )


__all__ = ["apply_verification", "partition_verification", "verification_prompt"]
