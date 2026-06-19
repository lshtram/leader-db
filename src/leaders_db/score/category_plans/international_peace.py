"""Source plan for the ``international_peace`` rating category.

The plan enumerates the canonical sources and indicators for the
"International peace vs aggression and war" category from
requirement §4. Per requirement §6 the canonical sources are UCDP
(event-based methodology) and SIPRI Military Expenditure
(expenditure-based methodology). COW/MID is "yet to be
implemented" per the source-vetting report; once the Stage 2
adapter lands, this plan widens.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/ucdp.csv`` (4 indicators: state-
based and internationalized events + fatalities) and
``src/leaders_db/ingest/catalogs/sipri_milex.csv`` (4 indicators:
share of GDP, per capita, constant USD, share of govt spending).
All 8 are LOWER_IS_BETTER (more conflict / more military spending
= worse peace signal).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`INTERNATIONAL_PEACE_PLAN`. Variable
#: names match the per-source catalogs: ``ucdp.csv`` (4
#: indicators) and ``sipri_milex.csv`` (4 indicators). All 8 are
#: LOWER_IS_BETTER.
INTERNATIONAL_PEACE_INDICATORS: tuple[IndicatorSpec, ...] = (
    # UCDP state-based conflict (event + fatality counts).
    IndicatorSpec(
        "ucdp_state_based_events",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    IndicatorSpec(
        "ucdp_state_based_fatalities",
        IndicatorRole.REQUIRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    # UCDP internationalized conflict (the cross-border subset).
    IndicatorSpec(
        "ucdp_intl_events",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    IndicatorSpec(
        "ucdp_intl_fatalities",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    # SIPRI Military Expenditure Database — 4 share/scale indicators.
    IndicatorSpec(
        "sipri_milex_share_of_gdp",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_milex",
    ),
    IndicatorSpec(
        "sipri_milex_per_capita",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_milex",
    ),
    IndicatorSpec(
        "sipri_milex_constant_usd",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_milex",
    ),
    IndicatorSpec(
        "sipri_milex_share_of_govt_spending",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_milex",
    ),
)

#: Plan for the ``international_peace`` category. UCDP state-based
#: + UCDP internationalized + SIPRI military-expenditure.
#: ``allowed_proxy_years`` is widened to 2 because UCDP and SIPRI
#: update on different cadences and the prototype target year
#: 2023 is sometimes only available as a 1- or 2-year-old reading.
INTERNATIONAL_PEACE_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="international_peace",
    expected_sources=("ucdp", "sipri_milex"),
    expected_indicators=INTERNATIONAL_PEACE_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1, 2),
    default_source_weights=(
        ("ucdp", 1.0),
        ("sipri_milex", 0.8),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["INTERNATIONAL_PEACE_INDICATORS", "INTERNATIONAL_PEACE_PLAN"]
