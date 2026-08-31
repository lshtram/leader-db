"""Recovery of immutable prior chapter-judge candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .chapter_judge_attempt import ChapterJudgeAttempt
from .chapter_judge_candidate import _prepare_batch
from .chapter_judge_models import ChapterJudgmentBatch


def _find_previous_chapter_candidate(job_dir: Path, *, attempt_dir: Path) -> dict[str, Any] | None:
    """Return the newest completed chapter candidate from an earlier attempt."""

    candidates = _find_previous_chapter_candidates(job_dir, attempt_dir=attempt_dir)
    return candidates[0] if candidates else None


def _find_previous_chapter_candidates(
    job_dir: Path, *, attempt_dir: Path
) -> tuple[dict[str, Any], ...]:
    """Return all completed candidates, newest first, for fallback recovery."""

    found: list[dict[str, Any]] = []
    attempts = sorted((job_dir / "attempts").glob("*"), reverse=True)
    for directory in attempts:
        if directory == attempt_dir or not (directory / "judge-complete.marker").is_file():
            continue
        for name in (
            "chapter-judgment.json",
            "chapter-judgment.orphaned.json",
            "chapter-judgment.pending.json",
        ):
            path = directory / name
            if not path.is_file() or path.stat().st_size > 10_000_000:
                continue
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                found.append(candidate)
                break
    return tuple(found)


def _recover_previous_chapter_batch(
    *, attempt: ChapterJudgeAttempt, job: dict[str, Any]
) -> tuple[ChapterJudgmentBatch | None, dict[str, Any] | None]:
    candidates = _find_previous_chapter_candidates(
        attempt.attempt_dir.parent.parent, attempt_dir=attempt.attempt_dir
    )
    for candidate in candidates:
        try:
            batch = _prepare_batch(
                candidate,
                job=job,
                dossiers=attempt.dossiers,
                projections=attempt.projections,
                rubric_version=attempt.rubric_version,
                events_path=attempt.events_path,
            )
        except (ValidationError, ValueError):
            continue
        return batch, candidate
    return None, candidates[0] if candidates else None
