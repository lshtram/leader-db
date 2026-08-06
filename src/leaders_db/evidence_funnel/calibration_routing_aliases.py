"""Strict alias handling for calibration routing model output."""

from __future__ import annotations

import re
from typing import Any

from .models import ChunkRoutingDecision

_QUESTION = re.compile(r"5B\.(?:10|[1-9])")
_RELEVANCE_LABELS = frozenset(
    {
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
    }
)


def resolve_decision_rows(payload: dict[str, Any]) -> list[Any] | None:
    """Return the sole supplied routing-decision list alias."""

    values = [
        payload[name]
        for name in ("decisions", "router_decisions", "routing_decisions")
        if name in payload
    ]
    if not values:
        return None
    if len(values) > 1:
        raise ValueError("routing JSON decision-list aliases conflict")
    if not isinstance(values[0], list):
        raise ValueError("routing JSON decisions must be a list")
    return values[0]


def resolve_question_ids(row: dict[str, Any], chunk_id: str) -> tuple[str, ...]:
    """Validate every supplied question-ID alias and reject disagreement."""

    values = [
        validate_question_ids(row[name], chunk_id)
        for name in (
            "question_ids",
            "applicable_question_ids",
            "applicable_lenses",
            "5B_lenses",
        )
        if name in row
    ]
    if not values:
        return ()
    if len(set(values)) != 1:
        raise ValueError(f"{chunk_id}: question ID aliases conflict")
    return values[0]


def validate_question_ids(value: Any, chunk_id: str) -> tuple[str, ...]:
    """Return one validated, duplicate-free tuple of Chapter 5B question IDs."""

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{chunk_id}: question_ids must be a list of strings")
    questions = tuple(value)
    invalid = [item for item in questions if _QUESTION.fullmatch(item) is None]
    if invalid:
        raise ValueError(f"{chunk_id}: question_ids contain non-5B IDs: {invalid}")
    if len(questions) != len(set(questions)):
        raise ValueError(f"{chunk_id}: question_ids contain duplicates")
    return questions


def resolve_text_alias(
    row: dict[str, Any],
    chunk_id: str,
    names: tuple[str, ...],
) -> str | None:
    """Validate supplied text aliases and reject non-identical values."""

    values: list[str] = []
    for name in names:
        if name not in row:
            continue
        value = row[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{chunk_id}: {name} must be non-empty text")
        values.append(value.strip())
    if len(set(values)) > 1:
        raise ValueError(f"{chunk_id}: {'/'.join(names)} aliases conflict")
    return values[0] if values else None


def resolve_optional_text_alias(
    row: dict[str, Any],
    chunk_id: str,
    names: tuple[str, ...],
) -> str | None:
    """Resolve text aliases while allowing explicit null values."""

    supplied = {name: row[name] for name in names if row.get(name) is not None}
    return resolve_text_alias(supplied, chunk_id, names)


def required_string(row: dict[str, Any], field: str) -> str:
    """Return one required non-empty string field."""

    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"routing JSON requires non-empty {field}")
    return value.strip()


def resolve_adjacent_ids(
    row: dict[str, Any],
    chunk_id: str,
    included: bool,
) -> tuple[str, ...]:
    """Validate list-valued adjacent-context aliases."""

    supplied = [
        row[name]
        for name in ("adjacent_context", "adjacent_context_needed")
        if row.get(name) is not None
    ]
    representations = {"text" if isinstance(value, str) else "list" for value in supplied}
    if len(representations) > 1:
        raise ValueError(f"{chunk_id}: adjacent context aliases use mixed representations")
    values: list[tuple[str, ...]] = []
    prose_values: list[tuple[str, ...]] = []
    kinds: list[str] = []
    for name in ("adjacent_context", "adjacent_context_needed"):
        value = row.get(name)
        if value is None or isinstance(value, str):
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{chunk_id}: {name} must be text or a list of chunk IDs")
        ids = tuple(value)
        matches = tuple(re.fullmatch(r"U[0-9]{4}", item) is not None for item in ids)
        if ids and not any(matches):
            if any(not item.strip() for item in ids):
                raise ValueError(f"{chunk_id}: adjacent context prose must be non-empty")
            kinds.append("prose")
            prose_values.append(ids)
            continue
        if not all(matches):
            raise ValueError(f"{chunk_id}: mixed adjacent chunk IDs and prose")
        if len(set(ids)) != len(ids):
            raise ValueError(f"{chunk_id}: duplicate adjacent chunk IDs")
        kinds.append("ids")
        values.append(ids)
    if len(set(kinds)) > 1:
        raise ValueError(f"{chunk_id}: adjacent context aliases conflict")
    if len(set(prose_values)) > 1:
        raise ValueError(f"{chunk_id}: adjacent context prose aliases conflict")
    if len(set(values)) > 1:
        raise ValueError(f"{chunk_id}: adjacent chunk ID aliases conflict")
    result = values[0] if values else ()
    return result if included else ()


