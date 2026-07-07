"""Static catalog data: stable concept keys, indicator codes, descriptors, and mappings.

This module owns the immutable registry of concept metadata. It
exposes:

- Stable concept key constants (``CONCEPT_GDP_PER_CAPITA`` etc.).
- Source-slug constants (``WDI_SOURCE_KEY`` etc.) re-used by the
  caller-facing helpers.
- The :data:`KNOWN_CONCEPT_KEYS` ordered tuple used by
  :func:`leaders_db.sources.concepts.list_concepts`.
- The :func:`build_concept_descriptors` /
  :func:`build_concept_mappings` factories that produce the canonical
  descriptor / mapping lists. The lists are immutable tuples so
  downstream code can rely on iteration order across runs.

The catalog covers the three migrated sources (WDI, Maddison, PWT)
for the three stable concepts (gdp_per_capita, population,
gdp_total). Future slices may add more sources per concept; this
module is the single point of registration. Indicator code strings
mirror the canonical source catalogs:

- ``src/leaders_db/ingest/catalogs/wdi.csv``
- ``src/leaders_db/ingest/catalogs/maddison_project.csv``
- ``src/leaders_db/ingest/sources/pwt/catalog.csv``
"""

from __future__ import annotations

from ..contracts import SourceId
from ._dataclasses import ConceptDescriptor, ConceptMapping

# ---------------------------------------------------------------------------
# Stable concept keys
# ---------------------------------------------------------------------------

CONCEPT_GDP_PER_CAPITA: str = "gdp_per_capita"
CONCEPT_POPULATION: str = "population"
CONCEPT_GDP_TOTAL: str = "gdp_total"
CONCEPT_HDI: str = "hdi"
CONCEPT_LIFE_EXPECTANCY: str = "life_expectancy"
CONCEPT_GNI_PER_CAPITA: str = "gni_per_capita"
CONCEPT_EXPECTED_YEARS_SCHOOLING: str = "expected_years_schooling"
CONCEPT_MEAN_YEARS_SCHOOLING: str = "mean_years_schooling"
CONCEPT_UNDER5_MORTALITY: str = "under5_mortality"
CONCEPT_BCG_IMMUNIZATION: str = "bcg_immunization"
CONCEPT_DTP3_IMMUNIZATION: str = "dtp3_immunization"
CONCEPT_HEPB3_IMMUNIZATION: str = "hepb3_immunization"
CONCEPT_ELECTORAL_DEMOCRACY: str = "electoral_democracy"
CONCEPT_LIBERAL_DEMOCRACY: str = "liberal_democracy"
CONCEPT_CIVIL_LIBERTIES: str = "civil_liberties"
CONCEPT_SUFFRAGE: str = "suffrage"
CONCEPT_RULE_OF_LAW: str = "rule_of_law"
CONCEPT_FREEDOM_EXPRESSION: str = "freedom_expression"
CONCEPT_FREEDOM_ASSOCIATION: str = "freedom_association"
CONCEPT_PRESS_FREEDOM_SCORE: str = "press_freedom_score"
CONCEPT_PRESS_FREEDOM_RANK: str = "press_freedom_rank"
CONCEPT_PHYSICAL_INTEGRITY: str = "physical_integrity"
CONCEPT_POLITICAL_LIBERTIES: str = "political_liberties"
CONCEPT_PRIVATE_CIVIL_LIBERTIES: str = "private_civil_liberties"
CONCEPT_CIVIL_SOCIETY_REPRESSION: str = "civil_society_repression"
CONCEPT_EXTRAJUDICIAL_KILLINGS: str = "extrajudicial_killings"
CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY: str = "cirights_physical_integrity"
CONCEPT_CIRIGHTS_TORTURE: str = "cirights_torture"
CONCEPT_CIRIGHTS_DISAPPEARANCES: str = "cirights_disappearances"
CONCEPT_CIRIGHTS_KILLINGS: str = "cirights_killings"
CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT: str = "cirights_political_imprisonment"
CONCEPT_CIRIGHTS_REPRESSION: str = "cirights_repression"
CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS: str = "cirights_civil_political_rights"
CONCEPT_PTS_AMNESTY_SCORE: str = "pts_amnesty_score"
CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE: str = "pts_human_rights_watch_score"
CONCEPT_PTS_STATE_DEPT_SCORE: str = "pts_state_dept_score"
CONCEPT_STATE_BASED_CONFLICT_EVENTS: str = "state_based_conflict_events"
CONCEPT_STATE_BASED_CONFLICT_FATALITIES: str = "state_based_conflict_fatalities"
CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS: str = "internationalized_conflict_events"
CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES: str = "internationalized_conflict_fatalities"
CONCEPT_ONE_SIDED_VIOLENCE_EVENTS: str = "one_sided_violence_events"
CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES: str = "one_sided_violence_fatalities"
CONCEPT_CORRUPTION_INDEX: str = "corruption_index"
CONCEPT_CPI_SCORE: str = "cpi_score"
CONCEPT_CONTROL_OF_CORRUPTION: str = "control_of_corruption"
CONCEPT_EXECUTIVE_CORRUPTION: str = "executive_corruption"
CONCEPT_PUBLIC_CORRUPTION: str = "public_corruption"
CONCEPT_ACCOUNTABILITY: str = "accountability"
CONCEPT_VOICE_AND_ACCOUNTABILITY: str = "voice_and_accountability"
CONCEPT_WGI_RULE_OF_LAW: str = "wgi_rule_of_law"
CONCEPT_GOVERNMENT_EFFECTIVENESS: str = "government_effectiveness"
CONCEPT_REGULATORY_QUALITY: str = "regulatory_quality"
CONCEPT_BTI_GOVERNANCE_INDEX: str = "bti_governance_index"
CONCEPT_BTI_STATUS_INDEX: str = "bti_status_index"
CONCEPT_BTI_DEMOCRACY_STATUS: str = "bti_democracy_status"
CONCEPT_JUDICIAL_CONSTRAINTS: str = "judicial_constraints"
CONCEPT_LEGISLATIVE_CONSTRAINTS: str = "legislative_constraints"
CONCEPT_MULTIPARTY_INSTITUTIONS: str = "multiparty_institutions"
CONCEPT_REGIME_TYPE: str = "regime_type"
CONCEPT_NUCLEAR_TOTAL_INVENTORY: str = "nuclear_total_inventory"
CONCEPT_NUCLEAR_MILITARY_STOCKPILE: str = "nuclear_military_stockpile"
CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC: str = "nuclear_operational_strategic"
CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC: str = "nuclear_operational_nonstrategic"
CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED: str = "nuclear_reserve_nondeployed"
CONCEPT_MILITARY_SPEND_CONSTANT_USD: str = "military_spend_constant_usd"
CONCEPT_MILITARY_SPEND_PER_CAPITA: str = "military_spend_per_capita"
CONCEPT_MILITARY_SPEND_SHARE_GDP: str = "military_spend_share_gdp"
CONCEPT_MILITARY_SPEND_SHARE_GOVT: str = "military_spend_share_govt"

