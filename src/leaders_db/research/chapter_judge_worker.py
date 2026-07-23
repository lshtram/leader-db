"""Execute one claimed comparative chapter-judge job through Codex."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.engine import Engine

from ._codex_worker_artifacts import (
    price_codex_usage,
    read_codex_usage,
)
from .chapter_guides import load_chapter_guide
from .chapter_judge_models import (
    ChapterJudgmentBatch,
    codex_chapter_judgment_json_schema,
)
from .chapter_judge_prompt import build_chapter_judge_prompt
from .chapter_projection import (
    ChapterProjectionBatchEstimate,
    RulerChapterProjection,
    build_ruler_chapter_projection,
    estimate_chapter_projection_batch_context,
)
from .codex_worker import WorkerOutputError, _run_codex
from .codex_worker_command import build_codex_exec_command, validate_worker_timing
from .dossier_models import DossierUsage, RulerEvidenceDossier
from .job_ledger import checkpoint_job, heartbeat_job
from .job_ledger_queries import list_jobs
from .model_profiles import load_research_model_profiles


@dataclass(frozen=True)
class ChapterJudgeAttempt:
    """Attempt-scoped paths and trusted input dossiers."""

    attempt_dir: Path
    result_path: Path
    pending_path: Path
    prompt_path: Path
    schema_path: Path
    events_path: Path
    dossiers: tuple[tuple[Path, RulerEvidenceDossier], ...]
    projections: tuple[tuple[Path, RulerChapterProjection], ...]
    context_estimate: ChapterProjectionBatchEstimate
    guide_text: str
    rubric_version: str


def execute_claimed_chapter_judge_job(
    engine: Engine,
    *,
    job: dict[str, Any],
    worker_id: str,
    project_root: Path,
    model_profiles_path: Path,
    lease_seconds: int,
    heartbeat_seconds: int,
    timeout_seconds: int,
) -> tuple[Path, ChapterJudgmentBatch]:
    """Run and validate one claimed chapter judge, without completing its lease."""

    validate_worker_timing(
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )
    if job["job_type"] != "question_judge" or job["status"] != "claimed":
        raise ValueError("worker can execute only a claimed chapter-judge job")
    lease_token = str(job["lease_token"])
    profile = load_research_model_profiles(model_profiles_path).profiles.get(
        job["provider_profile"]
    )
    if profile is None or "chapter_judge" not in profile.roles:
        raise ValueError("configured provider profile does not permit chapter judging")
    if (profile.provider, profile.model) != (job["provider"], job["model"]):
        raise ValueError("claimed job provider/model differs from the configured profile")

    if profile.context_window is None:
        raise ValueError("chapter judge profile must declare a context_window")
    attempt = _initialize_attempt(
        engine,
        job=job,
        project_root=project_root,
        context_window=profile.context_window,
    )
    batch, existing = _recover_previous_chapter_batch(attempt=attempt, job=job)
    if batch is not None:
        _write_null_recovery_queue(
            batch,
            projections=attempt.projections,
            path=attempt.attempt_dir / "null-recovery.json",
        )
        _publish_batch(
            engine,
            batch=batch,
            pending_path=attempt.pending_path,
            result_path=attempt.result_path,
            job=job,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
        )
        return attempt.result_path, batch
    previous_path = None
    if existing is not None:
        previous_path = attempt.attempt_dir / "previous-candidate.json"
        previous_path.write_text(json.dumps(existing), encoding="utf-8")

    candidate: dict[str, Any] | None = None
    if candidate is None:
        prompt = build_chapter_judge_prompt(
            job,
            project_root=project_root,
            guide_text=attempt.guide_text,
            projections=attempt.projections,
            previous_candidate_path=previous_path,
        )
        attempt.prompt_path.write_text(prompt, encoding="utf-8")
        command = build_codex_exec_command(
            profile=profile,
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
            checkpoint={
                "phase": "chapter_judge_starting",
                "attempt_dir": str(attempt.attempt_dir),
                "dossier_count": len(attempt.dossiers),
                "estimated_input_tokens": attempt.context_estimate.estimated_input_tokens,
            },
        )
        _run_judge(
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
        (attempt.attempt_dir / "judge-complete.marker").write_text(
            "complete\n", encoding="utf-8"
        )
        heartbeat_job(
            engine,
            job_id=int(job["id"]),
            worker_id=worker_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            progress={"phase": "validating_chapter_output"},
        )
        candidate = _read_candidate(attempt.pending_path)

    try:
        batch = _prepare_batch(
            candidate,
            job=job,
            dossiers=attempt.dossiers,
            projections=attempt.projections,
            rubric_version=attempt.rubric_version,
            events_path=attempt.events_path,
        )
    except (ValidationError, ValueError) as exc:
        raise WorkerOutputError("Codex chapter judgment failed semantic validation") from exc
    _write_null_recovery_queue(
        batch,
        projections=attempt.projections,
        path=attempt.attempt_dir / "null-recovery.json",
    )
    _publish_batch(
        engine,
        batch=batch,
        pending_path=attempt.pending_path,
        result_path=attempt.result_path,
        job=job,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )
    return attempt.result_path, batch


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
                "current_evidence_count": evidence_counts.get(
                    evaluation.dossier_job_key, 0
                ),
                "reason": evaluation.insufficient_evidence_reason,
                "missing_or_weak_lenses": list(evaluation.missing_or_weak_lenses),
                "requested_follow_up": evaluation.manual_review_reason,
                "next_action": (
                    "resume_same_ruler_research" if recoverable else "substantive_review"
                ),
                "maximum_research_rounds": 2 if recoverable else 0,
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


def _initialize_attempt(
    engine: Engine,
    *,
    job: dict[str, Any],
    project_root: Path,
    context_window: int,
) -> ChapterJudgeAttempt:
    configured = job["input"].get("output_root")
    if not configured:
        raise ValueError("chapter judge job has no output_root")
    root = Path(str(configured))
    root = (project_root / root).resolve() if not root.is_absolute() else root.resolve()
    if not root.is_relative_to(project_root.resolve()):
        raise ValueError("chapter judge output_root must remain inside the project")
    attempt_dir = (
        root
        / "jobs"
        / str(job["id"])
        / "attempts"
        / f"{int(job['attempt_count']):03d}-{str(job['lease_token'])[:12]}"
    )
    attempt_dir.mkdir(parents=True, exist_ok=False)
    guide_text, rubric_version = load_chapter_guide(
        str(job["input"]["chapter_id"]), project_root=project_root
    )
    if rubric_version != job["input"].get("rubric_version"):
        raise ValueError("active chapter guide rubric differs from the planned judge job")
    dossiers = _load_dependency_dossiers(engine, job=job, project_root=project_root)
    projections = _write_chapter_projections(
        dossiers,
        chapter_id=str(job["input"]["chapter_id"]),
        attempt_dir=attempt_dir,
    )
    prompt_overhead = 5_000 + (len(guide_text.encode("utf-8")) + 2) // 3
    context_ceiling = context_window - 60_000
    if context_ceiling < 1:
        raise ValueError("chapter judge context window leaves no safe output reserve")
    context_estimate = estimate_chapter_projection_batch_context(
        tuple(item for _, item in projections),
        context_ceiling=context_ceiling,
        prompt_overhead_tokens=prompt_overhead,
    )
    schema_path = attempt_dir / "chapter-judgment.schema.json"
    schema_path.write_text(
        json.dumps(codex_chapter_judgment_json_schema(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return ChapterJudgeAttempt(
        attempt_dir=attempt_dir,
        result_path=attempt_dir / "chapter-judgment.json",
        pending_path=attempt_dir / "chapter-judgment.pending.json",
        prompt_path=attempt_dir / "prompt.txt",
        schema_path=schema_path,
        events_path=attempt_dir / "codex-events.jsonl",
        dossiers=dossiers,
        projections=projections,
        context_estimate=context_estimate,
        guide_text=guide_text,
        rubric_version=rubric_version,
    )


def _write_chapter_projections(
    dossiers: tuple[tuple[Path, RulerEvidenceDossier], ...],
    *,
    chapter_id: str,
    attempt_dir: Path,
) -> tuple[tuple[Path, RulerChapterProjection], ...]:
    """Write immutable chapter-only model inputs beside the judge attempt."""

    inputs_dir = attempt_dir / "chapter-inputs"
    inputs_dir.mkdir()
    written: list[tuple[Path, RulerChapterProjection]] = []
    for source_path, dossier in dossiers:
        projection = build_ruler_chapter_projection(
            dossier,
            chapter_id=chapter_id,
            source_dossier_path=Path(source_path.name),
            source_dossier_sha256=sha256(source_path.read_bytes()).hexdigest(),
        )
        path = inputs_dir / f"{dossier.iso3}-{dossier.ruler_year_id}.json"
        path.write_text(projection.model_dump_json(indent=2), encoding="utf-8")
        written.append((path, projection))
    return tuple(written)


def _load_dependency_dossiers(
    engine: Engine, *, job: dict[str, Any], project_root: Path
) -> tuple[tuple[Path, RulerEvidenceDossier], ...]:
    expected = tuple(str(item) for item in job["input"].get("dossier_job_keys", []))
    dossier_run_key = str(job["input"].get("dossier_run_key") or job["run_key"])
    jobs = {
        item["job_key"]: item for item in list_jobs(engine, run_key=dossier_run_key)
    }
    loaded: list[tuple[Path, RulerEvidenceDossier]] = []
    for job_key in expected:
        parent = jobs.get(job_key)
        if parent is None or parent["status"] != "completed" or not parent["result_path"]:
            raise ValueError(f"required dossier is not completed: {job_key}")
        path = Path(str(parent["result_path"])).resolve()
        if not path.is_relative_to(project_root.resolve()) or not path.is_file():
            raise ValueError(f"dossier artifact is missing or outside the project: {job_key}")
        dossier = RulerEvidenceDossier.model_validate_json(path.read_text(encoding="utf-8"))
        if dossier.job_key != job_key or dossier.run_key != dossier_run_key:
            raise ValueError(f"dossier artifact identity differs from dependency: {job_key}")
        expected_identity = {
            "iso3": parent["iso3"],
            "country_name": parent["country_name"],
            "ruler_id": parent["ruler_id"],
            "ruler_year_id": parent["input"].get("ruler_year_id"),
            "ruler_name": parent["ruler_name"],
            "period_start_year": parent["period_start_year"],
            "period_end_year": parent["period_end_year"],
        }
        actual_identity = {key: getattr(dossier, key) for key in expected_identity}
        if actual_identity != expected_identity:
            raise ValueError(f"dossier identity or period differs from dependency: {job_key}")
        if not dossier.period_start_year <= int(job["target_year"]) <= dossier.period_end_year:
            raise ValueError(f"judge target year falls outside dossier period: {job_key}")
        chapter_ids = set(job["input"]["methodology_ids"])
        if not chapter_ids.issubset(dossier.methodology_ids):
            raise ValueError(f"dossier does not cover the complete chapter: {job_key}")
        loaded.append((path, dossier))
    if not loaded:
        raise ValueError("chapter judge has no usable dossier artifacts")
    return tuple(loaded)


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
    projection_by_key = {
        projection.job_key: projection for _, projection in projections
    }
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
            duplicate_reason = str(
                evaluation.get("insufficient_evidence_reason") or ""
            ).strip()
            if duplicate_reason and duplicate_reason != prior_reason:
                prior["insufficient_evidence_reason"] = (
                    f"{prior_reason} {duplicate_reason}".strip()
                )
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
        _ensure_bias_assessment(
            evaluation,
            valid_evidence_ids={
                item.evidence_id for item in projection_by_key[dossier_key].evidence
            },
        )
        _normalize_calibration_references(
            evaluation, available_dossier_keys=set(dossier_by_key)
        )
        _normalize_judgment_envelope(evaluation)
        evaluation.update({
            "iso3": dossier.iso3,
            "ruler_id": dossier.ruler_id,
            "ruler_year_id": dossier.ruler_year_id,
            "ruler_name": dossier.ruler_name,
            "period_start_year": dossier.period_start_year,
            "period_end_year": dossier.period_end_year,
            "chapter_id": job["input"]["chapter_id"],
            "rubric_version": rubric_version,
            "calibration_batch_id": job["job_key"],
        })
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


def _is_duplicate_placeholder(evaluation: dict[str, Any]) -> bool:
    """Recognize an explicit non-judgment duplicate row without guessing."""

    reason = str(evaluation.get("insufficient_evidence_reason") or "").casefold()
    return evaluation.get("score_1_to_10") is None and "duplicate placeholder" in reason


def _normalize_judgment_envelope(evaluation: dict[str, Any]) -> None:
    """Canonicalize null fields or scored review taxonomy without changing substance."""

    if "score_1_to_10" not in evaluation:
        return
    if evaluation["score_1_to_10"] is not None:
        if (
            evaluation.get("manual_review_required") is True
            and evaluation.get("manual_review_reason_type") == "recoverable_null"
        ):
            evaluation["manual_review_reason_type"] = "decisive_source"
        return
    reason = str(evaluation.get("insufficient_evidence_reason") or "").strip()
    if not reason:
        reason = "The judge returned no defensible score; see the chapter rationale."
    evaluation["insufficient_evidence_reason"] = reason
    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}


def _normalize_calibration_references(
    evaluation: dict[str, Any], *, available_dossier_keys: set[str]
) -> None:
    """Accept a singleton judge's prose sentinel without inventing a peer.

    Comparative batches retain unknown references so the strict validator rejects
    them. A one-dossier end-to-end smoke has no external ruler available, however,
    and an explanatory string such as ``no_other_available_dossier`` carries the
    same unambiguous meaning as an empty list.
    """

    if len(available_dossier_keys) != 1:
        return
    values = evaluation.get("calibrated_against")
    if not isinstance(values, list):
        return
    evaluation["calibrated_against"] = list(
        dict.fromkeys(str(value) for value in values if str(value) in available_dossier_keys)
    )


def _ensure_bias_assessment(
    evaluation: dict[str, Any], *, valid_evidence_ids: set[str]
) -> None:
    """Retain an otherwise usable judgment while exposing missing bias reasoning."""

    assessment = evaluation.get("bias_assessment")
    if isinstance(assessment, dict):
        findings = assessment.get("material_biases")
        retained_findings: list[dict[str, Any]] = []
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                raw_ids = finding.get("supporting_evidence_ids")
                valid_ids = (
                    [
                        str(evidence_id)
                        for evidence_id in raw_ids
                        if str(evidence_id) in valid_evidence_ids
                    ]
                    if isinstance(raw_ids, list)
                    else []
                )
                if not valid_ids:
                    continue
                finding["supporting_evidence_ids"] = list(dict.fromkeys(valid_ids))
                retained_findings.append(finding)
        if retained_findings:
            assessment["material_biases"] = retained_findings
            return
        evaluation.pop("bias_assessment", None)
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = (
            "Producer bias findings had no same-dossier evidence references; "
            "a conservative fallback assessment was applied."
        )
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()
        evaluation["manual_review_required"] = True
        evaluation["manual_review_reason_type"] = "projection_integrity"
    if not valid_evidence_ids:
        evaluation["bias_assessment"] = {
            "material_biases": [],
            "confidence_and_range_effect": (
                "No same-dossier evidence was available to support a material bias "
                "finding; confidence remains minimal and the full range is retained."
            ),
            "remaining_uncertainty": (
                "The evidence environment cannot be assessed with cited chapter evidence."
            ),
            "report_volume_not_used_as_severity": True,
            "no_blanket_regime_correction": True,
        }
        return
    evidence_id = sorted(valid_evidence_ids)[0]
    evaluation["bias_assessment"] = {
        "material_biases": [
            {
                "bias": "Bias assessment omitted by the producer",
                "supporting_evidence_ids": [evidence_id],
                "likely_direction": "uncertain",
                "interpretation_effect": (
                    "No result-changing interpretation adjustment was inferred."
                ),
            }
        ],
        "confidence_and_range_effect": (
            "Confidence is capped and the range widened pending bias review."
        ),
        "remaining_uncertainty": "The omitted bias assessment remains unresolved.",
        "report_volume_not_used_as_severity": True,
        "no_blanket_regime_correction": True,
    }
    confidence = evaluation.get("confidence_score")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        evaluation["confidence_score"] = min(float(confidence), 50.0)
    score_range = evaluation.get("plausible_score_range")
    if isinstance(score_range, dict):
        lower = score_range.get("lower")
        upper = score_range.get("upper")
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            score_range["lower"] = max(1, float(lower) - 1)
            score_range["upper"] = min(10, float(upper) + 1)


def _normalize_lens_lists(
    evaluation: dict[str, Any], *, valid_methodology_ids: set[str]
) -> None:
    """Keep free-form gap observations without treating them as methodology IDs."""

    qualitative_gaps: list[str] = []
    supported: set[str] = set()
    for field in ("supported_lenses", "missing_or_weak_lenses"):
        values = evaluation.get(field)
        if not isinstance(values, list):
            continue
        normalized_values = [
            (_lens_id_from_value(value, valid_methodology_ids), str(value))
            for value in values
        ]
        valid_values = [lens_id for lens_id, _ in normalized_values if lens_id]
        if field == "supported_lenses":
            supported = set(valid_values)
        if field == "missing_or_weak_lenses":
            qualitative_gaps.extend(
                original
                for lens_id, original in normalized_values
                if not lens_id or original != lens_id
            )
            overlap = list(
                dict.fromkeys(value for value in valid_values if value in supported)
            )
            if overlap:
                qualitative_gaps.append(
                    "Partially supported but weak lenses: " + ", ".join(overlap)
                )
            valid_values = [value for value in valid_values if value not in supported]
        evaluation[field] = list(dict.fromkeys(valid_values))
    if qualitative_gaps:
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = "Additional weak areas: " + "; ".join(qualitative_gaps)
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()


def _lens_id_from_value(value: object, valid_methodology_ids: set[str]) -> str:
    """Recover a valid lens ID from an exact value or a descriptive prefix."""

    text = str(value).strip()
    if text in valid_methodology_ids:
        return text
    prefix = text.split(maxsplit=1)[0].rstrip(":;,-") if text else ""
    return prefix if prefix in valid_methodology_ids else ""


def _normalize_evidence_reference_lists(
    evaluation: dict[str, Any], *, valid_evidence_ids: set[str]
) -> None:
    """Drop unverifiable decisive references without guessing replacement IDs."""

    dropped: list[str] = []
    for field in (
        "decisive_positive_evidence",
        "decisive_negative_evidence",
        "contrary_evidence",
    ):
        values = evaluation.get(field)
        if not isinstance(values, list):
            continue
        retained: list[object] = []
        for value in values:
            if not isinstance(value, dict):
                retained.append(value)
                continue
            evidence_id = str(value.get("evidence_id", ""))
            if evidence_id not in valid_evidence_ids:
                dropped.append(evidence_id or "<missing>")
                continue
            retained.append(value)
        evaluation[field] = retained
    if dropped:
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = (
            "Dropped out-of-projection evidence references during normalization: "
            + ", ".join(dict.fromkeys(dropped))
            + "."
        )
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()
        evaluation["manual_review_required"] = True
        evaluation["manual_review_reason_type"] = "projection_integrity"


def _normalize_confidence_scale(
    evaluations: list[object], *, candidate: dict[str, Any]
) -> None:
    """Normalize an unambiguous batch-wide 0-1 confidence scale to 0-100."""

    values: list[float] = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            return
        value = evaluation.get("confidence_score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        values.append(float(value))
    if not values or not all(0 <= value <= 1 for value in values):
        return
    if not any(0 < value < 1 for value in values):
        return
    for evaluation in evaluations:
        assert isinstance(evaluation, dict)
        evaluation["confidence_score"] = round(
            float(evaluation["confidence_score"]) * 100, 6
        )
    note = "Confidence scores normalized from a batch-wide 0-1 scale to 0-100."
    notes = candidate.get("batch_notes")
    if isinstance(notes, list):
        if note not in notes:
            notes.append(note)
    else:
        candidate["batch_notes"] = [note]


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


def _completed_judge_usage(
    attempt_dir: Path, current_events_path: Path
) -> DossierUsage | None:
    """Include current and prior completed judge execution turns."""

    event_paths = {current_events_path}
    attempts_dir = attempt_dir.parent
    if attempts_dir.is_dir():
        for prior in attempts_dir.iterdir():
            if prior.is_dir() and prior != attempt_dir and (
                prior / "judge-complete.marker"
            ).is_file():
                event_paths.add(prior / "codex-events.jsonl")
    usages = tuple(
        usage
        for path in event_paths
        if (usage := read_codex_usage(path)) is not None
    )
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


def _run_judge(
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
    """Execute a no-discovery judge; the complete projections are embedded."""

    _run_codex(
        engine,
        command=command,
        prompt=prompt,
        events_path=events_path,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        heartbeat_seconds=heartbeat_seconds,
        timeout_seconds=timeout_seconds,
    )


def _find_previous_chapter_candidate(
    job_dir: Path, *, attempt_dir: Path
) -> dict[str, Any] | None:
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


def _publish_batch(
    engine: Engine,
    *,
    batch: ChapterJudgmentBatch,
    pending_path: Path,
    result_path: Path,
    job: dict[str, Any],
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> None:
    with pending_path.open("w", encoding="utf-8") as pending:
        pending.write(batch.model_dump_json(indent=2))
        pending.flush()
        os.fsync(pending.fileno())
    heartbeat_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        progress={"phase": "publishing_validated_chapter_output"},
    )
    os.replace(pending_path, result_path)
    checkpoint_job(
        engine,
        job_id=int(job["id"]),
        worker_id=worker_id,
        lease_token=lease_token,
        checkpoint={
            "phase": "validated",
            "result_path": str(result_path),
            "chapter_score_count": len(batch.evaluations),
        },
    )


__all__ = ["execute_claimed_chapter_judge_job"]