def resolve_inverse_adjacency(rows: list[Any]) -> dict[str, tuple[str, ...]]:
    """Invert ``adjacent_context_for`` links into target-owned context IDs."""

    row_ids = {
        row.get("chunk_id")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("chunk_id"), str)
    }
    by_target: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or "adjacent_context_for" not in row:
            continue
        chunk_id = row.get("chunk_id")
        value = row["adjacent_context_for"]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{chunk_id}: adjacent_context_for must be a list of chunk IDs")
        if len(set(value)) != len(value):
            raise ValueError(f"{chunk_id}: duplicate adjacent_context_for IDs")
        unknown = [item for item in value if item not in row_ids]
        if unknown:
            raise ValueError(f"{chunk_id}: unknown adjacent_context_for IDs: {unknown}")
        if chunk_id in value:
            raise ValueError(f"{chunk_id}: adjacent_context_for cannot reference itself")
        for target in value:
            by_target.setdefault(target, []).append(str(chunk_id))
    return {target: tuple(values) for target, values in by_target.items()}


def apply_inverse_adjacency(
    rows: list[Any],
    decisions: tuple[ChunkRoutingDecision, ...],
) -> tuple[ChunkRoutingDecision, ...]:
    """Attach inverse context links only to included target decisions."""

    inverse = resolve_inverse_adjacency(rows)
    decisions_by_id = {item.chunk_id: item for item in decisions}
    for row in rows:
        if not isinstance(row, dict):
            continue
        chunk_id = row.get("chunk_id")
        decision = decisions_by_id.get(chunk_id)
        if decision is None or decision.included:
            continue
        for name in ("adjacent_context", "adjacent_context_needed"):
            value = row.get(name)
            if (
                isinstance(value, list)
                and value
                and all(re.fullmatch(r"U[0-9]{4}", item) for item in value)
            ):
                for target in value:
                    inverse[target] = tuple(
                        dict.fromkeys((*inverse.get(target, ()), decision.chunk_id))
                    )
    unknown_targets = sorted(set(inverse) - set(decisions_by_id))
    if unknown_targets:
        raise ValueError(f"adjacent context targets unknown chunks: {unknown_targets}")
    included_ids = {item.chunk_id for item in decisions if item.included}
    excluded_targets = sorted(set(inverse) - included_ids)
    if excluded_targets:
        raise ValueError(
            f"adjacent_context_for targets excluded chunks: {excluded_targets}"
        )
    return tuple(
        ChunkRoutingDecision.model_validate(
            {
                **item.model_dump(mode="python"),
                "adjacent_chunk_ids": tuple(
                    dict.fromkeys(item.adjacent_chunk_ids + inverse.get(item.chunk_id, ()))
                ),
            }
        )
        for item in decisions
    )


def prose_relevance(value: Any) -> str | None:
    """Return free-text relevance reasoning, excluding controlled labels."""

    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in _RELEVANCE_LABELS:
        return None
    return stripped


def unwrap_json_fence(raw: str) -> str:
    """Remove one complete Markdown code fence from a JSON candidate."""

    stripped = raw.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        return stripped[7:-3].strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped[3:-3].strip()
    return stripped
