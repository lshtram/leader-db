"""Exact-accounting normalization for sectioned Markdown routing tables."""

from __future__ import annotations

import re

from .calibration_routing_headings import normalize_heading_rows
from .low_cost import RoutingDecisionBatch
from .models import ChunkRoutingDecision, SourceDescriptor

_SECTION = re.compile(
    r"^###\s+(Excluded|Included)\s*$\n(.*?)(?=^###\s|\Z)",
    flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_CHUNK = re.compile(r"U[0-9]{4}")
_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_FIELD_BLOCK = re.compile(
    r"^\*\*chunk_id:\s*(U[0-9]{4})\*\*\s*$\n(.*?)(?=^---\s*$|\Z)",
    flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_BULLET_FIELD = re.compile(
    r"^-\s*([a-z0-9_]+):\s*(.*)$", flags=re.MULTILINE | re.IGNORECASE
)
def normalize_section_tables(
    *,
    raw: str,
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch | None:
    """Normalize complete ``Included``/``Excluded`` tables, in either order."""

    heading_rows = normalize_heading_rows(raw)
    if heading_rows is not None:
        return _complete_batch(heading_rows, source, chunk_ids)
    field_blocks = _normalize_field_blocks(raw, source, chunk_ids)
    if field_blocks is not None:
        return field_blocks
    decision_table = _normalize_decision_table(raw, source, chunk_ids)
    if decision_table is not None:
        return decision_table
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    matched_section = False
    for disposition, body in _SECTION.findall(raw):
        matched_section = True
        included = disposition.lower() == "included"
        header: tuple[str, ...] | None = None
        for line in (item for item in body.splitlines() if item.lstrip().startswith("|")):
            cells = _cells(line)
            canonical = _canonical_header(cells)
            if "chunk_id" in canonical:
                _validate_header(canonical)
                header = canonical
                continue
            if header is None or _separator(cells):
                continue
            chunk_id = _chunk_cell(cells, header)
            if chunk_id is None:
                continue
            questions = _questions(cells, header, chunk_id, included)
            explanation = _row_explanation(cells, header, chunk_id, included)
            if chunk_id in rows:
                raise ValueError(f"{chunk_id}: duplicate Markdown routing decision")
            rows[chunk_id] = (included, questions, explanation)
    if not matched_section:
        return None
    return _complete_batch(rows, source, chunk_ids)


def _normalize_field_blocks(
    raw: str,
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch | None:
    matches = _FIELD_BLOCK.findall(raw)
    if not matches:
        return None
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    for chunk_id, body in matches:
        pairs = [(name.lower(), value.strip()) for name, value in _BULLET_FIELD.findall(body)]
        names = [name for name, _ in pairs]
        if len(set(names)) != len(names):
            raise ValueError(f"{chunk_id}: duplicate field-block fields")
        fields = dict(pairs)
        decision = fields.get("decision", "").lower()
        if decision not in {"include", "exclude"}:
            raise ValueError(f"{chunk_id}: invalid field-block routing decision")
        included = decision == "include"
        lens_text = fields.get("applicable_5b_lenses", "")
        questions = _field_questions(lens_text, chunk_id)
        if included and not questions:
            raise ValueError(f"{chunk_id}: included field block lacks question IDs")
        if not included and questions:
            raise ValueError(f"{chunk_id}: excluded field block has question IDs")
        if len(set(questions)) != len(questions):
            raise ValueError(f"{chunk_id}: duplicate field-block question IDs")
        explanation = (
            fields.get("why_included") if included else fields.get("exclusion_reason")
        )
        if not explanation or explanation.lower() in {"none", "n/a", "-", "—"}:
            raise ValueError(f"{chunk_id}: field block lacks an auditable explanation")
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate field-block routing decision")
        rows[chunk_id] = (included, questions, explanation)
    return _complete_batch(rows, source, chunk_ids)


def _field_questions(value: str, chunk_id: str) -> tuple[str, ...]:
    if value.strip().lower() in {"", "none", "n/a", "-", "—"}:
        return ()
    questions = tuple(item for item in re.split(r"[\s,;/]+", value) if item)
    invalid = [item for item in questions if _QUESTION.fullmatch(item) is None]
    if invalid:
        raise ValueError(f"{chunk_id}: invalid field-block question IDs: {invalid}")
    if len(set(questions)) != len(questions):
        raise ValueError(f"{chunk_id}: duplicate field-block question IDs")
    return questions


def _normalize_decision_table(
    raw: str,
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch | None:
    rows: dict[str, tuple[bool, tuple[str, ...], str]] = {}
    header: tuple[str, ...] | None = None
    matched = False
    for line in _logical_table_lines(raw):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = _cells(line)
        canonical = _canonical_header(cells)
        if "chunk_id" in canonical and "decision" in canonical:
            _validate_header(canonical)
            header = canonical
            matched = True
            continue
        if header is None or _separator(cells):
            continue
        chunk_id = _chunk_cell(cells, header)
        if chunk_id is None:
            continue
        decision_index = header.index("decision")
        value = cells[decision_index].upper() if decision_index < len(cells) else ""
        if value not in {"INCLUDE", "EXCLUDE"}:
            raise ValueError(f"{chunk_id}: invalid Markdown routing decision")
        included = value == "INCLUDE"
        questions = _questions(cells, header, chunk_id, included)
        explanation = _row_explanation(cells, header, chunk_id, included)
        if chunk_id in rows:
            raise ValueError(f"{chunk_id}: duplicate Markdown routing decision")
        rows[chunk_id] = (included, questions, explanation)
    if not matched:
        return None
    return _complete_batch(rows, source, chunk_ids)


def _logical_table_lines(raw: str) -> tuple[str, ...]:
    lines = raw.splitlines()
    logical: list[str] = []
    header_width: int | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        cells = _cells(line) if line.lstrip().startswith("|") else ()
        canonical = _canonical_header(cells)
        if "chunk_id" in canonical and "decision" in canonical:
            header_width = len(cells)
        if (
            header_width is not None
            and _CHUNK.search(line)
            and len(cells) < header_width
        ):
            fragments = [line]
            while len(_cells(" ".join(fragments))) < header_width:
                index += 1
                if index >= len(lines) or (
                    lines[index].lstrip().startswith("|")
                    and _CHUNK.search(lines[index])
                ):
                    raise ValueError("routing Markdown row is incompletely wrapped")
                fragments.append(lines[index].strip())
            line = " ".join(fragments)
        elif not line.lstrip().startswith("|"):
            header_width = None
        logical.append(line)
        index += 1
    return tuple(logical)


def _complete_batch(
    rows: dict[str, tuple[bool, tuple[str, ...], str]],
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch:
    expected = set(chunk_ids)
    actual = set(rows)
    if actual != expected:
        raise ValueError(
            "routing Markdown chunk set mismatch; "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
    return RoutingDecisionBatch(
        decisions=tuple(
            _decision(source=source, chunk_id=chunk_id, row=rows[chunk_id])
            for chunk_id in chunk_ids
        )
    )


def _decision(
    *,
    source: SourceDescriptor,
    chunk_id: str,
    row: tuple[bool, tuple[str, ...], str],
) -> ChunkRoutingDecision:
    included, questions, explanation = row
    return ChunkRoutingDecision(
        schema_version="chunk_routing_decision_v1",
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        chunk_id=chunk_id,
        included=included,
        relevant_question_ids=questions,
        relevance_strength="material" if included else "none",
        explanation=explanation,
        exclusion_reason=None if included else explanation,
    )


def _cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|"))


def _canonical_header(cells: tuple[str, ...]) -> tuple[str, ...]:
    aliases = {
        "chunk": "chunk_id",
        "lenses": "question_ids",
        "5b_lenses_cited": "question_ids",
        "applicable_lens": "question_ids",
        "applicable_lenses": "question_ids",
        "applicable_lens_es": "question_ids",
        "applicable_5b_lens": "question_ids",
        "applicable_5b_lens_es": "question_ids",
        "applicable_5b_lenses": "question_ids",
        "relevant_question_ids": "question_ids",
        "reason_class": "reason",
    }
    names = tuple(
        re.sub(r"[^a-z0-9]+", "_", cell.lower()).strip("_") for cell in cells
    )
    return tuple(aliases.get(name, name) for name in names)


def _validate_header(canonical: tuple[str, ...]) -> None:
    nonempty = tuple(name for name in canonical if name)
    if len(set(nonempty)) != len(nonempty):
        raise ValueError("routing Markdown header aliases conflict")


def _separator(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _chunk_cell(cells: tuple[str, ...], header: tuple[str, ...]) -> str | None:
    index = header.index("chunk_id")
    if index >= len(cells):
        raise ValueError("routing Markdown row lacks chunk_id cell")
    value = cells[index]
    return value if _CHUNK.fullmatch(value) else None


def _questions(
    cells: tuple[str, ...],
    header: tuple[str, ...],
    chunk_id: str,
    included: bool,
) -> tuple[str, ...]:
    if not included:
        if "question_ids" in header:
            index = header.index("question_ids")
            value = cells[index].strip().lower() if index < len(cells) else ""
            if value not in {"", "—", "-", "n/a", "none"}:
                raise ValueError(f"{chunk_id}: excluded Markdown row has question IDs")
        return ()
    if "question_ids" not in header:
        raise ValueError("included Markdown table lacks question_ids column")
    index = header.index("question_ids")
    value = cells[index] if index < len(cells) else ""
    questions = tuple(item for item in re.split(r"[\s,;/]+", value) if item)
    if not questions:
        raise ValueError(f"{chunk_id}: included Markdown row lacks question IDs")
    invalid = [item for item in questions if _QUESTION.fullmatch(item) is None]
    if invalid:
        raise ValueError(f"{chunk_id}: invalid Markdown question IDs: {invalid}")
    if len(set(questions)) != len(questions):
        raise ValueError(f"{chunk_id}: duplicate Markdown question IDs")
    return questions


def _row_explanation(
    cells: tuple[str, ...],
    header: tuple[str, ...],
    chunk_id: str,
    included: bool,
) -> str:
    names = (
        (
            "concrete_evidence_record",
            "evidence",
            "explanation",
            "reason",
            "note",
            "relevance",
            "exclusion_reason",
        )
        if included
        else ("exclusion_reason", "reason", "explanation", "note")
    )
    name = next((item for item in names if item in header), None)
    if name is None:
        raise ValueError(f"{chunk_id}: routing Markdown table lacks explanation column")
    index = header.index(name)
    value = cells[index] if index < len(cells) else ""
    controlled = value.strip().lower().rstrip(".:;")
    if not value or controlled in {
        "—",
        "-",
        "n/a",
        "none",
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
        raise ValueError(f"{chunk_id}: routing Markdown row lacks explanation")
    return value
