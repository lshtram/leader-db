"""Validated release controls for deep-corpus judge handoffs."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from .pipeline_provenance import (
    PipelineStageVersion,
    ProductionPipelineProvenance,
    build_pipeline_provenance,
)


class DeepCorpusJudgeContract(BaseModel):
    """Runtime controls that determine whether thin fallback is permissible."""

    model_config = ConfigDict(extra="allow", frozen=True)

    require_approved_corpus_package: bool
    allow_legacy_dossier_fallback: bool
    require_all_eight_approved_chapters: bool
    require_hash_bound_analysis_review_and_corpus: bool


class DeepCorpusRelease(BaseModel):
    """Relevant, validated portion of one versioned evidence-pipeline release."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: str
    release_id: str
    status: str
    target_year: int
    pipeline_version_id: str
    methodology_version_id: str
    methodology_freeze: str
    stage_versions: tuple[PipelineStageVersion, ...]
    judge_contract: DeepCorpusJudgeContract


def load_deep_corpus_release(path: Path) -> DeepCorpusRelease:
    """Load a release and reject internally contradictory strict-judge controls."""

    release = DeepCorpusRelease.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    contract = release.judge_contract
    if contract.require_approved_corpus_package and contract.allow_legacy_dossier_fallback:
        raise ValueError("strict deep-corpus release cannot allow legacy fallback")
    if contract.require_approved_corpus_package and not (
        contract.require_all_eight_approved_chapters
        and contract.require_hash_bound_analysis_review_and_corpus
    ):
        raise ValueError("strict deep-corpus release requires complete hash-bound approval")
    _validate_methodology_freeze(path, release)
    return release


def _validate_methodology_freeze(path: Path, release: DeepCorpusRelease) -> None:
    """Verify the question, guide, and customer-document bytes named by the release."""

    root = path.resolve().parents[2]
    freeze_path = (root / release.methodology_freeze).resolve()
    if not freeze_path.is_relative_to(root) or not freeze_path.is_file():
        raise ValueError("methodology freeze must be a project-local file")
    payload = yaml.safe_load(freeze_path.read_text(encoding="utf-8"))
    if payload.get("release_id") != release.methodology_version_id:
        raise ValueError("methodology freeze ID differs from production release")
    hash_lines: list[str] = []
    for relative, expected in sorted(payload.get("file_hashes", {}).items()):
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError(f"methodology file is missing: {relative}")
        actual = sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"methodology file changed after freeze: {relative}")
        hash_lines.append(f"{actual}  {relative}\n")
    aggregate = sha256("".join(sorted(hash_lines)).encode()).hexdigest()
    if aggregate != payload.get("aggregate_sha256"):
        raise ValueError("methodology aggregate hash differs from frozen manifest")


def pipeline_provenance(
    path: Path,
    release: DeepCorpusRelease | None = None,
    *,
    project_root: Path | None = None,
) -> ProductionPipelineProvenance:
    """Build the full immutable provenance identity for a production release."""

    loaded = release or load_deep_corpus_release(path)
    resolved = path.resolve()
    persisted_path = (
        str(resolved.relative_to(project_root.resolve()))
        if project_root is not None and resolved.is_relative_to(project_root.resolve())
        else str(path)
    )
    root = project_root.resolve() if project_root is not None else resolved.parents[2]
    freeze_file = (root / loaded.methodology_freeze).resolve()
    freeze_payload = yaml.safe_load(freeze_file.read_text(encoding="utf-8"))
    return build_pipeline_provenance(
        release_file_path=path,
        release_id=loaded.release_id,
        release_path=persisted_path,
        pipeline_version_id=loaded.pipeline_version_id,
        methodology_version_id=loaded.methodology_version_id,
        methodology_freeze_path=loaded.methodology_freeze,
        methodology_freeze_file=freeze_file,
        methodology_aggregate_sha256=freeze_payload["aggregate_sha256"],
        stages=loaded.stage_versions,
    )


def release_reference(path: Path) -> dict[str, str]:
    """Return the immutable release identity persisted with planned judge jobs."""

    return {
        "path": str(path),
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }


def validate_release_reference(
    value: object, *, project_root: Path
) -> DeepCorpusRelease:
    """Reopen the exact project-local release frozen by the planner."""

    if not isinstance(value, dict):
        raise ValueError("deep-corpus release reference must be an object")
    path_value = value.get("path")
    expected_hash = value.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected_hash, str):
        raise ValueError("deep-corpus release reference is incomplete")
    candidate = Path(path_value)
    path = project_root / candidate if not candidate.is_absolute() else candidate
    path = path.resolve()
    if not path.is_relative_to(project_root.resolve()) or not path.is_file():
        raise ValueError("deep-corpus release must remain inside the project")
    if sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("deep-corpus release changed after judge planning")
    return load_deep_corpus_release(path)


__all__ = [
    "DeepCorpusRelease",
    "load_deep_corpus_release",
    "pipeline_provenance",
    "release_reference",
    "validate_release_reference",
]
