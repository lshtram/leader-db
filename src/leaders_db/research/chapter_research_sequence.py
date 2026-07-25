"""Run one focused research turn per selected chapter in the same Codex thread."""

from __future__ import annotations

import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from string import Formatter
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.engine import Engine

from leaders_db.conversational_evidence.data import load

from ._codex_worker_setup import WorkerAttempt
from .codex_worker_command import (
    build_codex_exec_command,
    build_codex_resume_command,
    read_codex_thread_id,
)
from .job_ledger import checkpoint_job
from .model_profiles import ResearchModelProfile
from .question_lens_presentation import (
    load_question_lens_presentation,
    render_evidence_category_key,
    render_lens_table,
)
from .research_workflow import ResearchWorkflow

ResearchCheckpoint = tuple[Path, str, Path, str, str]

_CHAPTER_PROMPT_FIELDS = frozenset(
    {
        "chapter_id",
        "compact_guide",
        "evidence_category_key",
        "identity",
        "layered_lenses",
        "lens_presentation_version",
        "prompt_config_version",
        "reconnaissance_summary",
        "resource_index_json",
        "selected_lenses_json",
    }
)


class ChapterResearchPromptConfig(BaseModel):
    """Validated editable text template for the chapter researcher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    template: str

    @model_validator(mode="after")
    def require_interpolation_contract(self) -> ChapterResearchPromptConfig:
        parsed = tuple(Formatter().parse(self.template))
        if any(
            field_name == ""
            or conversion is not None
            or bool(format_spec)
            or (field_name is not None and not field_name.isidentifier())
            for _, field_name, format_spec, conversion in parsed
        ):
            raise ValueError("chapter prompt contains unsupported formatting syntax")
        fields = {field_name for _, field_name, _, _ in parsed if field_name is not None}
        if fields != _CHAPTER_PROMPT_FIELDS:
            raise ValueError("chapter prompt interpolation fields do not match runtime")
        return self


@lru_cache(maxsize=1)
def load_chapter_research_prompt() -> ChapterResearchPromptConfig:
    """Load the versioned chapter-research prompt from package data."""

    return ChapterResearchPromptConfig.model_validate(
        load("chapter_research_prompt.json")
    )


def run_chapter_research_sequence(
    engine: Engine,
    *,
    checkpoint: ResearchCheckpoint,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    workflow: ResearchWorkflow,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> ResearchCheckpoint:
    """Run one fresh compact researcher session for each selected chapter."""

    current = checkpoint
    reconnaissance_session_id = read_codex_thread_id(checkpoint[0])
    for chapter_id in _selected_chapters(job, workflow):
        guide_path = next(
            (project_root / "docs/methodology/chapter-guides").glob(
                f"{chapter_id.lower()}-*.md"
            )
        )
        prompt = build_chapter_research_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide_path.read_text(encoding="utf-8"),
            workflow=workflow,
            resource_index=_chapter_resource_index(attempt, chapter_id),
            reconnaissance_summary=_bounded_reconnaissance_summary(current[1]),
        )
        prompt_hash = sha256(prompt.encode()).hexdigest()
        recovered = _existing_chapter_turn(
            attempt,
            chapter_id,
            job_id=int(job["id"]),
            chapter_session_mode=workflow.chapter_session_mode,
            prompt_hash=prompt_hash,
            provider_profile=str(job["provider_profile"]),
        )
        output_path = attempt.attempt_dir / f"research-chapter-{chapter_id}.md"
        events_path = attempt.trusted_dir / f"research-chapter-{chapter_id}.events.jsonl"
        base_manifest_path = (
            attempt.trusted_dir / f"research-ledger-before-{chapter_id}.json"
        )
        if recovered is None:
            _snapshot_parent_manifest(attempt, base_manifest_path)
            (attempt.trusted_dir / f"research-chapter-{chapter_id}.prompt.txt").write_text(
                prompt, encoding="utf-8"
            )
            if workflow.chapter_session_mode == "fresh_compact_context":
                command = build_codex_exec_command(
                    profile=profile,
                    project_root=project_root,
                    schema_path=None,
                    final_message_path=output_path,
                    writable_dir=attempt.attempt_dir,
                )
            else:
                command = build_codex_resume_command(
                    profile=profile,
                    session_id=reconnaissance_session_id,
                    project_root=project_root,
                    final_message_path=output_path,
                    writable_dir=attempt.attempt_dir,
                )
            checkpoint_job(
                engine,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                checkpoint={
                    "phase": "chapter_research",
                    "chapter_id": chapter_id,
                    "reconnaissance_session_id": reconnaissance_session_id,
                    "chapter_session_mode": workflow.chapter_session_mode,
                },
            )
            (
                attempt.trusted_dir / f"research-chapter-{chapter_id}.starting.json"
            ).write_text(
                json.dumps(
                    {
                        "chapter_id": chapter_id,
                        "job_id": job["id"],
                        "chapter_session_mode": workflow.chapter_session_mode,
                        "prompt_sha256": prompt_hash,
                        "provider_profile": str(job["provider_profile"]),
                        "workflow_version": workflow.version,
                    }
                ),
                encoding="utf-8",
            )
            from .codex_worker import _run_codex

            _run_codex(
                engine,
                command=command,
                prompt=prompt,
                events_path=events_path,
                job_id=int(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                timeout_seconds=timeout_seconds,
            )
        else:
            events_path, output_path, base_manifest_path = recovered
        if not output_path.is_file() or not output_path.stat().st_size:
            from .codex_worker import WorkerOutputError

            raise WorkerOutputError(
                f"chapter researcher produced no handoff for {chapter_id}"
            )
        if output_path.stat().st_size > 5_000_000:
            from .codex_worker import WorkerOutputError

            raise WorkerOutputError(
                f"chapter researcher handoff exceeds 5 MB for {chapter_id}"
            )
        addition = output_path.read_text(encoding="utf-8")
        notebook = (
            f"{current[1]}\n\n--- CHAPTER RESEARCH {chapter_id} ---\n\n{addition}"
        )
        from .notebook_continuation import _append_current_ledger_manifest

        notebook = _append_current_ledger_manifest(
            notebook,
            attempt,
            source_attempt_dir=output_path.parent,
            base_manifest_path=base_manifest_path,
        )
        notebook_path = attempt.trusted_dir / f"research-notebook-{chapter_id}.md"
        notebook_path.write_text(notebook, encoding="utf-8")
        notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
        events_hash = sha256(events_path.read_bytes()).hexdigest()
        current = (
            events_path,
            notebook,
            notebook_path,
            notebook_hash,
            events_hash,
        )
        (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
            json.dumps(
                {
                    "job_key": job["job_key"],
                    "provider_profile": job["provider_profile"],
                    "provider": profile.provider,
                    "model": profile.model,
                    "notebook_path": str(notebook_path),
                    "notebook_sha256": notebook_hash,
                    "events_path": str(events_path),
                    "events_sha256": events_hash,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return current


def build_chapter_research_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    workflow: ResearchWorkflow,
    resource_index: tuple[dict[str, Any], ...] = (),
    reconnaissance_summary: str = "",
) -> str:
    """Build the validated natural-language deep-research prompt."""

    del workflow
    selected_lenses = [
        item
        for item in job["input"]["question_ids"]
        if str(item).startswith(f"{chapter_id}.")
    ]
    compact_guide = _compact_chapter_guide(guide)
    lens_presentation_version = load_question_lens_presentation().version
    evidence_category_key = render_evidence_category_key()
    layered_lenses = render_lens_table(selected_lenses)
    subject = _chapter_subject(guide, chapter_id)
    identity = (
        f'{subject} under {job["ruler_name"]} in {job["country_name"]} '
        f'during {job["period_start_year"]}-{job["period_end_year"]}'
    )
    prompt_config = load_chapter_research_prompt()
    return prompt_config.template.format(
        identity=identity,
        prompt_config_version=prompt_config.version,
        lens_presentation_version=lens_presentation_version,
        evidence_category_key=evidence_category_key,
        layered_lenses=layered_lenses,
        compact_guide=compact_guide,
        reconnaissance_summary=reconnaissance_summary,
        resource_index_json=json.dumps(
            resource_index, separators=(",", ":"), sort_keys=True
        ),
        chapter_id=chapter_id,
        selected_lenses_json=json.dumps(selected_lenses),
    )


def _chapter_subject(guide: str, chapter_id: str) -> str:
    """Return the chapter's plain-language subject from its title."""

    first_line = next(
        (
            line.removeprefix("# ").strip()
            for line in guide.splitlines()
            if line.startswith("# ")
        ),
        f"Chapter {chapter_id}",
    )
    subject = first_line.replace(f"Chapter {chapter_id}", "").strip(" —-:")
    return subject or f"Chapter {chapter_id}"


