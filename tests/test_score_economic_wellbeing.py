"""Tests for the economic wellbeing deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.economic_wellbeing.score_economic_wellbeing`:

- (a) A realistic bundle produces a :class:`ScoreResult` with the
      right category key, ISO3, year, leader, and 1..10 integer
      score.
- (b) The 3-group weighted-average rubric structure (per-group
      weights, group contribution math, normalized-score sum).
- (c) Missingness summary: ``total_expected`` /
      ``total_observed`` and the by_reason / by_severity rollups.

Component / observation-ref bookkeeping, the scale mapping, the
rationale, the leader fallback, the client-source boundary
exclusion, and the regression tests for client missing-row
contamination live in the sibling file
:mod:`tests.test_score_economic_wellbeing_components`. Flag-detection
tests live in :mod:`tests.test_score_economic_wellbeing_flags`.

Style invariants (per ``docs/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import ECONOMIC_WELLBEING_PLAN
from leaders_db.score.economic_wellbeing import (
    CATEGORY_KEY,
    score_economic_wellbeing,
)
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.results import ScoreComponent, ScoreResult
from tests._economic_wellbeing_factories import (
    economic_wellbeing_make_bundle,
    realistic_economic_wellbeing_observations,
)

# (a) Happy path


def test_score_economic_wellbeing_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "economic_wellbeing"
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


def test_score_economic_wellbeing_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_economic_wellbeing_realistic_bundle_expected_score() -> None:
    """The realistic bundle produces the expected 1..10 score.

    The realistic fixture values:

    - WDI per-capita prosperity group (weight 0.45): mean of
      ``(0.60, 0.65, 0.55)`` = 0.60 → contribution
      0.45 × 0.60 = 0.270.
    - WDI scale / openness / investment group (weight 0.25):
      mean of ``(0.60, 0.55, 0.50, 0.55, 0.45, 0.65)`` = 0.55 →
      contribution 0.25 × 0.55 = 0.1375.
    - BTI economic transformation group (weight 0.30): mean of
      ``(0.50, 0.55, 0.50)`` ≈ 0.5167 → contribution
      0.30 × 0.5167 ≈ 0.155.

    Sum: 0.270 + 0.1375 + 0.155 ≈ 0.5625. The 1..10 mapping
    yields ``floor(1 + 9 × 0.5625 + 0.5)`` = ``floor(6.5625)``
    = 6.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    assert result.normalized_score_0_1 is not None
    assert result.normalized_score_0_1 == pytest.approx(0.5625, abs=1e-9)
    assert result.system_proposed_score_1_10 == 6


# ---------------------------------------------------------------------------
# (b) The 3-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The three economic wellbeing groups are WDI per-capita (0.45),
    WDI scale / openness / investment (0.25), and BTI (0.30).
    Within a group, ``per_obs_weight = group_weight / count_in_group``
    so per-component weights inside the group sum to the group
    weight. The per-capita group has 3 indicators in the realistic
    fixture, the scale group has 6, and the BTI group has 3.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

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


def test_score_economic_wellbeing_per_capita_group_uses_mean_of_indicators() -> None:
    """The WDI per-capita prosperity group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    per_capita_components = [
        c
        for c in result.components
        if c.component_key == "economic_wellbeing__wdi_per_capita_prosperity"
    ]
    assert len(per_capita_components) == 3
    per_obs_weight = 0.45 / 3
    expected_mean = (0.60 + 0.65 + 0.55) / 3
    for component in per_capita_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(
        c.contribution_0_1 for c in per_capita_components
    ) == pytest.approx(0.45 * expected_mean, abs=1e-9)


def test_score_economic_wellbeing_scale_group_uses_mean_of_indicators() -> None:
    """The WDI scale / openness / investment group emits one component
    per indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    scale_components = [
        c
        for c in result.components
        if c.component_key
        == "economic_wellbeing__wdi_scale_openness_investment"
    ]
    assert len(scale_components) == 6
    per_obs_weight = 0.25 / 6
    expected_mean = (0.60 + 0.55 + 0.50 + 0.55 + 0.45 + 0.65) / 6
    for component in scale_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in scale_components) == pytest.approx(
        0.25 * expected_mean, abs=1e-9
    )


def test_score_economic_wellbeing_bti_group_uses_mean_of_indicators() -> None:
    """The BTI economic transformation group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    bti_components = [
        c
        for c in result.components
        if c.component_key == "economic_wellbeing__bti_economic_transformation"
    ]
    assert len(bti_components) == 3
    per_obs_weight = 0.30 / 3
    expected_mean = (0.50 + 0.55 + 0.50) / 3
    for component in bti_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in bti_components) == pytest.approx(
        0.30 * expected_mean, abs=1e-9
    )


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        ECONOMIC_WELLBEING_PLAN.expected_indicators
    )
    # We observed all 12 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 12
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_economic_wellbeing_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="world_bank_wdi",
            variable_name="wdi_gdp_per_capita",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="world_bank_wdi",
            variable_name="wdi_gdp_per_capita_ppp_constant_2017",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="bti",
            variable_name="bti_q7_market_competition",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations(),
        missing=missing,
    )
    result = score_economic_wellbeing(bundle)

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


def test_score_economic_wellbeing_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``economic_wellbeing``."""
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_economic_wellbeing(bundle)
    assert result.category_key == CATEGORY_KEY == "economic_wellbeing"
