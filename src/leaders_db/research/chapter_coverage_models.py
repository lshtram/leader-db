"""Contracts for requirement-led chapter evidence repair."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .chapter_analysis_models import CorrectedLensAnswer


class CoverageRequirement(BaseModel):
    """One immutable correction requested by the independent reviewer."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    question_ids: tuple[str, ...]
    instruction: str


class RequirementMapping(BaseModel):
    """Evidence selected for one immutable correction requirement."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    question_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    rationale: str = Field(min_length=8)


class CoveragePlan(BaseModel):
    """Code-checked mapping from every correction to exact evidence."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    mappings: tuple[RequirementMapping, ...]


class RequirementDisposition(BaseModel):
    """How a repaired answer handled one reviewer requirement."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    action: Literal[
        "incorporated",
        "qualified",
        "already_covered",
        "out_of_scope",
        "unsupported_by_supplied_evidence",
    ]
    explanation: str = Field(min_length=8)


class RepairedLensAnswer(BaseModel):
    """Corrected answer plus a complete requirement disposition ledger."""

    model_config = ConfigDict(extra="forbid")

    answer: CorrectedLensAnswer
    dispositions: tuple[RequirementDisposition, ...]


class RoutedRequirementDisposition(BaseModel):
    """One final disposition bound to its requirement and target question."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    disposition: RequirementDisposition


def validate_routed_dispositions(
    expected_routes: set[tuple[str, str]],
    dispositions: tuple[RoutedRequirementDisposition, ...],
) -> None:
    """Require exactly one final disposition for every requirement/question route."""

    received_routes = {
        (item.disposition.requirement_id, item.question_id) for item in dispositions
    }
    if received_routes != expected_routes or len(dispositions) != len(expected_routes):
        raise ValueError("final disposition ledger does not reconcile with planned routes")


__all__ = [
    "CoveragePlan",
    "CoverageRequirement",
    "RepairedLensAnswer",
    "RequirementDisposition",
    "RequirementMapping",
    "RoutedRequirementDisposition",
    "validate_routed_dispositions",
]
