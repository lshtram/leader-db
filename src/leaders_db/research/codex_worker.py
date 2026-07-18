"""Execute one claimed research job through non-interactive Codex."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.engine import Engine

from ._codex_worker_artifacts import (
    price_codex_usage as _price_codex_usage,
)
from ._codex_worker_artifacts import (
    read_codex_usage as _read_codex_usage,
)
from ._codex_worker_setup import WorkerAttempt, initialize_worker_attempt
from .codex_worker_command import (
    build_codex_exec_command,
    read_codex_thread_id,
    validate_worker_timing,
)
from .costing import combine_priced_usage
from .dossier_models import (
    DossierLocalPrior,
    DossierUsage,
    RulerEvidenceDossier,
    normalize_dossier_candidate,
)
from .dossier_notebook_prompt import build_research_notebook_prompt
from .dossier_prompt import build_dossier_prompt
from .job_ledger import checkpoint_job, heartbeat_job
from .model_profiles import ResearchModelProfile, load_research_model_profiles
from .research_workflow import ResearchWorkflow


class WorkerOutputError(RuntimeError):
    """Retryable malformed or semantically invalid model output."""


def execute_claimed_dossier_job(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    model_profiles_path: Path,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> Path:
    """Run and validate one already-claimed dossier job, returning its artifact path."""

    validate_worker_timing(
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    if job["job_type"] != "dossier_researcher" or job["status"] != "claimed":
        raise ValueError("worker can execute only a claimed dossier_researcher job")
    lease_token = str(job["lease_token"])
    profile = load_research_model_profiles(model_profiles_path).profiles.get(
        job["provider_profile"]
    )
    if profile is None:
        raise ValueError("claimed job references an unknown provider profile")
    if "dossier_researcher" not in profile.roles:
        raise ValueError("configured provider profile does not permit dossier research")
    if (profile.provider, profile.model) != (job["provider"], job["model"]):
        raise ValueError("claimed job provider/model differs from the configured profile")

    attempt = initialize_worker_attempt(
        engine, job=job, project_root=project_root, lease_token=lease_token
    )
    existing_candidate = attempt.existing_candidate
    local_priors = attempt.local_priors
    local_prior_provenance = attempt.local_prior_provenance
    execution_profile, research_checkpoint = _prepare_execution_passes(
            engine,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            researcher_profile=profile,
            model_profiles_path=model_profiles_path,
            attempt=attempt,
            local_priors=local_priors,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
    research_notebook = research_checkpoint[1] if research_checkpoint else None
    recovered_path = _reuse_existing_notebook_candidate(
        engine,
        candidate=existing_candidate,
        job=job,
        worker_id=worker_id,
        attempt=attempt,
        local_priors=local_priors,
        local_prior_provenance=local_prior_provenance,
        research_checkpoint=research_checkpoint,
        formatter_profile=execution_profile,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )
    if recovered_path is not None:
        return recovered_path
    if _has_indeterminate_formatter_call(attempt):
        raise ValueError(
            "prior paid formatter call has no recoverable completed result; "
            "manual reconciliation is required"
        )
    prompt = build_dossier_prompt(
        job,
        project_root=project_root,
        worker_output_dir=attempt.attempt_dir,
        local_priors=local_priors,
        existing_candidate=existing_candidate,
        research_notebook=research_notebook,
    )
    attempt.prompt_path.write_text(prompt, encoding="utf-8")
    command = build_codex_exec_command(
        profile=execution_profile,
        project_root=project_root,
        schema_path=attempt.schema_path,
        final_message_path=attempt.pending_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={"phase": "codex_starting", "attempt_dir": str(attempt.attempt_dir)},
    )
    (attempt.trusted_dir / "formatter-starting.json").write_text(
        json.dumps({"job_id": job["id"]}, sort_keys=True), encoding="utf-8"
    )
    _run_codex(
        engine,
        command=command,
        prompt=prompt,
        events_path=attempt.events_path,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    (attempt.trusted_dir / "formatter-complete.marker").write_text(
        "complete\n", encoding="utf-8"
    )
    heartbeat_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        progress={"phase": "validating_output"},
    )
    if not attempt.pending_path.is_file():
        raise WorkerOutputError("Codex worker did not produce its final response file")
    if attempt.pending_path.stat().st_size > 5_000_000:
        raise WorkerOutputError("Codex worker output exceeds the 5 MB dossier limit")
    try:
        candidate = json.loads(attempt.pending_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkerOutputError("Codex worker produced invalid JSON") from exc
    if not isinstance(candidate, dict):
        raise WorkerOutputError("Codex worker output must be a JSON object")
    try:
        dossier = _prepare_dossier(
            candidate,
            job=job,
            local_priors=local_priors,
            local_prior_provenance=local_prior_provenance,
            events_path=attempt.events_path,
            usage_provider=execution_profile.provider,
            usage_model=execution_profile.model,
        )
    except (ValidationError, ValueError) as exc:
        attempt.pending_path.write_text(json.dumps(candidate), encoding="utf-8")
        raise WorkerOutputError("Codex dossier failed semantic validation") from exc
    _validate_substantive_evidence_yield(dossier)
    _validate_formatter_ledger_accounting(dossier, notebook=research_notebook or "")
    _validate_recovered_candidate_references(dossier)
    _finalize_execution_usage(
        dossier,
        job=job,
        research_checkpoint=research_checkpoint,
        formatter_events_path=attempt.events_path,
        attempt_dir=attempt.attempt_dir,
        formatter_profile=execution_profile,
    )
    return _publish_dossier(
        engine,
        dossier=dossier,
        pending_path=attempt.pending_path,
        result_path=attempt.result_path,
        job=job,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )


def _reuse_existing_notebook_candidate(
    engine: Engine,
    *,
    candidate: dict[str, Any] | None,
    job: dict[str, Any],
    worker_id: str,
    attempt: WorkerAttempt,
    local_priors: tuple[dict[str, Any], ...],
    local_prior_provenance: tuple[DossierLocalPrior, ...],
    research_checkpoint: tuple[Path, str, Path, str, str] | None,
    formatter_profile: ResearchModelProfile,
    lease_token: str,
    lease_seconds: int,
) -> Path | None:
    """Publish a recovered valid formatter candidate without another paid call."""

    if candidate is None or research_checkpoint is None:
        return None
    try:
        dossier = _prepare_dossier(
            candidate,
            job=job,
            local_priors=local_priors,
            local_prior_provenance=local_prior_provenance,
            events_path=attempt.events_path,
            usage_provider=formatter_profile.provider,
            usage_model=formatter_profile.model,
        )
    except (ValidationError, ValueError):
        return None
    try:
        _validate_recovered_candidate_references(dossier)
        _validate_substantive_evidence_yield(dossier)
        _validate_formatter_ledger_accounting(
            dossier, notebook=research_checkpoint[1]
        )
    except WorkerOutputError:
        return None
    _finalize_execution_usage(
        dossier,
        job=job,
        research_checkpoint=research_checkpoint,
        formatter_events_path=attempt.events_path,
        attempt_dir=attempt.attempt_dir,
        formatter_profile=formatter_profile,
    )
    return _publish_dossier(
        engine,
        dossier=dossier,
        pending_path=attempt.pending_path,
        result_path=attempt.result_path,
        job=job,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )


def _validate_recovered_candidate_references(dossier: RulerEvidenceDossier) -> None:
    """Require complete joins before reusing a deterministically normalized candidate."""

    mapped_ids = {item.evidence_id for item in dossier.mappings}
    evidence_ids = {item.evidence_id for item in dossier.evidence}
    if mapped_ids != evidence_ids:
        raise WorkerOutputError("recovered candidate contains unmapped evidence")
    mapping_pairs = {
        (item.methodology_id, item.evidence_id) for item in dossier.mappings
    }
    if any(
        (coverage.methodology_id, evidence_id) not in mapping_pairs
        for coverage in dossier.coverage
        for evidence_id in coverage.evidence_ids
    ):
        raise WorkerOutputError("recovered candidate coverage lacks an evidence mapping")


def _publish_dossier(
    engine: Engine,
    *,
    dossier: RulerEvidenceDossier,
    pending_path: Path,
    result_path: Path,
    job: dict[str, Any],
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> Path:
    with pending_path.open("w", encoding="utf-8") as pending:
        pending.write(dossier.model_dump_json(indent=2))
        pending.flush()
        os.fsync(pending.fileno())
    heartbeat_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        progress={"phase": "publishing_validated_output"},
    )
    os.replace(pending_path, result_path)
    try:
        checkpoint_job(
            engine,
            job_id=int(job["id"]),
            worker_id=worker_id,
            lease_token=lease_token,
            checkpoint={
                "phase": "validated",
                "result_path": str(result_path),
                "evidence_count": len(dossier.evidence),
                "question_count": len(dossier.coverage),
            },
        )
    except Exception:
        result_path.replace(result_path.with_suffix(".orphaned.json"))
        raise
    return result_path


def _prepare_dossier(
    candidate: dict[str, Any],
    *,
    job: dict[str, Any],
    local_priors: tuple[dict[str, Any], ...],
    local_prior_provenance: tuple[DossierLocalPrior, ...],
    events_path: Path,
    usage_provider: str | None = None,
    usage_model: str | None = None,
) -> RulerEvidenceDossier:
    candidate = normalize_dossier_candidate(
        candidate,
        methodology_ids=tuple(job["input"]["question_ids"]),
    )
    candidate |= {
        "schema_version": "ruler_evidence_dossier_v2",
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"]["ruler_year_id"],
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "methodology_ids": job["input"]["question_ids"],
        "local_priors": [item.model_dump(mode="json") for item in local_prior_provenance],
    }
    run_profile = candidate.get("run_profile")
    if not isinstance(run_profile, dict):
        raise ValueError("dossier run_profile must be an object")
    run_profile |= {
        "provider_profile": job["provider_profile"],
        "provider": job["provider"],
        "model": job["model"],
        "local_evidence_calls": [
            f"parent_local_prior:{item.get('methodology_id')}:{item.get('status')}"
            for item in local_priors
        ],
    }
    dossier = RulerEvidenceDossier.model_validate(candidate)
    _validate_dossier_matches_job(dossier, job)
    usage = _read_codex_usage(events_path)
    if usage is not None:
        dossier.run_profile.usage = _price_codex_usage(
            usage,
            provider=usage_provider or job["provider"],
            model=usage_model or job["model"],
        )
    return dossier


def _run_research_notebook_pass(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    profile: ResearchModelProfile,
    attempt: WorkerAttempt,
    local_priors: tuple[dict[str, Any], ...],
    workflow: ResearchWorkflow,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> tuple[Path, str, Path, str, str]:
    """Run a schema-light evidence pass and return its durable handoff text."""

    prompt = build_research_notebook_prompt(
        job,
        project_root=project_root,
        worker_output_dir=attempt.attempt_dir,
        local_priors=local_priors,
        workflow=workflow,
    )
    prompt_path = attempt.trusted_dir / "research-prompt.txt"
    events_path = attempt.trusted_dir / "research-events.jsonl"
    handoff_path = attempt.attempt_dir / "research-handoff.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=None,
        final_message_path=handoff_path,
        writable_dir=attempt.attempt_dir,
    )
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={"phase": "research_notebook_starting"},
    )
    (attempt.trusted_dir / "research-starting.json").write_text(
        json.dumps({"job_id": job["id"]}, sort_keys=True), encoding="utf-8"
    )
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
    (attempt.trusted_dir / "research-complete.marker").write_text(
        "complete\n", encoding="utf-8"
    )
    materials_path = attempt.attempt_dir / "research-materials.md"
    manifest_path = attempt.attempt_dir / "research-ledger-manifest.json"
    try:
        manifest = _load_or_recover_research_ledger_manifest(
            manifest_path, handoff_path=handoff_path
        )
    except WorkerOutputError:
        manifest = None
    parts = [
        path.read_text(encoding="utf-8")
        for path in (materials_path, handoff_path)
        if path.is_file() and path.stat().st_size <= 5_000_000
    ]
    if not parts:
        raise WorkerOutputError("researcher produced no notebook or handoff")
    if manifest is not None:
        parts.append(
            "--- RESEARCH LEDGER MANIFEST ---\n\n"
            + json.dumps(manifest, indent=2, sort_keys=True)
        )
    notebook = "\n\n--- RESEARCH HANDOFF ---\n\n".join(parts)
    notebook_path = attempt.trusted_dir / "research-notebook.md"
    notebook_path.write_text(notebook, encoding="utf-8")
    notebook_sha256 = sha256(notebook_path.read_bytes()).hexdigest()
    checkpoint_path = attempt.trusted_dir / "research-notebook-checkpoint.json"
    events_sha256 = sha256(events_path.read_bytes()).hexdigest()
    session_id = read_codex_thread_id(events_path)
    checkpoint_path.write_text(
        json.dumps(
            {
                "job_key": job["job_key"],
                "provider_profile": job["provider_profile"],
                "provider": job["provider"],
                "model": job["model"],
                "session_id": session_id,
                "notebook_path": str(notebook_path),
                "notebook_sha256": notebook_sha256,
                "events_path": str(events_path),
                "events_sha256": events_sha256,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return events_path, notebook, notebook_path, notebook_sha256, events_sha256


def _prepare_execution_passes(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    researcher_profile: ResearchModelProfile,
    model_profiles_path: Path,
    attempt: WorkerAttempt,
    local_priors: tuple[dict[str, Any], ...],
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> tuple[ResearchModelProfile, tuple[Path, str, Path, str, str]]:
    """Run direct research plus review loop and resolve the formatter profile."""

    workflow = ResearchWorkflow.model_validate(job["input"]["research_workflow"])
    checkpoint = _load_previous_research_checkpoint(
        attempt.trusted_dir, job=job, profile=researcher_profile
    )
    if checkpoint is None:
        checkpoint = _recover_completed_initial_research(
            attempt=attempt,
            job=job,
        )
    if checkpoint is None and _has_indeterminate_initial_research(attempt.trusted_dir):
        raise ValueError(
            "prior paid initial researcher call has no recoverable completed result; "
            "manual reconciliation is required"
        )
    if checkpoint is None:
        checkpoint = _run_research_notebook_pass(
            engine,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            profile=researcher_profile,
            attempt=attempt,
            local_priors=local_priors,
            workflow=workflow,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
    if workflow.max_review_rounds > 0:
        reviewer_name = str(job["input"].get("reviewer_profile"))
        reviewer = load_research_model_profiles(model_profiles_path).profiles.get(
            reviewer_name
        )
        if reviewer is None or "dossier_evidence_reviewer" not in reviewer.roles:
            raise ValueError("job references an unavailable evidence reviewer profile")
        if (
            workflow.supervisor_takeover_enabled
            and "dossier_researcher" not in reviewer.roles
        ):
            raise ValueError(
                "configured supervisor takeover profile does not permit dossier research"
            )
        if (reviewer.provider, reviewer.model) != (
            job["input"].get("reviewer_provider"),
            job["input"].get("reviewer_model"),
        ):
            raise ValueError("evidence reviewer profile differs from persisted job input")
        from .notebook_continuation import review_and_resume_notebook_if_needed

        continuation = review_and_resume_notebook_if_needed(
            engine,
            checkpoint=checkpoint,
            job=job,
            worker_id=worker_id,
            project_root=project_root,
            researcher_profile=researcher_profile,
            reviewer_profile=reviewer,
            attempt=attempt,
            workflow=workflow,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
        )
        checkpoint = continuation.checkpoint
    formatter_name = str(job["input"].get("formatter_profile"))
    formatter = load_research_model_profiles(model_profiles_path).profiles.get(
        formatter_name
    )
    if formatter is None or "dossier_formatter" not in formatter.roles:
        raise ValueError("job references an unavailable dossier formatter profile")
    if (formatter.provider, formatter.model) != (
        job["input"].get("formatter_provider"),
        job["input"].get("formatter_model"),
    ):
        raise ValueError("formatter profile differs from the persisted job input")
    return formatter, checkpoint


def _recover_completed_initial_research(
    *,
    attempt: WorkerAttempt,
    job: dict[str, Any],
) -> tuple[Path, str, Path, str, str] | None:
    """Recover a completed initial notebook call before purchasing another call."""

    for directory in sorted(attempt.trusted_dir.parent.glob("*"), reverse=True):
        if directory == attempt.trusted_dir or not (
            directory / "research-starting.json"
        ).is_file():
            continue
        events_path = directory / "research-events.jsonl"
        prior_attempt = directory.parent.parent / "attempts" / directory.name
        handoff_path = prior_attempt / "research-handoff.md"
        if not events_path.is_file() or not handoff_path.is_file():
            continue
        if not _events_show_completed_turn(events_path):
            continue
        marker = directory / "research-complete.marker"
        marker.write_text("complete\n", encoding="utf-8")
        materials_path = prior_attempt / "research-materials.md"
        parts = [
            path.read_text(encoding="utf-8")
            for path in (materials_path, handoff_path)
            if path.is_file() and path.stat().st_size <= 5_000_000
        ]
        prior_manifest_path = prior_attempt / "research-ledger-manifest.json"
        try:
            manifest = _load_or_recover_research_ledger_manifest(
                prior_manifest_path, handoff_path=handoff_path
            )
        except WorkerOutputError:
            manifest = None
        if manifest is not None:
            current_manifest_path = attempt.attempt_dir / "research-ledger-manifest.json"
            current_manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            parts.append(
                "--- RESEARCH LEDGER MANIFEST ---\n\n"
                + json.dumps(manifest, indent=2, sort_keys=True)
            )
        notebook = "\n\n--- RESEARCH HANDOFF ---\n\n".join(parts)
        notebook_path = attempt.trusted_dir / "research-notebook.md"
        notebook_path.write_text(notebook, encoding="utf-8")
        notebook_hash = sha256(notebook_path.read_bytes()).hexdigest()
        events_hash = sha256(events_path.read_bytes()).hexdigest()
        payload = {
            "job_key": job["job_key"],
            "provider_profile": job["provider_profile"],
            "provider": job["provider"],
            "model": job["model"],
            "session_id": read_codex_thread_id(events_path),
            "notebook_path": str(notebook_path),
            "notebook_sha256": notebook_hash,
            "events_path": str(events_path),
            "events_sha256": events_hash,
            "recovered_without_provider_call": True,
        }
        (attempt.trusted_dir / "research-notebook-checkpoint.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return events_path, notebook, notebook_path, notebook_hash, events_hash
    return None


def _has_indeterminate_initial_research(trusted_dir: Path) -> bool:
    return any(
        directory != trusted_dir
        and (directory / "research-starting.json").is_file()
        and not _checkpoint_has_initial_research(directory)
        and not _has_valid_operator_termination(directory)
        and _events_show_turn_started(directory / "research-events.jsonl")
        and not _events_show_failed_turn(directory / "research-events.jsonl")
        for directory in trusted_dir.parent.glob("*")
        if directory.is_dir()
    )


def _has_valid_operator_termination(
    directory: Path,
    *,
    marker_name: str = "research-operator-terminated.json",
    starting_name: str = "research-starting.json",
    events_name: str = "research-events.jsonl",
) -> bool:
    """Validate an explicit human cost-risk override for a wedged paid turn."""

    marker_path = directory / marker_name
    starting_path = directory / starting_name
    events_path = directory / events_name
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        terminated_at = datetime.fromisoformat(str(marker["terminated_at"]))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(marker, dict) or any(
        not isinstance(marker.get(field), str) or not marker[field].strip()
        for field in ("reason", "operator", "thread_id")
    ):
        return False
    if terminated_at.tzinfo is None or terminated_at.utcoffset() is None:
        return False
    try:
        if terminated_at.astimezone(UTC).timestamp() < starting_path.stat().st_mtime:
            return False
        return marker["thread_id"] == read_codex_thread_id(events_path)
    except (OSError, ValueError):
        return False


def _checkpoint_has_initial_research(directory: Path) -> bool:
    path = directory / "research-notebook-checkpoint.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload.get("notebook_sha256"))


def _events_show_completed_turn(events_path: Path) -> bool:
    if not events_path.is_file():
        return False
    for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "turn.completed":
            return True
    return False


def _events_show_turn_started(events_path: Path) -> bool:
    """Distinguish a potentially paid model turn from pre-turn startup failure."""

    if not events_path.is_file():
        return False
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "turn.started":
            return True
    return False


def _events_show_failed_turn(events_path: Path) -> bool:
    """Return whether Codex explicitly terminated the turn as failed."""

    if not events_path.is_file():
        return False
    for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "turn.failed":
            return True
    return False


def _validate_substantive_evidence_yield(dossier: RulerEvidenceDossier) -> None:
    """Prevent an all-chapter access failure from becoming a published dossier."""

    selected_chapters = {
        methodology_id.split(".", maxsplit=1)[0]
        for methodology_id in dossier.methodology_ids
    }
    if len(selected_chapters) > 1 and not dossier.evidence:
        raise WorkerOutputError("multi-chapter ruler dossier cannot publish with zero evidence")


def _load_research_ledger_manifest(path: Path) -> dict[str, Any]:
    """Load the researcher's minimal evidence-accounting index."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerOutputError("researcher produced no valid ledger manifest") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        "ruler_research_ledger_manifest_v1"
    ):
        raise WorkerOutputError("researcher ledger manifest has an invalid version")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise WorkerOutputError("researcher ledger manifest entries must be a list")
    seen: set[str] = set()
    allowed = {"final_evidence", "context", "discovery_only", "rejected"}
    for entry in entries:
        if not isinstance(entry, dict):
            raise WorkerOutputError("researcher ledger manifest entry must be an object")
        key = str(entry.get("canonical_fact_key", "")).strip()
        provisional_id = str(entry.get("provisional_id", "")).strip()
        disposition = str(entry.get("disposition", ""))
        chapter_ids = entry.get("chapter_ids", [])
        if not key or not provisional_id or disposition not in allowed or key in seen:
            raise WorkerOutputError("researcher ledger manifest entry is invalid")
        if not isinstance(chapter_ids, list) or any(
            not re.fullmatch(r"[1-8]B", str(chapter_id))
            for chapter_id in chapter_ids
        ):
            raise WorkerOutputError("researcher ledger manifest chapter_ids are invalid")
        if disposition == "rejected" and not str(entry.get("reason", "")).strip():
            raise WorkerOutputError("rejected ledger entry requires a reason")
        seen.add(key)
    return payload


