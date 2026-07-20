"""Validated configuration contract for hybrid research batches."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatchStage(BaseModel):
    """Concurrency enabled after a completed-ruler gate."""

    model_config = ConfigDict(extra="forbid")

    completed: int = Field(ge=0)
    workers: int = Field(ge=1, le=10)


class BatchCase(BaseModel):
    """One reviewed and locked ruler-year identity."""

    model_config = ConfigDict(extra="forbid")

    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    country: str = Field(min_length=1)
    ruler: str = Field(min_length=1)
    identity_status: Literal["reviewed_locked"]
    identity_rationale: str = Field(min_length=1)


class BatchManifest(BaseModel):
    """Complete scientific and operational inputs for one batch."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["hybrid_experiment_batch_v1"]
    batch_id: str = Field(min_length=1)
    year: int = Field(ge=1800, le=2100)
    researcher: str = Field(min_length=1)
    per_ruler_cost_ceiling_usd: float = Field(gt=0)
    batch_cost_ceiling_usd: float = Field(gt=0)
    maximum_failures_per_case: int = Field(ge=0, le=3)
    stages: tuple[BatchStage, ...] = Field(min_length=1)
    cases: tuple[BatchCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> BatchManifest:
        iso3s = [item.iso3 for item in self.cases]
        if len(iso3s) != len(set(iso3s)):
            raise ValueError("batch cases must have unique ISO3 codes")
        thresholds = [item.completed for item in self.stages]
        if thresholds != sorted(thresholds) or thresholds[0] != 0:
            raise ValueError("batch stages must start at zero and be sorted")
        required = self.per_ruler_cost_ceiling_usd * len(self.cases)
        if self.batch_cost_ceiling_usd > required:
            raise ValueError("batch ceiling may not exceed all per-ruler ceilings")
        return self


__all__ = ["BatchCase", "BatchManifest", "BatchStage"]