def _compact_chapter_guide(guide: str) -> str:
    """Keep researcher-facing questions while excluding judge-only instructions."""

    headings = (
        "## Researcher Guidance",
        "## Researcher Evidence Plan",
        "## Researcher Workflow and Evidence Themes",
    )
    stop_headings = (
        "## Baseline, Attribution, and Sparse Evidence",
        "## Chapter Judge",
    )
    sections: list[str] = []
    for heading in headings:
        start = guide.find(heading)
        if start < 0:
            continue
        possible_ends = [
            index
            for stop in stop_headings
            if (index := guide.find(stop, start + len(heading))) >= 0
        ]
        next_section = guide.find("\n## ", start + len(heading))
        if next_section >= 0:
            possible_ends.append(next_section)
        end = min(possible_ends) if possible_ends else len(guide)
        sections.append(guide[start:end].strip())
    return "\n\n".join(sections) if sections else guide[:4_000].strip()


def _bounded_reconnaissance_summary(notebook: str) -> str:
    """Return a few paragraphs without carrying the evidence ledger or tool history."""

    marker = "--- RESEARCH LEDGER MANIFEST ---"
    text = notebook.rsplit(marker, maxsplit=1)[0]
    anchors = (
        "Evidence-environment",
        "Evidence environment",
        "Identity, authority",
        "Identity and authority",
    )
    starts = [index for anchor in anchors if (index := text.find(anchor)) >= 0]
    start = min(starts) if starts else 0
    summary = text[start : start + 3_000].strip()
    return summary or "No reconnaissance prose was recoverable; verify authority directly."


