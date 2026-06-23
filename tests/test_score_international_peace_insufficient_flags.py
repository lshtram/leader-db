"""Tests for the international-peace scorer's insufficient-data branch.

These tests close the reviewer blocker "flag completeness on
insufficient-data path" for the international-peace scorer. The
fix calls :func:`detect_flags` on the insufficient-data path
too, then prepends :attr:`ReviewFlag.INSUFFICIENT_DATA` so the
gate signal still leads the tuple. The client-source filter
inside :func:`detect_flags` is preserved so a contaminated
bundle carrying only ``client_existing`` / ``client_matrix``
PRIMARY missing rows cannot trigger
``MISSING_PRIMARY_SOURCE``.

A second reviewer blocker ("insufficient-data rationale must
not state or imply a numeric score") is pinned by the
``rationale_short`` assertions below: the scorer used to
interpolate ``score_1_10=1`` as a placeholder for the
insufficient-data path, producing "International peace score
1/10 ..." for every no-score row. The fixed scorer suppresses
the numeric-score sentence on the insufficient-data path so
the rationale carries only the canonical gate-signal text
("Bundle fell below the plan's minimum-viable source count;
no score emitted."). The Stage 9 / CSV-facing proof for the
same contract lives in
:mod:`tests.test_score_stage9_international_peace_batch`.

The split mirrors the production code split
(:mod:`leaders_db.score.international_peace` (facade) +
:mod:`leaders_db.score._international_peace_flags` (flag
helpers)) and the existing test split
(:mod:`tests.test_score_international_peace_flags` covers the
scored-path flag derivation;
:mod:`tests.test_score_international_peace_remediation` covers
the client-contamination regressions for the scored path).
This file is the focused sibling for the insufficient-data
branch so the existing siblings stay under the 400-line
convention.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import re

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
)

# Pattern that catches a numeric-score sentence such as "International
# peace score 1/10 ..." or any "score N/10" interpolation. The
# insufficient-data rationale must not match — the scorer used to
# interpolate ``score_1_10=1`` as a placeholder here, which the
# reviewer blocked because the contract states
# ``system_proposed_score_1_10 is None`` on insufficient-data
# results.
_NUMERIC_SCORE_PATTERN: re.Pattern[str] = re.compile(r"\bscore\s+\d+/10\b")


def test_insufficient_data_derives_missing_primary_flag() -> None:
    """A below-minimum-viable bundle with a non-client PRIMARY missing row
    must surface ``MISSING_PRIMARY_SOURCE`` **plus**
    ``INSUFFICIENT_DATA`` (the latter prepended by the gate).

    The fix calls :func:`detect_flags` on the insufficient-data
    path so the ``MISSING_PRIMARY_SOURCE`` signal from
    ``primary_missing_observations`` is no longer silently
    dropped.
    """
    missing = [
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_state_based_fatalities",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # No observations → below ``minimum_viable_sources=2`` so
    # the insufficient-data gate fires.
    bundle = international_peace_make_bundle(missing=missing)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    # The rationale mentions the canonical UCDP REQUIRED so a
    # reviewer sees which indicator is missing.
    assert "ucdp_state_based_fatalities" in result.rationale_short
    assert result.human_review_required is True


def test_insufficient_data_derives_low_confidence_flag_for_proxy() -> None:
    """A below-minimum-viable bundle whose sole source has a PROXY
    observation must surface ``LOW_CONFIDENCE`` **plus**
    ``INSUFFICIENT_DATA``.

    The fix calls :func:`detect_flags` on the insufficient-data
    path so a PROXY observation produces a result the
    manual-review queue can flag for low confidence.
    """
    # One source with a single PROXY observation: this is
    # below ``minimum_viable_sources=2`` (the
    # international-peace plan needs two distinct sources) so
    # the insufficient-data gate fires. The PROXY temporal kind
    # still produces a LOW_CONFIDENCE signal via
    # ``detect_flags``.
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events",
                "ucdp",
                0.65,
                observation_year=2022,
                temporal_kind=TemporalKind.PROXY,
            ),
        ],
    )
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags
    # The rationale calls out the proxy count so the reviewer
    # sees the temporal-fit signal explicitly.
    assert "proxy" in result.rationale_short.lower()
    assert result.human_review_required is True


def test_insufficient_data_derives_low_confidence_flag_for_stale() -> None:
    """A STALE observation on the insufficient-data path also fires
    ``LOW_CONFIDENCE`` (same temporal-fit reason as PROXY)."""
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events",
                "ucdp",
                0.65,
                observation_year=2018,
                temporal_kind=TemporalKind.STALE,
            ),
        ],
    )
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


def test_insufficient_data_includes_all_three_derived_flags() -> None:
    """Combined scenario: empty bundle with non-client PRIMARY missing row.

    The derived flag set must include ``MISSING_PRIMARY_SOURCE``,
    ``SPARSE_DATA``, and ``INSUFFICIENT_DATA`` — the manual-
    review queue sorts on this exact combination.
    """
    missing = [
        MissingObservation(
            source_key="ucdp",
            variable_name="ucdp_state_based_fatalities",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = international_peace_make_bundle(missing=missing)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    expected_flags = {
        ReviewFlag.INSUFFICIENT_DATA,
        ReviewFlag.MISSING_PRIMARY_SOURCE,
        ReviewFlag.SPARSE_DATA,
    }
    assert expected_flags <= set(result.review_flags)
    # INSUFFICIENT_DATA is the gate signal — it must be first so
    # the manual-review queue can sort by it.
    assert result.review_flags[0] is ReviewFlag.INSUFFICIENT_DATA
    assert result.human_review_required is True


def test_insufficient_data_client_missing_rows_no_primary_flag() -> None:
    """A below-minimum-viable bundle contaminated with only client-source
    PRIMARY missing rows must **not** trigger
    ``MISSING_PRIMARY_SOURCE``.

    The client 2023 matrix is validation reference, never
    evidence (AGENTS.md rule #6). Even on the insufficient-
    data path, the ``_filter_excluded_missing`` guard inside
    :func:`detect_flags` must strip ``client_existing`` /
    ``client_matrix`` ``MissingObservation`` rows before the
    primary-severity check so a contaminated bundle cannot
    surface a phantom ``MISSING_PRIMARY_SOURCE``. The
    missingness rollup also stays empty for client rows.
    """
    only_client_missing = [
        MissingObservation(
            source_key="client_existing",
            variable_name="ucdp_state_based_fatalities",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="client_matrix",
            variable_name="sipri_milex_share_of_gdp",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = international_peace_make_bundle(missing=only_client_missing)
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    # The client PRIMARY rows must not surface
    # MISSING_PRIMARY_SOURCE.
    assert (
        ReviewFlag.MISSING_PRIMARY_SOURCE not in result.review_flags
    ), (
        "client_existing / client_matrix PRIMARY missing rows "
        "must not trigger MISSING_PRIMARY_SOURCE on the "
        "insufficient-data path "
        f"(review_flags={list(result.review_flags)})"
    )
    # by_reason / by_severity stay empty — client rows do not
    # contribute to the missingness rollup either.
    assert result.missingness is not None
    assert result.missingness.by_reason == ()
    assert result.missingness.by_severity == ()


# ---------------------------------------------------------------------------
# Insufficient-data rationale content
# ---------------------------------------------------------------------------
#
# Pins the reviewer-blocker remediation: insufficient-data results
# have ``system_proposed_score_1_10 is None`` (no numeric score was
# emitted), so the rationale must NOT state or imply a numeric
# score. The scorer used to interpolate ``score_1_10=1`` as a
# placeholder for the rationale text only, producing
# "International peace score 1/10 on the 1..10 prototype scale ..."
# for every insufficient-data row. The fix suppresses the
# numeric-score sentence on the insufficient-data path so the
# rationale carries only the canonical gate-signal text. The Stage
# 9 / CSV-facing proof for the same contract lives in
# :mod:`tests.test_score_stage9_international_peace_batch`.


def test_insufficient_data_rationale_does_not_state_numeric_score() -> None:
    """An empty-bundle insufficient-data result must not emit a numeric-score sentence.

    The scorer used to pass ``normalized=0.0``, ``score_1_10=1``
    to :func:`build_rationale` as a placeholder, producing a
    rationale that started with "International peace score 1/10
    on the 1..10 prototype scale ..." even though
    ``system_proposed_score_1_10 is None``. The fixed
    :func:`build_rationale` suppresses the numeric-score
    sentence when :attr:`ReviewFlag.INSUFFICIENT_DATA` is in
    the flag set.
    """
    bundle = international_peace_make_bundle()
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert not _NUMERIC_SCORE_PATTERN.search(result.rationale_short), (
        "insufficient-data rationale must not contain a numeric "
        "score sentence (reviewer blocker). "
        f"got: {result.rationale_short!r}"
    )


def test_insufficient_data_rationale_carries_no_score_emitted_signal() -> None:
    """The insufficient-data rationale must carry the canonical gate-signal text.

    The rationale must explicitly say "no score emitted" so the
    manual-review reader can distinguish "no score" from "lowest
    possible score". This complements
    :func:`test_insufficient_data_rationale_does_not_state_numeric_score`
    — together they pin both halves of the contract (no numeric
    score claim + explicit "no score emitted" gate signal).
    """
    bundle = international_peace_make_bundle()
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert "no score emitted" in result.rationale_short.lower(), (
        "insufficient-data rationale must say 'no score emitted' "
        f"(got: {result.rationale_short!r})"
    )
    # And the gate-signal sentence names the plan-level cause
    # (minimum-viable source count) so the reviewer can act on
    # it without re-walking the bundle.
    assert "minimum-viable" in result.rationale_short.lower()


def test_insufficient_data_rationale_no_numeric_score_for_proxy_bundle() -> None:
    """A below-minimum-viable bundle with a PROXY observation also has no numeric score.

    Combined scenario: the bundle is insufficient-data (one
    source, below the 2-source threshold) and the sole
    observation is PROXY (temporal fit reduced). The rationale
    must carry the proxy-count sentence (so the LOW_CONFIDENCE
    signal is visible to the manual-review reader) but must
    not interpolate a numeric score.
    """
    bundle = international_peace_make_bundle(
        observations=[
            international_peace_make_obs(
                "ucdp_state_based_events",
                "ucdp",
                0.65,
                observation_year=2022,
                temporal_kind=TemporalKind.PROXY,
            ),
        ],
    )
    result = score_international_peace(bundle)

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert not _NUMERIC_SCORE_PATTERN.search(result.rationale_short), (
        "PROXY + insufficient-data rationale must not contain a "
        "numeric score. "
        f"got: {result.rationale_short!r}"
    )
    # The proxy sentence and the gate-signal sentence both fire;
    # the rationale must surface them in plain language.
    assert "proxy" in result.rationale_short.lower()
    assert "no score emitted" in result.rationale_short.lower()