def _load_or_recover_research_ledger_manifest(
    path: Path, *, handoff_path: Path
) -> dict[str, Any] | None:
    """Use a valid optional manifest without making it a research gate."""

    if path.is_file():
        try:
            return _load_research_ledger_manifest(path)
        except WorkerOutputError:
            pass
    try:
        handoff = handoff_path.read_text(encoding="utf-8")
    except OSError:
        return None
    decoder = json.JSONDecoder()
    marker = '"schema_version"'
    for marker_index in (
        index for index in range(len(handoff)) if handoff.startswith(marker, index)
    ):
        object_start = handoff.rfind("{", 0, marker_index)
        if object_start < 0:
            continue
        try:
            candidate, _ = decoder.raw_decode(handoff[object_start:])
        except json.JSONDecodeError:
            continue
        if not isinstance(candidate, dict) or candidate.get("schema_version") != (
            "ruler_research_ledger_manifest_v1"
        ):
            continue
        path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        try:
            return _load_research_ledger_manifest(path)
        except WorkerOutputError:
            continue
    entries = _recover_markdown_ledger_entries(handoff)
    if entries:
        candidate = {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": entries,
        }
        path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return _load_research_ledger_manifest(path)
    return None


def _recover_markdown_ledger_entries(handoff: str) -> list[dict[str, Any]]:
    """Recover explicitly labeled evidence rows from a permissive Markdown ledger."""

    headings = list(
        re.finditer(
            r"(?m)^(?:#{2,4}\s+(?:Item\s+)?|-\s+\*\*(?:ID\s+)?)"
            r"((?=[A-Za-z0-9._-]*\d)[A-Za-z0-9][A-Za-z0-9._-]+)",
            handoff,
        )
    )
    entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(handoff)
        section = handoff[heading.end() : end]
        key_match = re.search(
            r"(?mi)(?:canonical[_ ]fact[_ ]key|canonical key)\*{0,2}:\*{0,2}"
            r"\s*`?([^`\n]+)",
            section,
        )
        url_match = re.search(r"(?mi)(?:\*?URL\*?|Citation):.*?(https?://[^\s)`]+)", section)
        if key_match is None and url_match is None:
            continue
        key = (
            key_match.group(1).strip()
            if key_match is not None
            else f"recovered:{url_match.group(1).rstrip('.,')}|{heading.group(1)}"
        )
        if not key or key in seen_keys:
            continue
        use_match = re.search(
            r"(?mi)(?:final use|disposition|role)\*{0,2}:\*{0,2}\s*([^\n]+)",
            section,
        )
        use = use_match.group(1).lower() if use_match else "final_evidence"
        if "rejected" in use:
            disposition = "rejected"
        elif "discovery_only" in use or "discovery only" in use:
            disposition = "discovery_only"
        elif "context" in use or "baseline" in use:
            disposition = "context"
        else:
            disposition = "final_evidence"
        entry = {
            "provisional_id": heading.group(1),
            "canonical_fact_key": key,
            "disposition": disposition,
            "chapter_ids": sorted(
                set(re.findall(r"\b([1-8]B)(?:\.\d+)?\b", heading.group(0) + section))
            ),
        }
        if disposition == "rejected":
            entry["reason"] = use_match.group(1).strip() if use_match else "rejected"
        entries.append(entry)
        seen_keys.add(key)
    return entries


