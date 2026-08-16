"""Trusted event discovery, classification, and aggregation for cost profiles."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

from .cost_profile_models import StageRule, StageRules

TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
_CHAPTERS = tuple(f"{number}B" for number in range(1, 9))


def event_rows(root: Path, rules: StageRules) -> list[dict[str, Any]]:
    """Return one normalized row for every completed or failed event artifact."""

    selected_roots = _selected_artifact_roots(root)
    seen: set[Path] = set()
    rows = []
    for path in sorted(root.rglob(rules.event_filename)):
        resolved = path.resolve(strict=True)
        if resolved in seen:
            continue
        seen.add(resolved)
        relative = PurePosixPath(path.relative_to(root).as_posix())
        rule = _classify(relative, rules.rules)
        if rule is None:
            raise ValueError(f"event artifact has no stage rule: {relative}")
        chapter_id = next((part for part in relative.parts if part in _CHAPTERS), None)
        status = _selection_status(relative, chapter_id, rule, selected_roots)
        usages = tuple(_completed_usages(path))
        if not usages:
            rows.append(_failed_row(relative, chapter_id, rule))
        for call_index, usage in enumerate(usages, start=1):
            rows.append(_completed_row(relative, chapter_id, rule, status, call_index, usage))
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    """Aggregate completed calls, failed calls, tokens, and cache rate."""

    result: dict[str, int | float] = {
        "calls": sum(row["call_status"] == "completed" for row in rows),
        "failed_calls": sum(row["call_status"] == "failed" for row in rows),
    }
    for key in TOKEN_KEYS:
        result[key] = sum(row[key] for row in rows)
    inputs = int(result["input_tokens"])
    result["cache_rate"] = (
        round(int(result["cached_input_tokens"]) / inputs, 6) if inputs else 0
    )
    return result


def group_totals(
    rows: list[dict[str, Any]], key: str
) -> dict[str, dict[str, int | float]]:
    """Aggregate rows by a stable string dimension."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {name: totals(grouped[name]) for name in sorted(grouped)}


def cache_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count calls meeting the plan's cache-rate thresholds."""

    rates = [
        row["cached_input_tokens"] / row["input_tokens"]
        for row in rows
        if row["input_tokens"]
    ]
    return {
        "calls_with_input": len(rates),
        "at_least_10_percent": sum(rate >= 0.1 for rate in rates),
        "at_least_50_percent": sum(rate >= 0.5 for rate in rates),
        "at_least_90_percent": sum(rate >= 0.9 for rate in rates),
    }


def output_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return deterministic minimum, median, p90, and maximum output sizes."""

    values = sorted(row["output_tokens"] for row in rows)
    if not values:
        return {"minimum": 0, "median": 0, "p90": 0, "maximum": 0}
    return {
        "minimum": values[0],
        "median": values[(len(values) - 1) // 2],
        "p90": values[min(len(values) - 1, (len(values) * 9 + 9) // 10 - 1)],
        "maximum": values[-1],
    }


def _completed_usages(path: Path) -> Iterable[dict[str, Any]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSONL at {path}:{line_number}") from exc
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            raise ValueError(f"completed event has no usage at {path}:{line_number}")
        yield usage


def _completed_row(
    path: PurePosixPath,
    chapter_id: str | None,
    rule: StageRule,
    status: str,
    call_index: int,
    usage: dict[str, Any],
) -> dict[str, Any]:
    input_tokens = _token(usage, "input_tokens")
    cached = _token(usage, "cached_input_tokens")
    if cached > input_tokens:
        raise ValueError(f"cached input exceeds input in {path}")
    return {
        "event_path": path.as_posix(), "call_index": call_index,
        "artifact_type": rule.artifact_type, "stage": rule.stage,
        "chapter_id": chapter_id or "shared", "selection_status": status,
        "call_status": "completed", "input_tokens": input_tokens,
        "cached_input_tokens": cached, "uncached_input_tokens": input_tokens - cached,
        "output_tokens": _token(usage, "output_tokens"),
        "reasoning_output_tokens": _token(usage, "reasoning_output_tokens"),
    }


def _failed_row(
    path: PurePosixPath, chapter_id: str | None, rule: StageRule
) -> dict[str, Any]:
    return {
        "event_path": path.as_posix(), "call_index": 0,
        "artifact_type": rule.artifact_type, "stage": rule.stage,
        "chapter_id": chapter_id or "shared", "selection_status": "failed",
        "call_status": "failed", **dict.fromkeys(TOKEN_KEYS, 0),
    }


def _token(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"invalid {key}: {value!r}")
    return value


def _classify(path: PurePosixPath, rules: tuple[StageRule, ...]) -> StageRule | None:
    matches = [rule for rule in rules if fnmatchcase(path.as_posix(), rule.path_pattern)]
    if len(matches) > 1:
        raise ValueError(f"event artifact matches multiple stage rules: {path}")
    return matches[0] if matches else None


def _selected_artifact_roots(root: Path) -> dict[str, set[PurePosixPath]]:
    path = root / "selected-chapter-manifest.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected: dict[str, set[PurePosixPath]] = defaultdict(set)
    for chapter in payload.get("chapters", []):
        if isinstance(chapter, dict):
            chapter_id = str(chapter.get("chapter_id", ""))
            for key, value in chapter.items():
                if key.endswith("_path") and isinstance(value, str):
                    selected[chapter_id].add(PurePosixPath(value).parent)
    return dict(selected)


def _selection_status(
    path: PurePosixPath,
    chapter_id: str | None,
    rule: StageRule,
    selected_roots: dict[str, set[PurePosixPath]],
) -> str:
    if rule.selection_mode == "all_completed":
        return "selected"
    if chapter_id is None:
        return "superseded"
    return (
        "selected"
        if any(path.is_relative_to(root) for root in selected_roots.get(chapter_id, set()))
        else "superseded"
    )


__all__ = [
    "TOKEN_KEYS", "cache_distribution", "event_rows", "group_totals",
    "output_distribution", "totals",
]
