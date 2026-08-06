"""Typed non-publication diagnostic judgment artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import EvidenceId, StrictModel


class DiagnosticJudgment(StrictModel):
    schema_version: Literal["diagnostic_judgment_v1"]
    arm: Literal["closed_book_funnel_packet", "reference_full_frozen_extracts"]
    score_1_to_10: float = Field(ge=1, le=10)
    decisive_evidence_ids: tuple[EvidenceId, ...]
    decisive_facts: tuple[str, ...]
    contrary_evidence: tuple[str, ...]
    attribution_assessment: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    reopening_requests: tuple[str, ...] = ()
    experimental_non_publication: Literal[True]


class DiagnosticComparison(StrictModel):
    schema_version: Literal["diagnostic_comparison_v1"]
    closed_book: DiagnosticJudgment
    reference: DiagnosticJudgment
    score_delta: float
    missing_decisive_facts: tuple[str, ...]
    missing_contrary_evidence: tuple[str, ...]
    material_attribution_regression: bool
    rationale_consistent: bool
    gate_passed: bool
    experimental_non_publication: Literal[True]

    @model_validator(mode="after")
    def validate_arms(self) -> DiagnosticComparison:
        if self.closed_book.arm != "closed_book_funnel_packet":
            raise ValueError("closed_book must contain the funnel-packet arm")
        if self.reference.arm != "reference_full_frozen_extracts":
            raise ValueError("reference must contain the frozen-extract arm")
        return self


__all__ = ["DiagnosticComparison", "DiagnosticJudgment"]
