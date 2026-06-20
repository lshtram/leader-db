"""Tests for the international-peace deterministic scorer — happy-path contract.

These tests pin the happy-path contract of
:func:`leaders_db.score.international_peace.score_international_peace`:

- (a) A realistic bundle produces a :class:`ScoreResult` with
      the right category key, ISO3, year, leader, and 1..10
      integer score.
- (b) The 2-group weighted-average rubric structure (per-group
      weights, group contribution math, normalized-score sum).
- (c) Missingness summary: ``total_expected`` /
      ``total_observed`` and the by_reason / by_severity rollups.

Component / observation-ref bookkeeping, the scale mapping, the
rationale, the leader fallback, and the client-source boundary
exclusion live in the sibling file
:mod:`tests.test_score_international_peace_components`. Flag-
detection tests live in
:mod:`tests.test_score_international_peace_flags`. Insufficient-
data branch flag derivation lives in
:mod:`tests.test_score_international_peace_insufficient_flags`.
Client-contamination regression tests live in
:mod:`tests.test_score_international_peace_remediation`.

Style invariants (per ``docs/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import INTERNATIONAL_PEACE_PLAN
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.international_peace import (
    CATEGORY_KEY,
    score_international_peace,
)
from leaders_db.score.results import ScoreComponent, ScoreResult
from tests._international_peace_factories import (
    international_peace_make_bundle,
    realistic_international_peace_observations,
)

# (a) Happy path


def test_score_international_peace_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "international_peace"
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


def test_score_international_peace_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_international_peace_realistic_bundle_expected_score() -> None:
    """The realistic bundle produces the expected 1..10 score.

    The realistic fixture values:

    - UCDP conflict involvement group (weight 0.65): mean of
      ``(0.65, 0.60, 0.55, 0.70)`` = 2.50 / 4 = 0.625 →
      contribution 0.65 × 0.625 = 0.40625.
    - SIPRI military expenditure group (weight 0.35): mean of
      ``(0.55, 0.60, 0.50, 0.65)`` = 2.30 / 4 = 0.575 →
      contribution 0.35 × 0.575 = 0.20125.

    Sum: 0.40625 + 0.20125 ≈ 0.6075. The 1..10 mapping yields
    ``floor(1 + 9 × 0.6075 + 0.5)`` = ``floor(6.9675)`` = 6.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert result.normalized_score_0_1 is not None
    assert result.normalized_score_0_1 == pytest.approx(0.6075, abs=1e-6)
    assert result.system_proposed_score_1_10 == 6


# ---------------------------------------------------------------------------
# (b) The 2-group weighted-average rubric
# ---------------------------------------------------------------------------


def test_score_international_peace_per_group_weights_sum_to_group_weight() -> None:
    """Per-group weights sum to the group weight; total sums to 1.0.

    The two international-peace groups are UCDP (0.65) and SIPRI
    (0.35). Within a group,
    ``per_obs_weight = group_weight / count_in_group`` so per-
    component weights inside the group sum to the group weight.
    The realistic fixture has 4 UCDP and 4 SIPRI observations.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

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

    # UCDP group: 4 indicators, group mean is 0.625, group
    # contribution is 0.65 × 0.625 = 0.40625.
    ucdp_components = [
        c
        for c in result.components
        if c.component_key == "international_peace__ucdp_conflict_involvement"
    ]
    assert len(ucdp_components) == 4
    per_obs_weight = 0.65 / 4
    expected_mean = (0.65 + 0.60 + 0.55 + 0.70) / 4
    for component in ucdp_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
        assert component.contribution_0_1 == pytest.approx(
            component.normalized_value_0_1 * per_obs_weight, abs=1e-9
        )
    assert sum(c.contribution_0_1 for c in ucdp_components) == pytest.approx(
        0.65 * expected_mean, abs=1e-9
    )


def test_score_international_peace_ucdp_group_uses_mean_of_indicators() -> None:
    """The UCDP conflict involvement group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    ucdp_components = [
        c
        for c in result.components
        if c.component_key
        == "international_peace__ucdp_conflict_involvement"
    ]
    assert len(ucdp_components) == 4
    per_obs_weight = 0.65 / 4
    expected_mean = (0.65 + 0.60 + 0.55 + 0.70) / 4
    for component in ucdp_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(
        c.contribution_0_1 for c in ucdp_components
    ) == pytest.approx(0.65 * expected_mean, abs=1e-9)


def test_score_international_peace_sipri_group_uses_mean_of_indicators() -> None:
    """The SIPRI military expenditure group emits one component per
    indicator and its contribution equals
    ``group_weight * mean(indicator values)``.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    sipri_components = [
        c
        for c in result.components
        if c.component_key
        == "international_peace__sipri_military_expenditure"
    ]
    assert len(sipri_components) == 4
    per_obs_weight = 0.35 / 4
    expected_mean = (0.55 + 0.60 + 0.50 + 0.65) / 4
    for component in sipri_components:
        assert component.weight == pytest.approx(per_obs_weight, abs=1e-9)
    assert sum(c.contribution_0_1 for c in sipri_components) == pytest.approx(
        0.35 * expected_mean, abs=1e-9
    )


def test_score_international_peace_two_groups_distinct() -> None:
    """The realistic fixture spans both expected groups / sources."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    component_source_keys = {c.source_key for c in result.components}
    assert component_source_keys == {"ucdp", "sipri_milex"}

    group_keys = {c.component_key for c in result.components}
    expected_groups = {
        "international_peace__ucdp_conflict_involvement",
        "international_peace__sipri_military_expenditure",
    }
    assert group_keys == expected_groups


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_international_peace_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        INTERNATIONAL_PEACE_PLAN.expected_indicators
    )
    # We observed all 8 plan variables in the realistic fixture.
    assert result.missingness.total_observed == 8
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_international_peace_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_state_based_fatalities",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="sipri_milex",
            variable_name="sipri_milex_share_of_gdp",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_intl_events",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations(),
        missing=missing,
    )
    result = score_international_peace(bundle)

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


def test_score_international_peace_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``international_peace``."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)
    assert result.category_key == CATEGORY_KEY == "international_peace"
