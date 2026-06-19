"""Source plan for the ``political_freedom`` rating category.

The plan enumerates the canonical sources and indicators for the
"Political freedom vs authoritarian rule" category from
requirement §4. Per requirement §6 the canonical sources are V-Dem
(531-indicator expert-coded), Polity V (1800-2018), and RSF
press freedom. Freedom House is "user-managed" (per
``docs/source-vetting-report.md`` §3.4) and Polity V is "yet to be
implemented" in Stage 2; the plan ships with V-Dem + RSF + BTI
(Bertelsmann Transformation Index) until the remaining Stage 2
adapters land. BTI is the third source because its 7 political-
transformation composites overlap substantially with V-Dem's
electoral / liberal-democracy / civil-liberties subdimensions and
provide a second expert-coded methodology.

Variable names match the per-source catalogs:
``src/leaders_db/ingest/catalogs/vdem.csv`` (7 polyarchy /
liberal-democracy / civil-liberties indicators),
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv`` (2
indicators: the headline score + the political-context
component), and ``src/leaders_db/ingest/catalogs/bti.csv`` (7
political-transformation questions: status index, democracy
status, Q1 stateness, Q2 participation, Q3 rule of law, Q4
democratic institutions, Q5 political/social integration).
"""

from __future__ import annotations

from ..evidence import CategorySourcePlan, Direction, IndicatorRole, IndicatorSpec, SparseDataPolicy

#: Indicators in the :data:`POLITICAL_FREEDOM_PLAN`. Variable
#: names match the per-source catalogs.
POLITICAL_FREEDOM_INDICATORS: tuple[IndicatorSpec, ...] = (
    # V-Dem — the canonical political-freedom signal for the
    # prototype. The 7 indicators cover electoral, liberal, civil
    # liberties, and rule-of-law subdimensions (per the V-Dem
    # catalog).
    IndicatorSpec(
        "vdem_v2x_polyarchy",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_libdem",
        IndicatorRole.REQUIRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_freexp",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_frassoc_thick",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_suffr",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_rule",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    IndicatorSpec(
        "vdem_v2x_civlib",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="vdem",
    ),
    # RSF (Reporters Without Borders) — the press-freedom
    # sub-signal. The headline score is HIGHER_IS_BETTER (closer
    # to a free press); the rank column is excluded from the
    # scoring plan (rank is a derived ranking, not an independent
    # measurement).
    IndicatorSpec(
        "rsf_press_freedom_score",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="rsf_press_freedom",
    ),
    IndicatorSpec(
        "rsf_press_freedom_political_context",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="rsf_press_freedom",
    ),
    # BTI (Bertelsmann Transformation Index) — the 7 political-
    # transformation composites / questions from the catalog.
    # All 1-10 BTI scores are HIGHER_IS_BETTER (10 = best per
    # the BTI catalog header).
    IndicatorSpec(
        "bti_status_index",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_democracy_status",
        IndicatorRole.PREFERRED,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q1_stateness",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q2_political_participation",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q3_rule_of_law",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q4_democratic_institutions",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
    IndicatorSpec(
        "bti_q5_political_social_integration",
        IndicatorRole.FALLBACK,
        Direction.HIGHER_IS_BETTER,
        source_key="bti",
    ),
)

#: Plan for the ``political_freedom`` category. Polity V and
#: Freedom House are "yet to be implemented" / "user-managed"
#: per the source-vetting report and so are not in the plan; the
#: plan will widen once those Stage 2 adapters land.
POLITICAL_FREEDOM_PLAN: CategorySourcePlan = CategorySourcePlan(
    category_key="political_freedom",
    expected_sources=("vdem", "rsf_press_freedom", "bti"),
    expected_indicators=POLITICAL_FREEDOM_INDICATORS,
    minimum_viable_sources=2,
    preferred_direct_year=2023,
    allowed_proxy_years=(1,),
    default_source_weights=(
        ("vdem", 1.0),
        ("rsf_press_freedom", 0.7),
        ("bti", 0.8),
    ),
    sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
)

__all__ = ["POLITICAL_FREEDOM_INDICATORS", "POLITICAL_FREEDOM_PLAN"]
