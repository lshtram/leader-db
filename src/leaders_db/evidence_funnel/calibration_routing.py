"""Deterministic normalization of M2.7's auditable routing table."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .calibration_routing_aliases import (
    apply_inverse_adjacency,
    prose_relevance,
    required_string,
    resolve_adjacent_ids,
    resolve_decision_rows,
    resolve_optional_text_alias,
    resolve_question_ids,
    resolve_text_alias,
    unwrap_json_fence,
    validate_question_ids,
)
from .calibration_routing_markdown import normalize_section_tables
from .low_cost import RoutingDecisionBatch
from .models import ChunkRoutingDecision, SourceDescriptor

_INCLUDED_SECTION = re.compile(
    r"### Included Chunks.*?(?=### Excluded Chunks)",
    flags=re.DOTALL,
)
_ROW = re.compile(r"^\|\s*\*\*(U[0-9]{4})\*\*\s*\|(.+)$", flags=re.MULTILINE)
_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_CHUNK_SECTION = re.compile(
    r"### (?:Chunk )?(U[0-9]{4})(.*?)"
    r"(?=\n---|\n### (?:Chunk )?U[0-9]{4}|\Z)",
    flags=re.DOTALL,
)
_INCLUDE_DECISION = re.compile(
    r"^\*\*Decision:\*\*[ \t]*INCLUDE[ \t]*$",
    flags=re.MULTILINE,
)
_APPLICABLE_LENSES = re.compile(
    r"^\*\*Applicable 5B Lenses:\*\*[ \t]*(.+)$",
    flags=re.MULTILINE,
)
_BOLD_CHUNK = re.compile(
    r"^\*\*Chunk (U[0-9]{4})\*\*(.*?)"
    r"(?=^\*\*Chunk U[0-9]{4}\*\*|\Z)",
    flags=re.DOTALL | re.MULTILINE,
)
_BOLD_INCLUDE = re.compile(
    r"^Decision:[ \t]*\*\*INCLUDE\*\*",
    flags=re.MULTILINE,
)


def normalize_routing_table(
    *,
    raw_path: Path,
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch:
    """Convert only explicit included table rows; default every other chunk excluded."""

    raw = raw_path.read_text(encoding="utf-8")
    json_result = _normalize_explicit_json(raw, source, chunk_ids)
    if json_result is not None:
        return json_result
    section_result = normalize_section_tables(
        raw=raw, source=source, chunk_ids=chunk_ids
    )
    if section_result is not None:
        return section_result
    included, explanations = _markdown_inclusions(raw)
    unknown = sorted(set(included) - set(chunk_ids))
    if unknown:
        raise ValueError(f"routing table contains unknown chunks: {unknown}")
    if not included:
        raise ValueError("routing table contains no explicit included chunks")
    return RoutingDecisionBatch(
        decisions=tuple(
            ChunkRoutingDecision(
                schema_version="chunk_routing_decision_v1",
                source_id=source.source_id,
                source_sha256=source.source_sha256,
                chunk_id=chunk_id,
                included=chunk_id in included,
                relevant_question_ids=included.get(chunk_id, ()),
                relevance_strength="material" if chunk_id in included else "none",
                explanation=explanations.get(
                    chunk_id,
                    "M2.7 routing table did not include this frozen chunk.",
                ),
                exclusion_reason=(
                    None
                    if chunk_id in included
                    else "Not included in the model's explicit high-recall table."
                ),
            )
            for chunk_id in chunk_ids
        )
    )


def _markdown_inclusions(
    raw: str,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Parse supported explicit Markdown routing dialects."""

    included: dict[str, tuple[str, ...]] = {}
    explanations: dict[str, str] = {}
    match = _INCLUDED_SECTION.search(raw)
    if match is not None:
        for row in _ROW.finditer(match.group()):
            _record_row(row.groups(), included, explanations)
        return included, explanations
    _parse_markdown_table(raw, included, explanations)
    if not included:
        _parse_heading_sections(raw, included, explanations)
    if not included:
        _parse_bold_sections(raw, included, explanations)
    return included, explanations


def _parse_markdown_table(
    raw: str,
    included: dict[str, tuple[str, ...]],
    explanations: dict[str, str],
) -> None:
    for line in raw.splitlines():
        cells = [cell.strip().replace("**", "") for cell in line.split("|")]
        if len(cells) >= 5 and re.fullmatch(r"U[0-9]{4}", cells[1]):
            if "INCLUDE" in cells:
                _record_row((cells[1], line), included, explanations)


