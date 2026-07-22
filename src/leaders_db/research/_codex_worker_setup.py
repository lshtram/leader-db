"""Attempt-scoped setup for the Codex dossier worker."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from ._codex_worker_artifacts import (
    find_previous_candidate,
    write_local_priors,
)
from .dossier_models import DossierLocalPrior, codex_dossier_json_schema
from .local_prior_query import load_leader_accession_year
from .local_prior_schema import (
    LeaderPriorMetadata,
    LocalPriorPeriod,
    LocalStructuredPriorRequest,
)
from .local_structured_prior import build_local_structured_prior


@dataclass(frozen=True)
class WorkerAttempt:
    """All attempt-scoped paths and parent-produced inputs."""

    attempt_dir: Path
    trusted_dir: Path
    result_path: Path
    schema_path: Path
    prompt_path: Path
    pending_path: Path
    events_path: Path
    existing_candidate: dict[str, Any] | None
    local_priors: tuple[dict[str, Any], ...]
    local_prior_provenance: tuple[DossierLocalPrior, ...]


def initialize_worker_attempt(
    engine: Engine,
    *,
    job: dict[str, Any],
    project_root: Path,
    lease_token: str,
) -> WorkerAttempt:
    """Create an isolated attempt directory and its trusted parent inputs."""

    job_dir = job_output_dir(job, project_root=project_root)
    attempt_name = f"{int(job['attempt_count']):03d}-{lease_token[:12]}"
    attempt_dir = job_dir / "attempts" / attempt_name
    trusted_dir = job_dir / "trusted" / attempt_name
    attempt_dir.mkdir(parents=True, exist_ok=False)
    trusted_dir.mkdir(parents=True, exist_ok=False)
    pending_path = attempt_dir / "dossier.pending.json"
    existing = find_previous_candidate(job_dir, attempt_dir=attempt_dir)
    schema_path = trusted_dir / "dossier.schema.json"
    schema_path.write_text(
        json.dumps(codex_dossier_json_schema(), indent=2, sort_keys=True), encoding="utf-8"
    )
    local_priors = collect_local_priors(engine, job)
    provenance = write_local_priors(trusted_dir, local_priors)
    return WorkerAttempt(
        attempt_dir=attempt_dir,
        trusted_dir=trusted_dir,
        result_path=attempt_dir / "dossier.json",
        schema_path=schema_path,
        prompt_path=attempt_dir / "prompt.txt",
        pending_path=pending_path,
        events_path=trusted_dir / "codex-events.jsonl",
        existing_candidate=existing,
        local_priors=local_priors,
        local_prior_provenance=provenance,
    )


def job_output_dir(job: dict[str, Any], *, project_root: Path) -> Path:
    configured = job["input"].get("output_root")
    if not configured:
        raise ValueError("dossier job has no output_root")
    root = Path(str(configured))
    resolved = (project_root / root).resolve() if not root.is_absolute() else root.resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError("dossier output_root must remain inside the project")
    return resolved / "jobs" / str(job["id"])


def collect_local_priors(
    engine: Engine, job: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    start_year = int(job["period_start_year"])
    end_year = int(job["period_end_year"])
    period = LocalPriorPeriod(
        year=None,
        start_year=start_year,
        end_year=end_year,
    )
    ruler_id = str(job.get("ruler_id", ""))
    numeric_ruler_id = int(ruler_id) if ruler_id.isdigit() else None
    accession_year = (
        load_leader_accession_year(
            engine,
            leader_id=numeric_ruler_id,
            iso3=str(job["iso3"]),
            target_year=end_year,
            leader_name=str(job.get("ruler_name") or "") or None,
        )
        if numeric_ruler_id is not None
        else None
    )
    leader = LeaderPriorMetadata(
        name=str(job.get("ruler_name") or "") or None,
        leader_id=numeric_ruler_id,
        period_label=(
            str(start_year) if start_year == end_year else f"{start_year}-{end_year}"
        ),
        accession_year=accession_year,
    )
    return tuple(
        build_local_structured_prior(
            engine,
            LocalStructuredPriorRequest(
                methodology_id=methodology_id,
                iso3=str(job["iso3"]),
                period=period,
                leader=leader,
            ),
        ).model_dump(mode="json", exclude_none=True)
        for methodology_id in job["input"]["question_ids"]
    )


__all__ = ["WorkerAttempt", "initialize_worker_attempt", "job_output_dir"]
