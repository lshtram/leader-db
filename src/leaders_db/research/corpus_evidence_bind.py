"""Resolve model fact intents to immutable source units and exact excerpts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .citation_spans import CitationSpan, paragraph_spans, resolve_citation_span
from .corpus_extraction import load_validated_extraction
from .corpus_reader_models import BatchFactOutput, BoundEvidence, EvidenceCitation
from .corpus_reading_plan import CorpusReadingPlan, ReadingBatch


def bind_batch_evidence(
    *,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    reader_output: BatchFactOutput,
) -> tuple[BoundEvidence, ...]:
    """Copy exact cited units after validating reader scope and coverage accounting."""

    documents = {item.source_id: item for item in plan.documents}
    expected = set(batch.source_ids)
    accounted = {item.source_id for item in reader_output.facts} | set(
        reader_output.documents_with_no_material_fact
    )
    overlap = {item.source_id for item in reader_output.facts} & set(
        reader_output.documents_with_no_material_fact
    )
    if overlap:
        raise ValueError(f"reader gave contradictory source dispositions: {sorted(overlap)}")
    if accounted != expected:
        raise ValueError(
            "reader must account for every batch source exactly through facts or no-material-fact"
        )
    evidence: list[BoundEvidence] = []
    for intent in reader_output.facts:
        if intent.source_id not in expected:
            raise ValueError(f"reader cited source outside batch: {intent.source_id}")
        document = documents[intent.source_id]
        if document.extracted_path is None or document.raw_sha256 is None:
            raise ValueError(f"queued document lacks extraction identity: {intent.source_id}")
        rows = load_validated_extraction(
            acquisition_dir / document.extracted_path,
            expected_source_id=intent.source_id,
            expected_raw_sha256=document.raw_sha256,
        )
        units = {int(item["unit"]): item for item in rows}
        batch_range = batch.unit_ranges.get(intent.source_id)
        if (
            batch_range is None
            or intent.start_unit < batch_range[0]
            or intent.end_unit > batch_range[1]
        ):
            raise ValueError(f"reader cited outside batch range for {intent.source_id}")
        selected = [
            units[number]
            for number in range(intent.start_unit, intent.end_unit + 1)
            if number in units
        ]
        if len(selected) != intent.end_unit - intent.start_unit + 1:
            raise ValueError(f"reader cited unavailable unit range for {intent.source_id}")
        excerpt = "\n\n".join(str(item["text"]) for item in selected).strip()
        citations = _resolve_citations(intent.citation_span_ids, selected)
        if not excerpt:
            raise ValueError(f"reader cited an empty unit range for {intent.source_id}")
        number = len(evidence) + 1
        evidence.append(
            BoundEvidence(
                evidence_id=f"{batch.batch_id}-E{number:03d}",
                source_id=intent.source_id,
                url=document.url,
                title=document.title,
                publisher=document.publisher,
                raw_sha256=document.raw_sha256,
                fact_summary=intent.fact_summary,
                question_ids=intent.question_ids,
                polarity=intent.polarity,
                period_fit=intent.period_fit,
                ruler_attribution=intent.ruler_attribution,
                limitations=intent.limitations,
                start_unit=intent.start_unit,
                end_unit=intent.end_unit,
                locator=_locator(selected),
                exact_excerpt=excerpt,
                excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
                citations=citations,
            )
        )
    return tuple(evidence)


def _locator(units: list[dict[str, object]]) -> str:
    first = str(units[0]["locator"])
    last = str(units[-1]["locator"])
    return first if first == last else f"{first} through {last}"


def _resolve_citations(
    span_ids: tuple[str, ...], units: list[dict[str, object]]
) -> tuple[EvidenceCitation, ...]:
    if not span_ids:
        return ()
    if len(span_ids) != len(set(span_ids)):
        raise ValueError("reader cited a duplicate paragraph span")
    available: dict[str, tuple[CitationSpan, str]] = {}
    for item in units:
        unit = int(item["unit"])
        text = str(item["text"])
        for number, span in enumerate(paragraph_spans(unit, text), start=1):
            available[f"U{unit}-P{number}"] = (span, text)
    if not set(span_ids).issubset(available):
        raise ValueError("reader cited an unavailable paragraph span")
    citations = []
    for span_id in span_ids:
        span, text = available[span_id]
        excerpt = resolve_citation_span(text, span)
        citations.append(
            EvidenceCitation(
                span_id=span_id,
                span=span,
                exact_excerpt=excerpt,
                excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
            )
        )
    return tuple(citations)


__all__ = ["bind_batch_evidence"]
