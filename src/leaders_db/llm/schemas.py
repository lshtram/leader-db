"""Pydantic schemas for the strict-JSON LLM contract (requirement §10).

Every LLM scoring call carries the same input shape and returns the same
output shape. The output is validated against :class:`LLMScoreOutput`
**before** it is persisted; a validation failure is logged and the item
is sent to the manual-review queue (the system never silently uses an
LLM response that fails schema validation).

REQ-LLM-002 enumerates the required input fields.
REQ-LLM-003 enumerates the required output fields.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------


class ScoreBand(str, Enum):
    """Confidence bands defined in requirement §11."""

    HIGH = "high"  # 85–100
    GOOD = "good"  # 70–84
    MEDIUM = "medium"  # 50–69
    LOW = "low"  # 30–49
    UNRELIABLE = "unreliable"  # 0–29


def band_for_confidence(confidence: int) -> ScoreBand:
    """Return the :class:`ScoreBand` for a 0–100 confidence value.

    Boundaries from requirement §11:
    85–100 high, 70–84 good, 50–69 medium, 30–49 low, 0–29 unreliable.
    """
    if not 0 <= confidence <= 100:
        raise ValueError(f"confidence must be 0..100, got {confidence}")
    if confidence >= 85:
        return ScoreBand.HIGH
    if confidence >= 70:
        return ScoreBand.GOOD
    if confidence >= 50:
        return ScoreBand.MEDIUM
    if confidence >= 30:
        return ScoreBand.LOW
    return ScoreBand.UNRELIABLE


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class EvidenceSnippet(BaseModel):
    """One evidence snippet passed to the LLM (REQ-LLM-002 caps at three)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=2000)
    source_label: str = Field(..., max_length=200)


class LLMScoreInput(BaseModel):
    """Required input for an LLM scoring call (REQ-LLM-002)."""

    model_config = ConfigDict(extra="forbid")

    country_iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str = Field(..., min_length=1, max_length=200)
    year: int = Field(..., ge=1900, le=2100)
    leader_candidate_name: str = Field(..., min_length=1, max_length=200)
    category_key: str = Field(..., min_length=1, max_length=100)
    rubric_description: str = Field(..., min_length=1, max_length=2000)
    structured_indicators: list[str] = Field(
        default_factory=list,
        description=(
            "Pre-extracted indicator values for the country/year/category. "
            "Strings, since we render heterogeneous numeric data into text."
        ),
    )
    client_score: Optional[int] = Field(default=None, ge=0, le=10)
    client_note: Optional[str] = Field(default=None, max_length=2000)
    evidence_snippets: list[EvidenceSnippet] = Field(
        default_factory=list,
        description="Up to three short text snippets from local sources.",
    )

    @field_validator("evidence_snippets")
    @classmethod
    def _cap_evidence(cls, v: list[EvidenceSnippet]) -> list[EvidenceSnippet]:
        if len(v) > 3:
            raise ValueError("evidence_snippets must contain at most 3 items (REQ-LLM-002)")
        return v


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class LLMScoreOutput(BaseModel):
    """Required output from an LLM scoring call (REQ-LLM-003).

    The model is strict — extra fields cause validation failure. This
    is intentional: it prevents the LLM from quietly inventing
    additional structure.
    """

    model_config = ConfigDict(extra="forbid")

    proposed_score: int = Field(..., ge=0, le=10)
    confidence: int = Field(..., ge=0, le=100)
    rationale: str = Field(..., min_length=1, max_length=2000)
    main_supporting_evidence: list[str] = Field(default_factory=list)
    main_contradicting_evidence: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    review_reason: str = Field(default="", max_length=2000)

    @field_validator("main_supporting_evidence", "main_contradicting_evidence")
    @classmethod
    def _limit_evidence(cls, v: list[str]) -> list[str]:
        # We keep this lenient on length but cap the count to discourage
        # unbounded dumps. The count cap is operational, not contractual.
        if len(v) > 20:
            raise ValueError("evidence list must contain at most 20 items")
        return [s[:1000] for s in v]

    def band(self) -> ScoreBand:
        """Return the :class:`ScoreBand` corresponding to ``self.confidence``."""
        return band_for_confidence(self.confidence)