def _parse_heading_sections(
    raw: str,
    included: dict[str, tuple[str, ...]],
    explanations: dict[str, str],
) -> None:
    for chunk_id, body in _CHUNK_SECTION.findall(raw):
        lenses = _APPLICABLE_LENSES.search(body)
        if _INCLUDE_DECISION.search(body) and lenses is not None:
            _record_row((chunk_id, lenses.group()), included, explanations)


def _parse_bold_sections(
    raw: str,
    included: dict[str, tuple[str, ...]],
    explanations: dict[str, str],
) -> None:
    for chunk_id, body in _BOLD_CHUNK.findall(raw):
        if not _BOLD_INCLUDE.search(body):
            continue
        question_line = next(
            (line for line in body.splitlines() if line.startswith("Question IDs:")),
            "",
        )
        _record_row((chunk_id, question_line), included, explanations)


def _normalize_explicit_json(
    raw: str,
    source: SourceDescriptor,
    chunk_ids: tuple[str, ...],
) -> RoutingDecisionBatch | None:
    """Normalize M3's explicit routing dialect without inferring omitted decisions."""

    payload = _json_payload(raw)
    if payload is None:
        return None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = resolve_decision_rows(payload)
        if rows is None:
            return None
    else:
        return None
    parsed = tuple(_parse_json_decision(row, source) for row in rows)
    parsed = apply_inverse_adjacency(rows, parsed)
    received_ids = tuple(item.chunk_id for item in parsed)
    if len(received_ids) != len(set(received_ids)):
        raise ValueError("routing JSON contains duplicate chunk decisions")
    if set(received_ids) != set(chunk_ids):
        missing = sorted(set(chunk_ids) - set(received_ids))
        unknown = sorted(set(received_ids) - set(chunk_ids))
        raise ValueError(
            f"routing JSON chunk set mismatch; missing={missing}, unknown={unknown}"
        )
    by_id = {item.chunk_id: item for item in parsed}
    return RoutingDecisionBatch(decisions=tuple(by_id[item] for item in chunk_ids))


def _json_payload(raw: str) -> Any | None:
    candidates = [unwrap_json_fence(raw)]
    fences = re.findall(r"```([A-Za-z]*)\s*(.*?)\s*```", raw, flags=re.DOTALL)
    candidates.extend(body for tag, body in fences if tag.lower() == "json")
    candidates.extend(body for tag, body in fences if not tag)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _parse_json_decision(
    row: Any,
    source: SourceDescriptor,
) -> ChunkRoutingDecision:
    if not isinstance(row, dict):
        raise ValueError("routing JSON decisions must be objects")
    chunk_id = required_string(row, "chunk_id")
    decision = _decision_value(row, chunk_id)
    decision = {"included": "include", "excluded": "exclude"}.get(decision, decision)
    if decision not in {"include", "exclude"}:
        raise ValueError(f"{chunk_id}: unsupported routing decision {decision!r}")
    included = decision == "include"
    question_ids = resolve_question_ids(row, chunk_id)
    relevance = _relevance(
        row.get("relevance", "material" if included else "none"),
        chunk_id,
        included,
    )
    explanation = _decision_explanation(row, chunk_id, included, question_ids)
    adjacent_chunk_ids = resolve_adjacent_ids(row, chunk_id, included)
    exclusion_reason = row.get("exclusion_reason")
    if exclusion_reason is not None and not isinstance(exclusion_reason, str):
        raise ValueError(f"{chunk_id}: exclusion_reason must be text or null")
    return ChunkRoutingDecision(
        schema_version="chunk_routing_decision_v1",
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        chunk_id=chunk_id,
        included=included,
        relevant_question_ids=question_ids,
        relevance_strength=relevance,
        adjacent_chunk_ids=adjacent_chunk_ids,
        explanation=explanation,
        exclusion_reason=exclusion_reason,
    )


def _decision_value(row: dict[str, Any], chunk_id: str) -> str:
    values: list[str] = []
    decision = row.get("decision")
    if decision is not None:
        if not isinstance(decision, str) or not decision.strip():
            raise ValueError(f"{chunk_id}: routing decision must be text")
        values.append(
            {"included": "include", "excluded": "exclude"}.get(
                decision.strip().lower(),
                decision.strip().lower(),
            )
        )
    if isinstance(row.get("include"), bool):
        values.append("include" if row["include"] else "exclude")
    if row.get("relevance") in {"include", "exclude"}:
        values.append(str(row["relevance"]))
    if not values:
        raise ValueError(f"{chunk_id}: routing JSON requires an explicit decision")
    if len(set(values)) != 1:
        raise ValueError(f"{chunk_id}: routing disposition aliases conflict")
    return values[0]


