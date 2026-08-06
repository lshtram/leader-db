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
    researcher_session_scope: Literal[
        "one_ruler_period", "segmented_ruler_period"
    ] = "one_ruler_period"
    chapter_session_mode: Literal[
        "persistent_thread", "fresh_compact_context"
    ] = "persistent_thread"
    researcher_receives_compact_briefing: Literal[True] = True
    complete_local_package_stays_parent_owned: Literal[True] = True
    researcher_direct_iterative_search: Literal[True] = True
    source_discovery_stage_enabled: bool = False
    chapter_research_turns_enabled: Literal[True] = True
    overview_candidate_document_target: int = Field(default=50, ge=20, le=100)
    chapter_candidate_document_target: int = Field(default=30, ge=10, le=60)
    chapter_opened_document_target: int = Field(default=12, ge=5, le=30)
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
    continuation_minimum_expected_new_units_per_selected_chapter: int = Field(
        default=2, ge=1
    )
    continuation_marginal_value_policy_enabled: Literal[True] = True
    supervisor_takeover_enabled: Literal[True] = True
    supervisor_takeover_after_research_attempts: int = Field(default=2, ge=1, le=3)

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
        expected_scope = (
            "segmented_ruler_period"
            if self.chapter_session_mode == "fresh_compact_context"
            else "one_ruler_period"
        )
        if self.researcher_session_scope != expected_scope:
            raise ValueError("researcher_session_scope must match chapter_session_mode")
        return self


def load_research_workflow(path: Path) -> ResearchWorkflow:
    """Load the checked-in direct-search research workflow."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ResearchWorkflow.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid research workflow YAML: {path}") from exc


__all__ = ["ResearchWorkflow", "load_research_workflow"]
