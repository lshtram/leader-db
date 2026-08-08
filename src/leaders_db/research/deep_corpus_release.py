"""Validated release controls for deep-corpus judge handoffs."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


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
    return release


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
    "release_reference",
    "validate_release_reference",
]
