"""Tests for the shared scoring result contract
(:mod:`leaders_db.score.results`).

These tests pin the contract every per-category deterministic scorer
will emit. The contract is the uniform payload that downstream
comparison / manual-review / summary-report stages consume; the
per-category scoring formulas are out of scope here (those land in
``src/leaders_db/score/<category>.py`` files, one per category).

Coverage:

- (a) Construction of the four core dataclasses
  (:class:`ScoreResult`, :class:`ScoreComponent`,
  :class:`ScoreObservationRef`, :class:`MissingnessSummary`) and
  the :class:`ReviewFlag` enum.
- (b) Required-field validation: non-empty category/component keys,
  ISO3 length, year range, score range, non-empty leader name.
- (c) Cross-field validation: insufficient_data implies no score;
      the ``human_review_required`` invariant is enforced (any
      ``review_flags`` entry, ``is_provisional``, or
      ``is_insufficient_data`` implies ``human_review_required=True``,
      and ``__post_init__`` rejects the inconsistent ``False``).
- (d) Tuple defensive-copy of collection fields (no mutable
  defaults leak into the dataclass).
- (e) The :class:`MissingnessSummary.total_missing` property is
  clipped at zero.
- (f) The :class:`ScoreResult.observed_component_count` property
  ignores components with a ``None`` normalized value.
- (g) :class:`ReviewFlag` values are stable string enums (the
  manual-review queue filters on the value).
- (h) Public re-export from :mod:`leaders_db.score`.
"""

from __future__ import annotations

import dataclasses

import pytest

from leaders_db.score.results import (
    MissingnessSummary,
    ReviewFlag,
    ScoreComponent,
    ScoreObservationRef,
    ScoreResult,
)

# ---------------------------------------------------------------------------
# (a) Construction smoke
# ---------------------------------------------------------------------------


def test_score_result_minimal_construction() -> None:
    """The dataclass accepts the minimal required keyword arguments."""
    result = ScoreResult(
        category_key="political_freedom",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
    )
    assert result.category_key == "political_freedom"
    assert result.iso3 == "MEX"
    assert result.year == 2023
    assert result.leader_name == "AMLO"
    assert result.normalized_score_0_1 == 0.5
    assert result.system_proposed_score_1_10 == 5
    # Defaults from the dataclass.
    assert result.components == ()
    assert result.observation_refs == ()
    assert result.missingness is None
    assert result.rationale_short == ""
    assert result.human_review_required is False
    assert result.review_flags == ()
    assert result.is_provisional is False
    assert result.is_insufficient_data is False
    assert result.score_delta_vs_client is None


