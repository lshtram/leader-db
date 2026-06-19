"""Tests for the social-wellbeing deterministic scorer
(:mod:`leaders_db.score.social_wellbeing`) — happy-path contract.

These tests pin the **happy-path** contract of
:func:`leaders_db.score.social_wellbeing.score_social_wellbeing`:

- (a) A realistic bundle produces a :class:`ScoreResult` with the
      right category key, ISO3, year, leader, and 1..10 integer
      score on the prototype rubric.
- (b) Component / observation-ref bookkeeping: every usable
      observation yields exactly one :class:`ScoreComponent` and
      one :class:`ScoreObservationRef`; the flat
      ``observation_refs`` mirrors the per-component refs.
- (c) Missingness summary: ``total_expected`` /
      ``total_observed``, ``by_reason`` and ``by_severity``
      rollups reflect the bundle state.
- (d) The 1..10 score mapping is half-up and clamped; the
      ``rationale_short`` surfaces the mapping for reviewers.

Flag-detection tests (missing primary source, sparse data, proxy
observations, insufficient-data gate) live in the sibling file
:mod:`tests.test_score_social_wellbeing_flags`. The client
comparison delta test lives in
:mod:`tests.test_score_social_wellbeing_client`.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on test parameters.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.category_plans import SOCIAL_WELLBEING_PLAN
from leaders_db.score.evidence import (
    Direction,
    EvidenceObservation,
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.results import (
    ScoreComponent,
    ScoreObservationRef,
    ScoreResult,
)
from leaders_db.score.social_wellbeing import (
    CATEGORY_KEY,
    score_social_wellbeing,
)
from tests._social_wellbeing_factories import (
    make_bundle,
    make_obs,
    realistic_mexico_observations,
)

# ---------------------------------------------------------------------------
# (a) Happy path
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_emits_valid_result_for_realistic_bundle() -> None:
    """A realistic bundle produces a result with the right shape."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "social_wellbeing"
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


def test_score_social_wellbeing_normalized_sums_to_group_contributions() -> None:
    """The normalized score equals the sum of component contributions."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    assert result.normalized_score_0_1 is not None
    total_contribution = sum(c.contribution_0_1 for c in result.components)
    assert total_contribution == pytest.approx(
        result.normalized_score_0_1, abs=1e-9
    )


def test_score_social_wellbeing_one_component_per_observation() -> None:
    """Every usable observation produces exactly one ScoreComponent."""
    observations = realistic_mexico_observations()
    bundle = make_bundle(observations=observations)
    result = score_social_wellbeing(bundle)

    assert len(result.components) == len(observations)
    assert len(result.observation_refs) == len(observations)


# ---------------------------------------------------------------------------
# (b) Component / observation-ref bookkeeping
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_components_carry_observation_refs() -> None:
    """Each component has a single observation_ref that points back."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    refs_by_var: dict[str, ScoreObservationRef] = {
        ref.variable_name: ref for ref in result.observation_refs
    }
    assert len(refs_by_var) == len(result.observation_refs)
    for component in result.components:
        assert component.observation_refs, (
            f"component {component.component_key!r} has no observation_refs"
        )
        ref = component.observation_refs[0]
        assert ref.source_key == component.source_key
        assert ref.variable_name == component.variable_name
        assert ref.target_year == bundle.year
        assert refs_by_var[component.variable_name] == ref


def test_score_social_wellbeing_observation_refs_flat_mirrors_components() -> None:
    """The flat ``observation_refs`` tuple mirrors the per-component refs."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    flat_refs = list(result.observation_refs)
    component_refs = [
        ref
        for component in result.components
        for ref in component.observation_refs
    ]
    assert flat_refs == component_refs


def test_score_social_wellbeing_component_weights_sum_to_one_within_group() -> (
    None
):
    """Per-group component weights sum to the group's weight.

    Within a group, ``per_obs_weight = group_weight / count_in_group``,
    so the group's per-component weights sum to ``group_weight`` and
    the sum across groups is 1.0 within float tolerance.
    """
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    by_group: dict[str, list[ScoreComponent]] = {}
    for component in result.components:
        by_group.setdefault(component.component_key, []).append(component)

    total_weight = 0.0
    for group_key, components in by_group.items():
        group_weight = sum(c.weight for c in components)
        total_weight += group_weight
        # The weight split within a group is uniform.
        weights = {round(c.weight, 9) for c in components}
        assert len(weights) == 1, (
            f"group {group_key!r} has non-uniform weights: {weights}"
        )
    assert total_weight == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# (c) Missingness summary
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_missingness_total_matches_plan() -> None:
    """``total_expected`` equals the plan's indicator count."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    assert result.missingness is not None
    assert result.missingness.total_expected == len(
        SOCIAL_WELLBEING_PLAN.expected_indicators
    )
    # We observed 10 distinct plan variables in the realistic fixture.
    assert result.missingness.total_observed == 10
    assert (
        result.missingness.total_missing
        == result.missingness.total_expected - result.missingness.total_observed
    )


