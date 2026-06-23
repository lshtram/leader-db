"""Tests for the economic wellbeing deterministic scorer
(:mod:`leaders_db.score.economic_wellbeing`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.economic_wellbeing.score_economic_wellbeing`:

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
:mod:`tests.test_score_economic_wellbeing`.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints on test parameters. No ``print()``, no ``TODO(debug)``, no
scratch code.
"""

from __future__ import annotations

from leaders_db.score.economic_wellbeing import score_economic_wellbeing
from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.results import ReviewFlag
from tests._economic_wellbeing_factories import (
    economic_wellbeing_make_bundle,
    economic_wellbeing_make_obs,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The economic wellbeing plan declares two REQUIRED indicators:
    ``wdi_gdp_per_capita`` and
    ``wdi_gdp_per_capita_ppp_constant_2017``. Drop the WDI
    REQUIRED ``wdi_gdp_per_capita`` from the bundle's
    observations AND record it as a PRIMARY missingness so the
    ``primary_missing_observations`` accessor is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="world_bank_wdi",
            variable_name="wdi_gdp_per_capita",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Two sources clear the minimum-viable gate so the
    # insufficient-data path does not steal the test; the WDI
    # REQUIRED is the only PRIMARY missingness.
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita_ppp_constant_2017", "world_bank_wdi", 0.65
        ),
        economic_wellbeing_make_obs(
            "bti_q6_socioeconomic_development", "bti", 0.50
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs, missing=missing)
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # WDI REQUIRED is listed in the message body).
    assert "wdi_gdp_per_capita" in result.rationale_short


def test_score_economic_wellbeing_ppp_primary_missing_flag() -> None:
    """A missing WDI PPP REQUIRED also triggers the flag.

    Companion to the per-capita-missing test: a missing
    ``wdi_gdp_per_capita_ppp_constant_2017`` (REQUIRED) raises
    the same flag with the canonical attribution in the
    rationale.
    """
    missing = [
        MissingObservation(
            source_key="world_bank_wdi",
            variable_name="wdi_gdp_per_capita_ppp_constant_2017",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita", "world_bank_wdi", 0.60
        ),
        economic_wellbeing_make_obs(
            "bti_q6_socioeconomic_development", "bti", 0.50
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs, missing=missing)
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert (
        "wdi_gdp_per_capita_ppp_constant_2017" in result.rationale_short
    )


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_sparse_flag_when_below_minimum_viable() -> None:
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``.

    Only one observation from one source — below the
    ``minimum_viable_sources=1`` would clear, but with no
    observations at all the bundle falls to the
    insufficient-data path; SPARSE_DATA fires alongside.
    """
    bundle = economic_wellbeing_make_bundle()
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.SPARSE_DATA in result.review_flags


def test_score_economic_wellbeing_sparse_flag_above_minimum_viable() -> None:
    """Sparse-data flag fires when observed/total < 0.5 even with ≥ minimum viable sources.

    The WDI source clears the minimum-viable gate but covers
    only 1 of the 12 plan indicators (8.3%, well below the 0.5
    threshold). The result is a real score (not insufficient
    data) with the SPARSE_DATA flag attached.
    """
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita", "world_bank_wdi", 0.60
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs)
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 12
    assert result.missingness.total_observed == 1
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_proxy_observation_triggers_low_confidence_flag() -> (
    None
):
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with at least one observation that has a
    # PROXY temporal kind.
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita",
            "world_bank_wdi",
            0.60,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita_ppp_constant_2017", "world_bank_wdi", 0.65
        ),
        economic_wellbeing_make_obs(
            "bti_q6_socioeconomic_development", "bti", 0.50
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs)
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_economic_wellbeing_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita", "world_bank_wdi", 0.60
        ),
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita_ppp_constant_2017", "world_bank_wdi", 0.65
        ),
        economic_wellbeing_make_obs(
            "bti_q6_socioeconomic_development",
            "bti",
            0.50,
            observation_year=2020,
            temporal_kind=TemporalKind.STALE,
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs)
    result = score_economic_wellbeing(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_insufficient_data_when_below_minimum_viable() -> (
    None
):
    """Below ``minimum_viable_sources`` with INSUFFICIENT_DATA policy → no score."""
    # No observations → below the plan's ``minimum_viable_sources=1``.
    bundle = economic_wellbeing_make_bundle()
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()


def test_score_economic_wellbeing_emits_score_with_one_source() -> None:
    """One distinct source with a usable observation clears the minimum-viable gate."""
    obs = [
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita", "world_bank_wdi", 0.60
        ),
        economic_wellbeing_make_obs(
            "wdi_gdp_per_capita_ppp_constant_2017", "world_bank_wdi", 0.65
        ),
    ]
    bundle = economic_wellbeing_make_bundle(observations=obs)
    result = score_economic_wellbeing(bundle)

    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_economic_wellbeing_insufficient_data_does_not_silently_overwrite() -> (
    None
):
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = economic_wellbeing_make_bundle()  # empty
    result = score_economic_wellbeing(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


# ---------------------------------------------------------------------------
# (e) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_economic_wellbeing_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (no observations).
    bundle = economic_wellbeing_make_bundle()
    result = score_economic_wellbeing(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True