def test_score_result_is_frozen() -> None:
    """The dataclass is frozen; assignment raises ``dataclasses.FrozenInstanceError``."""
    result = ScoreResult(
        category_key="integrity",
        iso3="USA",
        year=2023,
        leader_name="Biden",
        normalized_score_0_1=0.8,
        system_proposed_score_1_10=8,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.year = 2024  # type: ignore[misc]


def test_score_component_construction() -> None:
    """A component accepts the standard bullet of attributes."""
    ref = ScoreObservationRef(
        source_key="vdem",
        variable_name="vdem_v2x_polyarchy",
        observation_year=2023,
        target_year=2023,
    )
    component = ScoreComponent(
        component_key="vdem_polyarchy",
        source_key="vdem",
        variable_name="vdem_v2x_polyarchy",
        direction="higher_is_better",
        raw_value=0.5,
        normalized_value_0_1=0.5,
        weight=0.35,
        contribution_0_1=0.175,
        observation_refs=(ref,),
    )
    assert component.observation_refs == (ref,)
    assert component.contribution_0_1 == pytest.approx(0.175)


def test_missingness_summary_construction() -> None:
    """The summary accepts expected/observed counts and (reason, count) pairs."""
    summary = MissingnessSummary(
        total_expected=10,
        total_observed=7,
        by_reason=(("target_year_absent", 2), ("source_not_implemented", 1)),
        by_severity=(("important", 2), ("optional", 1)),
    )
    assert summary.total_expected == 10
    assert summary.total_observed == 7
    assert dict(summary.by_reason) == {
        "target_year_absent": 2,
        "source_not_implemented": 1,
    }
    assert dict(summary.by_severity) == {"important": 2, "optional": 1}


def test_review_flag_enum_values() -> None:
    """The enum values are stable string-typed identifiers."""
    # The manual-review queue filters on the string value (the enum
    # inherits from str). Lock the values in place so downstream
    # serialisation cannot silently rename a flag.
    assert ReviewFlag.MISSING_PRIMARY_SOURCE.value == "missing_primary_source"
    assert ReviewFlag.SPARSE_DATA.value == "sparse_data"
    assert ReviewFlag.LOW_CONFIDENCE.value == "low_confidence"
    assert ReviewFlag.PROVISIONAL_SCORE.value == "provisional_score"
    assert ReviewFlag.INSUFFICIENT_DATA.value == "insufficient_data"
    assert ReviewFlag.NUCLEAR_CASE.value == "nuclear_case"
    assert ReviewFlag.WAR_AGGRESSION_CASE.value == "war_aggression_case"
    assert ReviewFlag.SEVERE_REPRESSION_CASE.value == "severe_repression_case"
    assert ReviewFlag.CATEGORY_OUTLIER.value == "category_outlier"


# ---------------------------------------------------------------------------
# (b) Required-field validation
# ---------------------------------------------------------------------------


def test_score_result_rejects_empty_category_key() -> None:
    """``category_key`` must be a non-empty string."""
    with pytest.raises(ValueError, match="category_key"):
        ScoreResult(
            category_key="",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )


def test_score_result_rejects_non_iso3() -> None:
    """``iso3`` must be exactly 3 characters (the canonical ISO3 contract)."""
    with pytest.raises(ValueError, match="iso3"):
        ScoreResult(
            category_key="integrity",
            iso3="MEXICO",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )
    with pytest.raises(ValueError, match="iso3"):
        ScoreResult(
            category_key="integrity",
            iso3="ME",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )


def test_score_result_rejects_out_of_range_year() -> None:
    """``year`` must be in 1900..2100 to match the evidence contract."""
    with pytest.raises(ValueError, match="year"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=1899,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )
    with pytest.raises(ValueError, match="year"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2101,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )


def test_score_result_rejects_empty_leader_name() -> None:
    """``leader_name`` must be a non-empty string."""
    with pytest.raises(ValueError, match="leader_name"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
        )


def test_score_result_rejects_out_of_range_normalized_score() -> None:
    """``normalized_score_0_1`` must be in 0..1 (or None)."""
    with pytest.raises(ValueError, match="normalized_score_0_1"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=1.5,
            system_proposed_score_1_10=5,
        )
    with pytest.raises(ValueError, match="normalized_score_0_1"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=-0.1,
            system_proposed_score_1_10=5,
        )


def test_score_result_rejects_out_of_range_proposed_score() -> None:
    """``system_proposed_score_1_10`` must be in 0..10 (or None)."""
    with pytest.raises(ValueError, match="system_proposed_score_1_10"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=11,
        )
    with pytest.raises(ValueError, match="system_proposed_score_1_10"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=-1,
        )


def test_score_result_rejects_none_score_when_not_insufficient() -> None:
    """A ``None`` score outside of ``is_insufficient_data=True`` is a bug."""
    with pytest.raises(ValueError, match="is_insufficient_data"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=None,
            system_proposed_score_1_10=None,
        )


def test_score_component_rejects_empty_keys() -> None:
    """The component's identifying keys must be non-empty."""
    with pytest.raises(ValueError, match="component_key"):
        ScoreComponent(
            component_key="",
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=0.175,
        )
    with pytest.raises(ValueError, match="source_key"):
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=0.175,
        )
    with pytest.raises(ValueError, match="variable_name"):
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="vdem",
            variable_name="",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=0.175,
        )


