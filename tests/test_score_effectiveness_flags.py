"""Tests for the effectiveness deterministic scorer
(:mod:`leaders_db.score.effectiveness`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.effectiveness.score_effectiveness`:

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
      ``human_review_required=True``.

The happy-path tests live in
:mod:`tests.test_score_effectiveness`.

Style invariants (per ``docs/coding-guidelines.md``): type
hints on test parameters.
No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.effectiveness import score_effectiveness
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.results import ReviewFlag
from tests._effectiveness_factories import (
    effectiveness_make_bundle,
    effectiveness_make_obs,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_effectiveness_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The effectiveness plan declares four REQUIRED indicators:
    ``wgi_government_effectiveness`` and ``wgi_rule_of_law``
    (WGI), ``vdem_v2x_accountability`` (V-Dem), and
    ``bti_governance_index`` (BTI). Drop the WGI REQUIRED from
    the bundle's observations AND record it as a PRIMARY
    missingness so the ``primary_missing_observations`` accessor
    is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="wgi",
            variable_name="wgi_government_effectiveness",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources (vdem + bti) clear the minimum-viable gate so
    # the insufficient-data path does not steal the test; the
    # WGI REQUIRED is the only PRIMARY missingness.
    obs = [
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
        effectiveness_make_obs("bti_governance_index", "bti", 0.50),
    ]
    bundle = effectiveness_make_bundle(observations=obs, missing=missing)
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # WGI REQUIRED is listed in the message body).
    assert "wgi_government_effectiveness" in result.rationale_short


def test_score_effectiveness_bti_primary_missing_flag() -> None:
    """A missing BTI REQUIRED also triggers the flag.

    Companion to the WGI-missing test: a missing
    ``bti_governance_index`` (REQUIRED) raises the same flag
    with the canonical attribution in the rationale.
    """
    missing = [
        MissingObservation(
            source_key="bti",
            variable_name="bti_governance_index",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    obs = [
        effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
    ]
    bundle = effectiveness_make_bundle(observations=obs, missing=missing)
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert "bti_governance_index" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_effectiveness_sparse_flag_when_less_than_half_observed() -> None:
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``."""
    # Only one observation from one source — below the
    # ``minimum_viable_sources=2`` threshold. The plan's
    # INSUFFICIENT_DATA policy routes the result to the
    # insufficient-data path; SPARSE_DATA fires alongside.
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65)
        ]
    )
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.SPARSE_DATA in result.review_flags


def test_score_effectiveness_sparse_flag_above_minimum_viable() -> None:
    """Sparse-data flag fires when observed/total < 0.5 even with ≥ minimum viable sources.

    Two sources clear the minimum-viable gate but together cover
    only 2 of the 12 plan indicators (16.7%, well below the 0.5
    threshold). The result is a real score (not insufficient
    data) with the SPARSE_DATA flag attached.
    """
    obs = [
        effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
    ]
    bundle = effectiveness_make_bundle(observations=obs)
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 12
    assert result.missingness.total_observed == 2
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_effectiveness_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with enough indicators across two sources to
    # clear minimum_viable, but at least one observation with a
    # PROXY temporal kind.
    obs = [
        effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65),
        effectiveness_make_obs(
            "wgi_government_effectiveness",
            "wgi",
            0.60,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
        effectiveness_make_obs("bti_governance_index", "bti", 0.50),
    ]
    bundle = effectiveness_make_bundle(observations=obs)
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_effectiveness_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
        effectiveness_make_obs(
            "bti_governance_index",
            "bti",
            0.50,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
        ),
    ]
    bundle = effectiveness_make_bundle(observations=obs)
    result = score_effectiveness(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_effectiveness_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # Only one source → below the plan's minimum_viable_sources=2.
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness", "wgi", 0.65
            )
        ],
    )
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_effectiveness_insufficient_data_only_one_source() -> None:
    """One source is below the threshold (plan asks for >= 2)."""
    # Two observations but both from ``wgi`` — same source key,
    # so the distinct-source count is 1 (below
    # minimum_viable_sources=2).
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness", "wgi", 0.65
            ),
            effectiveness_make_obs("wgi_rule_of_law", "wgi", 0.50),
        ],
    )
    result = score_effectiveness(bundle)
    assert result.is_insufficient_data is True


def test_score_effectiveness_emits_score_with_two_sources() -> None:
    """Two distinct sources clear the minimum-viable threshold."""
    obs = [
        effectiveness_make_obs("wgi_government_effectiveness", "wgi", 0.65),
        effectiveness_make_obs("vdem_v2x_accountability", "vdem", 0.65),
    ]
    bundle = effectiveness_make_bundle(observations=obs)
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_effectiveness_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = effectiveness_make_bundle()  # empty
    result = score_effectiveness(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_effectiveness_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (only one
    # observation, below the minimum-viable gate and the
    # 0.5-observed threshold).
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness", "wgi", 0.65
            )
        ]
    )
    result = score_effectiveness(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True