# Canonical ordered list of stable concept keys. The order is the
# canonical iteration order for ``list_concepts()``; downstream code
# that needs a deterministic sequence relies on this order.
KNOWN_CONCEPT_KEYS: tuple[str, ...] = (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_POPULATION,
    CONCEPT_GDP_TOTAL,
    CONCEPT_HDI,
    CONCEPT_LIFE_EXPECTANCY,
    CONCEPT_GNI_PER_CAPITA,
    CONCEPT_EXPECTED_YEARS_SCHOOLING,
    CONCEPT_MEAN_YEARS_SCHOOLING,
    CONCEPT_UNDER5_MORTALITY,
    CONCEPT_BCG_IMMUNIZATION,
    CONCEPT_DTP3_IMMUNIZATION,
    CONCEPT_HEPB3_IMMUNIZATION,
    CONCEPT_ELECTORAL_DEMOCRACY,
    CONCEPT_LIBERAL_DEMOCRACY,
    CONCEPT_CIVIL_LIBERTIES,
    CONCEPT_SUFFRAGE,
    CONCEPT_RULE_OF_LAW,
    CONCEPT_FREEDOM_EXPRESSION,
    CONCEPT_FREEDOM_ASSOCIATION,
    CONCEPT_PRESS_FREEDOM_SCORE,
    CONCEPT_PRESS_FREEDOM_RANK,
    CONCEPT_PHYSICAL_INTEGRITY,
    CONCEPT_POLITICAL_LIBERTIES,
    CONCEPT_PRIVATE_CIVIL_LIBERTIES,
    CONCEPT_CIVIL_SOCIETY_REPRESSION,
    CONCEPT_EXTRAJUDICIAL_KILLINGS,
    CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
    CONCEPT_CIRIGHTS_TORTURE,
    CONCEPT_CIRIGHTS_DISAPPEARANCES,
    CONCEPT_CIRIGHTS_KILLINGS,
    CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT,
    CONCEPT_CIRIGHTS_REPRESSION,
    CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS,
    CONCEPT_PTS_AMNESTY_SCORE,
    CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE,
    CONCEPT_PTS_STATE_DEPT_SCORE,
    CONCEPT_STATE_BASED_CONFLICT_EVENTS,
    CONCEPT_STATE_BASED_CONFLICT_FATALITIES,
    CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS,
    CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES,
    CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
    CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
    CONCEPT_CORRUPTION_INDEX,
    CONCEPT_CPI_SCORE,
    CONCEPT_CONTROL_OF_CORRUPTION,
    CONCEPT_EXECUTIVE_CORRUPTION,
    CONCEPT_PUBLIC_CORRUPTION,
    CONCEPT_ACCOUNTABILITY,
    CONCEPT_VOICE_AND_ACCOUNTABILITY,
    CONCEPT_WGI_RULE_OF_LAW,
    CONCEPT_GOVERNMENT_EFFECTIVENESS,
    CONCEPT_REGULATORY_QUALITY,
    CONCEPT_BTI_GOVERNANCE_INDEX,
    CONCEPT_BTI_STATUS_INDEX,
    CONCEPT_BTI_DEMOCRACY_STATUS,
    CONCEPT_JUDICIAL_CONSTRAINTS,
    CONCEPT_LEGISLATIVE_CONSTRAINTS,
    CONCEPT_MULTIPARTY_INSTITUTIONS,
    CONCEPT_REGIME_TYPE,
    CONCEPT_NUCLEAR_TOTAL_INVENTORY,
    CONCEPT_NUCLEAR_MILITARY_STOCKPILE,
    CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC,
    CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC,
    CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED,
    CONCEPT_MILITARY_SPEND_CONSTANT_USD,
    CONCEPT_MILITARY_SPEND_PER_CAPITA,
    CONCEPT_MILITARY_SPEND_SHARE_GDP,
    CONCEPT_MILITARY_SPEND_SHARE_GOVT,
)


# ---------------------------------------------------------------------------
# Source-slug constants
# ---------------------------------------------------------------------------

WDI_SOURCE_KEY: str = "world_bank_wdi"
MADDISON_PROJECT_SOURCE_KEY: str = "maddison_project"
PWT_SOURCE_KEY: str = "pwt"
UNDP_HDI_SOURCE_KEY: str = "undp_hdi"
WHO_GHO_API_SOURCE_KEY: str = "who_gho_api"
VDEM_SOURCE_KEY: str = "vdem"
RSF_PRESS_FREEDOM_SOURCE_KEY: str = "rsf_press_freedom"
FREEDOM_HOUSE_SOURCE_KEY: str = "freedom_house"
UCDP_SOURCE_KEY: str = "ucdp"
FAS_SOURCE_KEY: str = "fas"
WGI_SOURCE_KEY: str = "world_bank_wgi"
TRANSPARENCY_CPI_SOURCE_KEY: str = "transparency_cpi"
BTI_SOURCE_KEY: str = "bti"
CIRIGHTS_SOURCE_KEY: str = "cirights"
CLIENT_EXISTING_SOURCE_KEY: str = "client_existing"


# ---------------------------------------------------------------------------
# Indicator-code constants
# ---------------------------------------------------------------------------

# WDI catalog (src/leaders_db/ingest/catalogs/wdi.csv).
WDI_GDP_PER_CAPITA_INDICATOR_CODE: str = "wdi_gdp_per_capita"
WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE: str = "wdi_gdp_per_capita_ppp_constant_2017"
WDI_POPULATION_INDICATOR_CODE: str = "wdi_population"
WDI_GDP_CURRENT_USD_INDICATOR_CODE: str = "wdi_gdp_current_usd"
WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE: str = "wdi_gdp_constant_2015_usd"

