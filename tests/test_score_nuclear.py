"""Tests for the nuclear deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.nuclear.score_nuclear`:

- (a) A realistic bundle produces a :class:`ScoreResult` with
      the right category key, ISO3, year, leader, and 1..10
      integer score.
- (b) The 2-group weighted-average rubric structure (per-group
      weights, group contribution math, normalized-score sum).
- (c) The NUCLEAR_CASE population-split flag fires on the
      scored path iff the bundle carries any usable
      nuclear-source observation (the §14 manual-review-queue
      hook per REQ-REV-002).
- (d) Missingness summary: ``total_expected`` /
      ``total_observed`` and the by_reason / by_severity rollups.

Component / observation-ref bookkeeping, the scale mapping, the
rationale, the leader fallback, and the client-source boundary
exclusion live in the sibling file
:mod:`tests.test_score_nuclear_components`. Flag-detection tests
live in :mod:`tests.test_score_nuclear_flags`. Insufficient-data
branch flag derivation lives in
:mod:`tests.test_score_nuclear_insufficient_flags`. Client-
contamination regression tests live in
:mod:`tests.test_score_nuclear_remediation`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import NUCLEAR_PLAN
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.nuclear import CATEGORY_KEY, score_nuclear
from leaders_db.score.results import ReviewFlag, ScoreComponent, ScoreResult
from tests._nuclear_factories import (
    nuclear_make_bundle,
    realistic_nuclear_observations,
)

# (a) Happy path


def test_score_nuclear_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "nuclear"
    assert result.iso3 == "USA"
    assert result.year == 2023
    assert result.leader_name == "Joe Biden"
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    # The result is not the insufficient-data variant.
    assert result.is_insufficient_data is False
    assert result.is_provisional is False
    # The nuclear-case population-split flag fires on the
    # scored path because the bundle carries usable FAS /
    # SIPRI Yearbook Ch.7 observations.
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags
    # Client comparison is downstream — the scorer leaves the slot empty.
    assert result.score_delta_vs_client is None


def test_score_nuclear_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_nuclear_realistic_bundle_expected_score() -> None:
    """The realistic bundle produces the expected 1..10 score.

    The realistic fixture values:

    - FAS nuclear forces group (weight 0.60): mean of
      ``(0.30, 0.40, 0.45, 0.35, 0.25)`` = 1.75 / 5 = 0.35 →
      contribution 0.60 × 0.35 = 0.21.
    - SIPRI Yearbook Ch.7 nuclear forces group (weight 0.40):
      mean of ``(0.40, 0.55, 0.65)`` = 1.60 / 3 ≈ 0.5333... →
      contribution 0.40 × 0.5333... ≈ 0.21333...

    Sum: 0.21 + 0.21333... ≈ 0.42333... The 1..10 mapping
    yields ``floor(1 + 9 × 0.42333... + 0.5)`` = ``floor(5.31)``
    = 5.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert result.normalized_score_0_1 is not None
    assert result.normalized_score_0_1 == pytest.approx(0.4233333333, abs=1e-6)
    assert result.system_proposed_score_1_10 == 5


# ---------------------------------------------------------------------------
# (b) The 2-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_nuclear_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The two nuclear groups are FAS (0.60) and SIPRI Yearbook
    Ch.7 (0.40). Within a group,
    ``per_obs_weight = group_weight / count_in_group`` so per-
    component weights inside the group sum to the group weight.
    The realistic fixture has 5 FAS and 3 SIPRI observations.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    by_group: dict[str, list[ScoreComponent]] = {}
    for component in result.components:
        by_group.setdefault(component.component_key, []).append(component)

    total_weight = 0.0
    for group_key, components in by_group.items():
        group_weight = sum(c.weight for c in components)
        total_weight += group_weight
        weights = {round(c.weight, 9) for c in components}
        assert len(weights) == 1, (
            f"group {group_key!r} has non-uniform weights: {weights}"
        )
    assert total_weight == pytest.approx(1.0, abs=1e-9)

    # FAS group: 5 indicators, group mean is 0.35, group
    # contribution is 0.60 × 0.35 = 0.21.
    fas_components = [
        c
        for c in result.components
        if c.component_key == "nuclear__fas_nuclear_forces"
    ]
    assert len(fas_components) == 5
    per_obs_weight = 0.60 / 5
    expected_mean = (0.30 + 0.40 + 0.45 + 0.35 + 0.25) / 5
    for component in fas_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(c.contribution_0_1 for c in fas_components) == pytest.approx(
        0.60 * expected_mean, abs=1e-9
    )


