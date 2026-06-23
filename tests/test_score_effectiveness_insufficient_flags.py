"""Tests for the effectiveness scorer's insufficient-data branch.

These tests close the reviewer blocker "flag completeness on
insufficient-data path" for the effectiveness scorer. The
pre-fix scorer hard-coded only
``[ReviewFlag.INSUFFICIENT_DATA, ReviewFlag.SPARSE_DATA]`` on
the insufficient-data branch and silently dropped
``MISSING_PRIMARY_SOURCE`` (driven from
``primary_missing_observations``) and ``LOW_CONFIDENCE``
(driven from the bundle's PROXY/STALE observations) — flags the
score path derives for the same bundle. The manual-review
queue sorts on the full flag set, so a "no flag" insufficient-
data result slips past the queue and the reviewer never sees
the underlying primary-missing or low-confidence signal.

The fix calls :func:`detect_flags` on the insufficient-data
path too, then prepends :attr:`ReviewFlag.INSUFFICIENT_DATA`
so the gate signal still leads the tuple. The client-source
filter inside :func:`detect_flags` is preserved so a
contaminated bundle carrying only ``client_existing`` /
``client_matrix`` PRIMARY missing rows cannot trigger
``MISSING_PRIMARY_SOURCE``.

The split mirrors the production code split
(:mod:`leaders_db.score.effectiveness` (facade) +
:mod:`leaders_db.score._effectiveness_flags` (flag helpers))
and the existing test split
(:mod:`tests.test_score_effectiveness_flags` covers the
scored-path flag derivation;
:mod:`tests.test_score_effectiveness_remediation` covers the
client-contamination regressions for the scored path). This
file is the focused sibling for the insufficient-data branch
so the existing siblings stay under the 400-line convention.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
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


def test_insufficient_data_derives_missing_primary_flag() -> None:
    """A below-minimum-viable bundle with a non-client PRIMARY missing row
    must surface ``MISSING_PRIMARY_SOURCE`` **plus**
    ``INSUFFICIENT_DATA`` (the latter prepended by the gate).

    Pre-fix the scorer hard-coded only
    ``[INSUFFICIENT_DATA, SPARSE_DATA]`` so the
    ``MISSING_PRIMARY_SOURCE`` signal from
    ``primary_missing_observations`` was silently dropped on
    the insufficient-data path.
    """
    missing = [
        MissingObservation(
            source_key="bti",
            variable_name="bti_governance_index",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # Single source → below ``minimum_viable_sources=2`` so the
    # insufficient-data gate fires.
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness", "wgi", 0.65
            )
        ],
        missing=missing,
    )
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    # The rationale mentions the canonical BTI REQUIRED so a
    # reviewer sees which indicator is missing.
    assert "bti_governance_index" in result.rationale_short
    assert result.human_review_required is True


def test_insufficient_data_derives_low_confidence_flag_for_proxy() -> None:
    """A below-minimum-viable bundle whose sole observation is PROXY
    must surface ``LOW_CONFIDENCE`` **plus** ``INSUFFICIENT_DATA``.

    Pre-fix the scorer never consulted the ``temporal_kind``
    on the insufficient-data path, so a PROXY observation
    produced a result the manual-review queue could not flag
    for low confidence.
    """
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness",
                "wgi",
                0.65,
                observation_year=2022,
                temporal_kind=TemporalKind.PROXY,
            )
        ],
    )
    result = score_effectiveness(bundle)

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
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness",
                "wgi",
                0.65,
                observation_year=2018,
                temporal_kind=TemporalKind.STALE,
            )
        ],
    )
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.LOW_CONFIDENCE in result.review_flags


def test_insufficient_data_includes_all_three_derived_flags() -> None:
    """Combined scenario: single-source bundle with PROXY observation
    **and** non-client PRIMARY missing row. The derived flag
    set must include ``MISSING_PRIMARY_SOURCE``, ``SPARSE_DATA``,
    and ``LOW_CONFIDENCE`` (plus ``INSUFFICIENT_DATA`` prepended) —
    the manual-review queue sorts on this exact combination.
    """
    missing = [
        MissingObservation(
            source_key="bti",
            variable_name="bti_governance_index",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness",
                "wgi",
                0.65,
                observation_year=2022,
                temporal_kind=TemporalKind.PROXY,
            ),
        ],
        missing=missing,
    )
    result = score_effectiveness(bundle)

    assert result.is_insufficient_data is True
    expected_flags = {
        ReviewFlag.INSUFFICIENT_DATA,
        ReviewFlag.MISSING_PRIMARY_SOURCE,
        ReviewFlag.SPARSE_DATA,
        ReviewFlag.LOW_CONFIDENCE,
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
            variable_name="wgi_government_effectiveness",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="client_matrix",
            variable_name="bti_governance_index",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = effectiveness_make_bundle(
        observations=[
            effectiveness_make_obs(
                "wgi_government_effectiveness", "wgi", 0.65
            )
        ],
        missing=only_client_missing,
    )
    result = score_effectiveness(bundle)

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
