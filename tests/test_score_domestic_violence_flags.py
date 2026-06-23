"""Tests for the domestic-violence deterministic scorer
(:mod:`leaders_db.score.domestic_violence`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.domestic_violence.score_domestic_violence`:

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

Insufficient-data branch flag derivation (the prepended
``INSUFFICIENT_DATA`` flag plus the derived
``MISSING_PRIMARY_SOURCE`` / ``SPARSE_DATA`` /
``LOW_CONFIDENCE`` triple on the insufficient-data path) lives
in :mod:`tests.test_score_domestic_violence_insufficient_flags`.

The happy-path tests live in
:mod:`tests.test_score_domestic_violence`.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on test parameters.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.domestic_violence import score_domestic_violence
from leaders_db.score.evidence import (
    Direction,
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.results import ReviewFlag
from tests._domestic_violence_factories import (
    domestic_violence_make_bundle,
    domestic_violence_make_obs,
    realistic_domestic_violence_observations,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_domestic_violence_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The domestic-violence plan declares two REQUIRED indicators:
    ``pts_amnesty_score`` (PTS) and ``cirights_physint``
    (CIRIGHTS). Drop the PTS REQUIRED from the bundle's
    observations AND record it as a PRIMARY missingness so the
    ``primary_missing_observations`` accessor is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="pts",
            variable_name="pts_amnesty_score",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources (cirights + ucdp) clear the minimum-viable
    # gate so the insufficient-data path does not steal the
    # test; the PTS REQUIRED is the only PRIMARY missingness.
    obs = [
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs, missing=missing)
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # PTS REQUIRED is listed in the message body).
    assert "pts_amnesty_score" in result.rationale_short


def test_score_domestic_violence_cirights_primary_missing_flag() -> None:
    """A missing CIRIGHTS physint REQUIRED also triggers the flag.

    Companion to the pts-amnesty-missing test: a missing
    ``cirights_physint`` (REQUIRED) raises the same flag with
    the canonical attribution in the rationale.
    """
    missing = [
        MissingObservation(
            source_key="cirights",
            variable_name="cirights_physint",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    obs = [
        domestic_violence_make_obs(
            "pts_amnesty_score", "pts", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs, missing=missing)
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert "cirights_physint" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_domestic_violence_sparse_flag_when_less_than_half_observed() -> (
    None
):
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``.

    Two sources clear the minimum-viable gate but together cover
    only 2 of the 17 plan indicators (~12%, well below the 0.5
    threshold). The result is a real score (not insufficient
    data) with the SPARSE_DATA flag attached.
    """
    obs = [
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs)
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 17
    assert result.missingness.total_observed == 2
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_domestic_violence_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with enough indicators across two sources to
    # clear minimum_viable, but at least one observation with a
    # PROXY temporal kind.
    obs = [
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs(
            "cirights_physint",
            "cirights",
            0.60,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        domestic_violence_make_obs(
            "pts_amnesty_score", "pts", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs)
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_domestic_violence_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs(
            "pts_amnesty_score", "pts", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
        domestic_violence_make_obs(
            "ucdp_onesided_events",
            "ucdp",
            0.65,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs)
    result = score_domestic_violence(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_domestic_violence_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # Only one source → below the plan's minimum_viable_sources=2.
    bundle = domestic_violence_make_bundle(
        observations=[
            domestic_violence_make_obs(
                "pts_amnesty_score", "pts", 0.65,
                direction=Direction.LOWER_IS_BETTER,
            ),
        ],
    )
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_domestic_violence_insufficient_data_only_one_source() -> None:
    """One source is below the threshold (plan asks for >= 2)."""
    # Two observations but both from ``pts`` — same source key, so
    # the distinct-source count is 1 (below minimum_viable_sources=2).
    bundle = domestic_violence_make_bundle(
        observations=[
            domestic_violence_make_obs(
                "pts_amnesty_score", "pts", 0.65,
                direction=Direction.LOWER_IS_BETTER,
            ),
            domestic_violence_make_obs(
                "pts_human_rights_watch_score", "pts", 0.60,
                direction=Direction.LOWER_IS_BETTER,
            ),
        ],
    )
    result = score_domestic_violence(bundle)
    assert result.is_insufficient_data is True


def test_score_domestic_violence_emits_score_with_two_sources() -> None:
    """Two distinct sources clear the minimum-viable threshold."""
    obs = [
        domestic_violence_make_obs("cirights_physint", "cirights", 0.65),
        domestic_violence_make_obs(
            "ucdp_onesided_events", "ucdp", 0.65,
            direction=Direction.LOWER_IS_BETTER,
        ),
    ]
    bundle = domestic_violence_make_bundle(observations=obs)
    result = score_domestic_violence(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_domestic_violence_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = domestic_violence_make_bundle()  # empty
    result = score_domestic_violence(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_domestic_violence_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (only one source).
    bundle = domestic_violence_make_bundle(
        observations=[
            domestic_violence_make_obs(
                "pts_amnesty_score", "pts", 0.65,
                direction=Direction.LOWER_IS_BETTER,
            ),
        ]
    )
    result = score_domestic_violence(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True


def test_score_domestic_violence_realistic_bundle_no_flags() -> None:
    """The realistic fixture emits no review flags.

    All 17 indicators are present, all DIRECT, no PRIMARY
    missing rows, observed/expected = 17/17 ≥ 0.5. The
    result is a clean score with ``human_review_required=False``.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_domestic_violence(bundle)

    assert result.review_flags == ()
    assert result.human_review_required is False