def test_score_social_wellbeing_missingness_rolls_up_missing_observations() -> None:
    """``by_reason`` and ``by_severity`` count the bundle's missing rows."""
    missing = [
        MissingObservation(
            source_key="who_gho_api",
            variable_name="who_gho_life_expectancy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
        MissingObservation(
            source_key="world_bank_wdi",
            variable_name="wdi_life_expectancy_at_birth",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_egal",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.OPTIONAL,
        ),
    ]
    bundle = make_bundle(
        observations=realistic_mexico_observations(), missing=missing
    )
    result = score_social_wellbeing(bundle)

    assert result.missingness is not None
    assert dict(result.missingness.by_reason) == {
        "raw_file_absent": 1,
        "target_year_absent": 1,
        "country_row_absent": 1,
    }
    assert dict(result.missingness.by_severity) == {
        "important": 2,
        "optional": 1,
    }


# ---------------------------------------------------------------------------
# (d) Scale mapping, rationale, leader fallback, determinism
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_rationale_short_mentions_scale() -> None:
    """The rationale explicitly surfaces the 1..10 mapping."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    # The rationale names the score and the scale.
    assert f"{result.system_proposed_score_1_10}/10" in result.rationale_short
    assert "1..10" in result.rationale_short


def test_score_social_wellbeing_score_clamped_to_1_to_10() -> None:
    """The proposed score is always in 1..10 for non-insufficient results."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_social_wellbeing_leader_name_falls_back_to_country() -> None:
    """If the bundle has no leader, the result uses the country name."""
    bundle = make_bundle(
        observations=realistic_mexico_observations(), leader_name=None
    )
    result = score_social_wellbeing(bundle)

    assert result.leader_name == "Mexico"


def test_score_social_wellbeing_observation_with_none_normalized_is_skipped() -> (
    None
):
    """Observations with ``normalized_value=None`` do not contribute.

    The bundle pairs a ``undp_hdi`` source with one null observation
    and one **usable** observation, plus a second source (vdem) with
    one usable observation. Both sources have ≥ 1 usable observation
    so the bundle clears the minimum-viable threshold on usable
    sources; the null observation must still be skipped — no
    component, no ref, no contribution.
    """
    null_obs = EvidenceObservation(
        source_key="undp_hdi",
        source_name="undp_hdi (test fixture)",
        variable_name="undp_hdi_gni_per_capita",
        raw_value="",
        numeric_value=None,
        normalized_value=None,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=None,
        authority_score=70,
        specificity_score=80,
    )
    # Add a *usable* observation from undp_hdi so the bundle has
    # two distinct usable sources (undp_hdi + vdem) and avoids the
    # insufficient-data gate. The null observation must still be
    # skipped.
    bundle = make_bundle(
        observations=[
            null_obs,
            make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
            make_obs("vdem_v2x_egal", "vdem", 0.55),
        ]
    )
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is False
    # The null observation contributes nothing.
    for component in result.components:
        assert not (
            component.source_key == "undp_hdi"
            and component.variable_name == "undp_hdi_gni_per_capita"
        )
    for ref in result.observation_refs:
        assert not (
            ref.source_key == "undp_hdi"
            and ref.variable_name == "undp_hdi_gni_per_capita"
        )
    # And only the two non-null observations contribute.
    assert len(result.components) == 2
    assert len(result.observation_refs) == 2


def test_score_social_wellbeing_is_deterministic() -> None:
    """Two calls with the same bundle produce the same score."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    first = score_social_wellbeing(bundle)
    second = score_social_wellbeing(bundle)

    assert first.system_proposed_score_1_10 == second.system_proposed_score_1_10
    assert first.normalized_score_0_1 == second.normalized_score_0_1
    assert first.review_flags == second.review_flags


def test_score_social_wellbeing_does_not_consult_client_observations() -> None:
    """A clean bundle (no client rows) keeps the score free of client data.

    The client matrix is the validation reference (AGENTS.md
    always-on rule #6). The bundle builder excludes
    ``client_existing`` / ``client_matrix`` from the Stage 5
    evidence bundle; this test pins the contract at the scorer
    boundary by asserting the realistic fixture's bundle has no
    client observations and that the score is fully reproducible
    from the non-client rows alone. The end-to-end "score then
    compare to client" path lives in
    :mod:`tests.test_score_social_wellbeing_client`.
    """
    bundle = make_bundle(observations=realistic_mexico_observations())

    # The fixture's bundle has no client-source observations.
    bundle_source_keys = {obs.source_key for obs in bundle.observations}
    assert "client_existing" not in bundle_source_keys
    assert "client_matrix" not in bundle_source_keys

    # The scorer's result also has no client-source components.
    result = score_social_wellbeing(bundle)
    component_source_keys = {c.source_key for c in result.components}
    assert "client_existing" not in component_source_keys
    assert "client_matrix" not in component_source_keys

    # And the score delta vs client is left ``None`` — the
    # comparison stage populates it after the scorer returns.
    assert result.score_delta_vs_client is None


def test_score_social_wellbeing_category_key_is_canonical() -> None:
    """The category_key on the result is the canonical ``social_wellbeing``."""
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_social_wellbeing(bundle)
    assert result.category_key == CATEGORY_KEY == "social_wellbeing"


def test_score_social_wellbeing_full_dense_bundle_has_no_flags() -> None:
    """A dense (>= half observed), direct-year bundle has empty flags."""
    # Build a bundle with all 17 plan variables present and DIRECT.
    obs: list[EvidenceObservation] = []
    for spec in SOCIAL_WELLBEING_PLAN.expected_indicators:
        if spec.source_key is None:
            continue
        obs.append(
            make_obs(
                variable_name=spec.variable_name,
                source_key=spec.source_key,
                normalized_value=0.75,
            )
        )
    bundle = make_bundle(observations=obs)
    result = score_social_wellbeing(bundle)

    assert result.review_flags == ()
    assert result.human_review_required is False
    assert result.is_insufficient_data is False
