"""Configuration for one direct-search ruler research session."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchWorkflow(BaseModel):
    """Bounded review loop around one chapter-sequential researcher session."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    chapter_order: tuple[str, ...]
    researcher_session_scope: Literal["one_ruler_period"] = "one_ruler_period"
    researcher_receives_complete_selected_guides: Literal[True] = True
    local_facts_before_internet: Literal[True] = True
    researcher_direct_iterative_search: Literal[True] = True
    research_stop_condition: Literal["reasonable_saturation_or_blocker"] = (
        "reasonable_saturation_or_blocker"
    )
    evidence_reviewer_checks_every_selected_chapter: Literal[True] = True
    review_continuation_session: Literal["same_researcher_thread"] = (
        "same_researcher_thread"
    )
    max_review_rounds: int = Field(default=3, ge=0, le=3)
    formatter_search_enabled: Literal[False] = False
    chapter_judge_search_enabled: Literal[False] = False
    score_order_audit_required: Literal[True] = True
    minimum_source_claim_units_per_chapter: int = Field(default=5, ge=1)
    normal_source_claim_units_per_chapter: int = Field(default=10, ge=1)
    maximum_source_claim_units_per_chapter: int = Field(default=20, ge=1)
    minimum_independent_source_families_per_chapter: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def _coherent(self) -> ResearchWorkflow:
        expected = tuple(f"{index}B" for index in range(1, 9))
        if self.chapter_order != expected:
            raise ValueError("chapter_order must contain 1B through 8B exactly once")
        if not (
            self.minimum_source_claim_units_per_chapter
            <= self.normal_source_claim_units_per_chapter
            <= self.maximum_source_claim_units_per_chapter
        ):
            raise ValueError("source-claim goals must be ordered")
        return self


def load_research_workflow(path: Path) -> ResearchWorkflow:
    """Load the checked-in direct-search research workflow."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ResearchWorkflow.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid research workflow YAML: {path}") from exc


__all__ = ["ResearchWorkflow", "load_research_workflow"]