def test_score_component_rejects_out_of_range_weight() -> None:
    """``weight`` must be in 0..1."""
    with pytest.raises(ValueError, match="weight"):
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=1.5,
            contribution_0_1=0.5,
        )


def test_score_component_rejects_out_of_range_contribution() -> None:
    """``contribution_0_1`` must be in 0..1."""
    with pytest.raises(ValueError, match="contribution_0_1"):
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=1.5,
        )


def test_score_observation_ref_rejects_empty_keys() -> None:
    """The ref's identifying keys must be non-empty."""
    with pytest.raises(ValueError, match="source_key"):
        ScoreObservationRef(
            source_key="",
            variable_name="vdem_v2x_polyarchy",
            observation_year=2023,
            target_year=2023,
        )
    with pytest.raises(ValueError, match="variable_name"):
        ScoreObservationRef(
            source_key="vdem",
            variable_name="",
            observation_year=2023,
            target_year=2023,
        )


def test_missingness_summary_rejects_negative_counts() -> None:
    """Expected/observed counts and reason/severity counts must be >= 0."""
    with pytest.raises(ValueError, match="total_expected"):
        MissingnessSummary(total_expected=-1, total_observed=0)
    with pytest.raises(ValueError, match="total_observed"):
        MissingnessSummary(total_expected=10, total_observed=-1)
    with pytest.raises(ValueError, match="by_reason"):
        MissingnessSummary(
            total_expected=10,
            total_observed=7,
            by_reason=(("target_year_absent", -1),),
        )


def test_missingness_summary_rejects_observed_gt_expected() -> None:
    """``total_observed`` cannot exceed ``total_expected``."""
    with pytest.raises(ValueError, match="exceed total_expected"):
        MissingnessSummary(total_expected=5, total_observed=10)


# ---------------------------------------------------------------------------
# (c) Cross-field validation
# ---------------------------------------------------------------------------


def test_insufficient_data_requires_none_scores() -> None:
    """``is_insufficient_data=True`` requires both scores to be ``None``."""
    # Both None is the only valid combination.
    ScoreResult(
        category_key="nuclear",
        iso3="ISL",
        year=2023,
        leader_name="Bess",
        normalized_score_0_1=None,
        system_proposed_score_1_10=None,
        is_insufficient_data=True,
        human_review_required=True,
    )
    # A non-None normalized score with is_insufficient_data=True is a bug.
    with pytest.raises(ValueError, match="is_insufficient_data"):
        ScoreResult(
            category_key="nuclear",
            iso3="ISL",
            year=2023,
            leader_name="Bess",
            normalized_score_0_1=0.0,
            system_proposed_score_1_10=None,
            is_insufficient_data=True,
        )
    with pytest.raises(ValueError, match="is_insufficient_data"):
        ScoreResult(
            category_key="nuclear",
            iso3="ISL",
            year=2023,
            leader_name="Bess",
            normalized_score_0_1=None,
            system_proposed_score_1_10=0,
            is_insufficient_data=True,
        )


# ---------------------------------------------------------------------------
# (c2) Cross-field invariant: human_review_required must agree with
# review_flags / is_provisional / is_insufficient_data. The forward
# direction is enforced: any review signal implies human_review_required=True.
# The reverse direction is allowed: a result may carry
# human_review_required=True with empty review_flags when the rationale
# flags a reason outside the typed enum.
# ---------------------------------------------------------------------------


def test_human_review_required_rejects_review_flags_with_false() -> None:
    """A non-empty ``review_flags`` tuple with ``human_review_required=False`` is rejected.

    A scorer that flags a result (e.g. ``LOW_CONFIDENCE``) but does not
    set the high-level "needs attention" signal would silently skip the
    manual-review queue. ``__post_init__`` rejects this combination
    loudly at construction.
    """
    with pytest.raises(ValueError, match="human_review_required"):
        ScoreResult(
            category_key="integrity",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
            review_flags=(ReviewFlag.LOW_CONFIDENCE,),
            human_review_required=False,
        )


