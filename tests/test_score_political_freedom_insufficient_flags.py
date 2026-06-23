"""Tests for the political freedom scorer's insufficient-data branch.

These tests close the reviewer blocker "flag completeness on
insufficient-data path" for the political freedom scorer. The
fix calls :func:`detect_flags` on the insufficient-data path
too, then prepends :attr:`ReviewFlag.INSUFFICIENT_DATA` so the
gate signal still leads the tuple. The client-source filter
inside :func:`detect_flags` is preserved so a contaminated
bundle carrying only ``client_existing`` / ``client_matrix``
PRIMARY missing rows cannot trigger
``MISSING_PRIMARY_SOURCE``.

The split mirrors the production code split
(:mod:`leaders_db.score.political_freedom` (facade) +
:mod:`leaders_db.score._political_freedom_flags` (flag
helpers)) and the existing test split
(:mod:`tests.test_score_political_freedom_flags` covers the
scored-path flag derivation;
:mod:`tests.test_score_political_freedom_remediation` covers
the client-contamination regressions for the scored path).
This file is the focused sibling for the insufficient-data
branch so the existing siblings stay under the 400-line
convention.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
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
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    # No observations → below ``minimum_viable_sources=2`` so
    # the insufficient-data gate fires.
    bundle = political_freedom_make_bundle(missing=missing)
    result = score_political_freedom(bundle)

    assert result.is_insufficient_data is True
    assert ReviewFlag.INSUFFICIENT_DATA in result.review_flags
    assert ReviewFlag.MISSING_PRIMARY_SOURCE in result.review_flags
    # The rationale mentions the canonical V-Dem REQUIRED so a
    # reviewer sees which indicator is missing.
    assert "vdem_v2x_polyarchy" in result.rationale_short
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
    # below ``minimum_viable_sources=2`` (the political freedom
    # plan needs two distinct sources) so the insufficient-data
    # gate fires. The PROXY temporal kind still produces a
    # LOW_CONFIDENCE signal via ``detect_flags``.
    bundle = political_freedom_make_bundle(
        observations=[
            political_freedom_make_obs(
                "vdem_v2x_polyarchy",
                "vdem",
                0.50,
                observation_year=2022,
                temporal_kind=TemporalKind.PROXY,
            ),
        ],
    )
    result = score_political_freedom(bundle)

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
    bundle = political_freedom_make_bundle(
        observations=[
            political_freedom_make_obs(
                "vdem_v2x_polyarchy",
                "vdem",
                0.50,
                observation_year=2018,
                temporal_kind=TemporalKind.STALE,
            ),
        ],
    )
    result = score_political_freedom(bundle)

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
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = political_freedom_make_bundle(missing=missing)
    result = score_political_freedom(bundle)

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
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="client_matrix",
            variable_name="vdem_v2x_libdem",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
    ]
    bundle = political_freedom_make_bundle(missing=only_client_missing)
    result = score_political_freedom(bundle)

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
