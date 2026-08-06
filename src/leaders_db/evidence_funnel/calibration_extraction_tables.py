"""Normalize explicit table-form evidence intents."""

from __future__ import annotations

import re

from .citation_models import CitationSelection, EvidenceIntent
from .low_cost import EvidenceIntentBatch, LocatorDisposition
from .models import SourceDescriptor

_FIELD = re.compile(r"^\| \*\*([^*]+)\*\* \| (.*?) \|$", flags=re.MULTILINE)
_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_UNDECOMPOSED = "[not separately decomposed]"


def normalize_table_intents(
    *,
    matches: tuple[tuple[str, str, str], ...],
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch:
    """Convert table rows while leaving quote copying to the citation ledger."""

    allowed = set(methodology_ids)
    intents: list[EvidenceIntent] = []
    for draft_id, _title, body in matches:
        fields = {name.strip().lower(): value.strip() for name, value in _FIELD.findall(body)}
        locator = _required(fields, "locator")
        if locator not in routed_locators:
            raise ValueError(f"{draft_id}: locator is outside the routed batch: {locator}")
        segments = re.findall(r"S[0-9]{5}", _required(fields, "segment_ids"))
        questions = tuple(
            item for item in _QUESTION.findall(_required(fields, "question_id")) if item in allowed
        )
        if not segments or not questions:
            raise ValueError(f"{draft_id}: invalid segments or question IDs")
        intents.append(_intent(draft_id, fields, source, locator, segments, questions))
    evidence_locators = {item.citation.locator for item in intents}
    return EvidenceIntentBatch(
        intents=tuple(intents),
        inspected_locator_count=len(routed_locators),
        locator_dispositions=tuple(
            LocatorDisposition(
                locator=locator,
                disposition=(
                    "evidence_extracted" if locator in evidence_locators else "no_material_evidence"
                ),
                explanation="Normalized from explicit table-form locator selection.",
            )
            for locator in sorted(routed_locators)
        ),
    )


def _intent(
    draft_id: str,
    fields: dict[str, str],
    source: SourceDescriptor,
    locator: str,
    segments: list[str],
    questions: tuple[str, ...],
) -> EvidenceIntent:
    claim = _required(fields, "intent")
    return EvidenceIntent(
        draft_id=draft_id,
        citation=CitationSelection(
            source_id=source.source_id,
            source_sha256=source.source_sha256,
            locator=locator,
            start_segment_id=segments[0],
            end_segment_id=segments[-1],
        ),
        claim=claim,
        claim_type="source_assertion",
        polarity=_polarity(_required(fields, "polarity")),
        actor=_UNDECOMPOSED,
        action=claim,
        mechanism=_UNDECOMPOSED,
        outcome=_UNDECOMPOSED,
        attribution=source.title,
        period_fit=_required(fields, "period_fit"),
        source_limitations=(_required(fields, "limitations"),),
        question_ids=questions,
    )


def _required(fields: dict[str, str], name: str) -> str:
    value = fields.get(name, "").strip()
    if not value:
        raise ValueError(f"table intent lacks {name}")
    return value


def _polarity(value: str) -> str:
    normalized = value.lower()
    if "mixed" in normalized:
        return "mixed"
    if "negative" in normalized or "adverse" in normalized:
        return "adverse"
    if "positive" in normalized or "supportive" in normalized:
        return "favorable"
    return "context"


__all__ = ["normalize_table_intents"]
