"""Source plan for the ``effectiveness`` rating category.

The plan enumerates the canonical sources and indicators for the
"Effectiveness and competence" category from requirement §4. Per
requirement §6 the canonical sources are World Bank WGI (6
indicators; Control of Corruption lives in integrity), BTI
Governance Index, and V-Dem governance / executive-constraint
indicators. Three distinct governance methodologies.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/wgi.csv`` (5 indicators,
excluding Control of Corruption which lives in integrity),
``src/leaders_db/ingest/catalogs/vdem.csv`` (5 governance /
executive-constraint indicators), and
``src/leaders_db/ingest/catalogs/bti.csv`` (2 governance
composites: Governance Index + Governance Performance).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`EFFECTIVENESS_PLAN`. Variable names
#: match the per-source catalogs.
EFFECTIVENESS_INDICATORS: tuple[IndicatorSpec, ...] = (
    # WGI — the 5 governance indicators (Control of Corruption
    # lives in integrity per the WGI catalog header).
    IndicatorSpec(
        "wgi_voice_and_accountability",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    IndicatorSpec(
        "wgi_political_stability",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    IndicatorSpec(
        "wgi_government_effectiveness",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    IndicatorSpec(
        "wgi_regulatory_quality",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    IndicatorSpec(
        "wgi_rule_of_law",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    # V-Dem — the 5 governance / executive-constraint indicators
    # (per the V-Dem catalog header "rating_category =
    # effectiveness").
    IndicatorSpec(
        "vdem_v2x_jucon",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2xlg_legcon",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_accountability",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_mpi",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_regime",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    # BTI — the 2 governance composites (Governance Index +
    # Governance Performance).
    IndicatorSpec(
        "bti_governance_index",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_governance_performance",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
)

#: Plan for the ``effectiveness`` category. The
#: minimum-viable-sources threshold is 2 because two of the
#: three sources are well-populated and a single-source bundle
#: is too thin to score confidently.
EFFECTIVENESS_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="effectiveness",
    expected_sources=("wgi", "vdem", "bti"),
    expected_indicators=EFFECTIVENESS_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1,),
    default_source_weights=(
        ("wgi", 1.0),
        ("vdem", 0.9),
        ("bti", 0.8),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["EFFECTIVENESS_INDICATORS", "EFFECTIVENESS_PLAN"]
