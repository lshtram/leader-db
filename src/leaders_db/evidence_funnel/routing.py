"""Deterministic routing support around the high-recall model decision."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from json_repair import repair_json
from pydantic import BaseModel

from .config import EvidenceFunnelConfig
from .ingest import FrozenExtraction
from .models import ChunkRoutingDecision


def render_stage_prompt(
    config: EvidenceFunnelConfig,
    stage: str,
    *,
    questions: Mapping[str, str],
    research_specification: str,
) -> str:
    """Render one routing/extraction prompt with all configured question lenses."""

    if tuple(questions) != config.methodology_ids:
        raise ValueError("questions must exactly match configured methodology IDs and order")
    question_block = "\n".join(f"{key}: {value}" for key, value in questions.items())
    return "\n\n".join(
        (
            config.prompts[stage],
            f"Chapter questions:\n{question_block}",
            f"Research specification:\n{research_specification}",
        )
    )


def complete_source_routing(
    extraction: FrozenExtraction,
    *,
    question_ids: Sequence[str],
    short_record_max_tokens: int,
) -> tuple[ChunkRoutingDecision, ...] | None:
    """Forward a short source in full; longer documents require question routing."""

    if extraction.estimated_source_tokens > short_record_max_tokens:
        return None
    return tuple(
        ChunkRoutingDecision(
            schema_version="chunk_routing_decision_v1",
            source_id=extraction.source_id,
            source_sha256=extraction.raw_sha256,
            chunk_id=f"unit-{unit.unit:04d}",
            included=True,
            relevant_question_ids=tuple(question_ids),
            relevance_strength="weak",
            adjacent_chunk_ids=(),
            explanation="Short record forwarded in full for extractor-level relevance filtering.",
        )
        for unit in extraction.units
    )


def include_adjacent_context(
    decisions: Sequence[ChunkRoutingDecision], *, adjacent_count: int
) -> tuple[str, ...]:
    """Return included chunk IDs plus requested neighboring chunks in source order."""

    if adjacent_count < 0:
        raise ValueError("adjacent_count cannot be negative")
    ordered_ids = [item.chunk_id for item in decisions]
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError("routing decisions require unique chunk IDs")
    positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
    requested_adjacent = {
        chunk_id
        for decision in decisions
        if decision.included
        for chunk_id in decision.adjacent_chunk_ids
    }
    unknown_adjacent = sorted(requested_adjacent - set(positions))
    if unknown_adjacent:
        raise ValueError(f"routing references unknown adjacent chunks: {unknown_adjacent}")
    selected: set[str] = set()
    for decision in decisions:
        if not decision.included:
            continue
        center = positions[decision.chunk_id]
        start = max(0, center - adjacent_count)
        end = min(len(ordered_ids), center + adjacent_count + 1)
        selected.update(ordered_ids[start:end])
        selected.update(decision.adjacent_chunk_ids)
    return tuple(chunk_id for chunk_id in ordered_ids if chunk_id in selected)


def normalize_model_json(raw: str, model: type[BaseModel]) -> BaseModel:
    """Repair serialization envelopes only, then validate the original content."""

    payload = extract_json_object(raw)
    return model.model_validate(payload)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Repair serialization envelopes and one known split-root syntax error."""

    payload, _ = extract_json_object_with_trace(raw)
    return payload


def extract_json_object_with_trace(raw: str) -> tuple[dict[str, Any], str]:
    """Return one object plus the deterministic normalization method selected."""

    candidates = [("raw", raw.strip())]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, ("fenced-envelope", fenced.group(1)))
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(("substring-envelope", raw[first : last + 1]))
    for origin, candidate in candidates:
        for repair_kind, normalized in _serialization_repairs(candidate):
            try:
                payload = json.loads(normalized)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                if origin == "raw":
                    kind = repair_kind
                elif repair_kind == "none":
                    kind = origin
                else:
                    kind = f"{origin}+{repair_kind}"
                return payload, kind
    for origin, candidate in candidates:
        repaired = repair_json(
            candidate,
            return_objects=True,
            skip_json_loads=True,
        )
        if isinstance(repaired, dict):
            kind = (
                "json-repair"
                if origin == "raw"
                else f"{origin}+json-repair"
            )
            return repaired, kind
    raise ValueError("model output does not contain a JSON object")


