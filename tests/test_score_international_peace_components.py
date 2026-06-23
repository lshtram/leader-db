"""Tests for the international-peace deterministic scorer — component / ref /
rationale / leader-fallback / scale-mapping contract.

These tests pin the per-component, per-observation-ref, rationale,
scale-mapping, leader-fallback, and determinism contract of
:func:`leaders_db.score.international_peace.score_international_peace`.
The client-source boundary exclusion for observations is exercised
here as the per-observation analogue of the per-missing-row
regression test in
:mod:`tests.test_score_international_peace_remediation`.

The split mirrors the production code split (the international-
peace scorer is broken into
:mod:`leaders_db.score.international_peace` (facade),
:mod:`leaders_db.score._international_peace_components` (per-
component helpers), and
:mod:`leaders_db.score._international_peace_flags` (flag-detection
helpers)). The test surface follows the same pattern:

- :mod:`tests.test_score_international_peace` — happy path /
  rubric weights / missingness rollup;
- :mod:`tests.test_score_international_peace_components` — this
  file, per-component bookkeeping + scale mapping + rationale +
  leader fallback + determinism + per-observation client
  exclusion;
- :mod:`tests.test_score_international_peace_remediation` — the
  client-source missingness regression tests (reviewer blocker
  "client-contamination / missingness correctness");
- :mod:`tests.test_score_international_peace_flags` — flag-
  detection paths (MISSING_PRIMARY_SOURCE / SPARSE_DATA /
  LOW_CONFIDENCE / INSUFFICIENT_DATA) and the
  ``human_review_required`` invariant.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    Direction,
    EvidenceObservation,
    TemporalKind,
)
from leaders_db.score.international_peace import score_international_peace
from leaders_db.score.results import ScoreObservationRef
from tests._international_peace_factories import (
    international_peace_make_bundle,
    international_peace_make_obs,
    realistic_international_peace_observations,
)

# ---------------------------------------------------------------------------
# (a) Component / observation-ref bookkeeping
# ---------------------------------------------------------------------------


def test_score_international_peace_one_component_per_observation() -> None:
    """Every usable observation produces exactly one ScoreComponent."""
    observations = realistic_international_peace_observations()
    bundle = international_peace_make_bundle(observations=observations)
    result = score_international_peace(bundle)

    assert len(result.components) == len(observations)
    assert len(result.observation_refs) == len(observations)


def test_score_international_peace_components_carry_observation_refs() -> None:
    """Each component has a single observation_ref that points back."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

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


def test_score_international_peace_observation_refs_flat_mirrors_components() -> (
    None
):
    """The flat ``observation_refs`` tuple mirrors the per-component refs."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    flat_refs = list(result.observation_refs)
    component_refs = [
        ref
        for component in result.components
        for ref in component.observation_refs
    ]
    assert flat_refs == component_refs


def test_score_international_peace_group_keys_match_rubric() -> None:
    """Every component's ``component_key`` is prefixed with the group key.

    The international-peace rubric emits
    ``international_peace__<group_key>`` for each per-observation
    :class:`ScoreComponent`. The two group keys are
    ``ucdp_conflict_involvement`` and
    ``sipri_military_expenditure`` per the rubric constants
    in :mod:`leaders_db.score._international_peace_rubric`.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    expected_prefixes = {
        "international_peace__ucdp_conflict_involvement",
        "international_peace__sipri_military_expenditure",
    }
    actual_prefixes = {c.component_key for c in result.components}
    assert actual_prefixes == expected_prefixes


# ---------------------------------------------------------------------------
# (b) Scale mapping, rationale, leader fallback, determinism
# ---------------------------------------------------------------------------


