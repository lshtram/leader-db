"""Strict routing rows whose include/exclude decision is in the heading."""

from __future__ import annotations

import re

_QUESTION = re.compile(r"(?<![A-Za-z0-9])5B\.(?:10|[1-9])(?![A-Za-z0-9])")
_ID_LIKE = re.compile(r"\b\d+[A-Z]\.\d+\b")
_QUESTION_TEXT = r"5B\.(?:10|[1-9])"
_ADJACENT_GROUP = re.compile(
    rf"(?:{_QUESTION_TEXT}\s*,\s*)*{_QUESTION_TEXT}\s*"
    r"\(\s*adjacent only\s*\)",
    flags=re.IGNORECASE,
)
_ADJACENT_EACH = re.compile(
    rf"{_QUESTION_TEXT}\s*\(\s*adjacent only\s*\)"
    rf"(?:\s*,\s*{_QUESTION_TEXT}\s*\(\s*adjacent only\s*\))*",
    flags=re.IGNORECASE,
)
_INCIDENTAL_ADJACENCY = re.compile(
    rf"[Nn]one\s*\(\s*incidental adjacency to\s+{_QUESTION_TEXT}"
    rf"(?:\s*,\s*{_QUESTION_TEXT})*\s*\)",
)
_NONMATERIAL_EACH = re.compile(
    rf"{_QUESTION_TEXT}\s*\(\s*(?:adjacent|marginal)(?:\s+only)?"
    rf"(?:\s+—[^)]*)?\)(?:\s*,\s*{_QUESTION_TEXT}\s*"
    r"\(\s*(?:adjacent|marginal)(?:\s+only)?(?:\s+—[^)]*)?\))*\.?",
    flags=re.IGNORECASE,
)
_NONMATERIAL_GROUP = re.compile(
    rf"(?:{_QUESTION_TEXT}\s*,\s*)*{_QUESTION_TEXT}\s*"
    r"\(\s*(?:adjacent|marginal)(?:\s+only)?\s*\)\.?",
    flags=re.IGNORECASE,
)
_BULLET_FIELD = re.compile(
    r"^-\s*\*\*([^*:]+):\*\*\s*(.*)$",
    flags=re.MULTILINE,
)
_PARAGRAPH_FIELD = re.compile(
    r"^\*\*([^*:]+):\*\*\s*(.*)$",
    flags=re.MULTILINE,
)
_INLINE_DECISION = re.compile(
    r"^\*\*Decision:\s*([^*\n]+)\*\*\s*$",
    flags=re.MULTILINE,
)
_INLINE_ID_EXCLUSION = re.compile(
    r"^\*\*(U[0-9]{4})\*\*\s+—\s+EXCLUDE\.\s+(.+)$",
    flags=re.MULTILINE,
)


def normalize_suffix_decision_row(
    body: str, chunk_id: str, decision: str
) -> tuple[bool, tuple[str, ...], str]:
    """Normalize explicit fields under a heading-controlled decision."""

    matches = _BULLET_FIELD.findall(body) + _PARAGRAPH_FIELD.findall(body)
    pairs = [
        (_field_name(name), value.strip())
        for name, value in matches
    ]
    names = [name for name, _ in pairs]
    if not pairs or len(set(names)) != len(names):
        raise ValueError(f"{chunk_id}: invalid heading-decision fields")
    fields = dict(pairs)
    supplied = [decision, *_INLINE_DECISION.findall(body)]
    if "decision" in fields:
        supplied.append(fields["decision"].strip("*"))
    canonical = tuple(_canonical_decision(value) for value in supplied)
    if any(value is None or value != decision for value in canonical):
        raise ValueError(f"{chunk_id}: heading and body decisions conflict")
    included = decision == "include"
    questions = _question_fields(fields, chunk_id, included=included)
    if included != bool(questions):
        raise ValueError(f"{chunk_id}: heading decision and question IDs conflict")
    explanation_names = (
        (
            "evidence_record",
            "concrete_evidence_present",
            "material_evidence_identified",
            "material_evidence",
            "material_content",
            "text",
            "reason",
            "exclusion_reason_why_included_despite_adjacency",
        )
        if included
        else ("exclusion_reason", "reason")
    )
    explanation = next(
        (fields[name] for name in explanation_names if fields.get(name)),
        "",
    )
    _require_explanation(explanation, chunk_id)
    return included, questions, explanation


def normalize_inline_id_exclusions(
    raw: str,
) -> dict[str, tuple[bool, tuple[str, ...], str]] | None:
    """Normalize explicit one-line, exclusion-only chunk decisions."""

    matches = _INLINE_ID_EXCLUSION.findall(raw)
    if not matches:
        return None
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    for chunk_id, explanation in matches:
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate inline exclusion")
        _require_explanation(explanation, chunk_id)
        rows[chunk_id] = (False, (), explanation.strip())
    return rows


