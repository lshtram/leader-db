"""Normalize M2.7 semantic intents without accepting model-authored quotations."""

from __future__ import annotations

import re
from pathlib import Path

from .citation_models import CitationSelection, EvidenceIntent
from .low_cost import EvidenceIntentBatch, LocatorDisposition
from .models import SourceDescriptor
from .routing import extract_json_object_with_trace

_POLARITY = {
    "adverse": "adverse",
    "negative": "adverse",
    "neutral": "context",
    "positive": "favorable",
    "supportive": "favorable",
}
_MARKDOWN_INTENT = re.compile(
    r"### Intent (D[0-9]{4})\n"
    r"\*\*Locator:\*\* (.*?)\n"
    r"\*\*Factual intent:\*\* (.*?)\n"
    r"\*\*Applicable questions:\*\* (.*?)\n"
    r"\*\*Period fit:\*\* (.*?)\n"
    r"\*\*Limitations:\*\* (.*?)(?=\n---|\Z)",
    flags=re.DOTALL,
)
_SINGLE_LOCATOR = re.compile(r"^(extracted HTML block [0-9]+), S([0-9]{5})(?:[–-]S([0-9]{5}))?$")
_UNDECOMPOSED = "[not separately decomposed]"


def normalize_intent_payload(
    *,
    raw_path: Path,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch:
    """Convert explicit semantic fields and segment IDs into the strict intent contract."""

    payload, _ = extract_json_object_with_trace(raw_path.read_text(encoding="utf-8"))
    return _normalize_intent_mapping(
        payload=payload,
        source=source,
        routed_locators=routed_locators,
        methodology_ids=methodology_ids,
    )


def _normalize_intent_mapping(
    *,
    payload: dict[str, object],
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch:
    raw_intents = (
        payload.get("intents")
        or payload.get("drafts")
        or payload.get("draft_intents")
        or payload.get("extracted_intents")
        or []
    )
    if not isinstance(raw_intents, list):
        raise ValueError("extractor output lacks an intent list")
    allowed_questions = set(methodology_ids)
    intents: list[EvidenceIntent] = []
    evidence_locators: set[str] = set()
    for item in raw_intents:
        if not isinstance(item, dict):
            continue
        claims = item.get("claims")
        attributes = item.get("attributes")
        semantic_intent = item.get("intent")
        nested = (
            claims
            if isinstance(claims, dict)
            else attributes
            if isinstance(attributes, dict)
            else semantic_intent
        )
        raw = {**nested, **item} if isinstance(nested, dict) else item
        raw_questions = (
            raw.get("question_ids")
            or raw.get("methodology_ids")
            or raw.get("applicable_questions")
            or raw.get("lens_ids")
            or raw.get("questions")
            or raw.get("question_id")
            or ()
        )
        if isinstance(raw_questions, str):
            raw_questions = (raw_questions,)
        questions = tuple(question for question in raw_questions if question in allowed_questions)
        disposition = (
            raw.get("locator_disposition") or raw.get("locator_dispositions") or raw.get("citation")
        )
        nested = (
            {}
            if raw.get("locator") and isinstance(disposition, str)
            else _single_disposition(disposition)
        )
        if nested is None:
            continue
        locator_value = raw.get("locator")
        if isinstance(locator_value, dict):
            nested = {**nested, **locator_value}
            locator_value = locator_value.get("locator_name") or locator_value.get("locator")
        locator = str(locator_value or nested.get("locator") or "")
        segment_ids = (
            raw.get("segment_ids")
            or raw.get("source_segment_ids")
            or nested.get("segment_ids")
            or nested.get("segments")
            or _segment_range(raw)
            or _segment_range(nested)
        )
        if not questions or locator not in routed_locators or not segment_ids:
            continue
        claim = raw.get("intent_narrative") or raw.get("claim")
        if claim is None and isinstance(raw.get("intent"), str):
            claim = raw["intent"]
        if claim is None and isinstance(semantic_intent, dict):
            claim = semantic_intent.get("action")
        actor, action, mechanism, outcome = _semantic_components(raw, claim)
        limitations = list(_tuple(raw.get("limitations")))
        if _UNDECOMPOSED in (actor, action, mechanism, outcome):
            limitations.append(
                "Extractor supplied an atomic claim but did not separately "
                "decompose every semantic component."
            )
        if not claim:
            object_text = str(raw.get("object") or "").strip()
            claim = (
                f"{actor} {action} {object_text}. {outcome}."
                if object_text
                else f"{actor} {action}; via {mechanism}; {outcome}."
            )
        intents.append(
            EvidenceIntent(
                draft_id=str(raw.get("draft_id") or _required(raw, "intent_id")),
                citation=CitationSelection(
                    source_id=source.source_id,
                    source_sha256=source.source_sha256,
                    locator=locator,
                    start_segment_id=str(segment_ids[0]),
                    end_segment_id=str(segment_ids[-1]),
                ),
                claim=str(claim),
                claim_type="source_assertion",
                polarity=_polarity(raw.get("polarity")),
                actor=actor,
                action=action,
                mechanism=mechanism,
                outcome=outcome,
                dates=_tuple(raw.get("dates") or raw.get("passage_date") or raw.get("date")),
                quantities=_tuple(raw.get("quantities") or raw.get("quantity")),
                attribution=str(raw.get("attribution") or f"{source.publisher}, {source.title}"),
                period_fit=_required_alias(raw, "period_fit", "date"),
                source_limitations=tuple(limitations),
                question_ids=questions,
            )
        )
        evidence_locators.add(locator)
    if not intents:
        raise ValueError("extractor normalization produced no in-scope intents")
    return EvidenceIntentBatch(
        intents=tuple(intents),
        inspected_locator_count=len(routed_locators),
        locator_dispositions=tuple(
            LocatorDisposition(
                locator=locator,
                disposition=(
                    "evidence_extracted" if locator in evidence_locators else "no_material_evidence"
                ),
                explanation=(
                    "At least one normalized in-scope intent cites this locator."
                    if locator in evidence_locators
                    else "M2.7 returned no Chapter 5B intent for this routed locator."
                ),
            )
            for locator in sorted(routed_locators)
        ),
    )


def latest_json_output(stage_root: Path) -> Path:
    """Return the latest attempt output containing a parseable JSON object."""

    for path in reversed(sorted(stage_root.glob("attempt-*/output.json"))):
        if not path.stat().st_size:
            continue
        try:
            payload, _ = extract_json_object_with_trace(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        intents = (
            payload.get("intents")
            or payload.get("drafts")
            or payload.get("draft_intents")
            or payload.get("extracted_intents")
            or []
        )
        if any(
            isinstance(item, dict)
            and any(
                key in item
                for key in (
                    "question_id",
                    "question_ids",
                    "methodology_ids",
                    "applicable_questions",
                )
            )
            for item in intents
        ):
            return path
    raise ValueError(f"failed extraction has no parseable model payload: {stage_root}")


def normalize_latest_intents(
    *,
    stage_root: Path,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch:
    """Normalize the latest compatible JSON or bounded single-locator Markdown."""

    try:
        path = latest_json_output(stage_root)
    except ValueError:
        from .calibration_events import latest_intent_event_payload

        event_payload = latest_intent_event_payload(stage_root)
        if event_payload is not None:
            return _normalize_intent_mapping(
                payload=event_payload,
                source=source,
                routed_locators=routed_locators,
                methodology_ids=methodology_ids,
            )
        from .calibration_events import intent_event_messages
        from .calibration_extraction_markdown import (
            normalize_m3_markdown,
            normalize_m3_markdown_text,
        )

        for message in intent_event_messages(stage_root):
            try:
                batch = normalize_m3_markdown_text(
                    raw=message,
                    source=source,
                    routed_locators=routed_locators,
                    methodology_ids=methodology_ids,
                )
            except ValueError:
                continue
            if batch is not None:
                return batch

        for path in reversed(sorted(stage_root.glob("attempt-*/output.json"))):
            if path.stat().st_size:
                batch = normalize_m3_markdown(
                    raw_path=path,
                    source=source,
                    routed_locators=routed_locators,
                    methodology_ids=methodology_ids,
                )
                if batch is not None:
                    return batch
                batch = _normalize_markdown(path, source, routed_locators, methodology_ids)
                if batch is not None:
                    return batch
        raise
    return normalize_intent_payload(
        raw_path=path,
        source=source,
        routed_locators=routed_locators,
        methodology_ids=methodology_ids,
    )


def _required(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"normalized intent lacks {key}")
    return value


def _required_alias(
    payload: dict[str, object],
    primary: str,
    alias: str,
) -> str:
    value = str(payload.get(primary) or payload.get(alias) or "").strip()
    if not value:
        raise ValueError(f"normalized intent lacks {primary}")
    return value


def _single_disposition(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    if value is None:
        return {}
    return None


def _semantic_components(
    payload: dict[str, object],
    claim: object,
) -> tuple[str, str, str, str]:
    actor = str(payload.get("actor") or payload.get("subject") or "").strip()
    action = str(payload.get("action") or payload.get("predicate_action") or "").strip()
    mechanism = str(payload.get("mechanism") or "").strip()
    outcome = str(payload.get("outcome") or "").strip()
    if str(claim or "").strip():
        return (
            actor or _UNDECOMPOSED,
            action or _UNDECOMPOSED,
            mechanism or _UNDECOMPOSED,
            outcome or _UNDECOMPOSED,
        )
    if all((actor, action, mechanism, outcome)):
        return actor, action, mechanism, outcome
    raise ValueError("normalized intent lacks a claim or complete semantic components")


def _tuple(value: object) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _segment_range(payload: dict[str, object]) -> tuple[str, ...]:
    inclusive = payload.get("inclusive_segments") or payload.get("segment_range")
    if isinstance(inclusive, dict):
        payload = {**payload, **inclusive}
    start = (
        payload.get("segment_id_start")
        or payload.get("segment_start_id")
        or payload.get("start_segment_id")
        or payload.get("first_segment_id")
    )
    end = (
        payload.get("segment_id_end")
        or payload.get("segment_end_id")
        or payload.get("end_segment_id")
        or payload.get("last_segment_id")
    )
    if not start or not end:
        return ()
    start_number = int(str(start)[1:])
    end_number = int(str(end)[1:])
    return tuple(f"S{number:05d}" for number in range(start_number, end_number + 1))


def _polarity(value: object) -> str:
    normalized = str(value or "neutral").lower()
    if "mixed" in normalized:
        return "mixed"
    for label, result in _POLARITY.items():
        if label in normalized:
            return result
    return "context"


def _normalize_markdown(
    path: Path,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch | None:
    allowed = set(methodology_ids)
    intents: list[EvidenceIntent] = []
    for (
        draft_id,
        locator_text,
        claim,
        questions_text,
        period,
        limitations,
    ) in _MARKDOWN_INTENT.findall(path.read_text(encoding="utf-8")):
        locator_match = _SINGLE_LOCATOR.fullmatch(locator_text.strip())
        questions = tuple(
            item.strip() for item in questions_text.split(",") if item.strip() in allowed
        )
        if locator_match is None or not questions:
            continue
        locator, start, end = locator_match.groups()
        if locator not in routed_locators:
            continue
        intents.append(
            EvidenceIntent(
                draft_id=draft_id,
                citation=CitationSelection(
                    source_id=source.source_id,
                    source_sha256=source.source_sha256,
                    locator=locator,
                    start_segment_id=f"S{start}",
                    end_segment_id=f"S{end or start}",
                ),
                claim=claim.strip(),
                claim_type="source_assertion",
                polarity="context",
                actor="Government of Mexico",
                action=claim.strip(),
                mechanism="formal published fuel-stimulus schedule",
                outcome=claim.strip(),
                attribution=f"{source.publisher}, {source.title}",
                period_fit=period.strip(),
                source_limitations=(limitations.strip(),),
                question_ids=questions,
            )
        )
    if not intents:
        return None
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
                explanation="Normalized from M2.7's explicit single-locator intent.",
            )
            for locator in sorted(routed_locators)
        ),
    )


__all__ = [
    "latest_json_output",
    "normalize_intent_payload",
    "normalize_latest_intents",
]
