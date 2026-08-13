"""Immutable scientific and implementation identity for one production run."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PipelineStageVersion(BaseModel):
    """One named production stage and its unique implementation identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_id: str = Field(min_length=1)
    implementation_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)


class ProductionPipelineProvenance(BaseModel):
    """Complete version identity carried by every publishable result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "production_pipeline_provenance_v1"
    pipeline_version_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    release_path: str = Field(min_length=1)
    release_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    methodology_version_id: str = Field(min_length=1)
    methodology_freeze_path: str = Field(min_length=1)
    methodology_freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    methodology_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stages: tuple[PipelineStageVersion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_stages(self) -> ProductionPipelineProvenance:
        names = [stage.stage_id for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("production pipeline stage IDs must be unique")
        return self


def build_pipeline_provenance(
    *,
    release_file_path: Path,
    release_id: str,
    release_path: str,
    pipeline_version_id: str,
    methodology_version_id: str,
    methodology_freeze_path: str,
    methodology_freeze_file: Path,
    methodology_aggregate_sha256: str,
    stages: tuple[PipelineStageVersion, ...],
) -> ProductionPipelineProvenance:
    """Bind configured stage identities to the exact release bytes."""

    return ProductionPipelineProvenance(
        pipeline_version_id=pipeline_version_id,
        release_id=release_id,
        release_path=release_path,
        release_sha256=sha256(release_file_path.read_bytes()).hexdigest(),
        methodology_version_id=methodology_version_id,
        methodology_freeze_path=methodology_freeze_path,
        methodology_freeze_sha256=sha256(methodology_freeze_file.read_bytes()).hexdigest(),
        methodology_aggregate_sha256=methodology_aggregate_sha256,
        stages=stages,
    )


__all__ = [
    "PipelineStageVersion",
    "ProductionPipelineProvenance",
    "build_pipeline_provenance",
]
