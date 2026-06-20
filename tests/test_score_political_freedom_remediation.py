"""Tests for the political freedom deterministic scorer — reviewer-blocker
regression tests.

These tests pin the regression fix for the reviewer blocker
"client-contamination / missingness correctness" on the
political freedom scorer. The political freedom scorer's flag-
detection and missingness-rollup paths must apply the same
client-source filter the observation path applies: a
contaminated bundle carrying ``MissingObservation`` rows whose
``source_key`` is in ``EXCLUDED_SOURCE_KEYS``
(``client_existing`` / ``client_matrix``) must not change
``missingness.by_reason`` / ``by_severity`` and must not
trigger ``MISSING_PRIMARY_SOURCE`` through
``primary_missing_observations``.

The split mirrors the production code split (the political
freedom scorer is broken into
:mod:`leaders_db.score.political_freedom` (facade),
:mod:`leaders_db.score._political_freedom_components` (per-
component helpers), and
:mod:`leaders_db.score._political_freedom_flags` (flag-detection
helpers)). The test surface follows the same pattern:

- :mod:`tests.test_score_political_freedom` — happy path /
  rubric weights / missingness rollup;
- :mod:`tests.test_score_political_freedom_components` — per-
  component bookkeeping + scale mapping + rationale + leader
  fallback + determinism + per-observation client exclusion;
- :mod:`tests.test_score_political_freedom_remediation` —
  this file, the client-source missingness regression tests
  (reviewer blocker "client-contamination / missingness
  correctness");
- :mod:`tests.test_score_political_freedom_flags` — flag-
  detection paths (MISSING_PRIMARY_SOURCE / SPARSE_DATA /
  LOW_CONFIDENCE / INSUFFICIENT_DATA) and the
  ``human_review_required`` invariant.

Style invariants (per ``docs/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    MissingObservation,
    MissingReason,
    MissingSeverity,
)
from leaders_db.score.political_freedom import score_political_freedom
from leaders_db.score.results import ReviewFlag
from tests._political_freedom_factories import (
    political_freedom_make_bundle,
    political_freedom_make_obs,
    realistic_political_freedom_observations,
)

# ---------------------------------------------------------------------------
# Client contamination cannot change missingness or trigger MISSING_PRIMARY_SOURCE
# ---------------------------------------------------------------------------
#
# Regression tests for reviewer blocker "client-contamination /
# missingness correctness". The political freedom scorer's flag-
# detection and missingness-rollup paths must apply the same
# client-source filter the observation path applies: a contaminated
# bundle carrying ``MissingObservation`` rows whose ``source_key``
# is in ``EXCLUDED_SOURCE_KEYS`` (``client_existing`` /
# ``client_matrix``) must not change ``missingness.by_reason`` /
# ``by_severity`` and must not trigger ``MISSING_PRIMARY_SOURCE``
# through ``primary_missing_observations``.


def test_score_political_freedom_client_missing_rows_do_not_inflate_missingness() -> (
    None
):
    """A bundle contaminated with client ``MissingObservation`` rows keeps
    the missingness counts, by_reason/by_severity rollups, and the
    review flags identical to a clean bundle.
    """
    # Three non-client missing rows: two PRIMARY (the two V-Dem
    # REQUIRED indicators) and one IMPORTANT (a BTI preferred).
    clean_missing = [
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_polyarchy",
            reason=MissingReason.RAW_FILE_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="vdem",
            variable_name="vdem_v2x_libdem",
            reason=MissingReason.TARGET_YEAR_ABSENT,
            severity=MissingSeverity.PRIMARY,
        ),
        MissingObservation(
            source_key="bti",
            variable_name="bti_status_index",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.IMPORTANT,
        ),
    ]
    # Three additional client-source missing rows. Without the
    # fix these would inflate ``by_reason`` / ``by_severity`` and
    # potentially trigger ``MISSING_PRIMARY_SOURCE`` if a
    # ``client_*`` row carried ``MissingSeverity.PRIMARY``.
    client_missing = [
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
            severity=MissingSeverity.IMPORTANT,
        ),
        MissingObservation(
            source_key="client_existing",
            variable_name="bti_status_index",
            reason=MissingReason.COUNTRY_ROW_ABSENT,
            severity=MissingSeverity.OPTIONAL,
        ),
    ]
    # Two non-client sources clear the minimum-viable gate so
    # the result is a real score, not insufficient-data.
    obs = [
        political_freedom_make_obs("vdem_v2x_freexp", "vdem", 0.55),
        political_freedom_make_obs("bti_q1_stateness", "bti", 0.60),
    ]
    clean_bundle = political_freedom_make_bundle(
        observations=obs, missing=clean_missing
    )
    contaminated_bundle = political_freedom_make_bundle(
        observations=obs, missing=[*clean_missing, *client_missing]
    )

    clean_result = score_political_freedom(clean_bundle)
    contaminated_result = score_political_freedom(contaminated_bundle)

    # 1. Missingness counts are identical — client rows do not
    #    contribute to ``by_reason`` / ``by_severity``.
    assert clean_result.missingness is not None
    assert contaminated_result.missingness is not None
    assert (
        clean_result.missingness.total_expected
        == contaminated_result.missingness.total_expected
    )
    assert (
        clean_result.missingness.total_observed
        == contaminated_result.missingness.total_observed
    )
    assert (
        clean_result.missingness.by_reason
        == contaminated_result.missingness.by_reason
    )
    assert (
        clean_result.missingness.by_severity
        == contaminated_result.missingness.by_severity
    ), (
        "client_existing/client_matrix missing rows must not "
        "inflate missingness.by_severity "
        f"(clean={dict(clean_result.missingness.by_severity)}, "
        f"contaminated={dict(contaminated_result.missingness.by_severity)})"
    )

    # 2. Review flags are identical — the client rows do not
    #    change which flags fire. Both bundles carry the V-Dem
    #    PRIMARY missing → MISSING_PRIMARY_SOURCE.
    assert clean_result.review_flags == contaminated_result.review_flags
    assert (
        ReviewFlag.MISSING_PRIMARY_SOURCE
        in contaminated_result.review_flags
    )

    # 3. ``human_review_required`` is identical.
    assert (
        clean_result.human_review_required
        == contaminated_result.human_review_required
        is True
    )

    # 4. The score pair is identical — the client missing rows
    #    do not influence the score.
    assert (
        clean_result.normalized_score_0_1
        == contaminated_result.normalized_score_0_1
    )
    assert (
        clean_result.system_proposed_score_1_10
        == contaminated_result.system_proposed_score_1_10
    )


def test_score_political_freedom_only_client_missing_rows_suppress_primary_flag() -> (
    None
):
    """A bundle with ONLY client missing rows must not trigger
    ``MISSING_PRIMARY_SOURCE`` or any review signal tied to
    client-source missingness.

    The realistic fixture plus only-client missing rows is the
    cleanest demonstration: removing every non-client
    ``MissingObservation`` would, without the fix, leave only
    client PRIMARY missing rows and
    ``MISSING_PRIMARY_SOURCE`` would still fire (because
    ``primary_missing_observations`` would be non-empty).
    """
    obs = realistic_political_freedom_observations()
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
    # Clean baseline: no missing rows.
    clean_bundle = political_freedom_make_bundle(observations=obs)
    # Contaminated: realistic observations + ONLY client missing
    # rows.
    contaminated_bundle = political_freedom_make_bundle(
        observations=obs, missing=only_client_missing
    )

    clean_result = score_political_freedom(clean_bundle)
    contaminated_result = score_political_freedom(contaminated_bundle)

    # The clean bundle observes all 16 plan variables and has no
    # review signal — no flags, no human review.
    assert clean_result.review_flags == ()
    assert clean_result.human_review_required is False

    # The contaminated bundle must also be clean — the client
    # missing rows are filtered out of
    # ``primary_missing_observations`` so
    # ``MISSING_PRIMARY_SOURCE`` does not fire. ``by_reason`` /
    # ``by_severity`` stay empty.
    assert (
        ReviewFlag.MISSING_PRIMARY_SOURCE
        not in contaminated_result.review_flags
    ), (
        "client_existing/client_matrix primary missing rows must "
        "not trigger MISSING_PRIMARY_SOURCE "
        f"(review_flags={list(contaminated_result.review_flags)})"
    )
    assert contaminated_result.review_flags == clean_result.review_flags
    assert (
        contaminated_result.human_review_required
        == clean_result.human_review_required
    )
    assert contaminated_result.missingness is not None
    assert contaminated_result.missingness.by_reason == ()
    assert contaminated_result.missingness.by_severity == ()
    # And the score pair is identical.
    assert (
        contaminated_result.normalized_score_0_1
        == clean_result.normalized_score_0_1
    )
    assert (
        contaminated_result.system_proposed_score_1_10
        == clean_result.system_proposed_score_1_10
    )


def test_score_political_freedom_client_missing_rows_skipped_in_insufficient_path() -> (
    None
):
    """The insufficient-data path also filters client missing rows.

    Companion test for the insufficient-data branch: a bundle
    that fails the minimum-viable-sources gate routes to
    ``is_insufficient_data=True``. The ``by_reason`` /
    ``by_severity`` rollup must still ignore client missing
    rows so the rationale's "X observation(s) across
    {total_observed}/{total_expected} plan indicator(s)" line
    is computed from the filtered scoring set, not the
    contaminated bundle.
    """
    clean_bundle = political_freedom_make_bundle()
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
    contaminated_bundle = political_freedom_make_bundle(
        missing=only_client_missing
    )

    clean_result = score_political_freedom(clean_bundle)
    contaminated_result = score_political_freedom(contaminated_bundle)

    # Both routes land on insufficient-data (no observations
    # are below ``minimum_viable_sources=2``).
    assert clean_result.is_insufficient_data is True
    assert contaminated_result.is_insufficient_data is True

    # Missingness rollup is identical — client rows do not
    # inflate ``by_reason`` / ``by_severity``.
    assert clean_result.missingness is not None
    assert contaminated_result.missingness is not None
    assert (
        clean_result.missingness.total_observed
        == contaminated_result.missingness.total_observed
    )
    assert (
        clean_result.missingness.by_reason
        == contaminated_result.missingness.by_reason
    )
    assert (
        clean_result.missingness.by_severity
        == contaminated_result.missingness.by_severity
    )
    # Review flags are identical.
    assert clean_result.review_flags == contaminated_result.review_flags
    # human_review_required is identical.
    assert (
        clean_result.human_review_required
        == contaminated_result.human_review_required
    )
