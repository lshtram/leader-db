"""Source plan for the ``social_wellbeing`` rating category.

The plan enumerates the canonical sources and indicators for the
"Social well-being and prosperity" category from requirement §4.
Per requirement §6 the canonical sources are UNDP HDI (composite),
WDI (raw indicators), and WHO GHO (health). The V-Dem egalitarian
component is added as the 4th source for cross-validation of the
distributional subdimension.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/undp_hdi.csv`` (5 indicators),
``src/leaders_db/ingest/catalogs/who_gho_api.csv`` (5 indicators),
``src/leaders_db/ingest/catalogs/wdi.csv`` (5 social indicators),
and ``src/leaders_db/ingest/catalogs/vdem.csv`` (2 egalitarian
indicators).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`SOCIAL_WELLBEING_PLAN`. Variable names
#: match the per-source catalogs under
#: ``src/leaders_db/ingest/catalogs/``:
#: ``undp_hdi_*.csv``, ``who_gho_api.csv``, ``wdi.csv``, ``vdem.csv``.
SOCIAL_WELLBEING_INDICATORS: tuple[IndicatorSpec, ...] = (
    # UNDP HDI composite + components (the canonical social-
    # wellbeing signal for the prototype per Phase C.8 / the
    # source-vetting report). The composite is REQUIRED; the
    # components are PREFERRED so a missing component drops
    # confidence but does not block a score.
    IndicatorSpec(
        "undp_hdi_hdi",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="undp_hdi",
    ),
    IndicatorSpec(
        "undp_hdi_life_expectancy",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="undp_hdi",
    ),
    IndicatorSpec(
        "undp_hdi_expected_years_schooling",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="undp_hdi",
    ),
    IndicatorSpec(
        "undp_hdi_mean_years_schooling",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="undp_hdi",
    ),
    IndicatorSpec(
        "undp_hdi_gni_per_capita",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="undp_hdi",
    ),
    # WHO GHO API social indicators (the second source for the
    # social_wellbeing category per the source-vetting report
    # §6).
    IndicatorSpec(
        "who_gho_life_expectancy",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="who_gho_api",
    ),
    IndicatorSpec(
        "who_gho_under5_mortality",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="who_gho_api",
    ),
    IndicatorSpec(
        "who_gho_dtp3_immunization",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="who_gho_api",
    ),
    IndicatorSpec(
        "who_gho_hepb3_immunization",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="who_gho_api",
    ),
    IndicatorSpec(
        "who_gho_bcg_immunization",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="who_gho_api",
    ),
    # World Bank WDI social indicators (per the WDI catalog).
    IndicatorSpec(
        "wdi_life_expectancy_at_birth",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_under5_mortality_per_1000",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_literacy_rate_adult",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_secondary_school_enrollment",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_gini_index",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    # V-Dem egalitarian component (per the V-Dem catalog).
    IndicatorSpec(
        "vdem_v2x_egal",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2clsocgrp_ord",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
)

#: Plan for the ``social_wellbeing`` category (requirement §6).
SOCIAL_WELLBEING_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="social_wellbeing",
    expected_sources=("undp_hdi", "who_gho_api", "world_bank_wdi", "vdem"),
    expected_indicators=SOCIAL_WELLBEING_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1,),
    default_source_weights=(
        ("undp_hdi", 1.0),
        ("who_gho_api", 0.8),
        ("world_bank_wdi", 0.8),
        ("vdem", 0.7),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["SOCIAL_WELLBEING_INDICATORS", "SOCIAL_WELLBEING_PLAN"]
