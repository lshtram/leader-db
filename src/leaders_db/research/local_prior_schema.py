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
    "wdi_gini_index",
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
    "wdi_gini_index",
    "wdi_literacy_rate_adult",
    "wdi_secondary_school_enrollment",
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


def _local_fields(*field_keys: str) -> tuple[str, ...]:
    """Declare an ordered, lens-specific local evidence selection."""
    return field_keys


ECONOMIC_LEVEL_FIELDS = _local_fields(
    "gdp_per_capita",
    "gdp_per_capita_nominal_current_usd",
    "gdp_per_capita_ppp_constant_2017_intl",
    "gdp_per_capita_ppp_constant_2011_intl",
    "gdp_per_capita_ppp_constant_2017_usd",
    "gni_per_capita",
    "pwt_real_consumption",
    "pwt_employment",
    "wdi_gini_index",
)
ECONOMIC_STABILITY_FIELDS = _local_fields(
    "gdp_total_real_constant_2015_usd",
    "gdp_total_ppp_constant_2011_intl",
    "gdp_total_ppp_expenditure_constant_2017_usd",
    "gdp_total_ppp_output_constant_2017_usd",
    "pwt_tfp_at_constant_national_prices",
)
ECONOMIC_PRODUCTIVITY_FIELDS = _local_fields(
    "pwt_human_capital_index",
    "pwt_capital_stock_index",
    "pwt_tfp_at_constant_national_prices",
    "pwt_average_annual_hours_worked",
)
ECONOMIC_DISTRIBUTION_FIELDS = _local_fields(
    "gdp_per_capita_nominal_current_usd",
    "gdp_per_capita_ppp_constant_2017_intl",
    "gni_per_capita",
    "wdi_gini_index",
)

SOCIAL_OUTCOME_FIELDS = _local_fields(
    "hdi",
    "life_expectancy",
    "under5_mortality",
    "expected_years_schooling",
    "mean_years_schooling",
    "gni_per_capita",
)
SOCIAL_ACCESS_FIELDS = _local_fields(
    "life_expectancy",
    "under5_mortality",
    "bcg_immunization",
    "dtp3_immunization",
    "hepb3_immunization",
    "expected_years_schooling",
    "mean_years_schooling",
    "wdi_literacy_rate_adult",
    "wdi_secondary_school_enrollment",
)
SOCIAL_DISTRIBUTION_FIELDS = _local_fields(
    "wdi_gini_index",
    "gni_per_capita",
    "wdi_literacy_rate_adult",
    "wdi_secondary_school_enrollment",
)

