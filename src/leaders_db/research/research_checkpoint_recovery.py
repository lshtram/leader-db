"""Select the most complete valid research checkpoint across worker attempts."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from .model_profiles import ResearchModelProfile

ResearchCheckpoint = tuple[Path, str, Path, str, str]


def load_previous_research_checkpoint(
    trusted_dir: Path,
    *,
    job: dict[str, Any],
    profile: ResearchModelProfile,
) -> ResearchCheckpoint | None:
    """Recover the most complete valid checkpoint, not merely the newest attempt."""

    candidates = [
        checkpoint
        for directory in trusted_dir.parent.glob("*")
        if directory != trusted_dir
        and (checkpoint := _load_checkpoint(directory, job=job, profile=profile))
        is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=_progress_key)


def _load_checkpoint(
    directory: Path,
    *,
    job: dict[str, Any],
    profile: ResearchModelProfile,
) -> ResearchCheckpoint | None:
    path = directory / "research-notebook-checkpoint.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = (
        job["job_key"],
        job["provider_profile"],
        profile.provider,
        profile.model,
    )
    if not isinstance(payload, dict) or (
        payload.get("job_key"),
        payload.get("provider_profile"),
        payload.get("provider"),
        payload.get("model"),
    ) != expected:
        return None
    notebook_path = Path(str(payload.get("notebook_path", "")))
    events_path = Path(str(payload.get("events_path", "")))
    notebook_hash = str(payload.get("notebook_sha256", ""))
    events_hash = str(payload.get("events_sha256", ""))
    if not (
        notebook_path.is_file()
        and events_path.is_file()
        and sha256(notebook_path.read_bytes()).hexdigest() == notebook_hash
        and sha256(events_path.read_bytes()).hexdigest() == events_hash
    ):
        return None
    return (
        events_path,
        notebook_path.read_text(encoding="utf-8"),
        notebook_path,
        notebook_hash,
        events_hash,
    )


def _progress_key(checkpoint: ResearchCheckpoint) -> tuple[int, int, int]:
    notebook = checkpoint[1]
    chapters = len(set(re.findall(r"--- CHAPTER RESEARCH ([1-8]B) ---", notebook)))
    review_rounds = [
        int(value)
        for value in re.findall(r"--- EVIDENCE REVIEW ROUND (\d+) ---", notebook)
    ]
    return chapters, max(review_rounds, default=0), len(notebook)


__all__ = ["ResearchCheckpoint", "load_previous_research_checkpoint"]
