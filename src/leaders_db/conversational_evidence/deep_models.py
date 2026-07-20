"""Validated state and configuration for the deep chapter experiment."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeepWorkflowConfig(BaseModel):
    """Scientific and operational controls for one experimental run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    candidate_target: int = Field(ge=20)
    accepted_minimum: int = Field(ge=1)
    accepted_maximum: int = Field(ge=1)
    discovery_max_rounds: int = Field(ge=1, le=10)
    inspection_wave_size: int = Field(ge=5, le=40)
    turn_timeout_seconds: int = Field(default=1800, ge=300, le=1800)
    chapters: tuple[str, ...]

    @model_validator(mode="after")
    def validate_ranges(self) -> DeepWorkflowConfig:
        if self.accepted_minimum > self.accepted_maximum:
            raise ValueError("accepted_minimum must not exceed accepted_maximum")
        if not self.chapters or len(set(self.chapters)) != len(self.chapters):
            raise ValueError("chapters must be non-empty and unique")
        return self


class ChapterState(BaseModel):
    """Durable progress for one chapter."""

    model_config = ConfigDict(extra="forbid")

    discovery_rounds: int = 0
    verified_candidate_urls: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    inspection_waves_completed: int = 0
    finalized: bool = False
    final_artifact: str | None = None


class PendingPhase(BaseModel):
    """One paid turn that may need artifact recovery after interruption."""

    model_config = ConfigDict(extra="forbid")

    phase_key: str
    turn_number: int
    artifact_path: str


class DeepSession(BaseModel):
    """Validated, resumable run state."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "deep-chapter-session-v1"
    ruler: str
    country: str
    iso3: str = Field(min_length=3, max_length=3)
    year: int = Field(ge=1, le=9999)
    researcher: str
    workflow: DeepWorkflowConfig
    thread_id: str | None = None
    completed_phases: tuple[str, ...] = ()
    pending: PendingPhase | None = None
    chapters: dict[str, ChapterState] = Field(default_factory=dict)


def load_workflow(path: Path) -> DeepWorkflowConfig:
    """Load and validate a deep-workflow JSON config."""

    return DeepWorkflowConfig.model_validate_json(path.read_text(encoding="utf-8"))


def load_session(path: Path) -> DeepSession | None:
    """Load a validated session when one exists."""

    if not path.exists():
        return None
    return DeepSession.model_validate_json(path.read_text(encoding="utf-8"))


def save_model(path: Path, model: BaseModel) -> None:
    """Atomically persist one Pydantic artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(pending, path)


__all__ = [
    "ChapterState",
    "DeepSession",
    "DeepWorkflowConfig",
    "PendingPhase",
    "load_session",
    "load_workflow",
    "save_model",
]