POLITICAL_ELECTION_FIELDS = _local_fields(
    "eiu_democracy_overall_score",
    "eiu_electoral_process_pluralism",
    "polity_composite_score",
    "polity_democracy_score",
    "polity_autocracy_score",
    "political_liberties",
    "civil_liberties",
    "electoral_democracy",
    "suffrage",
    "multiparty_institutions",
    "regime_type",
    "bti_democracy_status",
)
POLITICAL_CONSTRAINT_FIELDS = _local_fields(
    "eiu_functioning_government",
    "polity_executive_constraints",
    "rule_of_law",
    "wgi_rule_of_law",
    "accountability",
    "judicial_constraints",
    "legislative_constraints",
)
POLITICAL_MEDIA_FIELDS = _local_fields(
    "eiu_civil_liberties",
    "civil_liberties",
    "freedom_expression",
    "press_freedom_score",
    "press_freedom_rank",
    "voice_and_accountability",
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
        methodology_ids=("4B.1", "4B.2"),
        field_keys=POLITICAL_ELECTION_FIELDS,
        mapping_note=(
            "Election and regime measures contextualize contestability; they do not "
            "establish ruler intent or a specific manipulation."
        ),
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
        methodology_ids=("4B.4",),
        field_keys=POLITICAL_CONSTRAINT_FIELDS,
        mapping_note=(
            "Constraint and rule-of-law measures contextualize institutional independence; "
            "ruler-specific strengthening or interference still needs narrative evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("4B.5",),
        field_keys=(
            "regime_type",
            "multiparty_institutions",
            "accountability",
            "polity_regime_durability",
        ),
        mapping_note=(
            "Regime and party-system measures are context, not direct proof of personality "
            "cult, loyalty tests, intimidation, or state politicization."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("4B.6", "4B.9"),
        field_keys=POLITICAL_MEDIA_FIELDS,
        mapping_note=(
            "Media, expression, and voice measures contextualize information controls; "
            "specific censorship, propaganda, surveillance, or harassment needs evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("4B.7",),
        field_keys=(
            "suffrage",
            "political_liberties",
            "civil_liberties",
            "freedom_association",
            "eiu_political_participation",
        ),
        mapping_note=(
            "National participation and liberty averages require group-specific evidence "
            "before supporting political-equality claims."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("4B.8",),
        field_keys=(
            "polity_composite_score",
            "polity_regime_durability",
            "electoral_democracy",
            "multiparty_institutions",
            "regime_type",
        ),
        mapping_note=(
            "Regime trajectory contextualizes succession but cannot establish compliance "
            "with term limits, coalition promises, or constitutional transfer."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("4B.10",),
        field_keys=POLITICAL_FREEDOM_PRIOR_FIELD_KEYS,
        mapping_note=(
            "The full longitudinal political-freedom bundle supports inherited-versus-left "
            "trajectory analysis without automatic ruler attribution."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.1",),
        field_keys=ECONOMIC_LEVEL_FIELDS,
        mapping_note=(
            "Broad prosperity outcomes are context; intent and ruler action need "
            "narrative evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.2",),
        field_keys=(),
        mapping_note=(
            "No structured country outcome establishes the competence or independence "
            "of appointees."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.3", "5B.9"),
        field_keys=ECONOMIC_STABILITY_FIELDS,
        mapping_note=(
            "Real-output and productivity trajectories contextualize stability or "
            "shocks but do not prove policy competence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.4",),
        field_keys=("pwt_employment", "pwt_real_domestic_absorption"),
        mapping_note=(
            "Employment count and absorption are outcome context, not direct evidence "
            "of fair market rules."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.5",),
        field_keys=("wdi_gini_index",),
        mapping_note=(
            "National inequality is context only and cannot establish corruption, "
            "capture, or personal nexus."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.6",),
        field_keys=ECONOMIC_PRODUCTIVITY_FIELDS,
        mapping_note=(
            "Human-capital, capital-stock, hours, and TFP trends contextualize "
            "productivity foundations."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.7",),
        field_keys=(),
        mapping_note=(
            "Country outcomes cannot establish evidence-based decision-making or "
            "correction of mistakes."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.8",),
        field_keys=ECONOMIC_DISTRIBUTION_FIELDS,
        mapping_note=(
            "Average income and Gini provide distribution context but do not identify "
            "favored groups or ruler intent."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("5B.10",),
        field_keys=ECONOMIC_WELLBEING_PRIOR_FIELD_KEYS,
        mapping_note=(
            "Full longitudinal context supports inherited-versus-left trajectory "
            "analysis without automatic ruler credit."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.1",),
        field_keys=SOCIAL_OUTCOME_FIELDS,
        mapping_note=(
            "Aggregate welfare outcomes contextualize priority but cannot establish "
            "purpose or propaganda intent."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.2",),
        field_keys=SOCIAL_ACCESS_FIELDS,
        mapping_note=(
            "Health and education coverage/outcomes inform access; they do not alone "
            "establish affordability or quality."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.3", "6B.8"),
        field_keys=SOCIAL_DISTRIBUTION_FIELDS,
        mapping_note=(
            "National distribution and participation measures require group and "
            "regional evidence for equity claims."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.4", "6B.5"),
        field_keys=SOCIAL_ACCESS_FIELDS,
        mapping_note=(
            "Service outcomes are implementation context; professional management "
            "and correction require narrative evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.6",),
        field_keys=("life_expectancy", "under5_mortality", "hdi"),
        mapping_note=(
            "Outcome changes contextualize crises but require shock-specific timing "
            "and ruler-attributed response evidence."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.7",),
        field_keys=(),
        mapping_note=(
            "Aggregate service data cannot establish political conditionality, "
            "loyalty rewards, or punishment."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.9",),
        field_keys=SOCIAL_ACCESS_FIELDS,
        mapping_note=(
            "Sustained service series contextualize durability but do not establish "
            "institutional survival beyond the ruler."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("6B.10",),
        field_keys=SOCIAL_WELLBEING_PRIOR_FIELD_KEYS,
        mapping_note=(
            "Full longitudinal welfare context supports inherited-versus-left "
            "life-chance analysis without automatic attribution."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("7B.1", "7B.2", "7B.3", "7B.4", "7B.5", "7B.8", "7B.9"),
        field_keys=(),
        mapping_note=(
            "National corruption or governance indicators cannot establish ruler-specific "
            "truthfulness, interests, benefit, appointments, promises, or favoritism."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("7B.6", "7B.7", "7B.10"),
        field_keys=INTEGRITY_PRIOR_FIELD_KEYS,
        mapping_note=(
            "Institutional corruption, accountability, and rule-of-law facts are context "
            "for scrutiny or concealment only; scoring requires a direct personal nexus."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("8B.1", "8B.8"),
        field_keys=(),
        mapping_note=(
            "Generic capacity indicators cannot identify the ruler's program or establish "
            "adaptation and correction."
        ),
    ),
    LocalPriorMapping(
        methodology_ids=("8B.2", "8B.3", "8B.4", "8B.5", "8B.6", "8B.7", "8B.9", "8B.10"),
        field_keys=EFFECTIVENESS_PRIOR_FIELD_KEYS,
        mapping_note=(
            "Governance-capacity facts provide inherited implementation context only; "
            "program ownership, action, goal fit, and ruler attribution remain required."
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