def normalize_body_decision_row(
    body: str, chunk_id: str
) -> tuple[bool, tuple[str, ...], str]:
    """Normalize a paragraph block whose decision is an explicit body field."""

    supplied = [
        value.strip("*")
        for name, value in _PARAGRAPH_FIELD.findall(body)
        if _field_name(name) == "decision"
    ]
    supplied.extend(_INLINE_DECISION.findall(body))
    if not supplied:
        raise ValueError(f"{chunk_id}: paragraph block requires one decision")
    canonical = tuple(_canonical_decision(value) for value in supplied)
    if any(value is None for value in canonical) or len(set(canonical)) != 1:
        raise ValueError(f"{chunk_id}: invalid paragraph heading decision")
    return normalize_suffix_decision_row(body, chunk_id, canonical[0] or "")


def _canonical_decision(value: str) -> str | None:
    match = re.fullmatch(
        r"(include|exclude)(?:(?:\s+—\s+marginal)|(?:\s+\(primary\)))?",
        value.lower(),
    )
    return match.group(1) if match is not None else None


def _question_fields(
    fields: dict[str, str], chunk_id: str, *, included: bool
) -> tuple[str, ...]:
    structured = tuple(
        (
            _adjacent_only_questions(fields[name], chunk_id)
            if name == "relevant_questions"
            and not included
            else _nonmaterial_questions(fields[name], chunk_id)
            if name == "applicable_lenses"
            and not included
            else _questions(fields[name], chunk_id, structured=strict)
        )
        for name, strict in (
            ("question_ids", True),
            ("applicable_lenses", False),
            ("applicable_5b_lenses", False),
            ("relevant_questions", False),
        )
        if name in fields
    )
    optional = tuple(
        questions
        for name in ("cited_lenses", "lenses_cited", "relevance")
        if name in fields
        for questions in (
            (
                _nonmaterial_questions(fields[name], chunk_id)
                if name == "relevance" and not included
                else _questions(fields[name], chunk_id, structured=False)
            ),
        )
        if questions
    )
    parsed = structured + optional
    if parsed and any(item != parsed[0] for item in parsed[1:]):
        raise ValueError(f"{chunk_id}: heading question fields conflict")
    return parsed[0] if parsed else ()


def _adjacent_only_questions(value: str, chunk_id: str) -> tuple[str, ...]:
    questions = _questions(value, chunk_id, structured=False)
    if not questions:
        sentinel = value.strip().lower().strip("().:; ")
        if sentinel in {"none", "n/a", "-", "—"}:
            return ()
    if not (
        _ADJACENT_GROUP.fullmatch(value)
        or _ADJACENT_EACH.fullmatch(value)
        or _INCIDENTAL_ADJACENCY.fullmatch(value)
    ):
        raise ValueError(f"{chunk_id}: excluded relevant questions are not adjacent-only")
    return ()


def _nonmaterial_questions(value: str, chunk_id: str) -> tuple[str, ...]:
    questions = _questions(value, chunk_id, structured=False)
    if not questions:
        return ()
    if not (
        _NONMATERIAL_EACH.fullmatch(value)
        or _NONMATERIAL_GROUP.fullmatch(value)
    ):
        raise ValueError(f"{chunk_id}: excluded applicable lenses are not nonmaterial")
    return ()


def _questions(
    value: str, chunk_id: str, *, structured: bool
) -> tuple[str, ...]:
    tokens = tuple(_QUESTION.findall(value))
    if len(set(tokens)) != len(tokens):
        raise ValueError(f"{chunk_id}: duplicate heading question IDs")
    invalid_ids = tuple(item for item in _ID_LIKE.findall(value) if item not in tokens)
    if invalid_ids:
        raise ValueError(f"{chunk_id}: invalid heading question IDs: {invalid_ids}")
    residue = _QUESTION.sub("", value).strip().lower().strip("()*.,:;-— ")
    if structured and residue not in {"", "none", "n/a"}:
        raise ValueError(f"{chunk_id}: invalid heading question field")
    return tokens


def _field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _require_explanation(value: str, chunk_id: str) -> None:
    controlled = value.strip().lower().rstrip(".:;")
    if not value or controlled in {
        "none",
        "n/a",
        "-",
        "—",
        "include",
        "included",
        "exclude",
        "excluded",
    }:
        raise ValueError(f"{chunk_id}: heading block lacks an auditable explanation")


__all__ = [
    "normalize_body_decision_row",
    "normalize_inline_id_exclusions",
    "normalize_suffix_decision_row",
]