# Maddison catalog (src/leaders_db/ingest/catalogs/maddison_project.csv).
MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE: str = "maddison_project_gdp_per_capita_2011_intl"
MADDISON_PROJECT_POPULATION_INDICATOR_CODE: str = "maddison_project_population_thousands"
# The Maddison total real GDP indicator is already a derived
# value (gdppc * pop * 1000) computed by the Stage 2 reader;
# the concept catalog treats it as a direct mapping.
MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE: str = (
    "maddison_project_gdp_total_2011_intl_derived"
)

# PWT catalog (src/leaders_db/ingest/sources/pwt/catalog.csv).
PWT_POPULATION_INDICATOR_CODE: str = "pwt_population"
PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE: str = "pwt_real_gdp_output_side"
PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE: str = "pwt_real_gdp_expenditure_side"

# Derived-recipe key (stable string) for the PWT
# ``gdp_per_capita = real_gdp_output_side / population`` recipe.
PWT_GDP_PER_CAPITA_RECIPE_KEY: str = "pwt_gdp_per_capita_via_rgdpo_over_pop"

# UNDP HDI clean adapter.
UNDP_HDI_INDICATOR_CODE: str = "undp_hdi_hdi"
UNDP_HDI_LIFE_EXPECTANCY_INDICATOR_CODE: str = "undp_hdi_life_expectancy"
UNDP_HDI_GNI_PER_CAPITA_INDICATOR_CODE: str = "undp_hdi_gni_per_capita"
UNDP_HDI_EXPECTED_YEARS_SCHOOLING_INDICATOR_CODE: str = "undp_hdi_expected_years_schooling"
UNDP_HDI_MEAN_YEARS_SCHOOLING_INDICATOR_CODE: str = "undp_hdi_mean_years_schooling"

# WHO GHO API clean adapter.
WHO_GHO_UNDER5_MORTALITY_INDICATOR_CODE: str = "who_gho_under5_mortality"
WHO_GHO_BCG_IMMUNIZATION_INDICATOR_CODE: str = "who_gho_bcg_immunization"
WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE: str = "who_gho_dtp3_immunization"
WHO_GHO_HEPB3_IMMUNIZATION_INDICATOR_CODE: str = "who_gho_hepb3_immunization"

# V-Dem political freedom indicators.
VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE: str = "vdem_v2x_polyarchy"
VDEM_LIBERAL_DEMOCRACY_INDICATOR_CODE: str = "vdem_v2x_libdem"
VDEM_CIVIL_LIBERTIES_INDICATOR_CODE: str = "vdem_v2x_civlib"
VDEM_SUFFRAGE_INDICATOR_CODE: str = "vdem_v2x_suffr"
VDEM_RULE_OF_LAW_INDICATOR_CODE: str = "vdem_v2x_rule"
VDEM_FREEDOM_EXPRESSION_INDICATOR_CODE: str = "vdem_v2x_freexp"
VDEM_FREEDOM_ASSOCIATION_INDICATOR_CODE: str = "vdem_v2x_frassoc_thick"
VDEM_PHYSICAL_INTEGRITY_INDICATOR_CODE: str = "vdem_v2x_clphy"
VDEM_POLITICAL_LIBERTIES_INDICATOR_CODE: str = "vdem_v2x_clpol"
VDEM_PRIVATE_CIVIL_LIBERTIES_INDICATOR_CODE: str = "vdem_v2x_clpriv"
VDEM_CIVIL_SOCIETY_REPRESSION_INDICATOR_CODE: str = "vdem_v2csreprss"
VDEM_EXTRAJUDICIAL_KILLINGS_INDICATOR_CODE: str = "vdem_v2clkill"
VDEM_CORRUPTION_INDEX_INDICATOR_CODE: str = "vdem_v2x_corr"
VDEM_EXECUTIVE_CORRUPTION_INDICATOR_CODE: str = "vdem_v2x_execorr"
VDEM_PUBLIC_CORRUPTION_INDICATOR_CODE: str = "vdem_v2x_pubcorr"
VDEM_ACCOUNTABILITY_INDICATOR_CODE: str = "vdem_v2x_accountability"
VDEM_JUDICIAL_CONSTRAINTS_INDICATOR_CODE: str = "vdem_v2x_jucon"
VDEM_LEGISLATIVE_CONSTRAINTS_INDICATOR_CODE: str = "vdem_v2xlg_legcon"
VDEM_MULTIPARTY_INSTITUTIONS_INDICATOR_CODE: str = "vdem_v2x_mpi"
VDEM_REGIME_TYPE_INDICATOR_CODE: str = "vdem_v2x_regime"

# World Bank Worldwide Governance Indicators.
WGI_VOICE_AND_ACCOUNTABILITY_INDICATOR_CODE: str = "wgi_voice_and_accountability"
WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE: str = "wgi_government_effectiveness"
WGI_REGULATORY_QUALITY_INDICATOR_CODE: str = "wgi_regulatory_quality"
WGI_RULE_OF_LAW_INDICATOR_CODE: str = "wgi_rule_of_law"
WGI_CONTROL_OF_CORRUPTION_INDICATOR_CODE: str = "wgi_control_of_corruption"

# Transparency International CPI.
TRANSPARENCY_CPI_SCORE_INDICATOR_CODE: str = "cpi_score"

# CIRIGHTS physical-integrity / rights indicators.
CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE: str = "cirights_physint"
CIRIGHTS_TORTURE_INDICATOR_CODE: str = "cirights_tort"
CIRIGHTS_DISAPPEARANCES_INDICATOR_CODE: str = "cirights_disap"
CIRIGHTS_KILLINGS_INDICATOR_CODE: str = "cirights_kill"
CIRIGHTS_POLITICAL_IMPRISONMENT_INDICATOR_CODE: str = "cirights_polpris"
CIRIGHTS_REPRESSION_INDICATOR_CODE: str = "cirights_repression"
CIRIGHTS_CIVIL_POLITICAL_RIGHTS_INDICATOR_CODE: str = "cirights_civpol"

