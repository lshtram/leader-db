"""Manifest schemas for straight-through chapter question phases."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChapterQuestionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["pass", "fail"]


class ChapterQuestionPhaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "diagnostic_chapter_question_writing_v1",
        "diagnostic_chapter_question_review_v1",
    ]
    production_status: Literal["diagnostic_only"] = "diagnostic_only"
    api_key_used: Literal[False] = False
    chapter_id: str
    profile: str
    model: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_analysis_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    writing_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    question_count: int = Field(ge=1)
    artifacts: tuple[ChapterQuestionArtifact, ...]
    phase_gate: Literal["pass", "fail"]

    @model_validator(mode="after")
    def validate_artifacts(self) -> ChapterQuestionPhaseManifest:
        ids = [item.question_id for item in self.artifacts]
        expected = [f"{self.chapter_id}.{number}" for number in range(1, 11)]
        if ids != expected or self.question_count != 10:
            raise ValueError("chapter phase must contain questions 1 through 10 once")
        expected_gate = (
            "pass" if all(item.status == "pass" for item in self.artifacts) else "fail"
        )
        if self.phase_gate != expected_gate:
            raise ValueError("chapter phase gate contradicts question statuses")
        return self


__all__ = ["ChapterQuestionArtifact", "ChapterQuestionPhaseManifest"]
