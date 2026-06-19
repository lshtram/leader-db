"""Source plan for the ``integrity`` rating category.

The plan enumerates the canonical sources and indicators for the
"Integrity and honesty" category from requirement §4. Per
requirement §6 the canonical sources are Transparency
International CPI (perception-based), World Bank WGI Control of
Corruption (aggregate), and V-Dem political-corruption
(expert-coded). Three independent methodologies.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/wgi.csv`` (1 indicator),
``src/leaders_db/ingest/catalogs/vdem.csv`` (3 indicators), and
``src/leaders_db/ingest/catalogs/transparency_cpi.csv`` (1
indicator).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`INTEGRITY_PLAN`. Variable names match
#: the per-source catalogs: ``wgi.csv``, ``vdem.csv``,
#: ``transparency_cpi.csv``.
INTEGRITY_INDICATORS: tuple[IndicatorSpec, ...] = (
    # WGI Control of Corruption — the canonical integrity signal
    # (per the source-vetting report §3.6; cross-validates TI CPI
    # and V-Dem corruption).
    IndicatorSpec(
        "wgi_control_of_corruption",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="wgi",
    ),
    # V-Dem political-corruption indices. The V-Dem direction is
    # LOWER_IS_BETTER (higher = more corrupt per the V-Dem
    # codebook).
    IndicatorSpec(
        "vdem_v2x_corr",
        IndicatorRole.REQUIRED,
        Direction.LOWER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_execorr",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_pubcorr",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="vdem",
    ),
    # Transparency International CPI.
    IndicatorSpec(
        "cpi_score",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="ti_cpi",
    ),
)

#: Plan for the ``integrity`` category (requirement §6).
INTEGRITY_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="integrity",
    expected_sources=("wgi", "vdem", "ti_cpi"),
    expected_indicators=INTEGRITY_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1,),
    default_source_weights=(
        ("wgi", 1.0),
        ("vdem", 0.8),
        ("ti_cpi", 0.9),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["INTEGRITY_INDICATORS", "INTEGRITY_PLAN"]
