"""Tests for the integrity deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.integrity.score_integrity`:

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
:mod:`tests.test_score_integrity_components`. Flag-detection
tests live in :mod:`tests.test_score_integrity_flags`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import INTEGRITY_PLAN
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.integrity import (
    CATEGORY_KEY,
    score_integrity,
)
from leaders_db.score.results import ScoreComponent, ScoreResult
from tests._integrity_factories import (
    integrity_make_bundle,
    realistic_integrity_observations,
)

# (a) Happy path


def test_score_integrity_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations()
    )
    result = score_integrity(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "integrity"
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


def test_score_integrity_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations()
    )
    result = score_integrity(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


# ---------------------------------------------------------------------------
# (b) The 3-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_integrity_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The three integrity groups are WGI (0.35), V-Dem (0.35),
    TI CPI (0.30). Within a group, ``per_obs_weight =
    group_weight / count_in_group`` so per-component weights
    inside the group sum to the group weight. The V-Dem group
    has 3 indicators in the realistic fixture
    (``vdem_v2x_corr``=0.70, ``vdem_v2x_execorr``=0.65,
    ``vdem_v2x_pubcorr``=0.60) so the group mean is 0.65 and
    the group contribution is 0.35 * 0.65 = 0.2275.
    """
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations()
    )
    result = score_integrity(bundle)

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

    # V-Dem group: 3 indicators, group mean is 0.65, group
    # contribution is 0.35 * 0.65.
    vdem_components = [
        c
        for c in result.components
        if c.component_key == "integrity__vdem_corruption_composite"
    ]
    assert len(vdem_components) == 3
    per_obs_weight = 0.35 / 3
    expected_mean = (0.70 + 0.65 + 0.60) / 3
    for component in vdem_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(c.contribution_0_1 for c in vdem_components) == pytest.approx(
        0.35 * expected_mean, abs=1e-9
    )


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_integrity_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations()
    )
    result = score_integrity(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        INTEGRITY_PLAN.expected_indicators
    )
    # We observed all 5 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 5
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_integrity_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="wgi",
            variable_name="wgi_control_of_corruption",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="ti_cpi",
            variable_name="cpi_score",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations(), missing=missing
    )
    result = score_integrity(bundle)

    assert result.missingness is not None
    assert dict(result.missingness.by_reason) == {
        "raw_file_absent": 1,
        "target_year_absent": 1,
    }
    assert dict(result.missingness.by_severity) == {
        "primary": 1,
        "important": 1,
    }


def test_score_integrity_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``integrity``."""
    bundle = integrity_make_bundle(
        observations=realistic_integrity_observations()
    )
    result = score_integrity(bundle)
    assert result.category_key == CATEGORY_KEY == "integrity"