# Political Terror Scale indicators.
PTS_SOURCE_KEY: str = "pts"
PTS_AMNESTY_SCORE_INDICATOR_CODE: str = "pts_amnesty_score"
PTS_HUMAN_RIGHTS_WATCH_SCORE_INDICATOR_CODE: str = "pts_human_rights_watch_score"
PTS_STATE_DEPT_SCORE_INDICATOR_CODE: str = "pts_state_dept_score"

# Bertelsmann Transformation Index.
BTI_GOVERNANCE_INDEX_INDICATOR_CODE: str = "bti_governance_index"
BTI_STATUS_INDEX_INDICATOR_CODE: str = "bti_status_index"
BTI_DEMOCRACY_STATUS_INDICATOR_CODE: str = "bti_democracy_status"

# UCDP conflict and domestic one-sided violence indicators.
UCDP_STATE_BASED_EVENTS_INDICATOR_CODE: str = "ucdp_state_based_events"
UCDP_STATE_BASED_FATALITIES_INDICATOR_CODE: str = "ucdp_state_based_fatalities"
UCDP_INTL_EVENTS_INDICATOR_CODE: str = "ucdp_intl_events"
UCDP_INTL_FATALITIES_INDICATOR_CODE: str = "ucdp_intl_fatalities"
UCDP_ONE_SIDED_EVENTS_INDICATOR_CODE: str = "ucdp_onesided_events"
UCDP_ONE_SIDED_FATALITIES_INDICATOR_CODE: str = "ucdp_onesided_fatalities"

# RSF press freedom indicators.
RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE: str = "rsf_press_freedom_score"
RSF_PRESS_FREEDOM_RANK_INDICATOR_CODE: str = "rsf_press_freedom_rank"

# Freedom House Freedom in the World indicators.
FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE: str = (
    "freedom_house_political_rights"
)
FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE: str = (
    "freedom_house_civil_liberties"
)

# FAS nuclear notebook status table indicators.
FAS_TOTAL_INVENTORY_INDICATOR_CODE: str = "fas_total_inventory"
FAS_MILITARY_STOCKPILE_INDICATOR_CODE: str = "fas_military_stockpile"
FAS_OPERATIONAL_STRATEGIC_INDICATOR_CODE: str = "fas_operational_strategic"
FAS_OPERATIONAL_NONSTRATEGIC_INDICATOR_CODE: str = "fas_operational_nonstrategic"
FAS_RESERVE_NONDEPLOYED_INDICATOR_CODE: str = "fas_reserve_nondeployed"

# SIPRI Military Expenditure Database indicators.
SIPRI_MILEX_SOURCE_KEY: str = "sipri_milex"
SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE: str = "sipri_milex_constant_usd"
SIPRI_MILEX_PER_CAPITA_INDICATOR_CODE: str = "sipri_milex_per_capita"
SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE: str = "sipri_milex_share_of_gdp"
SIPRI_MILEX_SHARE_GOVT_INDICATOR_CODE: str = "sipri_milex_share_of_govt_spending"

# Quality-flag string surfaced on every derived ConceptObservation.
DERIVED_CONCEPT_QUALITY_FLAG: str = "derived_concept"

# Warning codes surfaced by ``extract_concept_result`` when a derivation
# cannot produce a value for a scope. The codes mirror SRC-CONCEPT-009
# and the per-scope failure modes the catalog handles. The "missing
# numerator / denominator" codes fire when the scope lacks one side of
# the pair; the "ambiguous_pair" code fires when the scope has more
# than one numerator or denominator and the slice refuses to guess;
# the "non_numeric_*" codes fire when the value is not a finite
# number (None / NaN / inf / non-numeric); the "zero_denominator"
# code fires when division would be undefined; the
# "missing_source_version" code fires when one or both inputs lack a
# non-empty source_version stamp (kept narrow to preserve
# provenance); the "pair_year_mismatch" code is a defensive safety
# net -- with year-scoped grouping it is normally unreachable, but
# the catalog keeps the check so a future refactor that loosens the
# scope key still produces a structured diagnostic rather than a
# silent row.
CONCEPT_WARNING_MISSING_NUMERATOR: str = "concept_missing_numerator"
CONCEPT_WARNING_MISSING_DENOMINATOR: str = "concept_missing_denominator"
CONCEPT_WARNING_AMBIGUOUS_PAIR: str = "concept_ambiguous_pair"
CONCEPT_WARNING_NON_NUMERIC_NUMERATOR: str = "concept_non_numeric_numerator"
CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR: str = "concept_non_numeric_denominator"
CONCEPT_WARNING_ZERO_DENOMINATOR: str = "concept_zero_denominator"
CONCEPT_WARNING_MISSING_SOURCE_VERSION: str = "concept_missing_source_version"
CONCEPT_WARNING_PAIR_YEAR_MISMATCH: str = "concept_pair_year_mismatch"


# ---------------------------------------------------------------------------
# Catalog factories
# ---------------------------------------------------------------------------