def _validate_formatter_ledger_accounting(
    dossier: RulerEvidenceDossier, *, notebook: str
) -> None:
    """Prevent formatter collapse while allowing consolidation and source upgrades."""

    marker = "--- RESEARCH LEDGER MANIFEST ---"
    if marker not in notebook:
        return
    try:
        manifest, _ = json.JSONDecoder().raw_decode(
            notebook.rsplit(marker, maxsplit=1)[1].lstrip()
        )
    except json.JSONDecodeError:
        return
    expected = {
        str(entry["canonical_fact_key"]): entry
        for entry in manifest.get("entries", [])
        if entry.get("disposition") == "final_evidence"
    }
    emitted = {
        item.canonical_fact_key: item
        for item in dossier.evidence
        if item.final_evidence_use == "final_evidence"
    }
    missing_keys = sorted(set(expected) - set(emitted))
    if missing_keys:
        raise WorkerOutputError(
            "formatter omitted accepted final evidence: " + ", ".join(missing_keys[:5])
        )
    mapped_chapters: dict[str, set[str]] = {}
    evidence_key_by_id = {
        item.evidence_id: item.canonical_fact_key for item in dossier.evidence
    }
    for mapping in dossier.mappings:
        key = evidence_key_by_id.get(mapping.evidence_id)
        if key:
            mapped_chapters.setdefault(key, set()).add(
                mapping.methodology_id.split(".", maxsplit=1)[0]
            )
    routing_failures = {
        key: sorted(set(entry.get("chapter_ids", [])) - mapped_chapters.get(key, set()))
        for key, entry in expected.items()
        if set(entry.get("chapter_ids", [])) - mapped_chapters.get(key, set())
    }
    if routing_failures:
        summary = ", ".join(
            f"{key}=>{'/'.join(chapters)}"
            for key, chapters in list(routing_failures.items())[:5]
        )
        raise WorkerOutputError("formatter dropped accepted chapter routing: " + summary)


