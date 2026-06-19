"""Source plan for the ``domestic_violence`` rating category.

The plan enumerates the canonical sources and indicators for the
"Domestic safety vs domestic violence, oppression, and incitement"
category from requirement §4. Per requirement §6 the canonical
sources are PTS (state-terror expert-coded), CIRIGHTS
(physical-integrity rights indices), and UCDP one-sided violence
(event-based). V-Dem physical-integrity / civil-liberties
indicators are added as the 4th source for cross-validation.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/pts.csv`` (3 parallel scores),
``src/leaders_db/ingest/catalogs/cirights.csv`` (7 indicators —
4 physical-integrity components + 3 additive indices),
``src/leaders_db/ingest/catalogs/ucdp.csv`` (2 one-sided
indicators), and ``src/leaders_db/ingest/catalogs/vdem.csv`` (5
indicators: 3 physical/political/private civil-liberties + 2
repression/killings point estimates).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`DOMESTIC_VIOLENCE_PLAN`. Variable
#: names match the per-source catalogs.
DOMESTIC_VIOLENCE_INDICATORS: tuple[IndicatorSpec, ...] = (
    # PTS (3 parallel scores per the 3-indicator choice in
    # docs/architecture/pts.md §3).
    IndicatorSpec(
        "pts_amnesty_score",
        IndicatorRole.REQUIRED,
        Direction.LOWER_IS_BETTER,
        source_key="pts",
    ),
    IndicatorSpec(
        "pts_human_rights_watch_score",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="pts",
    ),
    IndicatorSpec(
        "pts_state_dept_score",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="pts",
    ),
    # CIRIGHTS — the 4 physical-integrity components + the 3
    # additive indices. All HIGHER_IS_BETTER (CIRIGHTS convention:
    # higher index = more rights respect / less repression per the
    # CIRIGHTS catalog header §"Scale / Direction").
    IndicatorSpec(
        "cirights_physint",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_repression",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_civpol",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_disap",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_kill",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_polpris",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    IndicatorSpec(
        "cirights_tort",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="cirights",
    ),
    # UCDP one-sided violence (state-perpetrated violence against
    # civilians).
    IndicatorSpec(
        "ucdp_onesided_events",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    IndicatorSpec(
        "ucdp_onesided_fatalities",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="ucdp",
    ),
    # V-Dem physical-integrity / civil-liberties / repression
    # indicators. HIGHER_IS_BETTER for the 3 liberties;
    # LOWER_IS_BETTER for the 2 repression point estimates (per
    # the V-Dem catalog header "Scale conventions" and the
    # codebook: v2csreprss and v2clkill are point estimates where
    # higher = more repression).
    IndicatorSpec(
        "vdem_v2x_clphy",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_clpol",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_clpriv",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2csreprss",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2clkill",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="vdem",
    ),
)

#: Plan for the ``domestic_violence`` category. ``allowed_proxy_years``
#: is widened to 2 because CIRIGHTS coverage ends 2022 (the CIRIGHTS
#: catalog header is explicit about the 1-year proxy for target
#: year 2023) and PTS / UCDP release schedules vary.
DOMESTIC_VIOLENCE_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="domestic_violence",
    expected_sources=("pts", "cirights", "ucdp", "vdem"),
    expected_indicators=DOMESTIC_VIOLENCE_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1, 2),
    default_source_weights=(
        ("pts", 1.0),
        ("cirights", 1.0),
        ("ucdp", 0.9),
        ("vdem", 0.8),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["DOMESTIC_VIOLENCE_INDICATORS", "DOMESTIC_VIOLENCE_PLAN"]
