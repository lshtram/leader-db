"""Tests for the nuclear deterministic scorer — scoring-basis
filter regression tests.

These tests pin the regression fix for the reviewer blocker
"non-FAS / non-SIPRI source carrying expected nuclear
variable must not invent a numeric score" on the nuclear
scorer. Before the fix, the scorer's scoring-basis filter
stripped only client sources (via
:func:`filter_excluded_observations`) and let any other
source through, so a hand-built bundle carrying
``source_key="wgi"`` and ``variable_name="fas_total_inventory"``
sneaked through the viable-data gate and emitted an
**invented** numeric score. The fix introduces
:func:`leaders_db.score._nuclear_components.filter_scoring_basis`
that requires BOTH the expected nuclear variable AND its
owning nuclear source (``fas`` / ``sipri_yearbook_ch7``) on
every scoring-basis observation. A wrong-source row is
ignored by the scoring basis and routes the bundle to the
insufficient-data path with both scores ``None`` and no
:attr:`ReviewFlag.NUCLEAR_CASE` flag.

The split mirrors the production code split (the nuclear
scorer is broken into :mod:`leaders_db.score.nuclear`
(facade), :mod:`leaders_db.score._nuclear_components`
(per-component helpers including the scoring-basis filter),
:mod:`leaders_db.score._nuclear_flags` (flag-detection
helpers), and :mod:`leaders_db.score._nuclear_result`
(insufficient-data :class:`ScoreResult` assembler)). The
test surface follows the same pattern:

- :mod:`tests.test_score_nuclear_remediation` — the
  client-source missingness regression tests (reviewer
  blocker "client-contamination / missingness correctness");
- :mod:`tests.test_score_nuclear_scoring_basis` — this file,
  the scoring-basis filter regressions (reviewer blocker
  "non-FAS / non-SIPRI source carrying expected nuclear
  variable must not invent a numeric score").

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import re

from leaders_db.score.evidence import (
    Direction,
    EvidenceObservation,
    TemporalKind,
)
from leaders_db.score.nuclear import score_nuclear
from leaders_db.score.results import ReviewFlag
from tests._nuclear_factories import nuclear_make_bundle

# Pattern that catches a numeric-score sentence such as
# "score 1/10" or "score 5/10". The scoring basis must not
# emit a numeric-score sentence on the insufficient-data path
# (the contract requires ``system_proposed_score_1_10 is None``;
# a non-nuclear state / wrong-source state must never receive
# an invented numeric score).
_NUMERIC_SCORE_PATTERN: re.Pattern[str] = re.compile(r"\bscore\s+\d+/10\b")

# ---------------------------------------------------------------------------
# Non-FAS / non-SIPRI source carrying expected nuclear variable — no score
# ---------------------------------------------------------------------------
#
# Closes the reviewer blocker "nuclear scorer can invent a score
# for a hand-built bundle carrying an expected nuclear variable
# on a non-FAS / non-SIPRI source". Before the fix the scorer
# filtered only client sources (via
# :func:`filter_excluded_observations`), so a hand-built bundle
# with ``source_key="wgi"`` and
# ``variable_name="fas_total_inventory"`` sneaked through the
# viable-data gate and emitted a real (invented) numeric score.
# The fix introduces
# :func:`leaders_db.score._nuclear_components.filter_scoring_basis`
# that requires BOTH the expected nuclear variable AND its
# owning nuclear source (``fas`` / ``sipri_yearbook_ch7``) on
# every scoring-basis observation. A wrong-source row must be
# ignored by the scoring basis and route the bundle to the
# insufficient-data path with both scores ``None`` and no
# NUCLEAR_CASE flag.


def test_score_nuclear_non_nuclear_source_with_nuclear_variable_routes_to_insufficient() -> (
    None
):
    """A hand-built bundle carrying ``source_key="wgi"`` and
    ``variable_name="fas_total_inventory"`` (a non-client, non-nuclear
    source carrying an expected nuclear variable) must route to the
    insufficient-data path.

    Closes the reviewer blocker: before the fix the nuclear scorer
    filtered only client sources, so a non-nuclear source row could
    pass the viable-data gate and emit an invented numeric score.
    The fix routes such a bundle to ``is_insufficient_data=True``
    with both scores ``None`` and no components / observation refs.
    """
    contaminated = EvidenceObservation(
        source_key="wgi",
        source_name="wgi (probe)",
        variable_name="fas_total_inventory",
        raw_value="0.4200",
        numeric_value=0.42,
        normalized_value=0.42,
        unit="index",
        direction=Direction.LOWER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="wgi:fas_total_inventory:2023",
        authority_score=70,
        specificity_score=80,
    )
    bundle = nuclear_make_bundle(observations=[contaminated])
    result = score_nuclear(bundle)

    # No score — both scores must be ``None`` (the no-invented-score
    # invariant requires the bundle to route through the
    # insufficient-data path when the scoring basis has no
    # valid nuclear-source evidence).
    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None

    # No components / refs — the scoring basis has no FAS / SIPRI
    # Yearbook Ch.7 evidence so the score path is never reached.
    assert result.components == ()
    assert result.observation_refs == ()

    # NUCLEAR_CASE must NOT fire — a wrong-source row carrying an
    # expected nuclear variable is not "a nuclear case", it is the
    # absence of one.
    assert ReviewFlag.NUCLEAR_CASE not in result.review_flags, (
        "NUCLEAR_CASE must not fire for a non-FAS / non-SIPRI "
        "source row; got review_flags="
        f"{list(result.review_flags)}"
    )

    # The rationale must NOT state or imply a numeric score (the
    # scorer used to interpolate ``score_1_10=1`` as a
    # placeholder here, which the prior reviewer blocker fix
    # closed).
    assert not _NUMERIC_SCORE_PATTERN.search(result.rationale_short), (
        "non-FAS / non-SIPRI rationale must not contain a numeric "
        f"score (got: {result.rationale_short!r})"
    )
    # And the gate-signal sentence names the canonical cause so a
    # reviewer can act on it without re-walking the bundle.
    assert "no score emitted" in result.rationale_short.lower(), (
        "non-FAS / non-SIPRI rationale must say 'no score emitted' "
        f"(got: {result.rationale_short!r})"
    )
    # The wrong-source / non-nuclear-source sentence is the
    # canonical signal that distinguishes this case from a
    # sparse-bundle pathology.
    assert "no nuclear-source evidence" in result.rationale_short.lower(), (
        "non-FAS / non-SIPRI rationale must say 'no nuclear-source "
        f"evidence' (got: {result.rationale_short!r})"
    )

    # Insufficient-data flag is the gate signal; SPARSE_DATA rides
    # along because the scoring-basis observed ratio is 0/8
    # (well below the 0.5 threshold).
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.SPARSE_DATA in result.review_flags
    # human_review_required is True (the forward invariant: any
    # non-empty ``review_flags`` forces human review).
    assert result.human_review_required is True


def test_score_nuclear_mismatched_variable_and_source_still_insufficient() -> None:
    """A bundle carrying an expected nuclear variable attributed to the
    WRONG owning source (e.g. ``sipri_yearbook_ch7`` carrying the FAS
    variable) must also route to insufficient-data.

    Defence-in-depth companion test: even when both ``source_key`` and
    ``variable_name`` look "nuclear-shaped" individually, the per-
    variable ownership rule must be enforced — a SIPRI Yearbook Ch.7
    observation cannot carry the FAS variable, and vice versa.
    """
    mismatched = EvidenceObservation(
        source_key="sipri_yearbook_ch7",
        source_name="sipri_yearbook_ch7 (probe)",
        variable_name="fas_total_inventory",
        raw_value="0.5000",
        numeric_value=0.50,
        normalized_value=0.50,
        unit="index",
        direction=Direction.LOWER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=(
            "sipri_yearbook_ch7:fas_total_inventory:2023"
        ),
        authority_score=70,
        specificity_score=80,
    )
    bundle = nuclear_make_bundle(observations=[mismatched])
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.components == ()
    assert result.observation_refs == ()
    # NUCLEAR_CASE must NOT fire — the SIPRI Yearbook Ch.7 row
    # cannot own the FAS variable per the rubric's per-variable
    # ownership map.
    assert ReviewFlag.NUCLEAR_CASE not in result.review_flags


def test_score_nuclear_non_nuclear_source_with_non_nuclear_variable_insufficient() -> (
    None
):
    """A hand-built bundle carrying a non-nuclear variable on any source
    (including a nuclear-owning source) must also route to
    insufficient-data.

    Defence-in-depth: even a nuclear-owning source like ``fas`` cannot
    score a non-nuclear variable (e.g. ``vdem_v2x_polyarchy``) — the
    variable-name check is part of the scoring-basis contract.
    """
    wrong_variable = EvidenceObservation(
        source_key="fas",
        source_name="fas (probe)",
        variable_name="vdem_v2x_polyarchy",
        raw_value="0.5000",
        numeric_value=0.50,
        normalized_value=0.50,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="fas:vdem_v2x_polyarchy:2023",
        authority_score=70,
        specificity_score=80,
    )
    bundle = nuclear_make_bundle(observations=[wrong_variable])
    result = score_nuclear(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.components == ()
    assert result.observation_refs == ()
    assert ReviewFlag.NUCLEAR_CASE not in result.review_flags