def _has_indeterminate_formatter_call(attempt: WorkerAttempt) -> bool:
    job_dir = attempt.attempt_dir.parent.parent
    for directory in attempt.trusted_dir.parent.glob("*"):
        if directory == attempt.trusted_dir or not (
            directory / "formatter-starting.json"
        ).is_file():
            continue
        prior_attempt = job_dir / "attempts" / directory.name
        events_path = directory / "codex-events.jsonl"
        if _events_show_failed_turn(events_path):
            continue
        if not _events_show_completed_turn(events_path):
            return True
        if not any(
            (prior_attempt / name).is_file()
            for name in ("dossier.pending.json", "dossier.json")
        ):
            return True
    return False


def _load_previous_research_checkpoint(
    trusted_dir: Path,
    *,
    job: dict[str, Any],
    profile: ResearchModelProfile,
) -> tuple[Path, str, Path, str, str] | None:
    """Recover the newest hashed completed notebook for formatter retry."""

    for directory in sorted(trusted_dir.parent.glob("*"), reverse=True):
        if directory == trusted_dir:
            continue
        marker = directory / "research-complete.marker"
        checkpoint_path = directory / "research-notebook-checkpoint.json"
        if not marker.is_file() or not checkpoint_path.is_file():
            continue
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or (
            payload.get("job_key"),
            payload.get("provider_profile"),
            payload.get("provider"),
            payload.get("model"),
        ) != (job["job_key"], job["provider_profile"], profile.provider, profile.model):
            continue
        notebook_path = Path(str(payload.get("notebook_path", "")))
        events_path = Path(str(payload.get("events_path", "")))
        notebook_hash = str(payload.get("notebook_sha256", ""))
        events_hash = str(payload.get("events_sha256", ""))
        if (
            notebook_path.is_file()
            and events_path.is_file()
            and sha256(notebook_path.read_bytes()).hexdigest() == notebook_hash
            and sha256(events_path.read_bytes()).hexdigest() == events_hash
        ):
            return (
                events_path,
                notebook_path.read_text(encoding="utf-8"),
                notebook_path,
                notebook_hash,
                events_hash,
            )
    return None


