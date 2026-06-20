"""Shared test fixtures and helpers for the domestic-violence scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

The leading underscore keeps pytest from collecting this file as
a test module.

The factories mirror :mod:`tests._political_freedom_factories` so
the political_freedom and domestic_violence test surfaces share a
common shape (per-scorer ``make_obs`` / ``make_bundle`` /
realistic-set helpers). All 17 DOMESTIC_VIOLENCE_PLAN indicators
are populated by :func:`realistic_domestic_violence_observations`.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import DOMESTIC_VIOLENCE_PLAN
from leaders_db.score.domestic_violence import CATEGORY_KEY
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)


def domestic_violence_make_obs(
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

    The defaults are tuned for the domestic-violence plan: target
    year 2023, direct temporal kind, HIGHER_IS_BETTER direction.
    The scorer's contract is "high value = less violence /
    repression", so PTS (LOWER_IS_BETTER raw), UCDP one-sided
    counts (LOWER_IS_BETTER raw), and the V-Dem repression point
    estimates ``v2csreprss`` / ``v2clkill`` (LOWER_IS_BETTER raw)
    are normalized to the 0..1 high-is-better scale that the
    scorer consumes by Stage 6 normalization. The test passes
    ``normalized_value`` directly because Stage 6 normalization
    is upstream of the scorer.

    For PTS / UCDP one-sided / V-Dem repression variables the
    test can override ``direction`` to ``LOWER_IS_BETTER`` to
    mimic the raw direction.
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


def domestic_violence_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the domestic-violence plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=DOMESTIC_VIOLENCE_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_domestic_violence_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All 17 DOMESTIC_VIOLENCE_PLAN indicators are present and
    DIRECT (target year 2023). The values are illustrative 0..1
    normalized figures (PTS state terror ~0.55-0.65, CIRIGHTS
    physical-integrity ~0.50-0.70, UCDP one-sided ~0.65-0.70,
    V-Dem civil-liberties / repression ~0.45-0.65). They are
    illustrative, not real PTS / CIRIGHTS / UCDP / V-Dem numbers —
    the scorer treats ``normalized_value`` as Stage-6 output.
    """
    return [
        # PTS state-terror group (group weight 0.30; simple
        # mean of available parallel scores). The REQUIRED
        # pts_amnesty_score plus the two PREFERRED parallel
        # scores. All three are LOWER_IS_BETTER in raw form
        # (PTS 1-5 ordinal scale where higher = more terror);
        # Stage 6 inverts so the scorer sees 1 = best.
        domestic_violence_make_obs(
            "pts_amnesty_score", "pts", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "pts_human_rights_watch_score", "pts", 0.60,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "pts_state_dept_score", "pts", 0.55,
            direction=Direction.LOWER_IS_BETTER,
        ),
        # CIRIGHTS physical-integrity / repression group
        # (group weight 0.35; simple mean of available
        # indicators). The REQUIRED cirights_physint plus
        # the Repression / Disap / Kill / PolPris / Tort
        # PREFERRED components plus the FALLBACK CivPol
        # additive index. All HIGHER_IS_BETTER per the
        # CIRIGHTS catalog (higher index = more rights
        # respect / less repression).
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs("cirights_repression", "cirights", 0.70),
        domestic_violence_make_obs("cirights_civpol", "cirights", 0.60),
        domestic_violence_make_obs("cirights_disap", "cirights", 0.55),
        domestic_violence_make_obs("cirights_kill", "cirights", 0.50),
        domestic_violence_make_obs("cirights_polpris", "cirights", 0.55),
        domestic_violence_make_obs("cirights_tort", "cirights", 0.60),
        # UCDP one-sided violence group (group weight 0.20;
        # simple mean of available event-based indicators).
        # Both PREFERRED (events + fatalities) are
        # LOWER_IS_BETTER in raw form (more deaths = worse);
        # Stage 6 inverts so the scorer sees 1 = best.
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "ucdp_onesided_fatalities", "ucdp", 0.70,
            direction=Direction.LOWER_IS_BETTER,
        ),
        # V-Dem civil-liberties / repression group (group
        # weight 0.15; simple mean of available indicators).
        # 3 HIGHER_IS_BETTER liberties (Physical Violence,
        # Political Civil Liberties, Private Civil Liberties)
        # plus 2 LOWER_IS_BETTER repression point estimates
        # (CSO Repression, Political Killings). Stage 6
        # inverts the LOWER_IS_BETTER raw so the scorer sees
        # 1 = best.
        domestic_violence_make_obs("vdem_v2x_clphy", "vdem", 0.65),
        domestic_violence_make_obs("vdem_v2x_clpol", "vdem", 0.55),
        domestic_violence_make_obs("vdem_v2x_clpriv", "vdem", 0.60),
        domestic_violence_make_obs(
            "vdem_v2csreprss", "vdem", 0.45,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "vdem_v2clkill", "vdem", 0.50,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]


__all__ = [
    "domestic_violence_make_bundle",
    "domestic_violence_make_obs",
    "realistic_domestic_violence_observations",
]
