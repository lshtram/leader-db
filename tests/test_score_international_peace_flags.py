"""Tests for the international-peace deterministic scorer
(:mod:`leaders_db.score.international_peace`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.international_peace.score_international_peace`:

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
in :mod:`tests.test_score_international_peace_insufficient_flags`.

The happy-path tests live in
:mod:`tests.test_score_international_peace`.

Style invariants (per ``docs/coding-guidelines.md``):

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
from leaders_db.score.international_peace import score_international_peace
from leaders_db.score.results import ReviewFlag
from tests._international_peace_factories import (
    international_peace_make_bundle,
    international_peace_make_obs,
    realistic_international_peace_observations,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_international_peace_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The international-peace plan declares one REQUIRED indicator:
    ``ucdp_state_based_fatalities`` (UCDP). Drop the UCDP
    REQUIRED from the bundle's observations AND record it as
    a PRIMARY missingness so the ``primary_missing_observations``
    accessor is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_state_based_fatalities",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources (ucdp + sipri_milex) clear the minimum-viable
    # gate so the insufficient-data path does not steal the
    # test; the UCDP REQUIRED is the only PRIMARY missingness.
    obs = [
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
    ]
    bundle = international_peace_make_bundle(observations=obs, missing=missing)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # UCDP REQUIRED is listed in the message body).
    assert "ucdp_state_based_fatalities" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_international_peace_sparse_flag_when_less_than_half_observed() -> (
    None
):
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``.

    Two sources clear the minimum-viable gate but together cover
    only 2 of the 8 plan indicators (~25%, well below the 0.5
    threshold). The result is a real score (not insufficient
    data) with the SPARSE_DATA flag attached.
    """
    obs = [
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
    ]
    bundle = international_peace_make_bundle(observations=obs)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 8
    assert result.missingness.total_observed == 2
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_international_peace_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with enough indicators across two sources to
    # clear minimum_viable, but at least one observation with a
    # PROXY temporal kind.
    obs = [
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "ucdp_state_based_fatalities",
            "ucdp",
            0.60,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
        international_peace_make_obs(
            "sipri_milex_per_capita", "sipri_milex", 0.60
        ),
    ]
    bundle = international_peace_make_bundle(observations=obs)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_international_peace_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "ucdp_state_based_fatalities", "ucdp", 0.60
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp",
            "sipri_milex",
            0.55,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
        ),
        international_peace_make_obs(
            "sipri_milex_per_capita", "sipri_milex", 0.60
        ),
    ]
    bundle = international_peace_make_bundle(observations=obs)
    result = score_international_peace(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_international_peace_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # Only one source → below the plan's minimum_viable_sources=2.
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events", "ucdp", 0.65
            ),
        ],
    )
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_international_peace_insufficient_data_only_one_source() -> None:
    """One source is below the threshold (plan asks for >= 2)."""
    # Two observations but both from ``ucdp`` — same source key, so
    # the distinct-source count is 1 (below minimum_viable_sources=2).
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events", "ucdp", 0.65
            ),
            international_peace_make_obs(
                "ucdp_state_based_fatalities", "ucdp", 0.60
            ),
        ],
    )
    result = score_international_peace(bundle)
    assert result.is_insufficient_data is True


def test_score_international_peace_emits_score_with_two_sources() -> None:
    """Two distinct sources clear the minimum-viable threshold."""
    obs = [
        international_peace_make_obs(
            "ucdp_state_based_events", "ucdp", 0.65
        ),
        international_peace_make_obs(
            "sipri_milex_share_of_gdp", "sipri_milex", 0.55
        ),
    ]
    bundle = international_peace_make_bundle(observations=obs)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_international_peace_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = international_peace_make_bundle()  # empty
    result = score_international_peace(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_international_peace_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (only one source).
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events", "ucdp", 0.65
            ),
        ]
    )
    result = score_international_peace(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True


def test_score_international_peace_realistic_bundle_no_flags() -> None:
    """The realistic fixture emits no review flags.

    All 8 indicators are present, all DIRECT, no PRIMARY
    missing rows, observed/expected = 8/8 ≥ 0.5. The
    result is a clean score with ``human_review_required=False``.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_international_peace(bundle)

    assert result.review_flags == ()
    assert result.human_review_required is False