def _stamp_two_pass_usage(
    dossier: RulerEvidenceDossier,
    *,
    job: dict[str, Any],
    research_checkpoint: tuple[Path, str, Path, str, str],
    formatter_events_path: Path,
    attempt_dir: Path,
    formatter_profile: ResearchModelProfile,
) -> None:
    """Attach separate and combined trusted usage for mixed-model passes."""

    del formatter_events_path
    _assert_research_checkpoint_intact(research_checkpoint)
    priced_research = []
    priced_reviewer = []
    priced_formatter = []
    formatter_usage_incomplete = False
    trusted_root = attempt_dir.parent.parent / "trusted"
    for directory in sorted(trusted_root.glob("*")):
        research_events = [directory / "research-events.jsonl"]
        research_events.extend(
            sorted(directory.glob("research-continuation-round-*.events.jsonl"))
        )
        for events_path in research_events:
            if not events_path.is_file():
                continue
            usage = _read_codex_usage(events_path)
            if usage is not None:
                priced_research.append(
                    _price_codex_usage(
                        usage,
                        provider=job["provider"],
                        model=job["model"],
                    )
                )
        for takeover_events in sorted(
            directory.glob("research-supervisor-takeover-round-*.events.jsonl")
        ):
            usage = _read_codex_usage(takeover_events)
            if usage is not None:
                priced_research.append(
                    _price_codex_usage(
                        usage,
                        provider=str(job["input"]["reviewer_provider"]),
                        model=str(job["input"]["reviewer_model"]),
                    )
                )
        for reviewer_events in sorted(
            directory.glob("evidence-review-round-*.events.jsonl")
        ):
            usage = _read_codex_usage(reviewer_events)
            if usage is not None:
                priced_reviewer.append(
                    _price_codex_usage(
                        usage,
                        provider=str(job["input"]["reviewer_provider"]),
                        model=str(job["input"]["reviewer_model"]),
                    )
                )
        formatter_events = directory / "codex-events.jsonl"
        if (directory / "formatter-starting.json").is_file():
            usage = _read_codex_usage(formatter_events)
            if usage is None:
                formatter_usage_incomplete = True
            elif (directory / "formatter-complete.marker").is_file():
                priced_formatter.append(
                    _price_codex_usage(
                        usage,
                        provider=formatter_profile.provider,
                        model=formatter_profile.model,
                    )
                )
    combined_research = (
        combine_priced_usage(tuple(priced_research))
        if priced_research
        else _unknown_usage()
    )
    combined_reviewer = (
        combine_priced_usage(tuple(priced_reviewer))
        if priced_reviewer
        else (
            _zero_usage()
            if int(job["input"]["research_workflow"]["max_review_rounds"]) == 0
            else _unknown_usage()
        )
    )
    combined_formatter = _unknown_usage() if formatter_usage_incomplete else (
        combine_priced_usage(tuple(priced_formatter))
        if priced_formatter
        else _unknown_usage()
    )
    dossier.run_profile.workflow_mode = "direct_search_chapter_loop_v1"
    dossier.run_profile.formatter_provider_profile = str(
        job["input"]["formatter_profile"]
    )
    dossier.run_profile.formatter_provider = formatter_profile.provider
    dossier.run_profile.formatter_model = formatter_profile.model
    dossier.run_profile.reviewer_provider_profile = str(
        job["input"]["reviewer_profile"]
    )
    dossier.run_profile.reviewer_provider = str(job["input"]["reviewer_provider"])
    dossier.run_profile.reviewer_model = str(job["input"]["reviewer_model"])
    dossier.run_profile.research_notebook_path = str(research_checkpoint[2])
    dossier.run_profile.research_notebook_sha256 = research_checkpoint[3]
    dossier.run_profile.research_usage = combined_research
    dossier.run_profile.reviewer_usage = combined_reviewer
    dossier.run_profile.formatter_usage = combined_formatter
    dossier.run_profile.usage = combine_priced_usage(
        tuple(
            item
            for item in (combined_research, combined_reviewer, combined_formatter)
            if item.cost_certainty != "unknown"
        )
    ) if all(
        item.cost_certainty != "unknown"
        for item in (combined_research, combined_reviewer, combined_formatter)
    ) else _unknown_usage()


