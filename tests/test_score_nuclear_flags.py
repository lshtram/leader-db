"""Tests for the nuclear deterministic scorer
(:mod:`leaders_db.score.nuclear`) — flag detection paths.

These tests pin the **flag-detection** behaviour of
:func:`leaders_db.score.nuclear.score_nuclear`:

- (a) Missing REQUIRED (severity PRIMARY) observation triggers
      :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` and forces
      ``human_review_required=True``.
- (b) Substantial missingness (less than half of plan indicators
      observed) triggers :attr:`ReviewFlag.SPARSE_DATA`.
- (c) PROXY or STALE observations trigger
      :attr:`ReviewFlag.LOW_CONFIDENCE` and the rationale
      ``rationale_short`` mentions the proxy/stale count.
- (d) The insufficient-data gate: when the bundle falls below
      the plan's ``minimum_viable_sources``, the function
      returns a no-score result with both scores ``None`` and
      the :attr:`ReviewFlag.INSUFFICIENT_DATA` flag set.
- (e) The NUCLEAR_CASE population-split flag fires on the
      scored path iff the bundle carries any usable
      nuclear-source observation (the §14 manual-review-queue
      hook per REQ-REV-002: "nuclear / global responsibility
      cases").
- (f) The forward ``human_review_required`` invariant: any
      non-empty ``review_flags`` tuple implies
      ``human_review_required=True``.

Insufficient-data branch flag derivation (the prepended
``INSUFFICIENT_DATA`` flag plus the derived
``MISSING_PRIMARY_SOURCE`` / ``SPARSE_DATA`` /
``LOW_CONFIDENCE`` triple on the insufficient-data path; plus
the nuclear-specific "non-nuclear / no nuclear-source evidence"
rationale wording) lives in
:mod:`tests.test_score_nuclear_insufficient_flags`.

The happy-path tests live in :mod:`tests.test_score_nuclear`.

Style invariants (per ``docs/process/coding-guidelines.md``):
``from __future__ import annotations`` for forward-reference
safety. Type hints on test parameters. No ``print()``, no
``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
    TemporalKind,
)
from leaders_db.score.nuclear import score_nuclear
from leaders_db.score.results import ReviewFlag
from tests._nuclear_factories import (
    nuclear_make_bundle,
    nuclear_make_obs,
    realistic_nuclear_observations,
)

# ---------------------------------------------------------------------------
# (a) Missing REQUIRED (severity PRIMARY) observation → MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------


def test_score_nuclear_missing_primary_source_flag() -> None:
    """A missing REQUIRED indicator (severity PRIMARY) raises the flag.

    The nuclear plan declares two REQUIRED indicators (one in
    each rubric group): ``fas_total_inventory`` (FAS) and
    ``sipri_yearbook_ch7_nuclear_warheads_total_inventory``
    (SIPRI). Drop the FAS REQUIRED from the bundle's
    observations AND record it as a PRIMARY missingness so the
    ``primary_missing_observations`` accessor is non-empty.
    """
    missing = [
        MissingObservation(
            source_key="fas",
            variable_name="fas_total_inventory",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Both sources clear the minimum-viable gate so the
    # insufficient-data path does not steal the test; the FAS
    # REQUIRED is the only PRIMARY missingness.
    obs = [
        nuclear_make_obs("fas_operational_strategic", "fas", 0.30),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
            "sipri_yearbook_ch7",
            0.40,
        ),
    ]
    bundle = nuclear_make_bundle(observations=obs, missing=missing)
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    assert result.human_review_required is True
    # The rationale mentions the missing primary (the canonical
    # FAS + SIPRI REQUIREDs are listed in the message body).
    assert "fas_total_inventory" in result.rationale_short


# ---------------------------------------------------------------------------
# (b) Sparse data → SPARSE_DATA
# ---------------------------------------------------------------------------


def test_score_nuclear_sparse_flag_when_less_than_half_observed() -> None:
    """Sparse data triggers ``SPARSE_DATA`` and ``human_review_required=True``.

    One source clears the minimum-viable gate but covers only
    1 of the 8 plan indicators (~12.5%, well below the 0.5
    threshold). The result is a real score (not insufficient
    data) with the SPARSE_DATA flag attached.
    """
    obs = [
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
            "sipri_yearbook_ch7",
            0.40,
        ),
    ]
    bundle = nuclear_make_bundle(observations=obs)
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert result.missingness is not None
    assert result.missingness.total_expected == 8
    assert result.missingness.total_observed == 1
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# (c) Proxy / stale observations → LOW_CONFIDENCE
# ---------------------------------------------------------------------------


def test_score_nuclear_proxy_observation_triggers_low_confidence_flag() -> None:
    """A non-DIRECT observation raises ``LOW_CONFIDENCE`` and mentions proxy."""
    # Build a bundle with enough indicators across two sources to
    # clear minimum_viable, but at least one observation with a
    # PROXY temporal kind.
    obs = [
        nuclear_make_obs("fas_operational_strategic", "fas", 0.30),
        nuclear_make_obs(
            "fas_total_inventory",
            "fas",
            0.25,
            observation_year=2022,
            temporal_kind=TemporalKind.PROXY,
        ),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
            "sipri_yearbook_ch7",
            0.40,
        ),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_deployed",
            "sipri_yearbook_ch7",
            0.55,
        ),
    ]
    bundle = nuclear_make_bundle(observations=obs)
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale explicitly calls out the proxy/stale count.
    assert "proxy" in result.rationale_short.lower()


def test_score_nuclear_stale_observation_also_low_confidence() -> None:
    """STALE observations also raise ``LOW_CONFIDENCE`` (temporal fit reduced)."""
    obs = [
        nuclear_make_obs("fas_operational_strategic", "fas", 0.30),
        nuclear_make_obs("fas_total_inventory", "fas", 0.25),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
            "sipri_yearbook_ch7",
            0.40,
            observation_year=2018,
            temporal_kind=TemporalKind.STALE,
        ),
        nuclear_make_obs(
            "sipri_yearbook_ch7_nuclear_warheads_deployed",
            "sipri_yearbook_ch7",
            0.55,
        ),
    ]
    bundle = nuclear_make_bundle(observations=obs)
    result = score_nuclear(bundle)

    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


# ---------------------------------------------------------------------------
# (d) Insufficient-data gate
# ---------------------------------------------------------------------------


def test_score_nuclear_insufficient_data_when_below_minimum_viable() -> None:
    """Below ``minimum_viable_sources`` → no score, INSUFFICIENT_DATA flag.

    The nuclear plan requires ``minimum_viable_sources=1``;
    an empty bundle has 0 distinct sources of usable
    observations and must come back as
    ``is_insufficient_data=True`` with no score. The
    rationale explicitly says "non-nuclear state" so a
    manual-review reader can distinguish a non-nuclear country
    (the ~190 case) from a sparse-bundle pathology.
    """
    bundle = nuclear_make_bundle(
        iso3="MEX",
        country_name="Mexico",
        leader_name="Andrés Manuel López Obrador",
    )
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert result.human_review_required is True
    # No components / refs were emitted in the insufficient-data
    # path — the rationale explains the gate instead.
    assert result.components == ()
    assert result.observation_refs == ()
    # The nuclear-specific rationale wording explicitly says
    # "non-nuclear state" so a manual-review reader can
    # distinguish the ~190 non-nuclear countries from a
    # sparse-bundle pathology.
    assert "non-nuclear" in result.rationale_short.lower()


def test_score_nuclear_insufficient_data_does_not_silently_overwrite() -> None:
    """Insufficient-data results carry ``None`` for both scores, not zeros.

    A common bug is to silently emit score=0 when the bundle is
    empty; the contract requires ``None`` so the manual-review
    queue can distinguish "no score" from "lowest possible score".
    """
    bundle = nuclear_make_bundle()  # empty
    result = score_nuclear(bundle)

    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.is_insufficient_data is True


def test_score_nuclear_insufficient_data_no_nuclear_case_flag() -> None:
    """The insufficient-data path does **not** fire NUCLEAR_CASE.

    The NUCLEAR_CASE population-split flag is the §14 manual-
    review-queue hook per REQ-REV-002 ("nuclear / global
    responsibility cases"). The flag fires on the **scored**
    path iff the bundle carries any usable nuclear-source
    observation. A non-nuclear state with no observations is
    the absence of a nuclear case, not a "nuclear case"
    itself — so the flag is deliberately **not** added on the
    insufficient-data path.
    """
    bundle = nuclear_make_bundle(iso3="MEX", country_name="Mexico")
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.NUCLEAR_CASE not in result.review_flags


# ---------------------------------------------------------------------------
# (e) NUCLEAR_CASE population-split flag
# ---------------------------------------------------------------------------


def test_score_nuclear_nuclear_case_flag_fires_when_fas_present() -> None:
    """A bundle with only FAS observations (one source) still fires NUCLEAR_CASE.

    The minimum-viable threshold is 1 distinct source of usable
    observations; FAS alone clears it. The NUCLEAR_CASE flag is
    the population-split signal — it fires on the scored path
    whenever the bundle carries any usable nuclear-source
    observation (FAS or SIPRI Yearbook Ch.7), regardless of
    which source carries it.
    """
    bundle = nuclear_make_bundle(
        observations=[
            nuclear_make_obs("fas_total_inventory", "fas", 0.25),
        ]
    )
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags


def test_score_nuclear_nuclear_case_flag_fires_when_sipri_present() -> None:
    """A bundle with only SIPRI Yearbook Ch.7 observations also fires NUCLEAR_CASE."""
    bundle = nuclear_make_bundle(
        observations=[
            nuclear_make_obs(
                "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
                "sipri_yearbook_ch7",
                0.40,
            ),
        ]
    )
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is False
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags


# ---------------------------------------------------------------------------
# (f) human_review_required invariant
# ---------------------------------------------------------------------------


def test_score_nuclear_any_flag_implies_human_review_required() -> None:
    """Any non-empty ``review_flags`` forces ``human_review_required=True``.

    The forward invariant is enforced by
    :meth:`ScoreResult.__post_init__`; this test pins the
    scorer-side value so a regression in the scorer (e.g.
    forgetting to forward the flag) is caught.
    """
    # Build a bundle that triggers SPARSE_DATA (only one
    # indicator observed across one source).
    bundle = nuclear_make_bundle(
        observations=[
            nuclear_make_obs(
                "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
                "sipri_yearbook_ch7",
                0.40,
            ),
        ]
    )
    result = score_nuclear(bundle)

    assert result.review_flags  # at least one flag
    assert result.human_review_required is True


def test_score_nuclear_realistic_bundle_has_nuclear_case_flag() -> None:
    """The realistic fixture emits NUCLEAR_CASE on the scored path.

    The realistic fixture crosses both rubric groups (FAS +
    SIPRI Yearbook Ch.7), so the bundle clears the minimum-
    viable threshold and the scorer emits a real
    (non-insufficient-data) result. The NUCLEAR_CASE
    population-split flag fires on the scored path because
    the bundle carries usable FAS / SIPRI Yearbook Ch.7
    observations.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_nuclear(bundle)

    assert result.review_flags  # at least one flag (NUCLEAR_CASE)
    assert result.human_review_required is True
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags
