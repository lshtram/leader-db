"""Tests for the political freedom deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.political_freedom.score_political_freedom`:

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
:mod:`tests.test_score_political_freedom_components`. Flag-detection
tests live in :mod:`tests.test_score_political_freedom_flags`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import POLITICAL_FREEDOM_PLAN
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.political_freedom import (
    CATEGORY_KEY,
    score_political_freedom,
)
from leaders_db.score.results import ScoreComponent, ScoreResult
from tests._political_freedom_factories import (
    political_freedom_make_bundle,
    realistic_political_freedom_observations,
)

# (a) Happy path


def test_score_political_freedom_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "political_freedom"
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


def test_score_political_freedom_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_political_freedom_realistic_bundle_expected_score() -> None:
    """The realistic bundle produces the expected 1..10 score.

    The realistic fixture values:

    - V-Dem democratic / liberal / civil-liberties group (weight
      0.50): mean of ``(0.50, 0.45, 0.55, 0.50, 0.65, 0.50, 0.55)``
      = 3.70 / 7 ≈ 0.5286 → contribution
      0.50 × 0.5286 ≈ 0.2643.
    - BTI political-transformation group (weight 0.30): mean of
      ``(0.50, 0.55, 0.60, 0.45, 0.50, 0.55, 0.50)`` = 3.65 / 7
      ≈ 0.5214 → contribution 0.30 × 0.5214 ≈ 0.1564.
    - RSF press-freedom group (weight 0.20): mean of
      ``(0.50, 0.55)`` = 0.525 → contribution
      0.20 × 0.525 = 0.105.

    Sum: 0.2643 + 0.1564 + 0.105 ≈ 0.5257. The 1..10 mapping
    yields ``floor(1 + 9 × 0.5257 + 0.5)`` = ``floor(6.2314)``
    = 6.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    assert result.normalized_score_0_1 is not None
    assert result.normalized_score_0_1 == pytest.approx(0.525714, abs=1e-6)
    assert result.system_proposed_score_1_10 == 6


# ---------------------------------------------------------------------------
# (b) The 3-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_political_freedom_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The three political freedom groups are V-Dem democratic /
    liberal / civil-liberties (0.50), BTI political
    transformation (0.30), and RSF press freedom (0.20).
    Within a group, ``per_obs_weight = group_weight / count_in_group``
    so per-component weights inside the group sum to the group
    weight. The V-Dem group has 7 indicators in the realistic
    fixture, the BTI group has 7, and the RSF group has 2.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

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


def test_score_political_freedom_vdem_group_uses_mean_of_indicators() -> None:
    """The V-Dem democratic / liberal / civil-liberties group emits one
    component per indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    vdem_components = [
        c
        for c in result.components
        if c.component_key == "political_freedom__vdem_democracy_liberty"
    ]
    assert len(vdem_components) == 7
    per_obs_weight = 0.50 / 7
    expected_mean = (0.50 + 0.45 + 0.55 + 0.50 + 0.65 + 0.50 + 0.55) / 7
    for component in vdem_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(
        c.contribution_0_1 for c in vdem_components
    ) == pytest.approx(0.50 * expected_mean, abs=1e-9)


def test_score_political_freedom_bti_group_uses_mean_of_indicators() -> None:
    """The BTI political-transformation group emits one component
    per indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    bti_components = [
        c
        for c in result.components
        if c.component_key == "political_freedom__bti_political_transformation"
    ]
    assert len(bti_components) == 7
    per_obs_weight = 0.30 / 7
    expected_mean = (0.50 + 0.55 + 0.60 + 0.45 + 0.50 + 0.55 + 0.50) / 7
    for component in bti_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in bti_components) == pytest.approx(
        0.30 * expected_mean, abs=1e-9
    )


def test_score_political_freedom_rsf_group_uses_mean_of_indicators() -> None:
    """The RSF press-freedom group emits one component per indicator
    and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    rsf_components = [
        c
        for c in result.components
        if c.component_key == "political_freedom__rsf_press_freedom"
    ]
    assert len(rsf_components) == 2
    per_obs_weight = 0.20 / 2
    expected_mean = (0.50 + 0.55) / 2
    for component in rsf_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in rsf_components) == pytest.approx(
        0.20 * expected_mean, abs=1e-9
    )


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_political_freedom_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        POLITICAL_FREEDOM_PLAN.expected_indicators
    )
    # We observed all 16 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 16
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_political_freedom_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_libdem",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="bti",
            variable_name="bti_status_index",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations(),
        missing=missing,
    )
    result = score_political_freedom(bundle)

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


def test_score_political_freedom_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``political_freedom``."""
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_political_freedom(bundle)
    assert result.category_key == CATEGORY_KEY == "political_freedom"
