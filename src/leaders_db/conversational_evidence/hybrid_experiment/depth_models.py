"""Validated scientific controls for deeper evidence discovery pilots."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SaturationPolicy(BaseModel):
    """Persistable breadth, composition, and stopping controls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_target_per_wave: int = Field(default=35, gt=0)
    opened_target_per_wave: int = Field(default=20, gt=0)
    accepted_url_min: int = Field(default=20, gt=0)
    accepted_url_max: int = Field(default=35, gt=0)
    domain_min: int = Field(default=10, gt=0)
    marginal_url_stop: int = Field(default=2, gt=0)
    max_waves: int = Field(default=4, gt=0, le=6)

    @model_validator(mode="after")
    def _coherent(self) -> SaturationPolicy:
        if self.accepted_url_min > self.accepted_url_max:
            raise ValueError("accepted_url_min may not exceed accepted_url_max")
        return self


__all__ = ["SaturationPolicy"]
