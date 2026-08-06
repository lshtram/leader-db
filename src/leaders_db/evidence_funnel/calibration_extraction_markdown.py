"""Strict adapter for M3's explicit locator-bound Markdown handoff."""

from __future__ import annotations

import re
from pathlib import Path

from .citation_models import CitationSelection, EvidenceIntent
from .low_cost import EvidenceIntentBatch, LocatorDisposition
from .models import SourceDescriptor

_INTENT = re.compile(
    r"^### (D[0-9]{4})\s+[—-]\s+(.+?)\n(.*?)(?=^### D[0-9]{4}\s+[—-]|\Z)",
    flags=re.DOTALL | re.MULTILINE,
)
_FIELD = re.compile(r"^- \*\*([^*]+)\*\*:\s*(.*)$", flags=re.MULTILINE)
_SEGMENTS = re.compile(r"^(S[0-9]{5})[–-](S[0-9]{5})$")
_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_LOOSE_INTENT = re.compile(
    r"^\*\*(D[0-9]{4})\*\*\n(.*?)(?=^\*\*D[0-9]{4}\*\*|^</drafts>|\Z)",
    flags=re.DOTALL | re.MULTILINE,
)
_LOOSE_FIELD = re.compile(
    r"^- (?:\*\*)?([^:\n*]+)(?::)?(?:\*\*)?:\s*(.*)$",
    flags=re.MULTILINE,
)
_REPORT_INTENT = re.compile(
    r"^## (D[0-9]{4})\s+[—-]\s+(.+?)\n(.*?)(?=^## D[0-9]{4}\s+[—-]|\Z)",
    flags=re.DOTALL | re.MULTILINE,
)
_REPORT_FIELD = re.compile(
    r"^- \*\*([^*]+?)(?::)?\*\*:?[ \t]*(.*)$",
    flags=re.MULTILINE,
)
_REPORT_LOCATOR = re.compile(r"^(.+?),\s*(S[0-9]{5})(?:[–-](S[0-9]{5}))?\.?$")
_TABLE_FIELD_MARKER = re.compile(
    r"^\| \*\*([^*]+)\*\* \| (.*?) \|$",
    flags=re.MULTILINE,
)


