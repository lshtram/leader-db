"""Schema and mappings for local structured-prior artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PriorStatus = Literal["evidence_found", "no_evidence_found", "not_applicable", "error"]

CLIENT_MATRIX_SOURCE_SLUGS = frozenset({"client_existing", "vertical_slice_client_seed"})
LOCAL_PRIOR_METHOD_VERSION = "local_structured_prior_v1"

POLITICAL_FREEDOM_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "political_liberties",
    "civil_liberties",
    "electoral_democracy",
    "liberal_democracy",
    "suffrage",
    "rule_of_law",
    "freedom_expression",
    "freedom_association",
    "press_freedom_score",
    "press_freedom_rank",
    "voice_and_accountability",
    "wgi_rule_of_law",
    "accountability",
    "judicial_constraints",
    "legislative_constraints",
    "multiparty_institutions",
    "regime_type",
    "bti_democracy_status",
    "bti_status_index",
    "bti_governance_index",
)

OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "civil_liberties",
    "political_liberties",
    "freedom_expression",
    "freedom_association",
    "press_freedom_score",
    "press_freedom_rank",
    "voice_and_accountability",
    "rule_of_law",
    "wgi_rule_of_law",
    "accountability",
    "judicial_constraints",
    "legislative_constraints",
    "multiparty_institutions",
    "liberal_democracy",
    "electoral_democracy",
    "regime_type",
    "bti_democracy_status",
    "bti_status_index",
    "bti_governance_index",
)


@dataclass(frozen=True)
class LocalPriorMapping:
    """Config-like mapping from a manual methodology question to local fact keys."""

    methodology_ids: tuple[str, ...]
    field_keys: tuple[str, ...]
    mapping_note: str


LOCAL_PRIOR_MAPPINGS: tuple[LocalPriorMapping, ...] = (
    LocalPriorMapping(
        methodology_ids=("4B.1", "4B.2"),
        field_keys=POLITICAL_FREEDOM_PRIOR_FIELD_KEYS,
        mapping_note="Political-freedom D11 country-year facts usable as structured priors.",
    ),
    LocalPriorMapping(
        methodology_ids=("4B.3",),
        field_keys=OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D11 civil-liberties, expression, association, press/media, voice, "
            "accountability, and rule-of-law facts usable as structured priors for "
            "opposition/media/protest/civil-society tolerance."
        ),
    ),
)


class LeaderPriorMetadata(BaseModel):
    """Optional ruler metadata preserved for the research worker."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    leader_id: int | None = None
    period_label: str | None = None


class LocalPriorCountry(BaseModel):
    """Country identity for a local prior artifact."""

    model_config = ConfigDict(extra="forbid")

    iso3: str
    name: str | None = None


class LocalPriorPeriod(BaseModel):
    """Requested year or period for a local prior."""

    model_config = ConfigDict(extra="forbid")
    year: int | None = None
    start_year: int | None = None
    end_year: int | None = None

    @model_validator(mode="after")
    def _validate_period(self) -> LocalPriorPeriod:
        if self.year is not None and (self.start_year is not None or self.end_year is not None):
            raise ValueError("provide either year or start_year/end_year, not both")
        if self.year is None and (self.start_year is None or self.end_year is None):
            raise ValueError("provide either year or both start_year and end_year")
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.end_year < self.start_year
        ):
            raise ValueError("end_year must be greater than or equal to start_year")
        return self

    def years(self) -> tuple[int, ...]:
        """Return the requested years as a deterministic tuple."""

        if self.year is not None:
            return (self.year,)
        assert self.start_year is not None and self.end_year is not None
        return tuple(range(self.start_year, self.end_year + 1))


class LocalStructuredPriorRequest(BaseModel):
    """Request for a local structured-prior artifact."""

    model_config = ConfigDict(extra="forbid")
    methodology_id: str
    iso3: str
    period: LocalPriorPeriod
    leader: LeaderPriorMetadata = Field(default_factory=LeaderPriorMetadata)

    @model_validator(mode="after")
    def _normalize(self) -> LocalStructuredPriorRequest:
        self.iso3 = self.iso3.upper().strip()
        if not self.iso3:
            raise ValueError("iso3 must be non-empty")
        return self


class LocalPriorFact(BaseModel):
    """One selected local country-year fact exposed to a research worker."""

    model_config = ConfigDict(extra="forbid")
    year: int
    field_key: str
    label: str
    value: Any
    value_type: str
    source_slugs: list[str]
    source_observation_ids: list[str]
    confidence: int | None = None
    warnings: list[str] = Field(default_factory=list)


class LocalStructuredPriorArtifact(BaseModel):
    """Stable JSON artifact handed to internet/manual research workers."""

    model_config = ConfigDict(extra="forbid")
    methodology_id: str
    question_text: str
    category: str
    country: LocalPriorCountry
    period: LocalPriorPeriod
    leader: LeaderPriorMetadata
    status: PriorStatus
    local_facts: list[LocalPriorFact]
    missing_or_empty_reason: str | None = None
    recommended_research_instructions: list[str]
    client_matrix_policy: Literal["excluded_as_evidence"] = "excluded_as_evidence"
    method_version: str = LOCAL_PRIOR_METHOD_VERSION
    mapping_note: str | None = None


def mapping_for_methodology_id(methodology_id: str) -> LocalPriorMapping | None:
    for mapping in LOCAL_PRIOR_MAPPINGS:
        if methodology_id in mapping.methodology_ids:
            return mapping
    return None


__all__ = [
    "CLIENT_MATRIX_SOURCE_SLUGS",
    "LOCAL_PRIOR_MAPPINGS",
    "LOCAL_PRIOR_METHOD_VERSION",
    "OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS",
    "POLITICAL_FREEDOM_PRIOR_FIELD_KEYS",
    "LeaderPriorMetadata",
    "LocalPriorCountry",
    "LocalPriorFact",
    "LocalPriorMapping",
    "LocalPriorPeriod",
    "LocalStructuredPriorArtifact",
    "LocalStructuredPriorRequest",
    "PriorStatus",
    "mapping_for_methodology_id",
]
