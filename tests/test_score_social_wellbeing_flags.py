"""Tests for the social-wellbeing deterministic scorer
(:mod:`leaders_db.score.social_wellbeing`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.social_wellbeing.score_social_wellbeing`:

- (a) Missing REQUIRED (severity PRIMARY) observation triggers
      :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` and forces
      ``human_review_required=True``.
- (b) Substantial missingness (less than half of plan indicators
      observed) triggers :attr:`ReviewFlag.SPARSE_DATA`.
- (c) PROXY or STALE observations trigger
      :attr:`ReviewFlag.LOW_CONFIDENCE` and the rationale
      ``rationale_short`` mentions the proxy/stale count.
- (d) The insufficient-data gate: when the bundle falls below
      the plan's ``minimum_viable_sources`` and the plan's
      :class:`SparseDataPolicy` is ``INSUFFICIENT_DATA``, the
      function returns a no-score result with both scores
      ``None`` and the :attr:`ReviewFlag.INSUFFICIENT_DATA` flag
      set.
- (e) The forward ``human_review_required`` invariant: any
      non-empty ``review_flags`` tuple implies
      ``human_review_required=True``. The
      :class:`ScoreResult` contract enforces this; this test
      pins the scorer-side value.

The happy-path tests live in
:mod:`tests.test_score_social_wellbeing`. The client comparison
delta test lives in :mod:`tests.test_score_social_wellbeing_client`.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on test parameters.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.results import ReviewFlag
from leaders_db.score.social_wellbeing import score_social_wellbeing
from tests._social_wellbeing_factories import (
    make_bundle,
    make_obs,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag."""
    missing = [
        MissingObservation(
            source_key="undp_hdi",
            variable_name="undp_hdi_hdi",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources, no HDI row, but enough other observations to clear
    # the minimum-viable gate and avoid INSUFFICIENT_DATA.
    obs = [
        make_obs("undp_hdi_life_expectancy", "undp_hdi", 0.70),
        make_obs("wdi_gini_index", "world_bank_wdi", 0.60),
        make_obs("vdem_v2x_egal", "vdem", 0.55),
    ]
    bundle = make_bundle(observations=obs, missing=missing)
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary.
    assert "undp_hdi_hdi" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_sparse_flag_when_less_than_half_observed() -> None:
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``."""
    # Only the HDI anchor is observed — 1 of 17 plan indicators is
    # well below the 0.5 threshold, and the bundle has only one
    # source (below minimum_viable_sources for INSUFFICIENT_DATA).
    bundle = make_bundle(
        observations=[make_obs("undp_hdi_hdi", "undp_hdi", 0.75)]
    )
    result = score_social_wellbeing(bundle)

    # The bundle has only one source, so minimum_viable_sources is
    # not met and the function routes to insufficient_data. Confirm
    # both INSUFFICIENT_DATA and SPARSE_DATA fire — the SPARSE_DATA
    # flag is part of the insufficiency payload by design.
    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.SPARSE_DATA in result.review_flags


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with enough indicators across two sources to
    # clear minimum_viable, but at least one observation with a
    # PROXY temporal kind.
    obs = [
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs(
            "undp_hdi_life_expectancy",
            "undp_hdi",
            0.70,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        make_obs("wdi_gini_index", "world_bank_wdi", 0.60),
        make_obs("vdem_v2x_egal", "vdem", 0.55),
    ]
    bundle = make_bundle(observations=obs)
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_social_wellbeing_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs(
            "vdem_v2x_egal",
            "vdem",
            0.55,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
        ),
        make_obs("wdi_gini_index", "world_bank_wdi", 0.60),
    ]
    bundle = make_bundle(observations=obs)
    result = score_social_wellbeing(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # Only one source → below the plan's minimum_viable_sources=2.
    bundle = make_bundle(
        observations=[make_obs("undp_hdi_hdi", "undp_hdi", 0.78)],
    )
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_social_wellbeing_insufficient_data_only_one_source() -> None:
    """One source is below the threshold (plan asks for >= 2)."""
    obs = [
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs("undp_hdi_life_expectancy", "undp_hdi", 0.70),
    ]
    bundle = make_bundle(observations=obs)
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is True


def test_score_social_wellbeing_emits_score_with_two_sources() -> None:
    """Two distinct sources clear the minimum-viable threshold."""
    obs = [
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs("vdem_v2x_egal", "vdem", 0.55),
    ]
    bundle = make_bundle(observations=obs)
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_social_wellbeing_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = make_bundle()  # empty
    result = score_social_wellbeing(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (less than half
    # observed) — only the HDI indicator observed.
    bundle = make_bundle(
        observations=[make_obs("undp_hdi_hdi", "undp_hdi", 0.75)]
    )
    result = score_social_wellbeing(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True