def test_score_nuclear_fas_group_uses_mean_of_indicators() -> None:
    """The FAS nuclear forces group emits one component per indicator
    and its contribution equals ``group_weight * mean(indicator values)``.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    fas_components = [
        c
        for c in result.components
        if c.component_key == "nuclear__fas_nuclear_forces"
    ]
    assert len(fas_components) == 5
    per_obs_weight = 0.60 / 5
    expected_mean = (0.30 + 0.40 + 0.45 + 0.35 + 0.25) / 5
    for component in fas_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(
        c.contribution_0_1 for c in fas_components
    ) == pytest.approx(0.60 * expected_mean, abs=1e-9)


def test_score_nuclear_sipri_group_uses_mean_of_indicators() -> None:
    """The SIPRI Yearbook Ch.7 nuclear forces group emits one component
    per indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    sipri_components = [
        c
        for c in result.components
        if c.component_key == "nuclear__sipri_yearbook_ch7_nuclear_forces"
    ]
    assert len(sipri_components) == 3
    per_obs_weight = 0.40 / 3
    expected_mean = (0.40 + 0.55 + 0.65) / 3
    for component in sipri_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(
        c.contribution_0_1 for c in sipri_components
    ) == pytest.approx(0.40 * expected_mean, abs=1e-9)


def test_score_nuclear_two_groups_distinct() -> None:
    """The realistic fixture spans both expected groups / sources."""
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    component_source_keys = {c.source_key for c in result.components}
    assert component_source_keys == {"fas", "sipri_yearbook_ch7"}

    group_keys = {c.component_key for c in result.components}
    expected_groups = {
        "nuclear__fas_nuclear_forces",
        "nuclear__sipri_yearbook_ch7_nuclear_forces",
    }
    assert group_keys == expected_groups


# ---------------------------------------------------------------------------
# (c) The NUCLEAR_CASE population-split flag
# ---------------------------------------------------------------------------


def test_score_nuclear_nuclear_case_flag_fires_on_scored_path() -> None:
    """A scored bundle with usable nuclear-source observations fires
    :attr:`ReviewFlag.NUCLEAR_CASE`.

    The flag is the §14 manual-review-queue hook per
    REQ-REV-002 ("nuclear / global responsibility cases") and
    fires iff the bundle carries at least one usable FAS /
    SIPRI Yearbook Ch.7 observation.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags
    # The flag fires AFTER the scored-path-derived flags so
    # the manual-review queue can still sort on the existing
    # primary / sparse / low-confidence signals first.
    assert result.review_flags[-1] is ReviewFlag.NUCLEAR_CASE
    # The flag is the population-split signal — the
    # human_review_required invariant fires because the flag
    # is non-empty.
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (d) Missingness summary
# ---------------------------------------------------------------------------


def test_score_nuclear_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        NUCLEAR_PLAN.expected_indicators
    )
    # We observed all 8 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 8
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_nuclear_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="fas",
            variable_name="fas_total_inventory",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="sipri_yearbook_ch7",
            variable_name=(
                "sipri_yearbook_ch7_nuclear_warheads_total_inventory"
            ),
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="fas",
            variable_name="fas_operational_strategic",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = nuclear_make_bundle(
        observations=realistic_nuclear_observations(),
        missing=missing,
    )
    result = score_nuclear(bundle)

    assert result.missingness is not None
    assert dict(result.missingness.by_reason) == {
        "raw_file_absent": 1,
        "target_year_absent": 1,
        "country_row_absent": 1,
    }
    assert dict(result.missingness.by_severity) == {
        "primary": 2,
        "important": 1,
    }


def test_score_nuclear_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``nuclear``."""
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)
    assert result.category_key == CATEGORY_KEY == "nuclear"
