"""Shared test fixtures and helpers for the international-peace scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

The leading underscore keeps pytest from collecting this file as
a test module.

The factories mirror :mod:`tests._domestic_violence_factories` so
the domestic_violence and international_peace test surfaces share
a common shape (per-scorer ``make_obs`` / ``make_bundle`` /
realistic-set helpers). All 8 INTERNATIONAL_PEACE_PLAN indicators
are populated by :func:`realistic_international_peace_observations`.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import INTERNATIONAL_PEACE_PLAN
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)
from leaders_db.score.international_peace import CATEGORY_KEY


def international_peace_make_obs(
    variable_name: str,
    source_key: str,
    normalized_value: float,
    *,
    observation_year: int = 2023,
    temporal_kind: TemporalKind = TemporalKind.DIRECT,
    direction: Direction = Direction.LOWER_IS_BETTER,
    numeric_value: float | None = None,
) -> EvidenceObservation:
    """Build an :class:`EvidenceObservation` with sensible defaults.

    The defaults are tuned for the international-peace plan: target
    year 2023, direct temporal kind, LOWER_IS_BETTER direction.
    All 8 ``INTERNATIONAL_PEACE_PLAN`` indicators are
    LOWER_IS_BETTER in raw form (more conflict / more military
    spending = worse peace signal). Stage 6 normalization inverts
    the raw values so the scorer sees a 0..1 high-is-better scale
    where 1 = best (i.e. more peace / less military burden). The
    test passes ``normalized_value`` directly because Stage 6
    normalization is upstream of the scorer.
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


def international_peace_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the international-peace plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=INTERNATIONAL_PEACE_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_international_peace_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All 8 INTERNATIONAL_PEACE_PLAN indicators are present and
    DIRECT (target year 2023). The values are illustrative 0..1
    normalized figures (UCDP conflict involvement ~0.55-0.70,
    SIPRI military expenditure ~0.45-0.65). They are illustrative,
    not real UCDP / SIPRI milex numbers — the scorer treats
    ``normalized_value`` as Stage-6 output.
    """
    return [
        # UCDP conflict involvement group (group weight 0.65;
        # simple mean of available indicators). The REQUIRED
        # ``ucdp_state_based_fatalities`` plus the 3 PREFERRED
        # event-based indicators (state-based events + the
        # internationalized subset). All 4 are LOWER_IS_BETTER
        # in raw form (more deaths = worse); Stage 6 inverts so
        # the scorer sees 1 = best.
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "ucdp_state_based_fatalities", "ucdp", 0.60
        ),
        international_peace_make_obs(
            "ucdp_intl_events", "ucdp", 0.55
        ),
        international_peace_make_obs(
            "ucdp_intl_fatalities", "ucdp", 0.70
        ),
        # SIPRI Military Expenditure group (group weight 0.35;
        # simple mean of available indicators). The PREFERRED
        # ``sipri_milex_share_of_gdp`` plus the 3 FALLBACK
        # indicators (per capita, constant USD, share of govt
        # spending). All 4 are LOWER_IS_BETTER in raw form (more
        # spending = worse); Stage 6 inverts so the scorer sees
        # 1 = best.
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
        international_peace_make_obs(
            "sipri_milex_per_capita", "sipri_milex", 0.60
        ),
        international_peace_make_obs(
            "sipri_milex_constant_usd", "sipri_milex", 0.50
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_govt_spending",
            "sipri_milex",
            0.65,
        ),
    ]


__all__ = [
    "international_peace_make_bundle",
    "international_peace_make_obs",
    "realistic_international_peace_observations",
]