def test_human_review_required_accepts_review_flags_with_true() -> None:
    """A non-empty ``review_flags`` tuple with ``human_review_required=True`` is the happy path."""
    result = ScoreResult(
        category_key="integrity",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        review_flags=(ReviewFlag.LOW_CONFIDENCE,),
        human_review_required=True,
    )
    assert result.human_review_required is True
    assert result.review_flags == (ReviewFlag.LOW_CONFIDENCE,)


def test_human_review_required_rejects_is_provisional_with_false() -> None:
    """``is_provisional=True`` with ``human_review_required=False`` is rejected."""
    with pytest.raises(ValueError, match="human_review_required"):
        ScoreResult(
            category_key="political_freedom",
            iso3="MEX",
            year=2023,
            leader_name="AMLO",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
            is_provisional=True,
            human_review_required=False,
        )


def test_human_review_required_accepts_is_provisional_with_true() -> None:
    """``is_provisional=True`` with ``human_review_required=True`` is the happy path."""
    result = ScoreResult(
        category_key="political_freedom",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        is_provisional=True,
        human_review_required=True,
    )
    assert result.human_review_required is True
    assert result.is_provisional is True


def test_human_review_required_rejects_is_insufficient_data_with_false() -> None:
    """``is_insufficient_data=True`` with ``human_review_required=False`` is rejected."""
    with pytest.raises(ValueError, match="human_review_required"):
        ScoreResult(
            category_key="nuclear",
            iso3="ISL",
            year=2023,
            leader_name="Bess",
            normalized_score_0_1=None,
            system_proposed_score_1_10=None,
            is_insufficient_data=True,
            human_review_required=False,
        )


def test_human_review_required_accepts_is_insufficient_data_with_true() -> None:
    """``is_insufficient_data=True`` with ``human_review_required=True`` is the happy path."""
    result = ScoreResult(
        category_key="nuclear",
        iso3="ISL",
        year=2023,
        leader_name="Bess",
        normalized_score_0_1=None,
        system_proposed_score_1_10=None,
        is_insufficient_data=True,
        human_review_required=True,
    )
    assert result.human_review_required is True
    assert result.is_insufficient_data is True


def test_human_review_required_true_with_empty_flags_is_allowed() -> None:
    """``human_review_required=True`` with empty ``review_flags`` is valid.

    The reverse direction of the invariant is not constrained — a
    result may need manual attention for a reason outside the typed
    enum (e.g. a free-form rationale flag). The high-level signal
    is the join key downstream stages sort on.
    """
    result = ScoreResult(
        category_key="integrity",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        review_flags=(),
        human_review_required=True,
    )
    assert result.human_review_required is True
    assert result.review_flags == ()


def test_human_review_required_error_message_lists_offending_signals() -> None:
    """The ``ValueError`` message names which signals are inconsistent with ``False``.

    A scorer bug surface needs to be actionable — the message names
    the field(s) so the fix is obvious without re-reading the
    dataclass.
    """
    with pytest.raises(ValueError) as excinfo:
        ScoreResult(
            category_key="effectiveness",
            iso3="USA",
            year=2023,
            leader_name="Biden",
            normalized_score_0_1=0.5,
            system_proposed_score_1_10=5,
            review_flags=(ReviewFlag.SPARSE_DATA, ReviewFlag.LOW_CONFIDENCE),
            is_provisional=True,
            human_review_required=False,
        )
    message = str(excinfo.value)
    assert "human_review_required" in message
    assert "review_flags" in message
    assert "is_provisional" in message
    assert "sparse_data" in message
    assert "low_confidence" in message


# ---------------------------------------------------------------------------
# (d) Tuple defensive copy
# ---------------------------------------------------------------------------


