"""Source plan for the ``nuclear`` rating category.

The plan enumerates the canonical sources and indicators for the
"Global nuclear responsibility / global existential responsibility"
category from requirement §4. Per requirement §6 the canonical
sources are FAS and SIPRI Yearbook Ch.7; NTI is blocked
(Cloudflare 403 per ``docs/sources/vetting/report.md`` §11) so it
is not in the plan. The plan widens once NTI is unblocked.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/fas.csv`` (5 indicators) and
``src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv`` (3
indicators). All FAS indicators are LOWER_IS_BETTER (more warheads
= more nuclear risk); SIPRI's ``retired`` indicator is
HIGHER_IS_BETTER (more retired warheads = more disarmament
activity = better peace signal per the SIPRI catalog header).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`NUCLEAR_PLAN`. Variable names match
#: the per-source catalogs: ``fas.csv`` (5 indicators on the
#: consolidated "Status of World Nuclear Forces" page) and
#: ``sipri_yearbook_ch7.csv`` (3 indicators from Table 7.1 of the
#: SIPRI Yearbook 2024).
NUCLEAR_INDICATORS: tuple[IndicatorSpec, ...] = (
    # FAS (Federation of American Scientists) — the consolidated
    # snapshot page covers the 9 nuclear-armed states with 5 numeric
    # columns. Direction is LOWER_IS_BETTER (more warheads = more
    # nuclear risk) per the FAS catalog header.
    IndicatorSpec(
        "fas_operational_strategic",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="fas",
    ),
    IndicatorSpec(
        "fas_operational_nonstrategic",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="fas",
    ),
    IndicatorSpec(
        "fas_reserve_nondeployed",
        IndicatorRole.FALLBACK,
        Direction.LOWER_IS_BETTER,
        source_key="fas",
    ),
    IndicatorSpec(
        "fas_military_stockpile",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="fas",
    ),
    IndicatorSpec(
        "fas_total_inventory",
        IndicatorRole.REQUIRED,
        Direction.LOWER_IS_BETTER,
        source_key="fas",
    ),
    # SIPRI Yearbook Ch.7 (World Nuclear Forces) — the second
    # independent source for nuclear arsenal facts. ``total_inventory``
    # and ``deployed`` are LOWER_IS_BETTER (more warheads = bigger
    # arsenal = more nuclear capability) per the SIPRI catalog
    # header. ``retired`` is HIGHER_IS_BETTER (more retired
    # warheads = more disarmament activity = better peace signal).
    IndicatorSpec(
        "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
        IndicatorRole.REQUIRED,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_yearbook_ch7",
    ),
    IndicatorSpec(
        "sipri_yearbook_ch7_nuclear_warheads_deployed",
        IndicatorRole.PREFERRED,
        Direction.LOWER_IS_BETTER,
        source_key="sipri_yearbook_ch7",
    ),
    IndicatorSpec(
        "sipri_yearbook_ch7_nuclear_warheads_retired",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="sipri_yearbook_ch7",
    ),
)

#: Plan for the ``nuclear`` category. The
#: minimum-viable-sources threshold is 1 because the plan covers
#: the 9 nuclear-armed states only; the consolidated FAS snapshot
#: and the SIPRI Yearbook Ch.7 PDF are both keyed to that small
#: population. ``sparse_data_policy`` is
#: :attr:`SparseDataPolicy.PROVISIONAL_SCORE` so non-nuclear
#: states (the majority) still receive a categorical "non-nuclear"
#: label rather than a numeric score; the per-category scorer
#: handles that specialization. ``allowed_proxy_years`` is
#: widened to 2 because the consolidated FAS snapshot's
#: ``<meta name="date">`` is dated 2014-04-30 (per the FAS
#: catalog header) — the temporal-fit gap to the 2023 target
#: year is large and the per-plan proxy budget accommodates it.
NUCLEAR_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="nuclear",
    expected_sources=("fas", "sipri_yearbook_ch7"),
    expected_indicators=NUCLEAR_INDICATORS,
    minimum_viable_sources=1,
    preferred_direct_year=2023,
    allowed_proxy_years=(1, 2),
    default_source_weights=(
        ("fas", 1.0),
        ("sipri_yearbook_ch7", 1.0),
    ),
    sparse_data_policy=SparseDataPolicy.PROVISIONAL_SCORE,
)

__all__ = ["NUCLEAR_INDICATORS", "NUCLEAR_PLAN"]
