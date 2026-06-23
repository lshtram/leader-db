"""Tests for the political freedom deterministic scorer
(:mod:`leaders_db.score.political_freedom`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.political_freedom.score_political_freedom`:

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
:mod:`tests.test_score_political_freedom`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints on test parameters. No ``print()``, no ``TODO(debug)``, no
scratch code.
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.political_freedom import score_political_freedom
from leaders_db.score.results import ReviewFlag
from tests._political_freedom_factories import (
    political_freedom_make_bundle,
    political_freedom_make_obs,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_political_freedom_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The political freedom plan declares two REQUIRED indicators:
    ``vdem_v2x_polyarchy`` and ``vdem_v2x_libdem``. Drop the V-Dem
    REQUIRED ``vdem_v2x_polyarchy`` from the bundle's
    observations AND record it as a PRIMARY missingness so the
    ``primary_missing_observations`` accessor is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources clear the minimum-viable gate so the
    # insufficient-data path does not steal the test; the V-Dem
    # REQUIRED is the only PRIMARY missingness.
    obs = [
        political_freedom_make_obs("vdem_v2x_libdem", "vdem", 0.45),
        political_freedom_make_obs("bti_status_index", "bti", 0.50),
    ]
    bundle = political_freedom_make_bundle(observations=obs, missing=missing)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # V-Dem REQUIRED is listed in the message body).
    assert "vdem_v2x_polyarchy" in result.rationale_short


def test_score_political_freedom_libdem_primary_missing_flag() -> None:
    """A missing V-Dem libdem REQUIRED also triggers the flag.

    Companion to the polyarchy-missing test: a missing
    ``vdem_v2x_libdem`` (REQUIRED) raises the same flag with the
    canonical attribution in the rationale.
    """
    missing = [
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_libdem",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    obs = [
        political_freedom_make_obs("vdem_v2x_polyarchy", "vdem", 0.50),
        political_freedom_make_obs("bti_status_index", "bti", 0.50),
    ]
    bundle = political_freedom_make_bundle(observations=obs, missing=missing)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert "vdem_v2x_libdem" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_political_freedom_sparse_flag_when_below_minimum_viable() -> None:
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``.

    Only one observation from one source — below the
    ``minimum_viable_sources=2`` would clear, but with no
    observations at all the bundle falls to the
    insufficient-data path; SPARSE_DATA fires alongside.
    """
    bundle = political_freedom_make_bundle()
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.SPARSE_DATA in result.review_flags


def test_score_political_freedom_sparse_flag_above_minimum_viable() -> None:
    """Sparse-data flag fires when observed/total < 0.5 even with ≥ minimum viable sources.

    Two sources clear the minimum-viable gate but the V-Dem
    source covers only 1 of the 16 plan indicators (6.25%, well
    below the 0.5 threshold). The result is a real score (not
    insufficient data) with the SPARSE_DATA flag attached.
    """
    obs = [
        political_freedom_make_obs("vdem_v2x_polyarchy", "vdem", 0.50),
        political_freedom_make_obs("bti_status_index", "bti", 0.50),
    ]
    bundle = political_freedom_make_bundle(observations=obs)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 16
    assert result.missingness.total_observed == 2
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_political_freedom_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with at least one observation that has a
    # PROXY temporal kind.
    obs = [
        political_freedom_make_obs(
            "vdem_v2x_polyarchy",
            "vdem",
            0.50,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        political_freedom_make_obs("vdem_v2x_libdem", "vdem", 0.45),
        political_freedom_make_obs("bti_status_index", "bti", 0.50),
    ]
    bundle = political_freedom_make_bundle(observations=obs)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_political_freedom_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        political_freedom_make_obs("vdem_v2x_polyarchy", "vdem", 0.50),
        political_freedom_make_obs("vdem_v2x_libdem", "vdem", 0.45),
        political_freedom_make_obs(
            "bti_status_index",
            "bti",
            0.50,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
        ),
    ]
    bundle = political_freedom_make_bundle(observations=obs)
    result = score_political_freedom(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_political_freedom_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # No observations → below the plan's ``minimum_viable_sources=2``.
    bundle = political_freedom_make_bundle()
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_political_freedom_emits_score_with_two_sources() -> None:
    """Two distinct sources with usable observations clear the minimum-viable gate."""
    obs = [
        political_freedom_make_obs("vdem_v2x_polyarchy", "vdem", 0.50),
        political_freedom_make_obs("vdem_v2x_libdem", "vdem", 0.45),
        political_freedom_make_obs("bti_status_index", "bti", 0.50),
    ]
    bundle = political_freedom_make_bundle(observations=obs)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_political_freedom_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = political_freedom_make_bundle()  # empty
    result = score_political_freedom(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_political_freedom_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (no observations).
    bundle = political_freedom_make_bundle()
    result = score_political_freedom(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True
