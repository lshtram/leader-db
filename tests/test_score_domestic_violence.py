"""Tests for the domestic-violence deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.domestic_violence.score_domestic_violence`:

- (a) A realistic bundle produces a :class:`ScoreResult` with
      the right category key, ISO3, year, leader, and 1..10
      integer score.
- (b) The 4-group weighted-average rubric structure (per-group
      weights, group contribution math, normalized-score sum).
- (c) Missingness summary: ``total_expected`` /
      ``total_observed`` and the by_reason / by_severity rollups.

Component / observation-ref bookkeeping, the scale mapping, the
rationale, the leader fallback, and the client-source boundary
exclusion live in the sibling file
:mod:`tests.test_score_domestic_violence_components`. Flag-
detection tests live in
:mod:`tests.test_score_domestic_violence_flags`. Insufficient-
data branch flag derivation lives in
:mod:`tests.test_score_domestic_violence_insufficient_flags`.
Client-contamination regression tests live in
:mod:`tests.test_score_domestic_violence_remediation`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import DOMESTIC_VIOLENCE_PLAN
from leaders_db.score.domestic_violence import (
    CATEGORY_KEY,
    score_domestic_violence,
)
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.results import ScoreComponent, ScoreResult
from tests._domestic_violence_factories import (
    domestic_violence_make_bundle,
    realistic_domestic_violence_observations,
)

# (a) Happy path


def test_score_domestic_violence_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "domestic_violence"
    assert result.iso3 == "MEX"
    assert result.year == 2023
    assert result.leader_name == "Andrés Manuel López Obrador"
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    # The result is not the insufficient-data variant.
    assert result.is_insufficient_data is False
    assert result.is_provisional is False
    # Client comparison is downstream — the scorer leaves the slot empty.
    assert result.score_delta_vs_client is None


def test_score_domestic_violence_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_domestic_violence_realistic_bundle_expected_score() -> None:
    """The realistic bundle produces the expected 1..10 score.

    The realistic fixture values:

    - PTS state-terror group (weight 0.30): mean of
      ``(0.65, 0.60, 0.55)`` = 1.80 / 3 = 0.60 → contribution
      0.30 × 0.60 = 0.18.
    - CIRIGHTS physical-integrity / repression group (weight
      0.35): mean of ``(0.65, 0.70, 0.60, 0.55, 0.50, 0.55,
      0.60)`` = 4.15 / 7 ≈ 0.5929 → contribution 0.35 × 0.5929
      ≈ 0.2075.
    - UCDP one-sided violence group (weight 0.20): mean of
      ``(0.65, 0.70)`` = 1.35 / 2 = 0.675 → contribution
      0.20 × 0.675 = 0.135.
    - V-Dem civil-liberties / repression group (weight 0.15):
      mean of ``(0.65, 0.55, 0.60, 0.45, 0.50)`` = 2.75 / 5
      = 0.55 → contribution 0.15 × 0.55 = 0.0825.

    Sum: 0.18 + 0.2075 + 0.135 + 0.0825 ≈ 0.605. The 1..10
    mapping yields ``floor(1 + 9 × 0.605 + 0.5)`` =
    ``floor(6.945)`` = 6.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    assert result.normalized_score_0_1 is not None
    assert result.normalized_score_0_1 == pytest.approx(0.605, abs=1e-6)
    assert result.system_proposed_score_1_10 == 6


# ---------------------------------------------------------------------------
# (b) The 4-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_domestic_violence_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The four domestic-violence groups are PTS (0.30), CIRIGHTS
    (0.35), UCDP (0.20), V-Dem (0.15). Within a group,
    ``per_obs_weight = group_weight / count_in_group`` so per-
    component weights inside the group sum to the group weight.
    The realistic fixture has 3 PTS, 7 CIRIGHTS, 2 UCDP, 5 V-Dem
    observations.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

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

    # PTS group: 3 indicators, group mean is 0.60, group
    # contribution is 0.30 × 0.60 = 0.18.
    pts_components = [
        c
        for c in result.components
        if c.component_key == "domestic_violence__pts_state_terror"
    ]
    assert len(pts_components) == 3
    per_obs_weight = 0.30 / 3
    expected_mean = (0.65 + 0.60 + 0.55) / 3
    for component in pts_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(c.contribution_0_1 for c in pts_components) == pytest.approx(
        0.30 * expected_mean, abs=1e-9
    )


def test_score_domestic_violence_cirights_group_uses_mean_of_indicators() -> None:
    """The CIRIGHTS physical-integrity group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    cirights_components = [
        c
        for c in result.components
        if c.component_key
        == "domestic_violence__cirights_physint_repression"
    ]
    assert len(cirights_components) == 7
    per_obs_weight = 0.35 / 7
    expected_mean = (
        0.65 + 0.70 + 0.60 + 0.55 + 0.50 + 0.55 + 0.60
    ) / 7
    for component in cirights_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(
        c.contribution_0_1 for c in cirights_components
    ) == pytest.approx(0.35 * expected_mean, abs=1e-9)


def test_score_domestic_violence_ucdp_group_uses_mean_of_indicators() -> None:
    """The UCDP one-sided violence group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    ucdp_components = [
        c
        for c in result.components
        if c.component_key == "domestic_violence__ucdp_one_sided_violence"
    ]
    assert len(ucdp_components) == 2
    per_obs_weight = 0.20 / 2
    expected_mean = (0.65 + 0.70) / 2
    for component in ucdp_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in ucdp_components) == pytest.approx(
        0.20 * expected_mean, abs=1e-9
    )


def test_score_domestic_violence_vdem_group_uses_mean_of_indicators() -> None:
    """The V-Dem civil-liberties / repression group emits one
    component per indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    vdem_components = [
        c
        for c in result.components
        if c.component_key
        == "domestic_violence__vdem_civil_liberties_repression"
    ]
    assert len(vdem_components) == 5
    per_obs_weight = 0.15 / 5
    expected_mean = (0.65 + 0.55 + 0.60 + 0.45 + 0.50) / 5
    for component in vdem_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in vdem_components) == pytest.approx(
        0.15 * expected_mean, abs=1e-9
    )


def test_score_domestic_violence_four_groups_distinct() -> None:
    """The realistic fixture spans all four expected groups / sources."""
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    component_source_keys = {c.source_key for c in result.components}
    assert component_source_keys == {"pts", "cirights", "ucdp", "vdem"}

    group_keys = {c.component_key for c in result.components}
    expected_groups = {
        "domestic_violence__pts_state_terror",
        "domestic_violence__cirights_physint_repression",
        "domestic_violence__ucdp_one_sided_violence",
        "domestic_violence__vdem_civil_liberties_repression",
    }
    assert group_keys == expected_groups


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_domestic_violence_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        DOMESTIC_VIOLENCE_PLAN.expected_indicators
    )
    # We observed all 17 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 17
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_domestic_violence_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="pts",
            variable_name="pts_amnesty_score",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="cirights",
            variable_name="cirights_physint",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_onesided_events",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations(),
        missing=missing,
    )
    result = score_domestic_violence(bundle)

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


def test_score_domestic_violence_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``domestic_violence``."""
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)
    assert result.category_key == CATEGORY_KEY == "domestic_violence"
