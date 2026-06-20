"""Shared test fixtures and helpers for the effectiveness scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = effectiveness_make_bundle(observations=realistic_effectiveness_observations())
    result = score_effectiveness(bundle)

The leading underscore keeps pytest from collecting this file as a
test module.

The factories mirror :mod:`tests._integrity_factories` so the
integrity and effectiveness test surfaces share a common shape
(per-scorer ``make_obs`` / ``make_bundle`` / realistic-set
helpers). All 12 EFFECTIVENESS_PLAN indicators are populated by
:func:`realistic_effectiveness_observations`.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import EFFECTIVENESS_PLAN
from leaders_db.score.effectiveness import CATEGORY_KEY
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)


def effectiveness_make_obs(
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

    The defaults are tuned for the effectiveness plan: target
    year 2023, direct temporal kind, HIGHER_IS_BETTER direction
    (the default for all WGI governance indicators, BTI composites,
    and the V-Dem governance indicators after Stage 6
    normalization). The test passes ``normalized_value``
    directly because Stage 6 normalization is upstream of the
    scorer.

    For V-Dem ``vdem_v2x_regime`` (the 0..3 regime classifier),
    Stage 6 normalization maps the 0..3 scale into 0..1 with 1
    "best"; the test does not override ``direction`` for that
    variable.
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


def effectiveness_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the effectiveness plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=EFFECTIVENESS_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_effectiveness_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All 12 EFFECTIVENESS_PLAN indicators are present and DIRECT
    (target year 2023). The values are illustrative 0..1
    normalized figures (WGI governance ~0.55-0.65, V-Dem
    governance / accountability ~0.55-0.70, BTI governance ~0.50).
    They are illustrative, not real WGI / V-Dem / BTI numbers —
    the scorer treats ``normalized_value`` as Stage-6 output.
    """
    return [
        # WGI governance group (group weight 0.45; simple mean of
        # available WGI governance indicators). The two REQUIRED
        # indicators (government_effectiveness, rule_of_law) are
        # listed alongside the three PREFERRED.
        effectiveness_make_obs(
            "wgi_voice_and_accountability", "wgi", 0.60
        ),
        effectiveness_make_obs(
            "wgi_political_stability", "wgi", 0.55
        ),
        effectiveness_make_obs(
            "wgi_government_effectiveness", "wgi", 0.65
        ),
        effectiveness_make_obs(
            "wgi_regulatory_quality", "wgi", 0.60
        ),
        effectiveness_make_obs(
            "wgi_rule_of_law", "wgi", 0.50
        ),
        # V-Dem governance / accountability group (group weight
        # 0.35; simple mean of available V-Dem indicators). The
        # REQUIRED vdem_v2x_accountability plus the four
        # PREFERRED/FALLBACK indicators.
        effectiveness_make_obs("vdem_v2x_jucon", "vdem", 0.60),
        effectiveness_make_obs("vdem_v2xlg_legcon", "vdem", 0.55),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
        effectiveness_make_obs("vdem_v2x_mpi", "vdem", 0.55),
        effectiveness_make_obs("vdem_v2x_regime", "vdem", 0.70),
        # BTI governance group (group weight 0.20; simple mean of
        # available BTI governance composites). The REQUIRED
        # bti_governance_index plus the PREFERRED
        # bti_governance_performance.
        effectiveness_make_obs("bti_governance_index", "bti", 0.50),
        effectiveness_make_obs("bti_governance_performance", "bti", 0.55),
    ]


__all__ = [
    "effectiveness_make_bundle",
    "effectiveness_make_obs",
    "realistic_effectiveness_observations",
]
