"""Shared test fixtures and helpers for the economic wellbeing scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

The leading underscore keeps pytest from collecting this file as a
test module.

The factories mirror :mod:`tests._effectiveness_factories` so the
effectiveness and economic_wellbeing test surfaces share a common
shape (per-scorer ``make_obs`` / ``make_bundle`` / realistic-set
helpers). All 12 ECONOMIC_WELLBEING_PLAN indicators are populated
by :func:`realistic_economic_wellbeing_observations`.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import ECONOMIC_WELLBEING_PLAN
from leaders_db.score.economic_wellbeing import CATEGORY_KEY
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)


def economic_wellbeing_make_obs(
    variable_name: str,
    source_key: str,
    normalized_value: float,
    *,
    observation_year: int = 2023,
    temporal_kind: TemporalKind = TemporalKind.DIRECT,
    direction: Direction = Direction.HIGHER_IS_BETTER,
    numeric_value: float | None = None,
) -> EvidenceObservation:
    """Build an :class:`EvidenceObservation` with sensible defaults.

    The defaults are tuned for the economic wellbeing plan: target
    year 2023, direct temporal kind, HIGHER_IS_BETTER direction
    (the default for all WDI per-capita / scale / openness /
    investment indicators and all BTI economic-transformation
    questions). The test passes ``normalized_value`` directly
    because Stage 6 normalization is upstream of the scorer.
    """
    if numeric_value is None:
        numeric_value = normalized_value
    return EvidenceObservation(
        source_key=source_key,
        source_name=f"{source_key} (test fixture)",
        variable_name=variable_name,
        raw_value=f"{numeric_value:.4f}",
        numeric_value=numeric_value,
        normalized_value=normalized_value,
        unit="index",
        direction=direction,
        observation_year=observation_year,
        target_year=2023,
        temporal_kind=temporal_kind,
        source_row_reference=(
            f"{source_key}:{variable_name}:{observation_year}"
        ),
        authority_score=70,
        specificity_score=80,
    )


def economic_wellbeing_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the economic wellbeing plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=ECONOMIC_WELLBEING_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_economic_wellbeing_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All 12 ECONOMIC_WELLBEING_PLAN indicators are present and
    DIRECT (target year 2023). The values are illustrative 0..1
    normalized figures (WDI per-capita prosperity ~0.55-0.65,
    WDI scale / openness / investment ~0.50-0.65, BTI economic
    transformation ~0.50). They are illustrative, not real
    WDI / BTI numbers — the scorer treats ``normalized_value``
    as Stage-6 output.
    """
    return [
        # WDI per-capita prosperity group (group weight 0.45;
        # simple mean of available per-capita prosperity
        # indicators). The two REQUIRED indicators
        # (wdi_gdp_per_capita, wdi_gdp_per_capita_ppp_constant_2017)
        # plus the PREFERRED wdi_gni_per_capita_atlas.
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita", "world_bank_wdi", 0.60
        ),
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita_ppp_constant_2017", "world_bank_wdi", 0.65
        ),
        economic_wellbeing_make_obs(
            "wdi_gni_per_capita_atlas", "world_bank_wdi", 0.55
        ),
        # WDI scale / openness / investment group (group weight
        # 0.25; simple mean of available normalized values).
        # The two PREFERRED GDP-size indicators (current + constant)
        # plus the four FALLBACK trade / FDI / population indicators.
        economic_wellbeing_make_obs(
            "wdi_gdp_current_usd", "world_bank_wdi", 0.60
        ),
        economic_wellbeing_make_obs(
            "wdi_gdp_constant_2015_usd", "world_bank_wdi", 0.55
        ),
        economic_wellbeing_make_obs(
            "wdi_exports_pct_gdp", "world_bank_wdi", 0.50
        ),
        economic_wellbeing_make_obs(
            "wdi_imports_pct_gdp", "world_bank_wdi", 0.55
        ),
        economic_wellbeing_make_obs(
            "wdi_fdi_inflows_current_usd", "world_bank_wdi", 0.45
        ),
        economic_wellbeing_make_obs(
            "wdi_population", "world_bank_wdi", 0.65
        ),
        # BTI economic transformation group (group weight 0.30;
        # simple mean of available BTI economic composites). All
        # three PREFERRED economic questions.
        economic_wellbeing_make_obs(
            "bti_q6_socioeconomic_development", "bti", 0.50
        ),
        economic_wellbeing_make_obs(
            "bti_q7_market_competition", "bti", 0.55
        ),
        economic_wellbeing_make_obs(
            "bti_q11_economic_performance", "bti", 0.50
        ),
    ]


__all__ = [
    "economic_wellbeing_make_bundle",
    "economic_wellbeing_make_obs",
    "realistic_economic_wellbeing_observations",
]
