"""Shared test fixtures and helpers for the integrity scorer tests.

These helpers are not pytest fixtures — they are factory functions
that take keyword arguments and return constructed instances, so
the test bodies read naturally:

    bundle = integrity_make_bundle(observations=_realistic_integrity_observations())
    result = score_integrity(bundle)

The leading underscore keeps pytest from collecting this file as a
test module.

The factories mirror :mod:`tests._social_wellbeing_factories` so
the social_wellbeing and integrity test surfaces share a common
shape (per-scorer ``make_obs`` / ``make_bundle`` / realistic-set
helpers).
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import INTEGRITY_PLAN
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)
from leaders_db.score.integrity import CATEGORY_KEY


def integrity_make_obs(
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

    The defaults are tuned for the integrity plan: target year
    2023, direct temporal kind, HIGHER_IS_BETTER direction (the
    default for WGI Control of Corruption and TI CPI; V-Dem
    corruption indicators are LOWER_IS_BETTER but Stage 6
    normalization inverts them so the scorer sees HIGHER_IS_BETTER
    normalized values). The test passes ``normalized_value``
    directly because Stage 6 normalization is upstream of the
    scorer.

    For V-Dem variables the test can override ``direction`` to
    ``LOWER_IS_BETTER`` to mimic the raw direction — Stage 6
    still feeds the scorer a 0..1 value where 1 is "best".
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


def integrity_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Andrés Manuel López Obrador",
    iso3: str = "MEX",
    country_name: str = "Mexico",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the integrity plan."""
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=INTEGRITY_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_integrity_observations() -> list[EvidenceObservation]:
    """Return a realistic Mexico 2023 observation set.

    All five INTEGRITY_PLAN indicators are present and DIRECT
    (target year 2023). The values are illustrative 0..1
    normalized figures (WGI ~0.65, V-Dem corruption inverted to
    "less corrupt" framing ~0.70, CPI ~0.30). They are
    illustrative, not real WGI / V-Dem / TI CPI numbers — the
    scorer treats ``normalized_value`` as Stage-6 output.

    The V-Dem indicators here carry ``LOWER_IS_BETTER`` direction
    in the raw data; Stage 6 normalizes them to the 0..1
    high-is-better scale that the scorer consumes.
    """
    return [
        # WGI Control of Corruption — REQUIRED (group weight 0.35).
        integrity_make_obs(
            "wgi_control_of_corruption", "wgi", 0.65
        ),
        # V-Dem political-corruption composite — REQUIRED + PREFERRED
        # (group weight 0.35, mean of available indicators).
        integrity_make_obs(
            "vdem_v2x_corr", "vdem", 0.70,
            direction=Direction.LOWER_IS_BETTER,
        ),
        integrity_make_obs(
            "vdem_v2x_execorr", "vdem", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        integrity_make_obs(
            "vdem_v2x_pubcorr", "vdem", 0.60,
            direction=Direction.LOWER_IS_BETTER,
        ),
        # Transparency International CPI — REQUIRED (group weight 0.30).
        integrity_make_obs("cpi_score", "ti_cpi", 0.30),
    ]


__all__ = [
    "integrity_make_bundle",
    "integrity_make_obs",
    "realistic_integrity_observations",
]
