"""Schema and mappings for local structured-prior artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PriorStatus = Literal["evidence_found", "no_evidence_found", "not_applicable", "error"]

CLIENT_MATRIX_SOURCE_SLUGS = frozenset(
    {"client_existing", "client_matrix", "vertical_slice_client_seed"}
)
LOCAL_PRIOR_METHOD_VERSION = "local_structured_prior_v3"


def _chapter_methodology_ids(chapter: str) -> tuple[str, ...]:
    return tuple(f"{chapter}.{question}" for question in range(1, 11))


NUCLEAR_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "nuclear_total_inventory",
    "nuclear_military_stockpile",
    "nuclear_operational_strategic",
    "nuclear_operational_nonstrategic",
    "nuclear_reserve_nondeployed",
    "nuclear_deployed_warheads",
    "nuclear_retired_warheads",
)

INTERNATIONAL_PEACE_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "state_based_conflict_events",
    "state_based_conflict_fatalities",
    "internationalized_conflict_events",
    "internationalized_conflict_fatalities",
    "military_spend_constant_usd",
    "military_spend_per_capita",
    "military_spend_share_gdp",
    "military_spend_share_govt",
)

DOMESTIC_SAFETY_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "cirights_civil_political_rights",
    "cirights_disappearances",
    "cirights_killings",
    "cirights_physical_integrity",
    "cirights_political_imprisonment",
    "cirights_repression",
    "cirights_torture",
    "pts_amnesty_score",
    "pts_human_rights_watch_score",
    "pts_state_dept_score",
    "one_sided_violence_events",
    "one_sided_violence_fatalities",
    "physical_integrity",
    "private_civil_liberties",
    "extrajudicial_killings",
    "civil_society_repression",
)

POLITICAL_FREEDOM_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "eiu_democracy_overall_score",
    "eiu_electoral_process_pluralism",
    "eiu_functioning_government",
    "eiu_political_participation",
    "eiu_political_culture",
    "eiu_civil_liberties",
    "polity_composite_score",
    "polity_democracy_score",
    "polity_autocracy_score",
    "polity_executive_constraints",
    "polity_regime_durability",
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

ECONOMIC_WELLBEING_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    # Legacy aliases remain readable so preserved releases degrade gracefully.
    "gdp_per_capita",
    "gdp_total",
    "gdp_per_capita_nominal_current_usd",
    "gdp_per_capita_ppp_constant_2017_intl",
    "gdp_per_capita_ppp_constant_2011_intl",
    "gdp_per_capita_ppp_constant_2017_usd",
    "gdp_total_nominal_current_usd",
    "gdp_total_real_constant_2015_usd",
    "gdp_total_ppp_constant_2011_intl",
    "gdp_total_ppp_expenditure_constant_2017_usd",
    "gdp_total_ppp_output_constant_2017_usd",
    "gni_per_capita",
    "population",
    "pwt_employment",
    "pwt_average_annual_hours_worked",
    "pwt_human_capital_index",
    "pwt_real_consumption",
    "pwt_real_domestic_absorption",
    "pwt_capital_stock_index",
    "pwt_tfp_at_constant_national_prices",
    "bti_status_index",
)

SOCIAL_WELLBEING_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "hdi",
    "life_expectancy",
    "under5_mortality",
    "bcg_immunization",
    "dtp3_immunization",
    "hepb3_immunization",
    "expected_years_schooling",
    "mean_years_schooling",
    "gni_per_capita",
)

INTEGRITY_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "control_of_corruption",
    "corruption_index",
    "executive_corruption",
    "public_corruption",
    "cpi_score",
    "rule_of_law",
    "wgi_rule_of_law",
    "accountability",
)

EFFECTIVENESS_PRIOR_FIELD_KEYS: tuple[str, ...] = (
    "government_effectiveness",
    "regulatory_quality",
    "bti_governance_index",
    "accountability",
    "rule_of_law",
    "wgi_rule_of_law",
)


@dataclass(frozen=True)
class LocalPriorMapping:
    """Config-like mapping from a manual methodology question to local fact keys."""

    methodology_ids: tuple[str, ...]
    field_keys: tuple[str, ...]
    mapping_note: str


LOCAL_PRIOR_MAPPINGS: tuple[LocalPriorMapping, ...] = (
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("1B"),
        field_keys=NUCLEAR_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D17 FAS nuclear-force country-year facts provide capability context; "
            "absence of a row is not evidence of responsible ruler conduct."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("2B"),
        field_keys=INTERNATIONAL_PEACE_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D13-D14 UCDP conflict and SIPRI military-expenditure facts provide "
            "country-year exposure/context, not automatic ruler attribution."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("3B"),
        field_keys=DOMESTIC_SAFETY_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D12 CIRIGHTS, PTS, UCDP, and V-Dem safety/repression facts provide "
            "country-year baselines requiring narrative ruler attribution."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=tuple(item for item in _chapter_methodology_ids("4B") if item != "4B.3"),
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
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("5B"),
        field_keys=ECONOMIC_WELLBEING_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D5 economic level/scale and BTI status facts provide country-year context; "
            "they do not by themselves establish distribution, causation, or ruler credit."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("6B"),
        field_keys=SOCIAL_WELLBEING_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D6 HDI, health, education, and income facts provide welfare baselines; "
            "publication/source-year warnings and ruler attribution still apply."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("7B"),
        field_keys=INTEGRITY_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D15 corruption, accountability, and rule-of-law facts provide institutional "
            "context and must not be converted into personal-integrity claims without evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=_chapter_methodology_ids("8B"),
        field_keys=EFFECTIVENESS_PRIOR_FIELD_KEYS,
        mapping_note=(
            "D16 governance-capacity facts provide inherited/state-capacity context, not "
            "proof that the ruler selected goals or implemented them effectively."
        ),
    ),
)


class LeaderPriorMetadata(BaseModel):
    """Optional ruler metadata preserved for the research worker."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    leader_id: int | None = None
    period_label: str | None = None
    accession_year: int | None = None


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
    period_role: Literal["pre_accession", "tenure", "target"] = "target"
    unit: str | None = None
    scale: str | None = None
    uncertainty: dict[str, Any] | None = None


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
    "DOMESTIC_SAFETY_PRIOR_FIELD_KEYS",
    "ECONOMIC_WELLBEING_PRIOR_FIELD_KEYS",
    "EFFECTIVENESS_PRIOR_FIELD_KEYS",
    "INTEGRITY_PRIOR_FIELD_KEYS",
    "INTERNATIONAL_PEACE_PRIOR_FIELD_KEYS",
    "LOCAL_PRIOR_MAPPINGS",
    "LOCAL_PRIOR_METHOD_VERSION",
    "NUCLEAR_PRIOR_FIELD_KEYS",
    "OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS",
    "POLITICAL_FREEDOM_PRIOR_FIELD_KEYS",
    "SOCIAL_WELLBEING_PRIOR_FIELD_KEYS",
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
