"""Validate and normalize one chapter-judge candidate batch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._codex_worker_artifacts import price_codex_usage, read_codex_usage
from .chapter_judge_models import ChapterJudgmentBatch
from .chapter_judge_normalize import (
    _ensure_bias_assessment,
    _is_duplicate_placeholder,
    _local_evidence_ids,
    _normalize_calibration_references,
    _normalize_confidence_scale,
    _normalize_evidence_reference_lists,
    _normalize_judgment_envelope,
    _normalize_lens_lists,
    _normalize_local_evidence_reference_lists,
)
from .chapter_projection import RulerChapterProjection
from .codex_worker import WorkerOutputError
from .dossier_models import DossierUsage, RulerEvidenceDossier


def _write_null_recovery_queue(
    batch: ChapterJudgmentBatch,
    *,
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
    path: Path,
) -> None:
    """Persist a bounded follow-up queue from existing null-judgment fields."""

    evidence_counts = {
        projection.job_key: len(projection.evidence) for _, projection in projections
    }
    requests = []
    for evaluation in batch.evaluations:
        if evaluation.score_1_to_10 is not None:
            continue
        recoverable = evaluation.manual_review_reason_type == "recoverable_null"
        requests.append(
            {
                "dossier_job_key": evaluation.dossier_job_key,
                "iso3": evaluation.iso3,
                "ruler_year_id": evaluation.ruler_year_id,
                "ruler_name": evaluation.ruler_name,
                "chapter_id": evaluation.chapter_id,
                "current_evidence_count": evidence_counts.get(evaluation.dossier_job_key, 0),
                "reason": evaluation.insufficient_evidence_reason,
                "missing_or_weak_lenses": list(evaluation.missing_or_weak_lenses),
                "requested_follow_up": evaluation.manual_review_reason,
                "next_action": (
                    "request_user_authorized_research_return"
                    if recoverable
                    else "substantive_review"
                ),
                "maximum_research_rounds": 1 if recoverable else 0,
                "runs_automatically": False,
            }
        )
    payload = {
        "schema_version": "chapter_null_recovery_v1",
        "judge_job_key": batch.job_key,
        "chapter_id": batch.chapter_id,
        "request_count": len(requests),
        "requests": requests,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_candidate(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorkerOutputError("Codex judge did not produce its final response file")
    if path.stat().st_size > 10_000_000:
        raise WorkerOutputError("Codex judge output exceeds the 10 MB batch limit")
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkerOutputError("Codex judge produced invalid JSON") from exc
    if not isinstance(candidate, dict):
        raise WorkerOutputError("Codex judge output must be a JSON object")
    return candidate


def _prepare_batch(  # noqa: PLR0912, PLR0915
    candidate: dict[str, Any],
    *,
    job: dict[str, Any],
    dossiers: tuple[tuple[Path, RulerEvidenceDossier], ...],
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
    rubric_version: str,
    events_path: Path,
) -> ChapterJudgmentBatch:
    dossier_by_key = {dossier.job_key: dossier for _, dossier in dossiers}
    projection_by_key = {projection.job_key: projection for _, projection in projections}
    if set(projection_by_key) != set(dossier_by_key):
        raise ValueError("chapter projections differ from the dossier cohort")
    raw_evaluations = candidate.get("evaluations")
    if not isinstance(raw_evaluations, list):
        raise ValueError("chapter batch evaluations must be a list")
    deduplicated: list[dict[str, Any]] = []
    emitted_by_key: dict[str, dict[str, Any]] = {}
    for evaluation in raw_evaluations:
        if not isinstance(evaluation, dict):
            raise ValueError("chapter evaluation must be an object")
        dossier_key = str(evaluation.get("dossier_job_key", ""))
        prior = emitted_by_key.get(dossier_key)
        if prior is not None:
            if _is_duplicate_placeholder(evaluation):
                continue
            if _is_duplicate_placeholder(prior):
                deduplicated[deduplicated.index(prior)] = evaluation
                emitted_by_key[dossier_key] = evaluation
                continue
            comparable_fields = (
                "score_1_to_10",
                "manual_review_required",
            )
            if any(prior.get(field) != evaluation.get(field) for field in comparable_fields):
                raise ValueError("chapter evaluation has conflicting duplicate judgments")
            prior_reason = str(prior.get("insufficient_evidence_reason") or "").strip()
            duplicate_reason = str(evaluation.get("insufficient_evidence_reason") or "").strip()
            if duplicate_reason and duplicate_reason != prior_reason:
                prior["insufficient_evidence_reason"] = f"{prior_reason} {duplicate_reason}".strip()
            continue
        deduplicated.append(evaluation)
        emitted_by_key[dossier_key] = evaluation
    raw_evaluations = deduplicated
    candidate["evaluations"] = raw_evaluations
    seen: set[str] = set()
    for evaluation in raw_evaluations:
        if not isinstance(evaluation, dict):
            raise ValueError("chapter evaluation must be an object")
        dossier_key = str(evaluation.get("dossier_job_key", ""))
        dossier = dossier_by_key.get(dossier_key)
        if dossier is None or dossier_key in seen:
            raise ValueError("chapter evaluation has an unknown or duplicate dossier job key")
        seen.add(dossier_key)
        _normalize_lens_lists(
            evaluation, valid_methodology_ids=set(job["input"]["methodology_ids"])
        )
        _normalize_evidence_reference_lists(
            evaluation,
            valid_evidence_ids={
                item.evidence_id for item in projection_by_key[dossier_key].evidence
            },
        )
        _normalize_local_evidence_reference_lists(
            evaluation,
            valid_local_evidence_ids=_local_evidence_ids(projection_by_key[dossier_key]),
        )
        _ensure_bias_assessment(
            evaluation,
            valid_evidence_ids={
                item.evidence_id for item in projection_by_key[dossier_key].evidence
            },
        )
        _normalize_calibration_references(evaluation, available_dossier_keys=set(dossier_by_key))
        _normalize_judgment_envelope(evaluation)
        evaluation.update(
            {
                "iso3": dossier.iso3,
                "ruler_id": dossier.ruler_id,
                "ruler_year_id": dossier.ruler_year_id,
                "ruler_name": dossier.ruler_name,
                "period_start_year": dossier.period_start_year,
                "period_end_year": dossier.period_end_year,
                "chapter_id": job["input"]["chapter_id"],
                "rubric_version": rubric_version,
                "calibration_batch_id": job["job_key"],
            }
        )
    _normalize_confidence_scale(raw_evaluations, candidate=candidate)
    if seen != set(dossier_by_key):
        raise ValueError("chapter batch must evaluate every available dossier exactly once")
    candidate |= {
        "schema_version": "ruler_chapter_judgment_v1",
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "chapter_id": job["input"]["chapter_id"],
        "target_year": job["target_year"],
        "rubric_version": rubric_version,
        "calibration_batch_id": job["job_key"],
        "pipeline_provenance": job["input"].get("pipeline_provenance"),
        "unavailable_dossiers": job["input"].get("unavailable_dossiers", []),
    }
    profile = candidate.get("run_profile")
    if not isinstance(profile, dict):
        raise ValueError("chapter batch run_profile must be an object")
    profile |= {
        "provider_profile": job["provider_profile"],
        "provider": job["provider"],
        "model": job["model"],
        "dossier_count": len(dossiers),
        "unavailable_dossier_count": len(candidate["unavailable_dossiers"]),
    }
    usage = _completed_judge_usage(events_path.parent, events_path)
    if usage is not None:
        profile["usage"] = price_codex_usage(
            usage,
            provider=job["provider"],
            model=job["model"],
        ).model_dump(mode="json")
    batch = ChapterJudgmentBatch.model_validate(candidate)
    if len(batch.evaluations) > 1 and all(
        evaluation.score_1_to_10 is None for evaluation in batch.evaluations
    ):
        raise ValueError(
            "multi-ruler chapter judgment cannot publish an all-null comparative batch"
        )
    _validate_batch_evidence(
        batch,
        projection_by_key=projection_by_key,
        available_keys=set(dossier_by_key),
    )
    return batch


def _validate_batch_evidence(
    batch: ChapterJudgmentBatch,
    *,
    projection_by_key: dict[str, RulerChapterProjection],
    available_keys: set[str],
) -> None:
    """Confine calibration and decisive citations to chapter projections."""

    for evaluation in batch.evaluations:
        projection = projection_by_key[evaluation.dossier_job_key]
        evidence_by_id = {item.evidence_id: item for item in projection.evidence}
        calibrated = set(evaluation.calibrated_against)
        if not calibrated.issubset(available_keys):
            raise ValueError("calibrated_against must reference available dossier job keys")
        if len(available_keys) > 1 and not calibrated:
            raise ValueError("multi-ruler judgment must provide calibration references")
        if len(available_keys) > 1 and not calibrated - {evaluation.dossier_job_key}:
            raise ValueError("multi-ruler judgment must calibrate against another ruler")
        referenced = (
            *evaluation.decisive_positive_evidence,
            *evaluation.decisive_negative_evidence,
            *evaluation.contrary_evidence,
        )
        if any(item.evidence_id not in evidence_by_id for item in referenced):
            raise ValueError("chapter evaluation references evidence outside its dossier")
        local_ids = _local_evidence_ids(projection)
        local_references = (
            *evaluation.decisive_local_evidence,
            *evaluation.contextual_local_evidence,
        )
        if any(item.local_evidence_id not in local_ids for item in local_references):
            raise ValueError("chapter evaluation references local evidence outside its package")
        summary = evaluation.structured_prior_summary.casefold()
        if projection.local_evidence.status == "available" and (
            "not_available" in summary or "unavailable" in summary
        ):
            raise ValueError("structured_prior_summary contradicts available local evidence")
        bias_ids = {
            evidence_id
            for finding in evaluation.bias_assessment.material_biases
            for evidence_id in finding.supporting_evidence_ids
        }
        if not bias_ids.issubset(evidence_by_id):
            raise ValueError("bias assessment references evidence outside its dossier")
        if any(
            evidence_by_id[item.evidence_id].final_evidence_use == "discovery_only"
            for item in referenced
        ):
            raise ValueError("chapter evaluation decisively cites discovery-only evidence")


def _completed_judge_usage(attempt_dir: Path, current_events_path: Path) -> DossierUsage | None:
    """Include current and prior completed judge execution turns."""

    event_paths = {current_events_path}
    attempts_dir = attempt_dir.parent
    if attempts_dir.is_dir():
        for prior in attempts_dir.iterdir():
            if (
                prior.is_dir()
                and prior != attempt_dir
                and (prior / "judge-complete.marker").is_file()
            ):
                event_paths.add(prior / "codex-events.jsonl")
    usages = tuple(usage for path in event_paths if (usage := read_codex_usage(path)) is not None)
    if not usages:
        return None
    input_tokens = sum(int(item.input_tokens) for item in usages)
    cached_tokens = sum(int(item.cached_input_tokens) for item in usages)
    output_tokens = sum(int(item.output_tokens) for item in usages)
    reasoning_tokens = sum(int(item.reasoning_output_tokens) for item in usages)
    return DossierUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        uncached_input_tokens=input_tokens - cached_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd="unknown_not_exposed_by_tool",
    )
