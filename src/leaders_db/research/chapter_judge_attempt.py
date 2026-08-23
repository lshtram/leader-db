"""Prepare immutable inputs for a chapter-judge attempt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from .approved_chapter_projection import build_approved_chapter_projection
from .approved_ruler_package import ApprovedPackageReference
from .chapter_guides import load_chapter_guide
from .chapter_judge_models import codex_chapter_judgment_json_schema
from .chapter_projection import (
    ChapterProjectionBatchEstimate,
    RulerChapterProjection,
    build_ruler_chapter_projection,
    estimate_chapter_projection_batch_context,
)
from .deep_corpus_release import validate_release_reference
from .dossier_models import RulerEvidenceDossier
from .job_ledger_queries import list_jobs


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
    release_reference = job["input"].get("deep_corpus_release")
    if release_reference is not None:
        release = validate_release_reference(release_reference, project_root=project_root)
        if release.target_year != int(job["target_year"]):
            raise ValueError("deep-corpus release target year differs from judge job")
    dossiers = _load_dependency_dossiers(engine, job=job, project_root=project_root)
    projections = _write_chapter_projections(
        dossiers,
        chapter_id=str(job["input"]["chapter_id"]),
        target_year=int(job["target_year"]),
        attempt_dir=attempt_dir,
        project_root=project_root,
        approved_packages=job["input"].get("approved_ruler_packages", {}),
        require_approved_corpus=bool(job["input"].get("require_approved_corpus", False)),
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
        json.dumps(
            codex_chapter_judgment_json_schema(
                str(job["input"]["chapter_id"]),
                tuple(str(item) for item in job["input"]["dossier_job_keys"]),
            ),
            indent=2,
            sort_keys=True,
        ),
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
    target_year: int | None = None,
    attempt_dir: Path,
    project_root: Path | None = None,
    approved_packages: dict[str, dict[str, str]] | None = None,
    require_approved_corpus: bool = False,
) -> tuple[tuple[Path, RulerChapterProjection], ...]:
    """Write immutable chapter-only model inputs beside the judge attempt."""

    inputs_dir = attempt_dir / "chapter-inputs"
    inputs_dir.mkdir()
    written: list[tuple[Path, RulerChapterProjection]] = []
    package_paths = approved_packages or {}
    for source_path, dossier in dossiers:
        approved_value = package_paths.get(dossier.job_key)
        if approved_value is not None:
            if project_root is None:
                raise ValueError("approved corpus projection requires project root")
            approved = ApprovedPackageReference.model_validate(approved_value)
            path_value = Path(approved.path)
            manifest_path = (
                project_root / path_value if not path_value.is_absolute() else path_value
            )
            actual_hash = sha256(manifest_path.read_bytes()).hexdigest()
            if actual_hash != approved.sha256:
                raise ValueError(
                    f"approved corpus package changed after planning: {dossier.job_key}"
                )
            projection = build_approved_chapter_projection(
                dossier,
                chapter_id=chapter_id,
                dossier_path=source_path,
                approval_manifest_path=manifest_path,
                project_root=project_root,
                target_year=(target_year if target_year is not None else dossier.period_end_year),
            )
        else:
            if require_approved_corpus:
                raise ValueError(f"approved corpus package missing for dossier: {dossier.job_key}")
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


def _projection_hashes(
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
) -> dict[Path, str]:
    """Snapshot judge-input digests so file-backed reads cannot drift mid-run."""

    return {path: sha256(path.read_bytes()).hexdigest() for path, _ in projections}


def _load_dependency_dossiers(
    engine: Engine, *, job: dict[str, Any], project_root: Path
) -> tuple[tuple[Path, RulerEvidenceDossier], ...]:
    expected = tuple(str(item) for item in job["input"].get("dossier_job_keys", []))
    configured_runs = job["input"].get("dossier_run_keys") or (
        job["input"].get("dossier_run_key") or job["run_key"],
    )
    dossier_run_keys = tuple(str(item) for item in configured_runs)
    jobs = {
        item["job_key"]: item
        for run_key in dossier_run_keys
        for item in list_jobs(engine, run_key=run_key, job_type="dossier_researcher")
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
        if dossier.job_key != job_key or dossier.run_key != parent["run_key"]:
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