def test_score_international_peace_rationale_short_mentions_scale() -> None:
    """The rationale explicitly surfaces the 1..10 mapping."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    # The rationale names the score and the scale.
    assert f"{result.system_proposed_score_1_10}/10" in result.rationale_short
    assert "1..10" in result.rationale_short


def test_score_international_peace_score_clamped_to_1_to_10() -> None:
    """The proposed score is always in 1..10 for non-insufficient results."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_international_peace_leader_name_falls_back_to_country() -> None:
    """If the bundle has no leader, the result uses the country name."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations(),
        leader_name=None,
    )
    result = score_international_peace(bundle)

    assert result.leader_name == "Mexico"


def test_score_international_peace_observation_with_none_normalized_is_skipped() -> (
    None
):
    """Observations with ``normalized_value=None`` do not contribute.

    The bundle pairs a ``ucdp`` source with one null observation,
    plus a ``sipri_milex`` source with usable observations. The
    UCDP + SIPRI clear the minimum-viable gate on usable
    sources; the null observation must still be skipped — no
    component, no ref, no contribution.
    """
    null_obs = EvidenceObservation(
        source_key="ucdp",
        source_name="ucdp (test fixture)",
        variable_name="ucdp_state_based_fatalities",
        raw_value="",
        numeric_value=None,
        normalized_value=None,
        unit="index",
        direction=Direction.LOWER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=None,
        authority_score=70,
        specificity_score=80,
    )
    bundle = international_peace_make_bundle(
        observations=[
            null_obs,
            international_peace_make_obs(
                "ucdp_state_based_events", "ucdp", 0.65
            ),
            international_peace_make_obs(
                "sipri_milex_share_of_gdp", "sipri_milex", 0.55
            ),
        ]
    )
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is False
    for component in result.components:
        assert not (
            component.source_key == "ucdp"
            and component.variable_name == "ucdp_state_based_fatalities"
        )
    for ref in result.observation_refs:
        assert not (
            ref.source_key == "ucdp"
            and ref.variable_name == "ucdp_state_based_fatalities"
        )
    assert len(result.components) == 2
    assert len(result.observation_refs) == 2


def test_score_international_peace_is_deterministic() -> None:
    """Two calls with the same bundle produce the same score."""
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    first = score_international_peace(bundle)
    second = score_international_peace(bundle)

    assert first.system_proposed_score_1_10 == second.system_proposed_score_1_10
    assert first.normalized_score_0_1 == second.normalized_score_0_1
    assert first.review_flags == second.review_flags


def test_score_international_peace_does_not_consult_client_observations() -> None:
    """A bundle containing client contamination has the client rows stripped.

    The bundle builder excludes ``client_existing`` /
    ``client_matrix`` from the Stage 5 evidence bundle; this
    test pins the contract at the scorer boundary by feeding a
    contaminated bundle (one client row + two real rows) and
    asserting the result has no client components and no client
    refs. The client comparison path (delta computation) lives
    downstream of the scorer. The companion missing-row
    regression test (client ``MissingObservation`` rows must not
    inflate ``missingness.by_reason`` / ``by_severity``) lives in
    :mod:`tests.test_score_international_peace_remediation`.
    """
    contaminated_observations = [
        EvidenceObservation(
            source_key="client_existing",
            source_name="client_existing (test fixture)",
            variable_name="ucdp_state_based_fatalities",
            raw_value="0.99",
            numeric_value=0.99,
            normalized_value=0.99,
            unit="index",
            direction=Direction.LOWER_IS_BETTER,
            observation_year=2023,
            target_year=2023,
            temporal_kind=TemporalKind.DIRECT,
            source_row_reference="client_existing:ucdp_state_based_fatalities:2023",
            authority_score=70,
            specificity_score=80,
        ),
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
    ]
    bundle = international_peace_make_bundle(observations=contaminated_observations)
    result = score_international_peace(bundle)

    component_source_keys = {c.source_key for c in result.components}
    assert "client_existing" not in component_source_keys
    assert "client_matrix" not in component_source_keys
    ref_source_keys = {ref.source_key for ref in result.observation_refs}
    assert "client_existing" not in ref_source_keys
    assert "client_matrix" not in ref_source_keys
    assert result.score_delta_vs_client is None