def normalize_m3_markdown(
    *,
    raw_path: Path,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch | None:
    """Convert explicit M3 fields while leaving quotation binding entirely to code."""

    return normalize_m3_markdown_text(
        raw=raw_path.read_text(encoding="utf-8"),
        source=source,
        routed_locators=routed_locators,
        methodology_ids=methodology_ids,
    )


def normalize_m3_markdown_text(
    *,
    raw: str,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch | None:
    """Convert an explicit M3 Markdown message without a transient file."""

    matches = tuple(_INTENT.findall(raw))
    if matches and _TABLE_FIELD_MARKER.search(raw):
        from .calibration_extraction_tables import normalize_table_intents

        return normalize_table_intents(
            matches=matches,
            source=source,
            routed_locators=routed_locators,
            methodology_ids=methodology_ids,
        )
    if not matches:
        loose = _normalize_loose_m3(
            raw=raw,
            source=source,
            routed_locators=routed_locators,
            methodology_ids=methodology_ids,
        )
        if loose is not None:
            return loose
        return _normalize_report_m3(
            raw=raw,
            source=source,
            routed_locators=routed_locators,
            methodology_ids=methodology_ids,
        )
    allowed_questions = set(methodology_ids)
    intents = tuple(
        _parse_intent(
            draft_id=draft_id,
            claim=claim,
            body=body,
            source=source,
            routed_locators=routed_locators,
            allowed_questions=allowed_questions,
        )
        for draft_id, claim, body in matches
    )
    if len({item.draft_id for item in intents}) != len(intents):
        raise ValueError("M3 Markdown contains duplicate draft IDs")
    evidence_locators = {item.citation.locator for item in intents}
    return EvidenceIntentBatch(
        intents=intents,
        inspected_locator_count=len(routed_locators),
        locator_dispositions=tuple(
            LocatorDisposition(
                locator=locator,
                disposition=(
                    "evidence_extracted" if locator in evidence_locators else "no_material_evidence"
                ),
                explanation=(
                    "M3 supplied at least one explicit in-scope segment selection."
                    if locator in evidence_locators
                    else "M3 supplied no in-scope segment selection for this locator."
                ),
            )
            for locator in sorted(routed_locators)
        ),
    )


def _normalize_loose_m3(
    *,
    raw: str,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch | None:
    matches = tuple(_LOOSE_INTENT.findall(raw))
    if not matches:
        return None
    allowed = set(methodology_ids)
    intents: list[EvidenceIntent] = []
    for draft_id, body in matches:
        fields = {
            name.strip().lower().replace(" ", "_"): value.strip()
            for name, value in _LOOSE_FIELD.findall(body)
        }
        question_text = (
            fields.get("question_id")
            or fields.get("question_id(s)")
            or fields.get("5b_questions")
            or fields.get("question_ids_applicable")
            or ""
        )
        questions = tuple(
            dict.fromkeys(item for item in _QUESTION.findall(question_text) if item in allowed)
        )
        if not questions:
            continue
        locator, start, end = _loose_locator(fields, draft_id)
        if locator not in routed_locators:
            raise ValueError(f"{draft_id}: locator is outside the routed batch: {locator}")
        supplied_hash = fields.get("source_sha256")
        if supplied_hash is not None and supplied_hash != source.source_sha256:
            raise ValueError(f"{draft_id}: source hash does not match")
        claim = fields.get("intent_statement")
        undecomposed = "[not separately decomposed]"
        actor = fields.get("actor") or undecomposed
        action = fields.get("action") or claim or undecomposed
        mechanism = fields.get("mechanism") or undecomposed
        outcome = fields.get("outcome") or claim or undecomposed
        intents.append(
            EvidenceIntent(
                draft_id=draft_id,
                citation=CitationSelection(
                    source_id=source.source_id,
                    source_sha256=source.source_sha256,
                    locator=locator,
                    start_segment_id=start,
                    end_segment_id=end,
                ),
                claim=claim or f"{actor} {action}; via {mechanism}; {outcome}.",
                claim_type="source_assertion",
                polarity=_polarity(_required(fields, "polarity")),
                actor=actor,
                action=action,
                mechanism=mechanism,
                outcome=outcome,
                dates=(
                    fields.get("dates")
                    or fields.get("date")
                    or fields.get("period_fit")
                    or _required(fields, "date/period"),
                ),
                quantities=((fields.get("quantities") or "Not stated"),),
                attribution=_required(fields, "attribution"),
                period_fit=fields.get("period_fit") or _required(fields, "date/period"),
                source_limitations=(_required(fields, "limitations"),),
                question_ids=questions,
            )
        )
    if not intents:
        raise ValueError("M3 Markdown contains no in-scope intents")
    return _batch(tuple(intents), routed_locators)


def _loose_locator(
    fields: dict[str, str],
    draft_id: str,
) -> tuple[str, str, str]:
    locator = fields.get("locator")
    segment_range = fields.get("segment_range")
    if locator:
        locator = locator.replace("`", "")
        locator = locator.replace(" segment ", ", segments ")
        if ", segments " not in locator and " segments " in locator:
            locator = locator.replace(" segments ", ", segments ", 1)
    if locator and ", segments " in locator:
        locator, segment_range = locator.split(", segments ", maxsplit=1)
    if locator and segment_range:
        segment_match = _SEGMENTS.fullmatch(segment_range)
        if segment_match is None:
            if re.fullmatch(r"S[0-9]{5}", segment_range):
                return locator, segment_range, segment_range
            raise ValueError(f"{draft_id}: segment_range must be one explicit range")
        return locator, segment_match.group(1), segment_match.group(2)
    disposition = fields.get("locator_disposition", "")
    match = re.search(
        r"(?:extracted )?HTML block ([0-9]+), segments? "
        r"(S[0-9]{5})(?:[–-](S[0-9]{5}))?",
        disposition,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError(f"{draft_id}: invalid locator disposition")
    start = match.group(2)
    return f"extracted HTML block {match.group(1)}", start, match.group(3) or start


def _normalize_report_m3(
    *,
    raw: str,
    source: SourceDescriptor,
    routed_locators: set[str],
    methodology_ids: tuple[str, ...],
) -> EvidenceIntentBatch | None:
    matches = tuple(_REPORT_INTENT.findall(raw))
    if not matches:
        return None
    header = raw.split("---", maxsplit=1)[0]
    if "sha256" in header.lower() and source.source_sha256 not in header:
        raise ValueError("M3 report source hash does not match")
    allowed = set(methodology_ids)
    intents: list[EvidenceIntent] = []
    for draft_id, title, body in matches:
        fields = {
            name.strip().lower().rstrip(":"): value.strip()
            for name, value in _REPORT_FIELD.findall(body)
        }
        questions_text = fields.get("methodology ids") or fields.get("question ids")
        if not questions_text:
            raise ValueError(f"{draft_id}: report lacks question IDs")
        questions = tuple(
            dict.fromkeys(item for item in _QUESTION.findall(questions_text) if item in allowed)
        )
        if not questions:
            continue
        locator, start, end = _report_locator(fields, draft_id)
        if locator not in routed_locators:
            raise ValueError(f"{draft_id}: locator is outside the routed batch: {locator}")
        actor = fields.get("actor(s)") or fields.get("actor")
        if not actor:
            raise ValueError(f"{draft_id}: report lacks actor")
        action_mechanism = fields.get("action / mechanism") or fields.get("mechanism")
        if not action_mechanism:
            raise ValueError(f"{draft_id}: report lacks mechanism")
        period = fields.get("dates / period") or fields.get("period fit")
        if not period:
            raise ValueError(f"{draft_id}: report lacks period fit")
        source_name = fields.get("source")
        if source_name and source.source_id not in source_name:
            raise ValueError(f"{draft_id}: report source does not match")
        intents.append(
            EvidenceIntent(
                draft_id=draft_id,
                citation=CitationSelection(
                    source_id=source.source_id,
                    source_sha256=source.source_sha256,
                    locator=locator,
                    start_segment_id=start,
                    end_segment_id=end or start,
                ),
                claim=fields.get("claim") or title,
                claim_type="source_assertion",
                polarity=_polarity(_required(fields, "polarity")),
                actor=actor,
                action=fields.get("action") or title,
                mechanism=action_mechanism,
                outcome=_required(fields, "outcome"),
                dates=(period,),
                quantities=(fields.get("quantities") or fields["outcome"],),
                attribution=fields.get("attribution") or source.title,
                period_fit=period,
                source_limitations=(_required(fields, "limitations"),),
                question_ids=questions,
            )
        )
    if not intents:
        raise ValueError("M3 report contains no in-scope intents")
    return _batch(tuple(intents), routed_locators)


def _report_locator(
    fields: dict[str, str],
    draft_id: str,
) -> tuple[str, str, str | None]:
    disposition = fields.get("locator disposition")
    if disposition:
        match = _REPORT_LOCATOR.fullmatch(disposition)
        if match is not None:
            return match.groups()
    locator_fields = [
        (name, value) for name, value in fields.items() if name.startswith("locator / segments")
    ]
    if len(locator_fields) != 1:
        raise ValueError(f"{draft_id}: invalid locator disposition")
    name, value = locator_fields[0]
    locator_match = re.search(r"\((extracted HTML block [0-9]+)\)", name, re.I)
    segments = re.findall(r"S[0-9]{5}", value)
    if locator_match is None or not segments:
        raise ValueError(f"{draft_id}: invalid locator/segment field")
    return locator_match.group(1), segments[0], segments[-1]


def _batch(
    intents: tuple[EvidenceIntent, ...],
    routed_locators: set[str],
) -> EvidenceIntentBatch:
    evidence_locators = {item.citation.locator for item in intents}
    return EvidenceIntentBatch(
        intents=intents,
        inspected_locator_count=len(routed_locators),
        locator_dispositions=tuple(
            LocatorDisposition(
                locator=locator,
                disposition=(
                    "evidence_extracted" if locator in evidence_locators else "no_material_evidence"
                ),
                explanation="Normalized from M3's explicit locator handoff.",
            )
            for locator in sorted(routed_locators)
        ),
    )


def _parse_intent(
    *,
    draft_id: str,
    claim: str,
    body: str,
    source: SourceDescriptor,
    routed_locators: set[str],
    allowed_questions: set[str],
) -> EvidenceIntent:
    fields = {name.strip().lower(): value.strip() for name, value in _FIELD.findall(body)}
    locator = _required(fields, "locator")
    if locator not in routed_locators:
        raise ValueError(f"{draft_id}: locator is outside the routed batch: {locator}")
    if _required(fields, "source") != source.source_id:
        raise ValueError(f"{draft_id}: source ID does not match the routed source")
    segment_match = _SEGMENTS.fullmatch(_required(fields, "inclusive segments"))
    if segment_match is None:
        raise ValueError(f"{draft_id}: inclusive segments must be one explicit range")
    questions = tuple(
        dict.fromkeys(
            question
            for question in _QUESTION.findall(_required(fields, "methodology ids"))
            if question in allowed_questions
        )
    )
    if not questions:
        raise ValueError(f"{draft_id}: no in-scope methodology IDs")
    return EvidenceIntent(
        draft_id=draft_id,
        citation=CitationSelection(
            source_id=source.source_id,
            source_sha256=source.source_sha256,
            locator=locator,
            start_segment_id=segment_match.group(1),
            end_segment_id=segment_match.group(2),
        ),
        claim=claim.strip(),
        claim_type="source_assertion",
        polarity=_polarity(_required(fields, "polarity")),
        actor=_required(fields, "actor"),
        action=_required(fields, "action"),
        mechanism=_required(fields, "mechanism"),
        outcome=_required(fields, "outcome"),
        dates=(_required(fields, "dates"),),
        quantities=(_required(fields, "quantities"),),
        attribution=_required(fields, "attribution"),
        period_fit=_required(fields, "period fit"),
        source_limitations=(_required(fields, "limitations"),),
        question_ids=questions,
    )


def _required(fields: dict[str, str], name: str) -> str:
    value = fields.get(name, "").strip()
    if not value:
        raise ValueError(f"M3 Markdown intent lacks {name}")
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


__all__ = ["normalize_m3_markdown", "normalize_m3_markdown_text"]