def _unknown_usage() -> DossierUsage:
    unknown = "unknown_not_exposed_by_tool"
    return DossierUsage(
        input_tokens=unknown,
        output_tokens=unknown,
        total_tokens=unknown,
        estimated_cost_usd=unknown,
        cost_certainty="unknown",
    )


def _zero_usage() -> DossierUsage:
    return DossierUsage(
        input_tokens=0,
        cached_input_tokens=0,
        uncached_input_tokens=0,
        cache_write_input_tokens=0,
        output_tokens=0,
        reasoning_output_tokens=0,
        total_tokens=0,
        estimated_cost_usd=0.0,
        payg_equivalent_cost_usd_lower=0.0,
        payg_equivalent_cost_usd_upper=0.0,
        codex_equivalent_credits_lower=0.0,
        codex_equivalent_credits_upper=0.0,
        parallel_search_cost_usd=0.0,
        actual_billed_cost_usd=0.0,
        cost_certainty="exact",
    )


def _assert_research_checkpoint_intact(
    checkpoint: tuple[Path, str, Path, str, str],
) -> None:
    """Reject mutation of parent-trusted research material before publication."""

    if (
        sha256(checkpoint[2].read_bytes()).hexdigest() != checkpoint[3]
        or sha256(checkpoint[0].read_bytes()).hexdigest() != checkpoint[4]
    ):
        raise WorkerOutputError("trusted research checkpoint changed after approval")