def _snapshot_parent_manifest(attempt: WorkerAttempt, destination: Path) -> None:
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


def _selected_chapters(
    job: dict[str, Any], workflow: ResearchWorkflow
) -> tuple[str, ...]:
    selected = {
        str(item).split(".", maxsplit=1)[0]
        for item in job["input"]["question_ids"]
    }
    return tuple(chapter for chapter in workflow.chapter_order if chapter in selected)


def _existing_chapter_turn(
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
            job_dir
            / "attempts"
            / trusted.name
            / f"research-chapter-{chapter_id}.md"
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


def _chapter_resource_index(
    attempt: WorkerAttempt, chapter_id: str
) -> tuple[dict[str, Any], ...]:
    """Expose a small list of already found chapter-relevant resources."""

    path = attempt.attempt_dir / "research-ledger-manifest.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return ()
    relevant = []
    cross_chapter = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        compact = {
            key: entry[key]
            for key in (
                "provisional_id",
                "url",
                "claim",
                "locator",
                "disposition",
            )
            if entry.get(key)
        }
        chapter_ids = entry.get("chapter_ids", [])
        if chapter_id in chapter_ids:
            relevant.append(compact)
        elif len(chapter_ids) >= 3:
            cross_chapter.append(compact)
    return tuple((relevant[:15] + cross_chapter[:5])[:20])


__all__ = ["build_chapter_research_prompt", "run_chapter_research_sequence"]
