"""Per-action token and payload-size audit for dossier LLM calls."""

from __future__ import annotations

import json
from math import ceil
from pathlib import Path
from typing import Any

from ._codex_worker_artifacts import read_codex_usage


def write_llm_usage_profile(attempt_dir: Path) -> Path:
    """Write one row per trusted LLM action without estimating actual usage."""

    trusted_root = attempt_dir.parent.parent / "trusted"
    rows: list[dict[str, Any]] = []
    for trusted_dir in sorted(trusted_root.glob("*")):
        event_paths = set(trusted_dir.glob("*.events.jsonl"))
        event_paths.update(
            path
            for name in ("research-events.jsonl", "codex-events.jsonl")
            if (path := trusted_dir / name).is_file()
        )
        for events_path in sorted(event_paths):
            rows.append(_profile_row(events_path))
    output_path = attempt_dir / "llm-usage-profile.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": "llm_usage_profile_v1",
                "actions": rows,
                "notes": (
                    "Actual token counters come from trusted provider events. "
                    "Prompt estimates are payload-size diagnostics only."
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output_path


_SECTION_MARKERS = (
    "Evidence-environment and authority briefing:",
    "Chapter questions and research note:",
    "Known resource index from prior turns:",
    "This is a fresh compact chapter session.",
    "For every newly accepted unit,",
    "The immutable selected lens scope is:",
    "Immutable job:",
    "Deterministic QA:",
    "Configured research workflow:",
    "Research notebook:",
    "Job input:",
    "Deduplicated local structured evidence",
    "Permissive evidence-research notebook and handoff:",
    "Existing candidate from a prior failed validation:",
    "Requirements:",
    "Immutable batch identity:",
    "Unavailable dossiers ",
    "Available dossier manifest:",
    "Embedded chapter projections ",
    "Active chapter guide:",
    "Return only the requested JSON batch.",
)


def _profile_row(events_path: Path) -> dict[str, Any]:
    prompt_path = _prompt_path(events_path)
    prompt = (
        prompt_path.read_text(encoding="utf-8")
        if prompt_path is not None and prompt_path.is_file()
        else None
    )
    prompt_chars = len(prompt) if prompt is not None else None
    usage = read_codex_usage(events_path)
    actual_usage = usage.model_dump(mode="json") if usage is not None else None
    if actual_usage is not None:
        input_tokens = actual_usage.get("input_tokens")
        cached_tokens = actual_usage.get("cached_input_tokens") or 0
        actual_usage["uncached_input_tokens"] = (
            max(0, input_tokens - cached_tokens)
            if isinstance(input_tokens, int)
            else None
        )
    estimated_tokens = ceil(prompt_chars / 3) if prompt_chars is not None else None
    return {
        "action": _action_name(events_path.name),
        "events_path": str(events_path),
        "prompt_path": str(prompt_path) if prompt_path is not None else None,
        "prompt_characters": prompt_chars,
        "estimated_prompt_tokens": estimated_tokens,
        "prompt_components": _prompt_components(prompt) if prompt is not None else [],
        "actual_usage": actual_usage,
        "input_amplification_vs_prompt_estimate": (
            round(actual_usage["input_tokens"] / estimated_tokens, 2)
            if actual_usage is not None
            and isinstance(actual_usage.get("input_tokens"), int)
            and estimated_tokens
            else None
        ),
    }


def _prompt_components(prompt: str) -> list[dict[str, Any]]:
    starts = [(0, "preamble")]
    for marker in _SECTION_MARKERS:
        offset = prompt.find(marker)
        if offset >= 0:
            starts.append((offset, marker.rstrip(":,.").lower().replace(" ", "_")))
    starts = sorted(set(starts))
    components = []
    for index, (start, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(prompt)
        characters = end - start
        components.append(
            {
                "component": name,
                "characters": characters,
                "estimated_tokens": ceil(characters / 3),
                "share_of_prompt": round(characters / len(prompt), 4) if prompt else 0,
            }
        )
    return components


def _prompt_path(events_path: Path) -> Path | None:
    name = events_path.name
    job_dir = events_path.parent.parent.parent
    matching_attempt = job_dir / "attempts" / events_path.parent.name
    if name == "research-events.jsonl":
        candidates = (
            events_path.parent / "research-prompt.txt",
            matching_attempt / "research-prompt.txt",
        )
    elif name == "codex-events.jsonl":
        candidates = (matching_attempt / "prompt.txt",)
    else:
        candidates = (events_path.with_name(name.replace(".events.jsonl", ".prompt.txt")),)
    return next((path for path in candidates if path.is_file()), candidates[0])


def _action_name(name: str) -> str:
    if name == "research-events.jsonl":
        return "research_reconnaissance"
    if name == "codex-events.jsonl":
        return "dossier_formatter"
    return name.removesuffix(".events.jsonl")


__all__ = ["write_llm_usage_profile"]