def build_concept_descriptors() -> tuple[ConceptDescriptor, ...]:
    """Return the canonical ordered list of :class:`ConceptDescriptor` records.

    The first slice supports three concepts per SRC-CONCEPT-001:
    ``gdp_per_capita``, ``population``, ``gdp_total``. Future slices
    may add more; this function is the single point of registration.
    """
    return (
        ConceptDescriptor(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            display_name="Real GDP per capita",
            description=(
                "Country-year GDP per capita. Source-specific "
                "scales (USD, PPP constant 2017 intl $, 2011 intl "
                "$, 2017 USD, etc.) are preserved on each emitted "
                "ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_POPULATION,
            display_name="Country population",
            description=(
                "Country-year population. Source-specific scales "
                "(persons, thousands of persons) are preserved on "
                "each emitted ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_GDP_TOTAL,
            display_name="Country GDP (total)",
            description=(
                "Country-year total GDP. Source-specific scales "
                "(current USD, constant 2015 USD, 2011 intl $, "
                "2017 USD millions, etc.) are preserved on each "
                "emitted ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_HDI,
            display_name="Human Development Index",
            description="UNDP country-year Human Development Index score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_LIFE_EXPECTANCY,
            display_name="Life expectancy",
            description="UNDP country-year life expectancy at birth.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_GNI_PER_CAPITA,
            display_name="GNI per capita",
            description="UNDP country-year gross national income per capita.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_EXPECTED_YEARS_SCHOOLING,
            display_name="Expected years of schooling",
            description="UNDP country-year expected years of schooling.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MEAN_YEARS_SCHOOLING,
            display_name="Mean years of schooling",
            description="UNDP country-year mean years of schooling.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_UNDER5_MORTALITY,
            display_name="Under-5 mortality",
            description="WHO GHO country-year under-5 mortality indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_BCG_IMMUNIZATION,
            display_name="BCG immunization coverage",
            description="WHO GHO country-year BCG immunization coverage indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_DTP3_IMMUNIZATION,
            display_name="DTP3 immunization coverage",
            description="WHO GHO country-year DTP3 immunization coverage indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_HEPB3_IMMUNIZATION,
            display_name="HepB3 immunization coverage",
            description="WHO GHO country-year HepB3 immunization coverage indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_ELECTORAL_DEMOCRACY,
            display_name="Electoral democracy",
            description="V-Dem country-year electoral democracy index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_LIBERAL_DEMOCRACY,
            display_name="Liberal democracy",
            description="V-Dem country-year liberal democracy index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIVIL_LIBERTIES,
            display_name="Civil liberties",
            description="V-Dem country-year civil liberties index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_SUFFRAGE,
            display_name="Suffrage",
            description="V-Dem country-year suffrage indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_RULE_OF_LAW,
            display_name="Rule of law",
            description="V-Dem country-year equality before the law and individual liberty index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_FREEDOM_EXPRESSION,
            display_name="Freedom of expression",
            description=(
                "V-Dem country-year freedom of expression and alternative information index."
            ),
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_FREEDOM_ASSOCIATION,
            display_name="Freedom of association",
            description="V-Dem country-year freedom of association index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PRESS_FREEDOM_SCORE,
            display_name="Press freedom score",
            description="RSF country-year press freedom score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PRESS_FREEDOM_RANK,
            display_name="Press freedom rank",
            description="RSF country-year press freedom rank.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PHYSICAL_INTEGRITY,
            display_name="Physical integrity liberties",
            description="V-Dem country-year physical integrity liberties index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_POLITICAL_LIBERTIES,
            display_name="Political civil liberties",
            description="V-Dem country-year political civil liberties index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PRIVATE_CIVIL_LIBERTIES,
            display_name="Private civil liberties",
            description="V-Dem country-year private civil liberties index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIVIL_SOCIETY_REPRESSION,
            display_name="Civil society repression",
            description="V-Dem country-year civil society repression indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_EXTRAJUDICIAL_KILLINGS,
            display_name="Extrajudicial killings",
            description="V-Dem country-year political killings indicator.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
            display_name="CIRIGHTS physical integrity",
            description="CIRIGHTS country-year physical integrity score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_TORTURE,
            display_name="CIRIGHTS torture",
            description="CIRIGHTS country-year torture score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_DISAPPEARANCES,
            display_name="CIRIGHTS disappearances",
            description="CIRIGHTS country-year disappearance score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_KILLINGS,
            display_name="CIRIGHTS killings",
            description="CIRIGHTS country-year extrajudicial-killing score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT,
            display_name="CIRIGHTS political imprisonment",
            description="CIRIGHTS country-year political imprisonment score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_REPRESSION,
            display_name="CIRIGHTS repression",
            description="CIRIGHTS country-year repression score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS,
            display_name="CIRIGHTS civil and political rights",
            description="CIRIGHTS country-year civil and political rights score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PTS_AMNESTY_SCORE,
            display_name="PTS Amnesty score",
            description="Political Terror Scale country-year Amnesty International score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE,
            display_name="PTS Human Rights Watch score",
            description="Political Terror Scale country-year Human Rights Watch score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PTS_STATE_DEPT_SCORE,
            display_name="PTS State Department score",
            description="Political Terror Scale country-year US State Department score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_STATE_BASED_CONFLICT_EVENTS,
            display_name="State-based conflict events",
            description="UCDP country-year state-based conflict event count.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_STATE_BASED_CONFLICT_FATALITIES,
            display_name="State-based conflict fatalities",
            description="UCDP country-year state-based conflict fatality count.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS,
            display_name="Internationalized conflict events",
            description=(
                "UCDP country-year internationalized state-based conflict event count."
            ),
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES,
            display_name="Internationalized conflict fatalities",
            description=(
                "UCDP country-year internationalized state-based conflict fatality count."
            ),
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
            display_name="One-sided violence events",
            description="UCDP country-year one-sided violence event count.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
            display_name="One-sided violence fatalities",
            description="UCDP country-year one-sided violence fatality count.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CORRUPTION_INDEX,
            display_name="Political corruption index",
            description="V-Dem country-year political corruption index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CPI_SCORE,
            display_name="Corruption Perceptions Index score",
            description="Transparency International country-year CPI score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_CONTROL_OF_CORRUPTION,
            display_name="Control of corruption",
            description="World Bank WGI country-year control of corruption estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_EXECUTIVE_CORRUPTION,
            display_name="Executive corruption",
            description="V-Dem country-year executive corruption index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_PUBLIC_CORRUPTION,
            display_name="Public-sector corruption",
            description="V-Dem country-year public-sector corruption index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_ACCOUNTABILITY,
            display_name="Accountability",
            description="V-Dem country-year accountability index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_VOICE_AND_ACCOUNTABILITY,
            display_name="Voice and accountability",
            description="World Bank WGI country-year voice and accountability estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_WGI_RULE_OF_LAW,
            display_name="WGI rule of law",
            description="World Bank WGI country-year rule of law estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_GOVERNMENT_EFFECTIVENESS,
            display_name="Government effectiveness",
            description="World Bank WGI country-year government effectiveness estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_REGULATORY_QUALITY,
            display_name="Regulatory quality",
            description="World Bank WGI country-year regulatory quality estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_BTI_GOVERNANCE_INDEX,
            display_name="BTI governance index",
            description="Bertelsmann BTI country-year governance index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_BTI_STATUS_INDEX,
            display_name="BTI status index",
            description="Bertelsmann BTI country-year status index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_BTI_DEMOCRACY_STATUS,
            display_name="BTI democracy status",
            description="Bertelsmann BTI country-year democracy status score.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_JUDICIAL_CONSTRAINTS,
            display_name="Judicial constraints",
            description="V-Dem country-year judicial constraints on the executive.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_LEGISLATIVE_CONSTRAINTS,
            display_name="Legislative constraints",
            description="V-Dem country-year legislative constraints on the executive.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MULTIPARTY_INSTITUTIONS,
            display_name="Multiparty institutions",
            description="V-Dem country-year multiparty institutions index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_REGIME_TYPE,
            display_name="Regime type",
            description="V-Dem country-year regime type index.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_NUCLEAR_TOTAL_INVENTORY,
            display_name="Nuclear warheads total inventory",
            description="FAS country-year nuclear warheads total inventory estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_NUCLEAR_MILITARY_STOCKPILE,
            display_name="Nuclear military stockpile",
            description="FAS country-year nuclear military stockpile estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC,
            display_name="Operational strategic nuclear warheads",
            description="FAS country-year operational strategic nuclear warhead estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC,
            display_name="Operational nonstrategic nuclear warheads",
            description="FAS country-year operational nonstrategic nuclear warhead estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED,
            display_name="Reserve/nondeployed nuclear warheads",
            description="FAS country-year reserve or nondeployed nuclear warhead estimate.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MILITARY_SPEND_CONSTANT_USD,
            display_name="Military expenditure, constant USD",
            description="SIPRI country-year military expenditure in constant US dollars.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MILITARY_SPEND_PER_CAPITA,
            display_name="Military expenditure per capita",
            description="SIPRI country-year military expenditure per capita.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MILITARY_SPEND_SHARE_GDP,
            display_name="Military expenditure share of GDP",
            description="SIPRI country-year military expenditure as a share of GDP.",
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_MILITARY_SPEND_SHARE_GOVT,
            display_name="Military expenditure share of government spending",
            description=(
                "SIPRI country-year military expenditure as a share of government spending."
            ),
        ),
    )


def build_concept_mappings() -> tuple[ConceptMapping, ...]:
    """Return the canonical ordered list of :class:`ConceptMapping` records.

    The mappings cover the three migrated sources (WDI, Maddison,
    PWT) for the three concepts above. Future slices may add more
    sources per concept; this function is the single point of
    registration.
    """
    return (
        # --- WDI direct mappings -------------------------------------
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
            ),
            notes=(
                "WDI publishes GDP per capita in two scales: "
                "current USD (NY.GDP.PCAP.CD) and constant 2017 "
                "international dollars at PPP (NY.GDP.PCAP.PP.KD). "
                "Both alias the concept; extraction produces one "
                "ConceptObservation per matching observation."
            ),
        ),
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WDI_POPULATION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                WDI_GDP_CURRENT_USD_INDICATOR_CODE,
                WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE,
            ),
            notes=(
                "WDI publishes total GDP in current USD "
                "(NY.GDP.MKTP.CD) and constant 2015 USD "
                "(NY.GDP.MKTP.KD). Both alias the concept."
            ),
        ),
        # --- Maddison direct mappings ---------------------------------
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,),
            output_unit="2011_international_dollars",
        ),
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(MADDISON_PROJECT_POPULATION_INDICATOR_CODE,),
            output_unit="thousands_of_persons",
        ),
        # The Maddison GDP-total indicator is itself a derived value
        # (``gdppc * pop * 1000``) computed by the Stage 2 reader;
        # the concept catalog treats it as a direct mapping onto the
        # already-derived observation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE,),
            output_unit="2011_international_dollars",
        ),
        # --- PWT direct mappings --------------------------------------
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(PWT_POPULATION_INDICATOR_CODE,),
            output_unit="thousands_of_persons",
        ),
        # PWT publishes real GDP under two sides (output + expenditure);
        # both alias the concept; extraction produces one
        # ConceptObservation per matching observation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
                PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE,
            ),
            output_unit="million_2017_USD",
        ),
        # --- PWT derived mapping --------------------------------------
        # ``gdp_per_capita = pwt_real_gdp_output_side / pwt_population``.
        # Numerator is in million_2017_USD, denominator in thousands of
        # persons; the ratio is therefore in "1000 USD per person".
        # The recipe key is carried on every emitted ConceptObservation
        # so audit code can reproduce the exact derivation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="derived",
            indicator_codes=(
                PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
                PWT_POPULATION_INDICATOR_CODE,
            ),
            output_unit="thousand_2017_USD_per_person",
            output_scale="ratio",
            recipe_key=PWT_GDP_PER_CAPITA_RECIPE_KEY,
            notes=(
                "Per-capita GDP derived from PWT real GDP output "
                "side (rgdpo, million_2017_USD) divided by PWT "
                "population (pop, thousands of persons). Output "
                "unit is therefore 1000 USD per person. Missing, "
                "non-numeric, zero, or ambiguous inputs produce "
                "no derived row for the affected (country, year, "
                "source_version) scope."
            ),
        ),
        # --- UNDP HDI direct mappings ---------------------------------
        ConceptMapping(
            concept_key=CONCEPT_HDI,
            source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UNDP_HDI_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_LIFE_EXPECTANCY,
            source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UNDP_HDI_LIFE_EXPECTANCY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_GNI_PER_CAPITA,
            source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UNDP_HDI_GNI_PER_CAPITA_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_EXPECTED_YEARS_SCHOOLING,
            source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UNDP_HDI_EXPECTED_YEARS_SCHOOLING_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_MEAN_YEARS_SCHOOLING,
            source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UNDP_HDI_MEAN_YEARS_SCHOOLING_INDICATOR_CODE,),
        ),
        # --- WHO GHO direct mappings ----------------------------------
        ConceptMapping(
            concept_key=CONCEPT_UNDER5_MORTALITY,
            source_id=SourceId(slug=WHO_GHO_API_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WHO_GHO_UNDER5_MORTALITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_BCG_IMMUNIZATION,
            source_id=SourceId(slug=WHO_GHO_API_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WHO_GHO_BCG_IMMUNIZATION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_DTP3_IMMUNIZATION,
            source_id=SourceId(slug=WHO_GHO_API_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_HEPB3_IMMUNIZATION,
            source_id=SourceId(slug=WHO_GHO_API_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WHO_GHO_HEPB3_IMMUNIZATION_INDICATOR_CODE,),
        ),
        # --- V-Dem political freedom mappings -------------------------
        ConceptMapping(
            concept_key=CONCEPT_ELECTORAL_DEMOCRACY,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_LIBERAL_DEMOCRACY,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_LIBERAL_DEMOCRACY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIVIL_LIBERTIES,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_CIVIL_LIBERTIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIVIL_LIBERTIES,
            source_id=SourceId(slug=FREEDOM_HOUSE_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_SUFFRAGE,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_SUFFRAGE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_RULE_OF_LAW,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_RULE_OF_LAW_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_FREEDOM_EXPRESSION,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_FREEDOM_EXPRESSION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_FREEDOM_ASSOCIATION,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_FREEDOM_ASSOCIATION_INDICATOR_CODE,),
        ),
        # --- RSF direct press-freedom mappings ------------------------
        ConceptMapping(
            concept_key=CONCEPT_PRESS_FREEDOM_SCORE,
            source_id=SourceId(slug=RSF_PRESS_FREEDOM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PRESS_FREEDOM_RANK,
            source_id=SourceId(slug=RSF_PRESS_FREEDOM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(RSF_PRESS_FREEDOM_RANK_INDICATOR_CODE,),
        ),
        # --- V-Dem domestic safety / repression mappings ---------------
        ConceptMapping(
            concept_key=CONCEPT_PHYSICAL_INTEGRITY,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_PHYSICAL_INTEGRITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_POLITICAL_LIBERTIES,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_POLITICAL_LIBERTIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_POLITICAL_LIBERTIES,
            source_id=SourceId(slug=FREEDOM_HOUSE_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PRIVATE_CIVIL_LIBERTIES,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_PRIVATE_CIVIL_LIBERTIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIVIL_SOCIETY_REPRESSION,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_CIVIL_SOCIETY_REPRESSION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_EXTRAJUDICIAL_KILLINGS,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_EXTRAJUDICIAL_KILLINGS_INDICATOR_CODE,),
        ),
        # --- CIRIGHTS domestic safety / rights mappings ----------------
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_TORTURE,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_TORTURE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_DISAPPEARANCES,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_DISAPPEARANCES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_KILLINGS,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_KILLINGS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_POLITICAL_IMPRISONMENT_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_REPRESSION,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_REPRESSION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS,
            source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(CIRIGHTS_CIVIL_POLITICAL_RIGHTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PTS_AMNESTY_SCORE,
            source_id=SourceId(slug=PTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(PTS_AMNESTY_SCORE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE,
            source_id=SourceId(slug=PTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(PTS_HUMAN_RIGHTS_WATCH_SCORE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PTS_STATE_DEPT_SCORE,
            source_id=SourceId(slug=PTS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(PTS_STATE_DEPT_SCORE_INDICATOR_CODE,),
        ),
        # --- UCDP conflict / one-sided violence mappings ---------------
        ConceptMapping(
            concept_key=CONCEPT_STATE_BASED_CONFLICT_EVENTS,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_STATE_BASED_EVENTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_STATE_BASED_CONFLICT_FATALITIES,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_STATE_BASED_FATALITIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_INTL_EVENTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_INTL_FATALITIES_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_ONE_SIDED_EVENTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
            source_id=SourceId(slug=UCDP_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(UCDP_ONE_SIDED_FATALITIES_INDICATOR_CODE,),
        ),
        # --- V-Dem corruption / integrity mappings --------------------
        ConceptMapping(
            concept_key=CONCEPT_CORRUPTION_INDEX,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_CORRUPTION_INDEX_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CPI_SCORE,
            source_id=SourceId(slug=TRANSPARENCY_CPI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_CONTROL_OF_CORRUPTION,
            source_id=SourceId(slug=WGI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WGI_CONTROL_OF_CORRUPTION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_EXECUTIVE_CORRUPTION,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_EXECUTIVE_CORRUPTION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_PUBLIC_CORRUPTION,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_PUBLIC_CORRUPTION_INDICATOR_CODE,),
        ),
        # --- V-Dem governance capacity mappings -----------------------
        ConceptMapping(
            concept_key=CONCEPT_ACCOUNTABILITY,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_ACCOUNTABILITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_VOICE_AND_ACCOUNTABILITY,
            source_id=SourceId(slug=WGI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WGI_VOICE_AND_ACCOUNTABILITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_WGI_RULE_OF_LAW,
            source_id=SourceId(slug=WGI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WGI_RULE_OF_LAW_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_GOVERNMENT_EFFECTIVENESS,
            source_id=SourceId(slug=WGI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_REGULATORY_QUALITY,
            source_id=SourceId(slug=WGI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WGI_REGULATORY_QUALITY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_BTI_GOVERNANCE_INDEX,
            source_id=SourceId(slug=BTI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(BTI_GOVERNANCE_INDEX_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_BTI_STATUS_INDEX,
            source_id=SourceId(slug=BTI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(BTI_STATUS_INDEX_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_BTI_DEMOCRACY_STATUS,
            source_id=SourceId(slug=BTI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(BTI_DEMOCRACY_STATUS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_JUDICIAL_CONSTRAINTS,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_JUDICIAL_CONSTRAINTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_LEGISLATIVE_CONSTRAINTS,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_LEGISLATIVE_CONSTRAINTS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_MULTIPARTY_INSTITUTIONS,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_MULTIPARTY_INSTITUTIONS_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_REGIME_TYPE,
            source_id=SourceId(slug=VDEM_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(VDEM_REGIME_TYPE_INDICATOR_CODE,),
        ),
        # --- FAS nuclear risk mappings ---------------------------------
        ConceptMapping(
            concept_key=CONCEPT_NUCLEAR_TOTAL_INVENTORY,
            source_id=SourceId(slug=FAS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FAS_TOTAL_INVENTORY_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_NUCLEAR_MILITARY_STOCKPILE,
            source_id=SourceId(slug=FAS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FAS_MILITARY_STOCKPILE_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC,
            source_id=SourceId(slug=FAS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FAS_OPERATIONAL_STRATEGIC_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC,
            source_id=SourceId(slug=FAS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FAS_OPERATIONAL_NONSTRATEGIC_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED,
            source_id=SourceId(slug=FAS_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(FAS_RESERVE_NONDEPLOYED_INDICATOR_CODE,),
        ),
        # --- SIPRI military expenditure mappings -----------------------
        ConceptMapping(
            concept_key=CONCEPT_MILITARY_SPEND_CONSTANT_USD,
            source_id=SourceId(slug=SIPRI_MILEX_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_MILITARY_SPEND_PER_CAPITA,
            source_id=SourceId(slug=SIPRI_MILEX_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(SIPRI_MILEX_PER_CAPITA_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_MILITARY_SPEND_SHARE_GDP,
            source_id=SourceId(slug=SIPRI_MILEX_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_MILITARY_SPEND_SHARE_GOVT,
            source_id=SourceId(slug=SIPRI_MILEX_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(SIPRI_MILEX_SHARE_GOVT_INDICATOR_CODE,),
        ),
    )


__all__ = [
    "CLIENT_EXISTING_SOURCE_KEY",
    "CONCEPT_BCG_IMMUNIZATION",
    "CONCEPT_CIVIL_LIBERTIES",
    "CONCEPT_DTP3_IMMUNIZATION",
    "CONCEPT_ELECTORAL_DEMOCRACY",
    "CONCEPT_EXPECTED_YEARS_SCHOOLING",
    "CONCEPT_FREEDOM_ASSOCIATION",
    "CONCEPT_FREEDOM_EXPRESSION",
    "CONCEPT_GDP_PER_CAPITA",
    "CONCEPT_GDP_TOTAL",
    "CONCEPT_GNI_PER_CAPITA",
    "CONCEPT_HDI",
    "CONCEPT_HEPB3_IMMUNIZATION",
    "CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS",
    "CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES",
    "CONCEPT_LIBERAL_DEMOCRACY",
    "CONCEPT_LIFE_EXPECTANCY",
    "CONCEPT_MEAN_YEARS_SCHOOLING",
    "CONCEPT_MILITARY_SPEND_CONSTANT_USD",
    "CONCEPT_MILITARY_SPEND_PER_CAPITA",
    "CONCEPT_MILITARY_SPEND_SHARE_GDP",
    "CONCEPT_MILITARY_SPEND_SHARE_GOVT",
    "CONCEPT_POPULATION",
    "CONCEPT_PRESS_FREEDOM_RANK",
    "CONCEPT_PRESS_FREEDOM_SCORE",
    "CONCEPT_RULE_OF_LAW",
    "CONCEPT_STATE_BASED_CONFLICT_EVENTS",
    "CONCEPT_STATE_BASED_CONFLICT_FATALITIES",
    "CONCEPT_SUFFRAGE",
    "CONCEPT_UNDER5_MORTALITY",
    "CONCEPT_WARNING_AMBIGUOUS_PAIR",
    "CONCEPT_WARNING_MISSING_DENOMINATOR",
    "CONCEPT_WARNING_MISSING_NUMERATOR",
    "CONCEPT_WARNING_MISSING_SOURCE_VERSION",
    "CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR",
    "CONCEPT_WARNING_NON_NUMERIC_NUMERATOR",
    "CONCEPT_WARNING_PAIR_YEAR_MISMATCH",
    "CONCEPT_WARNING_ZERO_DENOMINATOR",
    "DERIVED_CONCEPT_QUALITY_FLAG",
    "FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE",
    "FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE",
    "FREEDOM_HOUSE_SOURCE_KEY",
    "KNOWN_CONCEPT_KEYS",
    "MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE",
    "MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE",
    "MADDISON_PROJECT_POPULATION_INDICATOR_CODE",
    "MADDISON_PROJECT_SOURCE_KEY",
    "PWT_GDP_PER_CAPITA_RECIPE_KEY",
    "PWT_POPULATION_INDICATOR_CODE",
    "PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE",
    "PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE",
    "PWT_SOURCE_KEY",
    "RSF_PRESS_FREEDOM_RANK_INDICATOR_CODE",
    "RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "SIPRI_MILEX_CONSTANT_USD_INDICATOR_CODE",
    "SIPRI_MILEX_PER_CAPITA_INDICATOR_CODE",
    "SIPRI_MILEX_SHARE_GDP_INDICATOR_CODE",
    "SIPRI_MILEX_SHARE_GOVT_INDICATOR_CODE",
    "SIPRI_MILEX_SOURCE_KEY",
    "UCDP_INTL_EVENTS_INDICATOR_CODE",
    "UCDP_INTL_FATALITIES_INDICATOR_CODE",
    "UCDP_STATE_BASED_EVENTS_INDICATOR_CODE",
    "UCDP_STATE_BASED_FATALITIES_INDICATOR_CODE",
    "UNDP_HDI_EXPECTED_YEARS_SCHOOLING_INDICATOR_CODE",
    "UNDP_HDI_GNI_PER_CAPITA_INDICATOR_CODE",
    "UNDP_HDI_INDICATOR_CODE",
    "UNDP_HDI_LIFE_EXPECTANCY_INDICATOR_CODE",
    "UNDP_HDI_MEAN_YEARS_SCHOOLING_INDICATOR_CODE",
    "UNDP_HDI_SOURCE_KEY",
    "VDEM_CIVIL_LIBERTIES_INDICATOR_CODE",
    "VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE",
    "VDEM_FREEDOM_ASSOCIATION_INDICATOR_CODE",
    "VDEM_FREEDOM_EXPRESSION_INDICATOR_CODE",
    "VDEM_LIBERAL_DEMOCRACY_INDICATOR_CODE",
    "VDEM_RULE_OF_LAW_INDICATOR_CODE",
    "VDEM_SOURCE_KEY",
    "VDEM_SUFFRAGE_INDICATOR_CODE",
    "WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE",
    "WDI_GDP_CURRENT_USD_INDICATOR_CODE",
    "WDI_GDP_PER_CAPITA_INDICATOR_CODE",
    "WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE",
    "WDI_POPULATION_INDICATOR_CODE",
    "WDI_SOURCE_KEY",
    "WHO_GHO_API_SOURCE_KEY",
    "WHO_GHO_BCG_IMMUNIZATION_INDICATOR_CODE",
    "WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE",
    "WHO_GHO_HEPB3_IMMUNIZATION_INDICATOR_CODE",
    "WHO_GHO_UNDER5_MORTALITY_INDICATOR_CODE",
    "build_concept_descriptors",
    "build_concept_mappings",
]
