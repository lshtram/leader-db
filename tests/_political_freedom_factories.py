"""Shared test fixtures and helpers for the political freedom scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

The leading underscore keeps pytest from collecting this file as a
test module.

The factories mirror :mod:`tests._effectiveness_factories` so the
effectiveness and political_freedom test surfaces share a common
shape (per-scorer ``make_obs`` / ``make_bundle`` / realistic-set
helpers). All 16 POLITICAL_FREEDOM_PLAN indicators are populated
by :func:`realistic_political_freedom_observations`.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import POLITICAL_FREEDOM_PLAN
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)
from leaders_db.score.political_freedom import CATEGORY_KEY


def political_freedom_make_obs(
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

    The defaults are tuned for the political freedom plan: target
    year 2023, direct temporal kind, HIGHER_IS_BETTER direction
    (the default for all V-Dem polyarchy / liberal / civil-
    liberties indicators, RSF press-freedom indicators after Stage
    6 normalization, and BTI political-transformation questions
    on the 1-10 scale with 10 = best). The test passes
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


def political_freedom_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the political freedom plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=POLITICAL_FREEDOM_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_political_freedom_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All 16 POLITICAL_FREEDOM_PLAN indicators are present and
    DIRECT (target year 2023). The values are illustrative 0..1
    normalized figures (V-Dem democratic / liberal / civil-
    liberties ~0.45-0.65, BTI political transformation ~0.45-0.60,
    RSF press freedom ~0.50-0.60). They are illustrative, not
    real V-Dem / BTI / RSF numbers — the scorer treats
    ``normalized_value`` as Stage-6 output.
    """
    return [
        # V-Dem democratic / liberal / civil-liberties group
        # (group weight 0.50; simple mean of available indicators).
        # The two REQUIRED indicators (vdem_v2x_polyarchy,
        # vdem_v2x_libdem) plus the five PREFERRED indicators.
        political_freedom_make_obs(
            "vdem_v2x_polyarchy", "vdem", 0.50
        ),
        political_freedom_make_obs(
            "vdem_v2x_libdem", "vdem", 0.45
        ),
        political_freedom_make_obs("vdem_v2x_freexp", "vdem", 0.55),
        political_freedom_make_obs(
            "vdem_v2x_frassoc_thick", "vdem", 0.50
        ),
        political_freedom_make_obs("vdem_v2x_suffr", "vdem", 0.65),
        political_freedom_make_obs("vdem_v2x_rule", "vdem", 0.50),
        political_freedom_make_obs("vdem_v2x_civlib", "vdem", 0.55),
        # BTI political-transformation group (group weight 0.30;
        # simple mean of available indicators). The two PREFERRED
        # composites (status_index, democracy_status) plus the
        # five FALLBACK political-transformation questions.
        political_freedom_make_obs(
            "bti_status_index", "bti", 0.50
        ),
        political_freedom_make_obs(
            "bti_democracy_status", "bti", 0.55
        ),
        political_freedom_make_obs("bti_q1_stateness", "bti", 0.60),
        political_freedom_make_obs(
            "bti_q2_political_participation", "bti", 0.45
        ),
        political_freedom_make_obs("bti_q3_rule_of_law", "bti", 0.50),
        political_freedom_make_obs(
            "bti_q4_democratic_institutions", "bti", 0.55
        ),
        political_freedom_make_obs(
            "bti_q5_political_social_integration", "bti", 0.50
        ),
        # RSF press-freedom group (group weight 0.20; simple mean
        # of available indicators). The PREFERRED headline score
        # plus the FALLBACK political-context component.
        political_freedom_make_obs(
            "rsf_press_freedom_score", "rsf_press_freedom", 0.50
        ),
        political_freedom_make_obs(
            "rsf_press_freedom_political_context",
            "rsf_press_freedom",
            0.55,
        ),
    ]


__all__ = [
    "political_freedom_make_bundle",
    "political_freedom_make_obs",
    "realistic_political_freedom_observations",
]
