"""Strict normalization of per-chunk Markdown routing headings."""

from __future__ import annotations

import json
import re

from .calibration_routing_heading_suffix import (
    normalize_body_decision_row,
    normalize_inline_id_exclusions,
    normalize_suffix_decision_row,
)

_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_HEADING_BLOCK = re.compile(
    r"^#{2,3}\s+(U[0-9]{4})(?:\s+—\s*([^\n]*))?\s*$\n"
    r"(.*?)(?=^---\s*$|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_BOLD_DECISION = re.compile(
    r"^-\s*\*\*Decision:\*\*\s*(include|exclude)\s*$",
    flags=re.MULTILINE | re.IGNORECASE,
)
_BOLD_EXCLUSION = re.compile(
    r"^-\s*\*\*Exclusion reason:\*\*\s*(.+)$",
    flags=re.MULTILINE | re.IGNORECASE,
)
_BOLD_LENSES_FIELD = re.compile(
    r"^-\s*\*\*Applicable lenses:\*\*\s*(.*?)"
    r"(?=^-\s*\*\*[A-Za-z][^*]*:\*\*|\Z)",
    flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_BOLD_LENS_BULLET = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*", flags=re.MULTILINE)
_BOLD_ID_BLOCK = re.compile(
    r"^\*\*(U[0-9]{4})\*\*(?:\s+—\s*([^\n]*))?\s*$\n"
    r"(.*?)(?=^---\s*$|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_BOLD_FIELD = re.compile(
    r"^-\s*\*\*([^*:]+):\*\*\s*(.*)$",
    flags=re.MULTILINE,
)
_UNBULLETED_EXCLUSION = re.compile(
    r"^\*\*Exclusion reason:\*\*\s*(.+)$",
    flags=re.MULTILINE,
)
_PARAGRAPH_FIELD = re.compile(
    r"^\*\*([^*:]+):\*\*\s*(.*)$",
    flags=re.MULTILINE,
)
_CHUNK_BLOCK = re.compile(
    r"^##\s+Chunk:\s*(U[0-9]{4})\s*$\n(.*?)(?=^---\s*$|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_INLINE_BOLD_DECISION = re.compile(
    r"^\*\*Decision:\s*(INCLUDE|EXCLUDE)\*\*\s*$",
    flags=re.MULTILINE,
)
_ROUTING_RATIONALE = re.compile(
    r"^\*\*Routing rationale:\*\*\s*(.+)$",
    flags=re.MULTILINE,
)
_EVIDENCE_FINDING_TEXT = re.compile(
    r"^-\s*\*\*Evidence finding\(s\):\*\*\s*(.*?)"
    r"(?=^(?:-\s*)?\*\*[A-Za-z][^*]*:\*\*|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)


def normalize_heading_rows(
    raw: str,
) -> dict[str, tuple[bool, tuple[str, ...], str]] | None:
    """Return complete explicit rows from per-chunk heading blocks."""

    matches = _HEADING_BLOCK.findall(raw)
    inline_exclusions = normalize_inline_id_exclusions(raw)
    if inline_exclusions is not None and (
        matches
        or _CHUNK_BLOCK.search(raw)
        or any(
            _BOLD_FIELD.search(body) or _UNBULLETED_EXCLUSION.search(body)
            for _, _, body in _BOLD_ID_BLOCK.findall(raw)
        )
    ):
        raise ValueError("mixed inline-exclusion and structured routing dialects")
    if not matches:
        return (
            _normalize_chunk_rows(raw)
            or inline_exclusions
            or _normalize_bold_id_rows(raw)
        )
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    for chunk_id, suffix, body in matches:
        heading_decision = (
            suffix.strip().replace("**", "").lower().removesuffix(" ✓")
        )
        decisions = _BOLD_DECISION.findall(body)
        if not decisions:
            if "| Field |" in body:
                row = _field_value_row(body, chunk_id)
            elif heading_decision in {"include", "exclude"}:
                row = normalize_suffix_decision_row(
                    body, chunk_id, heading_decision
                )
            else:
                row = normalize_body_decision_row(body, chunk_id)
        else:
            row = _bold_row(body, chunk_id, decisions)
        if heading_decision in {"include", "exclude"} and (
            row[0] != (heading_decision == "include")
        ):
            raise ValueError(f"{chunk_id}: heading and body decisions conflict")
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate heading-block routing decision")
        rows[chunk_id] = row
    return rows


def _normalize_chunk_rows(
    raw: str,
) -> dict[str, tuple[bool, tuple[str, ...], str]] | None:
    matches = _CHUNK_BLOCK.findall(raw)
    if not matches:
        return None
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    for chunk_id, body in matches:
        decisions = _INLINE_BOLD_DECISION.findall(body)
        if len(decisions) != 1:
            raise ValueError(f"{chunk_id}: chunk block requires one decision")
        included = decisions[0] == "INCLUDE"
        fields = _two_column_fields(body, chunk_id)
        if fields.get("chunk_id") != chunk_id:
            raise ValueError(f"{chunk_id}: chunk block table identity conflicts")
        relevance = fields.get("relevance")
        try:
            question_value = json.loads(relevance) if relevance is not None else None
        except json.JSONDecodeError as exc:
            raise ValueError(f"{chunk_id}: invalid chunk-block relevance JSON") from exc
        if not isinstance(question_value, list) or not all(
            isinstance(item, str) for item in question_value
        ):
            raise ValueError(f"{chunk_id}: chunk-block relevance must be an ID list")
        questions = _validate_questions(tuple(question_value), chunk_id) if included else ()
        if not included and question_value:
            raise ValueError(f"{chunk_id}: excluded chunk block has question IDs")
        if included:
            rationales = _ROUTING_RATIONALE.findall(body)
            if len(rationales) != 1:
                raise ValueError(f"{chunk_id}: included chunk block requires one rationale")
            explanation = rationales[0].strip()
        else:
            explanation = fields.get("exclusion_reason", "")
        _require_explanation(explanation, chunk_id)
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate chunk-block routing decision")
        rows[chunk_id] = (included, questions, explanation)
    return rows


def _two_column_fields(body: str, chunk_id: str) -> dict[str, str]:
    pairs: list[tuple[str, str]] = []
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = tuple(
            cell.strip().replace("**", "")
            for cell in line.strip().strip("|").split("|")
        )
        if len(cells) != 2 or cells[0].lower() == "field":
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        name = re.sub(r"[^a-z0-9]+", "_", cells[0].lower()).strip("_")
        if not name:
            raise ValueError(f"{chunk_id}: empty two-column field name")
        pairs.append((name, cells[1]))
    names = [name for name, _ in pairs]
    if not pairs or len(set(names)) != len(names):
        raise ValueError(f"{chunk_id}: invalid two-column fields")
    return dict(pairs)


def _normalize_bold_id_rows(
    raw: str,
) -> dict[str, tuple[bool, tuple[str, ...], str]] | None:
    matches = _BOLD_ID_BLOCK.findall(raw)
    if not matches:
        return None
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    for chunk_id, suffix, body in matches:
        pairs = [
            (
                re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                value.strip(),
            )
            for name, value in _BOLD_FIELD.findall(body)
        ]
        names = [name for name, _ in pairs]
        if not pairs or len(set(names)) != len(names):
            raise ValueError(f"{chunk_id}: invalid bold-ID fields")
        fields = dict(pairs)
        explicit_decision = fields.get("decision")
        heading_decision = suffix.lower() if suffix.lower() in {"include", "exclude"} else ""
        relevance_decision = fields.get("relevance", "").lower()
        dispositions = tuple(
            value.lower()
            for value in (explicit_decision, heading_decision, relevance_decision)
            if value and value.lower() in {"include", "exclude"}
        )
        if not dispositions or len(set(dispositions)) != 1:
            raise ValueError(f"{chunk_id}: bold-ID disposition fields conflict")
        decision = dispositions[0]
        if explicit_decision is not None and explicit_decision.lower() not in {
            "include",
            "exclude",
        }:
            raise ValueError(f"{chunk_id}: invalid bold-ID decision")
        included = decision == "include"
        question_text = fields.get(
            "question_ids",
            fields.get("applicable_lenses", fields.get("lenses", "")),
        )
        questions = _plain_questions(question_text, chunk_id)
        if included != bool(questions):
            raise ValueError(f"{chunk_id}: bold-ID decision and questions conflict")
        explanation = (
            (
                fields.get("material_content")
                or _evidence_finding(body)
                or (
                    fields.get("relevance")
                    if relevance_decision not in {"include", "exclude"}
                    else ""
                )
            )
            if included
            else (
                fields.get("exclusion_reason")
                or next(iter(_UNBULLETED_EXCLUSION.findall(body)), "")
            )
        )
        _require_explanation(explanation, chunk_id)
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate bold-ID routing decision")
        rows[chunk_id] = (included, questions, explanation)
    return rows


def _evidence_finding(body: str) -> str:
    matches = _EVIDENCE_FINDING_TEXT.findall(body)
    if len(matches) > 1:
        raise ValueError("duplicate evidence-finding fields")
    return re.sub(r"\s+", " ", matches[0]).strip(" -") if matches else ""


def _bold_row(
    body: str,
    chunk_id: str,
    decisions: list[str],
) -> tuple[bool, tuple[str, ...], str]:
    if len(decisions) != 1:
        raise ValueError(f"{chunk_id}: heading block requires one decision")
    included = decisions[0].lower() == "include"
    questions = _heading_questions(body, chunk_id, included)
    if included:
        explanation = re.sub(r"\s+", " ", body).strip()
    else:
        reasons = _BOLD_EXCLUSION.findall(body)
        if len(reasons) != 1:
            raise ValueError(f"{chunk_id}: excluded heading block requires one reason")
        explanation = reasons[0].strip()
    _require_explanation(explanation, chunk_id)
    return included, questions, explanation


def _field_value_row(
    body: str,
    chunk_id: str,
) -> tuple[bool, tuple[str, ...], str]:
    pairs: list[tuple[str, str]] = []
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = tuple(
            cell.strip().replace("**", "")
            for cell in line.strip().strip("|").split("|")
        )
        if len(cells) != 2 or cells[0].lower() in {"field", "---"}:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        name = re.sub(r"[^a-z0-9]+", "_", cells[0].lower()).strip("_")
        if not name:
            raise ValueError(f"{chunk_id}: empty field-value field name")
        pairs.append((name, cells[1]))
    names = [name for name, _ in pairs]
    if not pairs or len(set(names)) != len(names):
        raise ValueError(f"{chunk_id}: invalid field-value heading table")
    fields = dict(pairs)
    table_chunk_id = fields.get("chunk_id")
    if table_chunk_id is not None and (
        re.fullmatch(r"U[0-9]{4}", table_chunk_id) is None
        or table_chunk_id != chunk_id
    ):
        raise ValueError(f"{chunk_id}: field-value chunk_id conflicts with heading")
    decision = fields.get("decision", "").lower()
    if decision not in {"include", "exclude"}:
        raise ValueError(f"{chunk_id}: invalid field-value decision")
    included = decision == "include"
    questions = _plain_questions(fields.get("applicable_lenses", ""), chunk_id)
    if included != bool(questions):
        raise ValueError(f"{chunk_id}: field-value decision and lenses conflict")
    explanation_names = (
        ("inclusion_reason", "reason", "exclusion_reason", "adjacent_context_flagged")
        if included
        else ("exclusion_reason", "reason")
    )
    explanation = next(
        (fields[name] for name in explanation_names if fields.get(name)),
        "",
    )
    _require_explanation(explanation, chunk_id)
    return included, questions, explanation


def _heading_questions(
    body: str,
    chunk_id: str,
    included: bool,
) -> tuple[str, ...]:
    fields = _BOLD_LENSES_FIELD.findall(body)
    if len(fields) > 1:
        raise ValueError(f"{chunk_id}: duplicate applicable-lenses fields")
    if not fields:
        if included:
            raise ValueError(f"{chunk_id}: included heading block lacks question IDs")
        return ()
    value = fields[0].strip()
    if not included:
        if _sentinel(value) not in {"", "none", "n/a", "-", "—"}:
            raise ValueError(f"{chunk_id}: excluded heading block has question IDs")
        return ()
    tokens = tuple(item.strip() for item in _BOLD_LENS_BULLET.findall(value))
    return _validate_questions(tokens, chunk_id)


def _plain_questions(value: str, chunk_id: str) -> tuple[str, ...]:
    if _sentinel(value).strip("()") in {"", "none", "n/a", "-", "—"}:
        return ()
    return _validate_questions(
        tuple(item for item in re.split(r"[\s,;/]+", value) if item),
        chunk_id,
    )


def _validate_questions(
    questions: tuple[str, ...],
    chunk_id: str,
) -> tuple[str, ...]:
    if not questions:
        raise ValueError(f"{chunk_id}: included heading block lacks question IDs")
    invalid = [item for item in questions if _QUESTION.fullmatch(item) is None]
    if invalid:
        raise ValueError(f"{chunk_id}: invalid heading-block question IDs: {invalid}")
    if len(set(questions)) != len(questions):
        raise ValueError(f"{chunk_id}: duplicate heading-block question IDs")
    return questions


def _require_explanation(value: str, chunk_id: str) -> None:
    if not value or _sentinel(value) in {
        "none",
        "n/a",
        "-",
        "—",
        "low",
        "weak",
        "medium",
        "material",
        "high",
        "pivotal",
        "include",
        "included",
        "exclude",
        "excluded",
    }:
        raise ValueError(f"{chunk_id}: heading block lacks an auditable explanation")


def _sentinel(value: str) -> str:
    return value.strip().lower().rstrip(".:;")


__all__ = ["normalize_heading_rows"]
