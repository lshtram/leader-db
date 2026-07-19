"""Build a live cost, performance, coverage, and source-quality profile."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from .data import load, questions


def write_profile(output_dir: Path) -> Path:
    """Derive one monitoring profile from durable turn and output artifacts."""

    state = _read(output_dir / "session.json")
    evidence = _read(output_dir / "evidence.json").get("evidence", [])
    mappings = _read(output_dir / "mappings.json").get("questions", {})
    research = _profiles(output_dir / ".researcher")
    luna = _profiles(output_dir / ".luna")
    usage = _research_usage(output_dir / ".researcher")
    pricing = load("researchers.json")[state["researcher"]].get("pricing_per_million")
    domains = Counter(
        urlparse(item["url"]).netloc.lower().removeprefix("www.") for item in evidence
    )
    summary_lengths = [len(item["summary"]) for item in evidence]
    result = {
        "identity": {key: state[key] for key in ("ruler", "country", "year")},
        "researcher": state["researcher"],
        "progress": {
            "completed_steps": len(state["completed"]),
            "total_steps": len(questions()) + 1,
            "last_step": state["completed"][-1] if state["completed"] else None,
            "pending": state.get("pending"),
        },
        "research": _runtime(research, cumulative_usage=usage),
        "formatter": _runtime(luna, cumulative_usage=_sum_usage(luna)),
        "estimated_researcher_cost_usd": _cost(usage, pricing),
        "evidence": {
            "records": len(evidence),
            "unique_urls": len({item["url"] for item in evidence}),
            "unique_domains": len(domains),
            "top_domains": domains.most_common(10),
            "mapped_questions": len(mappings),
            "empty_mappings": [key for key, value in mappings.items() if not value["evidence_ids"]],
            "summary_characters": {
                "median": statistics.median(summary_lengths) if summary_lengths else 0,
                "maximum": max(summary_lengths, default=0),
                "at_600_limit": sum(length == 600 for length in summary_lengths),
            },
        },
    }
    path = output_dir / "profile.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def _runtime(
    profiles: list[dict[str, object]], cumulative_usage: dict[str, int]
) -> dict[str, object]:
    durations = [float(item["duration_seconds"]) for item in profiles]
    tools: Counter[str] = Counter()
    for item in profiles:
        tools.update(item.get("tool_calls", {}))
    return {
        "completed_turns": len(profiles),
        "total_duration_seconds": round(sum(durations), 3),
        "median_duration_seconds": round(statistics.median(durations), 3) if durations else 0,
        "maximum_duration_seconds": round(max(durations), 3) if durations else 0,
        "usage": cumulative_usage,
        "tool_calls": dict(tools),
        "tool_errors": sum(int(item.get("tool_errors", 0)) for item in profiles),
    }


def _cost(usage: dict[str, int], pricing: dict[str, float] | None) -> float | None:
    if not pricing or not usage:
        return None
    cached = usage.get("cached_input_tokens", 0)
    uncached = max(0, usage.get("input_tokens", 0) - cached)
    total = (
        uncached * pricing["input"]
        + cached * pricing["cached_input"]
        + usage.get("output_tokens", 0) * pricing["output"]
    ) / 1_000_000
    return round(total, 6)


def _profiles(directory: Path) -> list[dict[str, object]]:
    return [_read(path) for path in sorted(directory.glob("turn-*.profile.json"))]


def _sum_usage(profiles: list[dict[str, object]]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for item in profiles:
        total.update(item.get("usage", {}))
    return dict(total)


def _research_usage(directory: Path) -> dict[str, int]:
    """Sum cumulative usage once per persistent thread."""

    by_thread: dict[str, dict[str, int]] = {}
    for path in sorted(directory.glob("turn-*.jsonl")):
        thread_id = ""
        usage: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                thread_id = str(event.get("thread_id", ""))
            if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                usage = event["usage"]
        if thread_id and usage:
            by_thread[thread_id] = usage
    total: Counter[str] = Counter()
    for usage in by_thread.values():
        total.update(usage)
    return dict(total)


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value
