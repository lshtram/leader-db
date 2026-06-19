"""Shared test fixtures and helpers for the social-wellbeing scorer tests.

These helpers are not pytest fixtures — they are factory
functions that take keyword arguments and return constructed
instances, so the test bodies read naturally:

    bundle = make_bundle(observations=_realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

The leading underscore keeps pytest from collecting this file as
a test module.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import SOCIAL_WELLBEING_PLAN
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)
from leaders_db.score.social_wellbeing import CATEGORY_KEY


def make_obs(
    variable_name: str,
    source_key: str,
    normalized_value: float,
    *,
    observation_year: int = 2023,
    temporal_kind: TemporalKind = TemporalKind.DIRECT,
    numeric_value: float | None = None,
) -> EvidenceObservation:
    """Build an :class:`EvidenceObservation` with sensible defaults.

    The defaults are tuned for the social-wellbeing plan: target
    year 2023, direct temporal kind, HIGHER_IS_BETTER direction,
    70/80 authority/specificity. The test passes
    ``normalized_value`` directly because Stage 6 normalization is
    upstream of the scorer.
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
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=observation_year,
        target_year=2023,
        temporal_kind=temporal_kind,
        source_row_reference=(
            f"{source_key}:{variable_name}:{observation_year}"
        ),
        authority_score=70,
        specificity_score=80,
    )


def make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the social-wellbeing plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=SOCIAL_WELLBEING_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_mexico_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    The values are plausible normalized 0..1 figures (HDI ~0.78,
    life expectancy ~0.70, literacy ~0.95, gini normalized so
    higher = more equal). They are illustrative, not real HDI
    numbers — the scorer treats ``normalized_value`` as Stage-6
    output.
    """
    return [
        # HDI composite anchor (REQUIRED).
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        # Health signal.
        make_obs("undp_hdi_life_expectancy", "undp_hdi", 0.70),
        make_obs("who_gho_under5_mortality", "who_gho_api", 0.85),
        make_obs("who_gho_dtp3_immunization", "who_gho_api", 0.85),
        # Education signal.
        make_obs(
            "undp_hdi_expected_years_schooling", "undp_hdi", 0.75
        ),
        make_obs("undp_hdi_mean_years_schooling", "undp_hdi", 0.65),
        make_obs("wdi_literacy_rate_adult", "world_bank_wdi", 0.95),
        # Income / standard-of-living.
        make_obs("undp_hdi_gni_per_capita", "undp_hdi", 0.70),
        # Inequality / social protection.
        make_obs("wdi_gini_index", "world_bank_wdi", 0.60),
        make_obs("vdem_v2x_egal", "vdem", 0.55),
    ]


__all__ = [
    "make_bundle",
    "make_obs",
    "realistic_mexico_observations",
]
