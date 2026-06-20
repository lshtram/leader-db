"""Shared test fixtures and helpers for the nuclear scorer tests.

These helpers are not pytest fixtures — they are factory
functions that take keyword arguments and return constructed
instances, so the test bodies read naturally:

    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

The leading underscore keeps pytest from collecting this file as
a test module.

The factories mirror
:mod:`tests._international_peace_factories` so the
international_peace and nuclear test surfaces share a common
shape (per-scorer ``make_obs`` / ``make_bundle`` /
realistic-set helpers). All 8 NUCLEAR_PLAN indicators are
populated by :func:`realistic_nuclear_observations`. The
defaults are USA 2023 (a nuclear-armed state) so the happy-path
factory proves the scored path with the NUCLEAR_CASE flag; the
non-nuclear / no-observations path is tested separately via
the ``make_bundle`` factory with no observations and via
direct ``iso3="MEX"`` overrides.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.score.category_plans import NUCLEAR_PLAN
from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    EvidenceObservation,
    MissingObservation,
    TemporalKind,
)
from leaders_db.score.nuclear import CATEGORY_KEY


def nuclear_make_obs(
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

    The defaults are tuned for the nuclear plan: target year
    2023, direct temporal kind, LOWER_IS_BETTER direction.
    All 5 FAS indicators are LOWER_IS_BETTER in raw form (more
    warheads = bigger arsenal = more nuclear capability / risk);
    Stage 6 normalization inverts so the scorer sees 1 = best.
    For the 3 SIPRI Yearbook Ch.7 indicators the direction is
    set explicitly (2 are LOWER_IS_BETTER; ``retired`` is
    HIGHER_IS_BETTER). The test passes ``normalized_value``
    directly because Stage 6 normalization is upstream of the
    scorer.
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


def nuclear_make_bundle(
    *,
    observations: Iterable[EvidenceObservation] | None = None,
    missing: Iterable[MissingObservation] | None = None,
    leader_name: str | None = "Joe Biden",
    iso3: str = "USA",
    country_name: str = "United States",
) -> CategoryEvidenceBundle:
    """Build a :class:`CategoryEvidenceBundle` against the nuclear plan.

    The default iso3 is ``USA`` (a nuclear-armed state) so the
    realistic fixture clears the minimum-viable threshold and
    the scorer emits a real (non-insufficient-data) result
    with the :attr:`ReviewFlag.NUCLEAR_CASE` flag. Non-nuclear
    state tests pass ``iso3="MEX"`` (or any other non-nuclear
    iso3) and an empty observations list to exercise the
    insufficient-data branch.
    """
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country_name,
        leader_name=leader_name,
        year=2023,
        category_key=CATEGORY_KEY,
        source_plan=NUCLEAR_PLAN,
        observations=tuple(observations) if observations else (),
        missing=tuple(missing) if missing else (),
    )


def realistic_nuclear_observations() -> list[EvidenceObservation]:
    """Return a realistic USA 2023 nuclear observation set.

    All 8 NUCLEAR_PLAN indicators are present and DIRECT
    (target year 2023). The values are illustrative 0..1
    normalized figures (FAS arsenal ~0.30-0.45 — more warheads
    = lower normalized score on the 0..1 best scale, SIPRI
    Yearbook Ch.7 ~0.40-0.65 including the retired indicator
    which is HIGHER_IS_BETTER in raw form). They are
    illustrative, not real FAS / SIPRI numbers — the scorer
    treats ``normalized_value`` as Stage-6 output.

    The realistic fixture crosses both rubric groups (FAS +
    SIPRI) so the bundle clears the minimum-viable threshold
    (1 distinct source) by a wide margin and the scorer emits
    a real (non-insufficient-data) result with both the
    NUCLEAR_CASE population-split flag and the per-group
    components.
    """
    return [
        # FAS nuclear forces group (group weight 0.60; simple
        # mean of available indicators). The REQUIRED
        # ``fas_total_inventory`` plus the 4 PREFERRED /
        # FALLBACK indicators (Operational Strategic, Operational
        # Nonstrategic, Reserve/Nondeployed, Military Stockpile).
        # All 5 are LOWER_IS_BETTER in raw form (more warheads
        # = bigger arsenal = more nuclear capability / risk);
        # Stage 6 inverts so the scorer sees 1 = best (less
        # nuclear capability).
        nuclear_make_obs(
            "fas_operational_strategic", "fas", 0.30
        ),
        nuclear_make_obs(
            "fas_operational_nonstrategic", "fas", 0.40
        ),
        nuclear_make_obs(
            "fas_reserve_nondeployed", "fas", 0.45
        ),
        nuclear_make_obs(
            "fas_military_stockpile", "fas", 0.35
        ),
        nuclear_make_obs(
            "fas_total_inventory", "fas", 0.25
        ),
        # SIPRI Yearbook Ch.7 nuclear forces group (group
        # weight 0.40; simple mean of available indicators). The
        # REQUIRED ``sipri_yearbook_ch7_nuclear_warheads_total_inventory``
        # plus the PREFERRED ``deployed`` (LOWER_IS_BETTER) and
        # FALLBACK ``retired`` (HIGHER_IS_BETTER: more retired
        # = more disarmament progress = better). Stage 6
        # normalizes both directions so the scorer sees 1 =
        # best.
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
            "sipri_yearbook_ch7",
            0.40,
        ),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_deployed",
            "sipri_yearbook_ch7",
            0.55,
        ),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_retired",
            "sipri_yearbook_ch7",
            0.65,
            direction=Direction.HIGHER_IS_BETTER,
        ),
    ]


__all__ = [
    "nuclear_make_bundle",
    "nuclear_make_obs",
    "realistic_nuclear_observations",
]
