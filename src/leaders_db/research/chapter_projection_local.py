"""Hash-verified local evidence inputs for chapter projections."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dossier_models import DossierLocalPrior
from .local_prior_package import JudgeLocalEvidencePackage, build_local_judge_package


class ChapterLocalEvidenceInput(BaseModel):
    """Hash-verified local evidence routed directly from its parent artifact."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "unavailable", "invalid"]
    artifact_path: str | None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    package: JudgeLocalEvidencePackage | None
    error: str | None

    @model_validator(mode="after")
    def _coherent_status(self) -> ChapterLocalEvidenceInput:
        if self.status == "available" and (
            self.package is None
            or self.artifact_path is None
            or self.artifact_sha256 is None
            or self.error is not None
        ):
            raise ValueError("available local evidence requires a verified package")
        if self.status != "available" and (
            self.package is not None or not self.error
        ):
            raise ValueError("unavailable local evidence requires an explicit error")
        return self


def legacy_unavailable_local_evidence() -> ChapterLocalEvidenceInput:
    """Keep preserved v1 projections readable without inventing local facts."""

    return ChapterLocalEvidenceInput(
        status="unavailable",
        artifact_path=None,
        artifact_sha256=None,
        package=None,
        error="legacy projection does not embed a direct local-evidence package",
    )


def load_local_evidence(
    *,
    local_priors: tuple[DossierLocalPrior, ...],
    chapter_id: str,
) -> ChapterLocalEvidenceInput:
    """Load and compact one hash-bound parent artifact without using web output."""

    artifact_pairs = {
        (item.artifact_path, item.artifact_sha256) for item in local_priors
    }
    if len(artifact_pairs) != 1:
        return _error_input(
            "invalid",
            "chapter local-prior provenance references multiple artifacts",
        )
    artifact_path, expected_sha256 = next(iter(artifact_pairs))
    path = Path(artifact_path)
    if not path.is_file():
        return _error_input(
            "unavailable",
            "parent local-evidence artifact is unavailable",
            artifact_path,
            expected_sha256,
        )
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        return _error_input(
            "unavailable",
            f"parent local-evidence artifact could not be read: {exc}",
            artifact_path,
            expected_sha256,
        )
    if sha256(encoded).hexdigest() != expected_sha256:
        return _error_input(
            "invalid",
            "parent local-evidence artifact hash does not match provenance",
            artifact_path,
            expected_sha256,
        )
    try:
        payload = json.loads(encoded)
        if not isinstance(payload, list):
            raise ValueError("local-evidence artifact must contain a list")
        package = build_local_judge_package(
            tuple(_require_mapping(item) for item in payload),
            chapter_id=chapter_id,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _error_input(
            "invalid",
            f"parent local-evidence artifact is invalid: {exc}",
            artifact_path,
            expected_sha256,
        )
    return ChapterLocalEvidenceInput(
        status="available",
        artifact_path=artifact_path,
        artifact_sha256=expected_sha256,
        package=package,
        error=None,
    )


def _error_input(
    status: Literal["unavailable", "invalid"],
    error: str,
    artifact_path: str | None = None,
    artifact_sha256: str | None = None,
) -> ChapterLocalEvidenceInput:
    return ChapterLocalEvidenceInput(
        status=status,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        package=None,
        error=error,
    )


def _require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("local-evidence artifact entries must be objects")
    return value


__all__ = [
    "ChapterLocalEvidenceInput",
    "legacy_unavailable_local_evidence",
    "load_local_evidence",
]
