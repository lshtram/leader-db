"""Validated contracts for canonical research cost profiles."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StageRule(BaseModel):
    """One versioned mapping from an artifact path to a scientific stage."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    path_pattern: str = Field(min_length=1)
    selection_mode: Literal["all_completed", "selected_chapter_artifact"]


class StageRules(BaseModel):
    """Versioned stage-classification registry."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research_cost_stage_rules_v1"]
    event_filename: str = Field(min_length=1)
    rules: tuple[StageRule, ...] = Field(min_length=1)


__all__ = ["StageRule", "StageRules"]
