"""Run source discovery separately from evidence extraction."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from leaders_db.conversational_evidence.data import load

from ._codex_worker_setup import WorkerAttempt
from .chapter_research_sequence import _compact_chapter_guide, _selected_chapters
from .codex_worker_command import build_codex_exec_command
from .job_ledger import checkpoint_job
from .model_profiles import ResearchModelProfile
from .question_lens_presentation import render_lens_table
from .research_workflow import ResearchWorkflow
from .source_candidate_catalog import (
    recover_source_candidate_catalog,
    seed_source_candidate_catalog,
    write_source_candidate_catalog,
)


def run_chapter_source_discovery(
    engine: Engine,
    *,
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
) -> Path:
    """Build a durable candidate catalogue before chapter fact extraction."""

    catalog_path = attempt.attempt_dir / "source-candidate-catalog.json"
    seed_paths = _validated_seed_paths(job, project_root=project_root)
    seed_set_sha256 = sha256(
        json.dumps(
            job["input"].get("source_catalog_seed_paths", []), sort_keys=True
        ).encode()
    ).hexdigest()
    if seed_paths:
        seed_source_candidate_catalog(seed_paths, catalog_path)
    cumulative = ""
    overview_prompt = _build_overview_discovery_prompt(job=job, workflow=workflow)
    overview = _execute_discovery_turn(
        engine,
        job=job,
        worker_id=worker_id,
        project_root=project_root,
        profile=profile,
        attempt=attempt,
        discovery_id="overview",
        prompt=overview_prompt,
        seed_set_sha256=seed_set_sha256,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    cumulative = overview.read_text(encoding="utf-8")
    write_source_candidate_catalog(
        cumulative, catalog_path
    )
    _validate_discovery_depth(
        catalog_path,
        discovery_id="overview",
        minimum=workflow.overview_candidate_document_target,
        output=overview,
    )
    for chapter_id in _selected_chapters(job, workflow):
        guide_path = next(
            (project_root / "docs/methodology/chapter-guides").glob(
                f"{chapter_id.lower()}-*.md"
            )
        )
        prompt = _build_discovery_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide_path.read_text(encoding="utf-8"),
            workflow=workflow,
        )
        output = _execute_discovery_turn(
            engine,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            profile=profile,
            attempt=attempt,
            discovery_id=chapter_id,
            prompt=prompt,
            seed_set_sha256=seed_set_sha256,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
        cumulative += "\n" + output.read_text(encoding="utf-8")
        write_source_candidate_catalog(
            cumulative, catalog_path
        )
        _validate_discovery_depth(
            catalog_path,
            discovery_id=chapter_id,
            minimum=workflow.chapter_candidate_document_target,
            output=output,
        )
    return catalog_path


def _validated_seed_paths(
    job: dict[str, Any], *, project_root: Path
) -> tuple[Path, ...]:
    resolved = []
    for configured in job["input"].get("source_catalog_seed_paths", []):
        if not isinstance(configured, dict):
            raise ValueError("source catalogue seed must include path and hash")
        path = Path(str(configured.get("path", "")))
        path = (project_root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(project_root.resolve()):
            raise ValueError("source catalogue seed must remain inside the project")
        if not path.is_file():
            raise ValueError(f"source catalogue seed does not exist: {path}")
        if configured.get("sha256") != sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"source catalogue seed hash changed: {path}")
        resolved.append(path)
    return tuple(resolved)


def _execute_discovery_turn(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    discovery_id: str,
    prompt: str,
    seed_set_sha256: str,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> Path:
    prompt_hash = sha256(prompt.encode()).hexdigest()
    recovered = _completed_discovery(
        attempt,
        chapter_id=discovery_id,
        prompt_hash=prompt_hash,
        provider=profile.provider,
        model=profile.model,
        seed_set_sha256=seed_set_sha256,
    )
    if recovered is not None:
        return recovered
    output_path = attempt.attempt_dir / f"source-discovery-{discovery_id}.md"
    events_path = attempt.trusted_dir / f"source-discovery-{discovery_id}.events.jsonl"
    (attempt.trusted_dir / f"source-discovery-{discovery_id}.prompt.txt").write_text(
        prompt, encoding="utf-8"
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={"phase": "source_discovery", "chapter_id": discovery_id},
    )
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=None,
        final_message_path=output_path,
        writable_dir=attempt.attempt_dir,
        isolated_web_research=True,
    )
    (attempt.trusted_dir / f"source-discovery-{discovery_id}.starting.json").write_text(
        json.dumps(
            {
                "job_id": job["id"],
                "prompt_sha256": prompt_hash,
                "provider": profile.provider,
                "model": profile.model,
                "seed_set_sha256": seed_set_sha256,
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
    output_hash = sha256(output_path.read_bytes()).hexdigest()
    (attempt.trusted_dir / f"source-discovery-{discovery_id}.complete.json").write_text(
        json.dumps(
            {
                "job_id": job["id"],
                "prompt_sha256": prompt_hash,
                "provider": profile.provider,
                "model": profile.model,
                "seed_set_sha256": seed_set_sha256,
                "output_sha256": output_hash,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output_path


def _build_overview_discovery_prompt(
    *, job: dict[str, Any], workflow: ResearchWorkflow
) -> str:
    configured = load("source_overview_discovery_prompt.json")
    return str(configured["template"]).format(
        ruler_name=job["ruler_name"],
        country_name=job["country_name"],
        period_start_year=job["period_start_year"],
        period_end_year=job["period_end_year"],
        candidate_document_target=workflow.overview_candidate_document_target,
    )


def _build_discovery_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    workflow: ResearchWorkflow,
) -> str:
    selected = [
        item
        for item in job["input"]["question_ids"]
        if str(item).startswith(f"{chapter_id}.")
    ]
    configured = load("source_discovery_prompt.json")
    return str(configured["template"]).format(
        ruler_name=job["ruler_name"],
        country_name=job["country_name"],
        period_start_year=job["period_start_year"],
        period_end_year=job["period_end_year"],
        chapter_id=chapter_id,
        candidate_document_target=workflow.chapter_candidate_document_target,
        compact_guide=_compact_chapter_guide(guide),
        layered_lenses=render_lens_table(selected),
    )


def _completed_discovery(
    attempt: WorkerAttempt,
    *,
    chapter_id: str,
    prompt_hash: str,
    provider: str,
    model: str,
    seed_set_sha256: str,
) -> Path | None:
    job_dir = attempt.attempt_dir.parent.parent
    for trusted in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        output = job_dir / "attempts" / trusted.name / f"source-discovery-{chapter_id}.md"
        starting = trusted / f"source-discovery-{chapter_id}.starting.json"
        completion = trusted / f"source-discovery-{chapter_id}.complete.json"
        events = trusted / f"source-discovery-{chapter_id}.events.jsonl"
        try:
            metadata = json.loads(starting.read_text(encoding="utf-8"))
            completed = json.loads(completion.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        identity = (prompt_hash, provider, model, seed_set_sha256)
        if (
            tuple(
                metadata.get(key)
                for key in ("prompt_sha256", "provider", "model", "seed_set_sha256")
            )
            != identity
            or tuple(
                completed.get(key)
                for key in ("prompt_sha256", "provider", "model", "seed_set_sha256")
            )
            != identity
            or not output.is_file()
            or completed.get("output_sha256")
            != sha256(output.read_bytes()).hexdigest()
        ):
            continue
        from .codex_worker import _events_show_completed_turn

        if _events_show_completed_turn(events) and _is_recoverable_discovery_output(
            output, discovery_id=chapter_id
        ):
            return output
    return None


def _is_recoverable_discovery_output(output: Path, *, discovery_id: str) -> bool:
    """Reuse only output that can satisfy discovery or explain a genuine shortfall."""

    handoff = output.read_text(encoding="utf-8")
    return bool(recover_source_candidate_catalog(handoff).candidates) or (
        _discovery_blocker(handoff, discovery_id=discovery_id) is not None
    )


def _validate_discovery_depth(
    catalog_path: Path, *, discovery_id: str, minimum: int, output: Path
) -> None:
    from .codex_worker import WorkerOutputError
    from .source_candidate_catalog import SourceCandidateCatalog

    catalog = SourceCandidateCatalog.model_validate_json(
        catalog_path.read_text(encoding="utf-8")
    )
    count = (
        len(catalog.candidates)
        if discovery_id == "overview"
        else sum(discovery_id in item.chapter_ids for item in catalog.candidates)
    )
    if count >= minimum:
        return
    handoff = output.read_text(encoding="utf-8")
    if _discovery_blocker(handoff, discovery_id=discovery_id) is not None:
        return
    raise WorkerOutputError(
        f"source discovery {discovery_id} produced {count} candidates; "
        f"expected at least {minimum} or an explicit saturation blocker"
    )


def _discovery_blocker(handoff: str, *, discovery_id: str) -> dict[str, Any] | None:
    prefix = "DISCOVERY_SATURATION_BLOCKER_JSON:"
    for line in handoff.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line.removeprefix(prefix).strip())
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("discovery_id") == discovery_id
            and _valid_searches(payload.get("searches_attempted"))
            and str(payload.get("limitation", "")).strip()
        ):
            return payload
    return None


def _valid_searches(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


__all__ = ["run_chapter_source_discovery"]