def _decision_explanation(
    row: dict[str, Any],
    chunk_id: str,
    included: bool,
    question_ids: tuple[str, ...],
) -> str:
    cited_lenses = row.get("evidence_cited_lenses")
    if cited_lenses is not None:
        if (
            not isinstance(cited_lenses, dict)
            or not cited_lenses
            or not all(
                isinstance(item, str) and item.strip()
                for item in cited_lenses.values()
            )
        ):
            raise ValueError(f"{chunk_id}: evidence_cited_lenses must map IDs to text")
        cited_ids = validate_question_ids(list(cited_lenses), chunk_id)
        if not set(cited_ids).issubset(question_ids):
            raise ValueError(
                f"{chunk_id}: evidence_cited_lenses disagree with question_ids"
            )
    text_row = {
        name: row[name]
        for name in ("adjacent_context", "adjacent_context_needed")
        if isinstance(row.get(name), str)
    }
    adjacent = resolve_text_alias(
        text_row, chunk_id, ("adjacent_context", "adjacent_context_needed")
    )
    rationale = resolve_optional_text_alias(
        row,
        chunk_id,
        ("rationale", "explanation", "material_finding"),
    )
    if rationale:
        return rationale
    if adjacent:
        return adjacent
    relevance = prose_relevance(row.get("relevance"))
    if relevance:
        return relevance
    relevant_facts = row.get("relevant_facts")
    if (
        included
        and isinstance(relevant_facts, list)
        and relevant_facts
        and all(isinstance(item, str) and item.strip() for item in relevant_facts)
    ):
        return "; ".join(relevant_facts)
    if included and isinstance(cited_lenses, dict):
        return "; ".join(cited_lenses.values())
    exclusion = row.get("exclusion_reason")
    if not included and isinstance(exclusion, str) and exclusion.strip():
        return exclusion.strip()
    raise ValueError(f"{chunk_id}: routing JSON lacks an explicit explanation")


def _relevance(value: Any, chunk_id: str, included: bool) -> str:
    if isinstance(value, dict) and included and value:
        return "material"
    if not isinstance(value, str):
        raise ValueError(f"{chunk_id}: relevance must be text")
    normalized = value.lower()
    mapping = {
        "none": "none",
        "low": "weak",
        "weak": "weak",
        "medium": "material",
        "material": "material",
        "high": "pivotal",
        "pivotal": "pivotal",
    }
    try:
        result = mapping[normalized]
    except KeyError as exc:
        if included and normalized.strip():
            result = "material"
        elif not included and normalized.strip():
            result = "none"
        else:
            raise ValueError(f"{chunk_id}: unsupported relevance {value!r}") from exc
    if (included and result == "none") or (
        not included and result not in {"none", "weak"}
    ):
        raise ValueError(f"{chunk_id}: decision and relevance conflict")
    return result


def latest_model_output(stage_root: Path) -> Path:
    """Return the latest non-empty attempt output for a failed stage."""

    paths = sorted(stage_root.glob("attempt-*/output.json"))
    nonempty = [path for path in paths if path.stat().st_size]
    if not nonempty:
        raise ValueError(f"failed stage has no model output: {stage_root}")
    return nonempty[-1]


def stage_tokens(stage_root: Path) -> int:
    """Sum provider-reported attempt usage, including discarded attempts."""

    from .execution import read_stage_usage

    total = 0
    for path in stage_root.glob("attempt-*/events.jsonl"):
        usage = read_stage_usage(path)
        total += usage.get("total_tokens") or (
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
    return total


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("**", "")).strip(" |")


def _record_row(
    row: tuple[str, str],
    included: dict[str, tuple[str, ...]],
    explanations: dict[str, str],
) -> None:
    chunk_id, cells = row
    questions = tuple(dict.fromkeys(_QUESTION.findall(cells)))
    if questions:
        included[chunk_id] = questions
        explanations[chunk_id] = _plain(cells)


__all__ = ["latest_model_output", "normalize_routing_table", "stage_tokens"]
