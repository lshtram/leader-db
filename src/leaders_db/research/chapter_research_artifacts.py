"""Resume and resource-index helpers for chapter research turns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._codex_worker_setup import WorkerAttempt
from .source_candidate_catalog import (
    _evidence_urls,
    read_source_candidate_catalog,
    recover_source_candidate_catalog,
)


def snapshot_parent_manifest(attempt: WorkerAttempt, destination: Path) -> None:
    """Freeze the parent ledger before a model can write a chapter delta."""

    current = attempt.attempt_dir / "research-ledger-manifest.json"
    if current.is_file():
        payload = current.read_text(encoding="utf-8")
    else:
        payload = json.dumps(
            {
                "schema_version": "ruler_research_ledger_manifest_v1",
                "entries": [],
            },
            sort_keys=True,
        )
    destination.write_text(payload, encoding="utf-8")


def existing_chapter_turn(
    attempt: WorkerAttempt,
    chapter_id: str,
    *,
    job_id: int,
    chapter_session_mode: str,
    prompt_hash: str,
    provider_profile: str,
) -> tuple[Path, Path, Path] | None:
    """Recover a completed chapter turn from any prior worker attempt."""

    job_dir = attempt.attempt_dir.parent.parent
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        events_path = trusted / f"research-chapter-{chapter_id}.events.jsonl"
        output_path = (
            job_dir / "attempts" / trusted.name / f"research-chapter-{chapter_id}.md"
        )
        if not events_path.is_file() or not output_path.is_file():
            continue
        starting_path = trusted / f"research-chapter-{chapter_id}.starting.json"
        base_manifest_path = trusted / f"research-ledger-before-{chapter_id}.json"
        try:
            starting = json.loads(starting_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            starting.get("job_id") != job_id
            or starting.get("chapter_session_mode") != chapter_session_mode
            or starting.get("prompt_sha256") != prompt_hash
            or starting.get("provider_profile") != provider_profile
            or not base_manifest_path.is_file()
        ):
            continue
        from .codex_worker import _events_show_completed_turn

        if _events_show_completed_turn(events_path):
            return events_path, output_path, base_manifest_path
    return None


def chapter_resource_index(
    attempt: WorkerAttempt, chapter_id: str
) -> tuple[dict[str, Any], ...]:
    """Expose evidence plus unresolved discovery candidates for one chapter."""

    path = attempt.attempt_dir / "research-ledger-manifest.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        entries = []
    relevant = []
    cross_chapter = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        compact = {
            key: entry[key]
            for key in ("provisional_id", "url", "claim", "locator", "disposition")
            if entry.get(key)
        }
        chapter_ids = entry.get("chapter_ids", [])
        if chapter_id in chapter_ids:
            relevant.append(compact)
        elif len(chapter_ids) >= 3:
            cross_chapter.append(compact)
    evidence_resources = (relevant[:15] + cross_chapter[:5])[:20]
    candidate_resources = _candidate_resources(attempt, chapter_id)
    return tuple((evidence_resources + candidate_resources)[:60])


def validate_chapter_inspection(
    handoff: str, *, chapter_id: str, minimum: int
) -> None:
    """Require auditable inspection dispositions or a structured blocker."""

    catalog = recover_source_candidate_catalog(handoff)
    inspected = {
        item.url
        for item in catalog.candidates
        if chapter_id in item.chapter_ids
        and item.access_status in {"opened", "accepted", "rejected", "access_blocked"}
    }
    inspected.update(_evidence_urls(handoff))
    if inspected:
        return
    blocker = _inspection_blocker(handoff, chapter_id=chapter_id)
    if blocker is not None:
        return
    from .codex_worker import WorkerOutputError

    raise WorkerOutputError(
        f"chapter {chapter_id} inspected no candidate documents; the configured "
        f"depth target is {minimum}, or a structured inspection blocker is required"
    )


def _inspection_blocker(handoff: str, *, chapter_id: str) -> dict[str, Any] | None:
    prefix = "INSPECTION_SATURATION_BLOCKER_JSON:"
    for line in handoff.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line.removeprefix(prefix).strip())
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("chapter_id") == chapter_id
            and _valid_attempted_documents(payload.get("documents_attempted"))
            and str(payload.get("limitation", "")).strip()
        ):
            return payload
    return None


def _valid_attempted_documents(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(item, str)
        and item.startswith(("http://", "https://"))
        and bool(item.partition("://")[2].strip("/"))
        for item in value
    )


def _candidate_resources(
    attempt: WorkerAttempt, chapter_id: str
) -> list[dict[str, Any]]:
    path = attempt.attempt_dir / "source-candidate-catalog.json"
    candidates = read_source_candidate_catalog(path).candidates
    return [
        {
            key: getattr(candidate, key)
            for key in ("url", "title", "publisher", "document_type", "access_status")
            if getattr(candidate, key)
        }
        for candidate in candidates
        if chapter_id in candidate.chapter_ids
        and candidate.access_status in {"unopened", "opened"}
    ][:40]


__all__ = [
    "chapter_resource_index",
    "existing_chapter_turn",
    "validate_chapter_inspection",
]
