"""Source plan for the ``economic_wellbeing`` rating category.

The plan enumerates the canonical sources and indicators for the
"Economic well-being and prosperity" category from requirement §4.
Per requirement §6 the canonical sources are World Bank WDI (market
rate) and Penn World Table (PPP). PWT is "yet to be implemented"
per the source-vetting report; the plan ships with WDI + BTI
(Bertelsmann Transformation Index) as the two-source foundation
until PWT lands. BTI is the second source because its 3
economic-transformation questions (Q6 socioeconomic development,
Q7 market competition, Q11 economic performance) overlap with WDI's
GDP / GNI / trade indicators and provide an expert-coded cross-
validation methodology.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/wdi.csv`` (9 indicators: 4 GDP /
GNI per-capita measures + 3 trade measures + FDI + population)
and ``src/leaders_db/ingest/catalogs/bti.csv`` (3 economic
questions). All are HIGHER_IS_BETTER (higher per-capita income,
higher market competition = better economic wellbeing).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`ECONOMIC_WELLBEING_PLAN`. Variable
#: names match the per-source catalogs.
ECONOMIC_WELLBEING_INDICATORS: tuple[IndicatorSpec, ...] = (
    # WDI — the canonical economic-wellbeing signal.
    IndicatorSpec(
        "wdi_gdp_per_capita",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_gdp_per_capita_ppp_constant_2017",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_gdp_current_usd",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_gdp_constant_2015_usd",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_gni_per_capita_atlas",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_exports_pct_gdp",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_imports_pct_gdp",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_fdi_inflows_current_usd",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    IndicatorSpec(
        "wdi_population",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="world_bank_wdi",
    ),
    # BTI — the 3 economic-transformation questions from the
    # catalog. All 1-10 BTI scores are HIGHER_IS_BETTER (10 =
    # best). The Q13 "Level of Difficulty" composite is
    # intentionally excluded (the catalog header flags its
    # direction is inverted relative to the other composites; the
    # per-source catalog note says it is "intentionally excluded
    # from the catalog").
    IndicatorSpec(
        "bti_q6_socioeconomic_development",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q7_market_competition",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q11_economic_performance",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
)

#: Plan for the ``economic_wellbeing`` category. The
#: minimum-viable-sources threshold is 1 because the BTI biennial
#: cadence and WDI's near-universal coverage mean
#: ``world_bank_wdi`` is almost always observed; the threshold
#: guards against the rare "no WDI row at all" case.
ECONOMIC_WELLBEING_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="economic_wellbeing",
    expected_sources=("world_bank_wdi", "bti"),
    expected_indicators=ECONOMIC_WELLBEING_INDICATORS,
    minimum_viable_sources=1,
    preferred_direct_year=2023,
    allowed_proxy_years=(1,),
    default_source_weights=(
        ("world_bank_wdi", 1.0),
        ("bti", 0.7),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["ECONOMIC_WELLBEING_INDICATORS", "ECONOMIC_WELLBEING_PLAN"]