def _serialization_repairs(raw: str) -> tuple[tuple[str, str], ...]:
    split_root = _repair_split_candidate_batch(raw)
    values = (
        ("none", raw),
        ("split-candidate-root", split_root),
        ("escaped-excerpt-locator-boundary", _repair_escaped_locator_boundary(raw)),
        (
            "escaped-excerpt-locator-boundary-after-split-root",
            _repair_escaped_locator_boundary(split_root),
        ),
        (
            "quoted-source-limitations-question-ids-boundary",
            _repair_quoted_question_ids_boundary(raw),
        ),
        (
            "quoted-source-limitations-question-ids-boundary-after-split-root",
            _repair_quoted_question_ids_boundary(split_root),
        ),
    )
    unique: dict[str, str] = {}
    for kind, value in values:
        unique.setdefault(value, kind)
    return tuple((kind, value) for value, kind in unique.items())


def _repair_split_candidate_batch(raw: str) -> str:  # noqa: PLR0912
    """Rejoin a candidate batch whose root was closed before sibling fields."""

    if not re.match(r'^\s*\{\s*"candidates"\s*:', raw):
        return raw
    recognized = {
        '"inspected_locator_count"',
        '"locator_dispositions"',
        '"material_omissions"',
        '"unresolved_gaps"',
    }
    brace_depth = 0
    bracket_depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth -= 1
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth -= 1
            if bracket_depth == 0 and brace_depth == 1:
                repaired = _remove_split_root_braces(raw, index, recognized)
                if repaired is not None:
                    return repaired
    return raw


def _repair_escaped_locator_boundary(raw: str) -> str:
    """Close one excerpt string before an accidentally escaped locator key."""

    if not re.match(r'^\s*\{\s*"candidates"\s*:', raw):
        return raw
    malformed = '\\",\\"locator":'
    if raw.count(malformed) != 1:
        return raw
    boundary = raw.index(malformed)
    field_starts = tuple(
        re.finditer(r'(?<!\\)"([A-Za-z_]+)"\s*:\s*"', raw[:boundary])
    )
    if not field_starts or field_starts[-1].group(1) != "excerpt":
        return raw
    return raw.replace(malformed, '\\"","locator":', 1)


def _repair_quoted_question_ids_boundary(raw: str) -> str:
    """Remove one stray quote between source limitations and question IDs."""

    if not re.match(r'^\s*\{\s*"candidates"\s*:', raw):
        return raw
    malformed = ']","question_ids":'
    if raw.count(malformed) != 1:
        return raw
    boundary = raw.index(malformed)
    field_starts = tuple(
        re.finditer(r'(?<!\\)"([A-Za-z_]+)"\s*:\s*[\["]', raw[:boundary])
    )
    if not field_starts or field_starts[-1].group(1) != "source_limitations":
        return raw
    return raw.replace(malformed, '],"question_ids":', 1)


def _remove_split_root_braces(
    raw: str, array_end: int, recognized: set[str]
) -> str | None:
    close_root = _next_non_whitespace(raw, array_end + 1)
    if close_root >= len(raw) or raw[close_root] != "}":
        return None
    comma = _next_non_whitespace(raw, close_root + 1)
    if comma >= len(raw) or raw[comma] != ",":
        return None
    open_sibling = _next_non_whitespace(raw, comma + 1)
    if open_sibling >= len(raw) or raw[open_sibling] != "{":
        return None
    sibling_key = _next_non_whitespace(raw, open_sibling + 1)
    if not any(raw.startswith(key, sibling_key) for key in recognized):
        return None
    return raw[:close_root] + raw[close_root + 1 : open_sibling] + raw[open_sibling + 1 :]


def _next_non_whitespace(raw: str, start: int) -> int:
    while start < len(raw) and raw[start].isspace():
        start += 1
    return start


__all__ = [
    "complete_source_routing",
    "extract_json_object",
    "extract_json_object_with_trace",
    "include_adjacent_context",
    "normalize_model_json",
    "render_stage_prompt",
]