def _finalize_execution_usage(
    dossier: RulerEvidenceDossier,
    *,
    job: dict[str, Any],
    research_checkpoint: tuple[Path, str, Path, str, str] | None,
    formatter_events_path: Path,
    attempt_dir: Path,
    formatter_profile: ResearchModelProfile,
) -> None:
    if research_checkpoint is None:
        return
    _stamp_two_pass_usage(
        dossier,
        job=job,
        research_checkpoint=research_checkpoint,
        formatter_events_path=formatter_events_path,
        attempt_dir=attempt_dir,
        formatter_profile=formatter_profile,
    )


def _run_codex(
    engine: Engine,
    *,
    command: tuple[str, ...],
    prompt: str,
    events_path: Path,
    job_id: int,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> None:
    started = time.monotonic()
    next_heartbeat = started + heartbeat_seconds
    with events_path.open("a", encoding="utf-8") as events:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=events,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            while process.poll() is None:
                now = time.monotonic()
                if now - started >= timeout_seconds:
                    raise TimeoutError(f"Codex worker exceeded {timeout_seconds} seconds")
                if now >= next_heartbeat:
                    heartbeat_job(
                        engine,
                        job_id=job_id,
                        worker_id=worker_id,
                        lease_token=lease_token,
                        lease_seconds=lease_seconds,
                        progress={
                            "phase": "codex_running",
                            "elapsed_seconds": round(now - started),
                        },
                    )
                    next_heartbeat = now + heartbeat_seconds
                time.sleep(min(1.0, max(0.1, next_heartbeat - now)))
            if process.returncode != 0:
                raise RuntimeError(f"Codex worker exited with status {process.returncode}")
        finally:
            _terminate_process_group(process)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, 15)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        process.wait(timeout=10)


def _validate_dossier_matches_job(
    dossier: RulerEvidenceDossier, job: dict[str, Any]
) -> None:
    expected = {
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"]["ruler_year_id"],
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "methodology_ids": tuple(job["input"]["question_ids"]),
    }
    actual = {key: getattr(dossier, key) for key in expected}
    if actual != expected:
        raise ValueError("validated dossier identity or question scope differs from its job")
    profile = dossier.run_profile
    if (profile.provider_profile, profile.provider, profile.model) != (
        job["provider_profile"],
        job["provider"],
        job["model"],
    ):
        raise ValueError("validated dossier run profile differs from its job")


__all__ = ["WorkerOutputError", "execute_claimed_dossier_job"]