def test_score_result_stores_components_as_tuple() -> None:
    """A list of components is stored as a tuple (defensive copy)."""
    components = [
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=0.175,
        ),
    ]
    result = ScoreResult(
        category_key="political_freedom",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        components=components,
    )
    assert isinstance(result.components, tuple)
    # Mutating the caller's list must not affect the stored tuple.
    components.append(
        ScoreComponent(
            component_key="vdem_libdem",
            source_key="vdem",
            variable_name="vdem_v2x_libdem",
            direction="higher_is_better",
            raw_value=0.4,
            normalized_value_0_1=0.4,
            weight=0.35,
            contribution_0_1=0.14,
        )
    )
    assert len(result.components) == 1


def test_score_result_stores_review_flags_as_tuple() -> None:
    """A list of review flags is stored as a tuple (defensive copy)."""
    flags = [ReviewFlag.SPARSE_DATA, ReviewFlag.LOW_CONFIDENCE]
    result = ScoreResult(
        category_key="integrity",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        review_flags=flags,
        human_review_required=True,
    )
    assert isinstance(result.review_flags, tuple)
    # Mutating the caller's list must not affect the stored tuple.
    flags.append(ReviewFlag.PROVISIONAL_SCORE)
    assert len(result.review_flags) == 2


def test_missingness_summary_stores_pairs_as_tuple() -> None:
    """Reason/severity pairs are stored as a tuple of pairs (defensive copy)."""
    pairs = [("target_year_absent", 2)]
    summary = MissingnessSummary(
        total_expected=10,
        total_observed=8,
        by_reason=pairs,
    )
    assert isinstance(summary.by_reason, tuple)
    assert isinstance(summary.by_reason[0], tuple)
    pairs.append(("source_not_implemented", 1))
    assert len(summary.by_reason) == 1


# ---------------------------------------------------------------------------
# (e) MissingnessSummary.total_missing property
# ---------------------------------------------------------------------------


def test_missingness_summary_total_missing_typical_case() -> None:
    """``total_missing`` is ``total_expected - total_observed``."""
    summary = MissingnessSummary(total_expected=10, total_observed=7)
    assert summary.total_missing == 3


def test_missingness_summary_total_missing_clipped_at_zero() -> None:
    """``total_missing`` is clipped at zero (defends against plan-over-report)."""
    summary = MissingnessSummary(total_expected=5, total_observed=5)
    assert summary.total_missing == 0


# ---------------------------------------------------------------------------
# (f) ScoreResult.observed_component_count property
# ---------------------------------------------------------------------------


def test_observed_component_count_ignores_none_normalized() -> None:
    """The property counts only components with a non-None normalized value."""
    components = (
        ScoreComponent(
            component_key="vdem_polyarchy",
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            direction="higher_is_better",
            raw_value=0.5,
            normalized_value_0_1=0.5,
            weight=0.35,
            contribution_0_1=0.175,
        ),
        # Missing-observation placeholder: no raw value, no normalized
        # value, weight 0, contribution 0.
        ScoreComponent(
            component_key="wgi_voice",
            source_key="wgi",
            variable_name="wgi_voice_and_accountability",
            direction="higher_is_better",
            raw_value=None,
            normalized_value_0_1=None,
            weight=0.35,
            contribution_0_1=0.0,
        ),
        ScoreComponent(
            component_key="wgi_rule_of_law",
            source_key="wgi",
            variable_name="wgi_rule_of_law",
            direction="higher_is_better",
            raw_value=0.4,
            normalized_value_0_1=0.4,
            weight=0.30,
            contribution_0_1=0.12,
        ),
    )
    result = ScoreResult(
        category_key="effectiveness",
        iso3="MEX",
        year=2023,
        leader_name="AMLO",
        normalized_score_0_1=0.5,
        system_proposed_score_1_10=5,
        components=components,
    )
    assert result.observed_component_count == 2


# ---------------------------------------------------------------------------
# (g) Re-export from leaders_db.score
# ---------------------------------------------------------------------------


def test_results_are_reexported_from_score_package() -> None:
    """The five contract types are importable from the package root."""
    from leaders_db.score import (  # noqa: F401
        MissingnessSummary,
        ReviewFlag,
        ScoreComponent,
        ScoreObservationRef,
        ScoreResult,
    )
