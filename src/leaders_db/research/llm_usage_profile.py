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


def _profile_row(events_path: Path) -> dict[str, Any]:
    prompt_path = _prompt_path(events_path)
    prompt_chars = (
        len(prompt_path.read_text(encoding="utf-8"))
        if prompt_path is not None and prompt_path.is_file()
        else None
    )
    usage = read_codex_usage(events_path)
    return {
        "action": _action_name(events_path.name),
        "events_path": str(events_path),
        "prompt_path": str(prompt_path) if prompt_path is not None else None,
        "prompt_characters": prompt_chars,
        "estimated_prompt_tokens": ceil(prompt_chars / 3) if prompt_chars is not None else None,
        "actual_usage": usage.model_dump(mode="json") if usage is not None else None,
    }


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
