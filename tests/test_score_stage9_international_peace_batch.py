"""Stage 9 all-countries batch seam tests for the ``international_peace`` category.

Sibling of :mod:`tests.test_score_stage9_international_peace`
(the single-country seam + sparse-bundle insufficient-data proof).
Splitting the batch-seam proof into its own focused module keeps
the single-country file under the 400-line convention while
still being one test module per production seam family — same
pattern as
``test_score_stage9_batch_csv.py`` / ``test_score_stage9_batch.py``.

The batch seam
(:func:`leaders_db.score.stage9.score_category_for_all_countries`)
returns a :class:`tuple` of :class:`ScoreResult`; this file seeds
``MEX`` 2023 with the dense international_peace bundle (UCDP +
SIPRI, 8 indicators across 2 sources) plus ``BRA`` 2023 with no
observations (a clean insufficient-data result), then asserts
the batch returns one :class:`ScoreResult` per country in
``iso3`` order — ``BRA < MEX`` lexicographically — so the
deterministic order is independent of insertion order.

A CSV-facing proof pins the reviewer-blocker remediation that
insufficient-data ``rationale_short`` strings do **not** state
or imply a numeric score. The Stage 9 CSV writer
(:func:`leaders_db.score.stage9.write_score_results_csv`) carries
``rationale_short`` as the last column of
:data:`SCORE_RESULTS_CSV_COLUMNS`; the test seeds MEX + BRA,
writes the CSV, and asserts the BRA row's ``rationale_short``
column does not contain a numeric-score pattern and does contain
the canonical "no score emitted" gate-signal text. The companion
unit test for the same contract (without the CSV layer) lives
in :mod:`tests.test_score_international_peace_insufficient_flags`
under the focused-file convention.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import re
from pathlib import Path

from leaders_db.db.models import Country
from leaders_db.db.session import session_scope
from leaders_db.score.results import ReviewFlag, ScoreResult
from leaders_db.score.stage9 import (
    score_category_for_all_countries,
    write_score_results_csv,
)

from ._resolve_indicators_factories import COUNTRY_ISO3, TARGET_YEAR
from .test_score_stage9_batch import _read_csv_rows
from .test_score_stage9_international_peace import (
    _seed_mexico_international_peace_bundle,
)

# ``BRA`` is inserted *after* ``MEX`` so the iso3 ordering of the
# batch result is exercised, not just the insertion order
# (``BRA < MEX`` lexicographically). Mirrors the domestic-
# violence batch-seam sibling.
SECOND_COUNTRY_ISO3: str = "BRA"
SECOND_COUNTRY_NAME: str = "Brazil"
SECOND_COUNTRY_REGION: str = "LAC"

# Matches a numeric-score sentence the rubric used to interpolate
# into insufficient-data rationales (e.g. "score 1/10"). Pinning
# this in the CSV-facing proof catches any future regression that
# re-introduces a placeholder score on the insufficient-data path.
_NUMERIC_SCORE_PATTERN: re.Pattern[str] = re.compile(r"\bscore\s+\d+/10\b")


def _seed_mexico_and_brazil(database_url: str) -> None:
    """Seed MEX (dense international_peace bundle) + BRA (no observations).

    Mirrors the domestic-violence batch-seam helper. The seed
    loop inserts ``BRA`` after ``MEX`` so the iso3-ordering
    assertion below exercises the deterministic sort, not just
    the insertion order of the seed loop.
    """
    _seed_mexico_international_peace_bundle(database_url)
    with session_scope(database_url) as session:
        brazil = Country(
            iso3=SECOND_COUNTRY_ISO3,
            country_name=SECOND_COUNTRY_NAME,
            country_name_normalized="brazil",
            region=SECOND_COUNTRY_REGION,
        )
        session.add(brazil)
        session.flush()


# ---------------------------------------------------------------------------
# All-countries batch seam
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_international_peace_returns_one_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="international_peace",
        )

    iso3s = tuple(r.iso3 for r in results)
    # Ordered by iso3 — BRA < MEX lexicographically — so the
    # deterministic order is independent of insertion order.
    assert iso3s == (SECOND_COUNTRY_ISO3, COUNTRY_ISO3)
    for r in results:
        assert isinstance(r, ScoreResult)
        assert r.category_key == "international_peace"
        assert r.year == TARGET_YEAR


def test_score_category_for_all_countries_international_peace_scored_country_has_score(
    database_url: str,
) -> None:
    """The dense MEX row in the batch gets a real (non-insufficient) score."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="international_peace",
        )

    by_iso = {r.iso3: r for r in results}
    mex = by_iso[COUNTRY_ISO3]
    assert mex.is_insufficient_data is False
    assert mex.system_proposed_score_1_10 is not None
    assert 1 <= mex.system_proposed_score_1_10 <= 10
    assert 0.0 <= (mex.normalized_score_0_1 or 0.0) <= 1.0
    # 8 indicators × 1 ref each = 8 refs total.
    assert len(mex.observation_refs) == 8
    assert mex.review_flags == ()
    assert mex.human_review_required is False


def test_score_category_for_all_countries_international_peace_missing_country_has_insufficient(
    database_url: str,
) -> None:
    """A Country row with no observations emits ``is_insufficient_data=True``.

    End-to-end proof that the insufficient-data branch — including
    the BLOCKER-1 fix that derives ``MISSING_PRIMARY_SOURCE`` /
    ``SPARSE_DATA`` / ``LOW_CONFIDENCE`` from the bundle on top
    of the ``INSUFFICIENT_DATA`` gate — fires correctly through
    the batch seam + bundle builder + dispatcher + scorer chain.
    """
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="international_peace",
        )

    by_iso = {r.iso3: r for r in results}
    bra = by_iso[SECOND_COUNTRY_ISO3]
    assert bra.is_insufficient_data is True
    assert bra.system_proposed_score_1_10 is None
    assert bra.normalized_score_0_1 is None
    assert bra.human_review_required is True
    # INSUFFICIENT_DATA is the gate signal; SPARSE_DATA rides along
    # because observed_ratio (0/8) is below the 0.5 threshold.
    assert ReviewFlag.INSUFFICIENT_DATA in bra.review_flags
    assert ReviewFlag.SPARSE_DATA in bra.review_flags
    assert bra.observation_refs == ()
    # Missingness summary is the missingness-investigation artifact;
    # the batch seam relies on the dispatcher to populate it even
    # for the empty-bundle path.
    assert bra.missingness is not None
    assert bra.missingness.total_expected == 8
    assert bra.missingness.total_observed == 0


# ---------------------------------------------------------------------------
# CSV-facing proof: insufficient-data rationale has no numeric score
# ---------------------------------------------------------------------------


def test_write_score_results_csv_international_peace_insufficient_rationale_has_no_numeric_score(
    database_url: str,
    tmp_path: Path,
) -> None:
    """The Stage 9 CSV's ``rationale_short`` column for an insufficient-data row
    does **not** contain a numeric score.

    Closes the reviewer blocker: the rubric used to interpolate
    ``score_1_10=1`` as a placeholder for the insufficient-data
    path, producing "International peace score 1/10 on the 1..10
    prototype scale ..." for every insufficient-data row. The
    fix suppresses the score sentence entirely on the
    insufficient-data path so the rationale carries the canonical
    gate-signal text ("Bundle fell below ...; no score emitted.")
    and no numeric score claim. This test pins the contract at
    the CSV-writer seam because the CSV is the artifact the
    manual-review queue consumes.
    """
    _seed_mexico_and_brazil(database_url)
    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="international_peace",
        )

    output_path = write_score_results_csv(
        results, tmp_path / "international_peace.csv"
    )
    header, rows = _read_csv_rows(output_path)
    by_iso = {row[header.index("iso3")]: row for row in rows}

    # Scored row (MEX) — the numeric score IS expected here; this
    # is the happy-path round-trip proof.
    mex_rationale = by_iso[COUNTRY_ISO3][
        header.index("rationale_short")
    ]
    assert _NUMERIC_SCORE_PATTERN.search(mex_rationale), (
        "scored row rationale must surface the numeric score "
        f"(got: {mex_rationale!r})"
    )

    # Insufficient-data row (BRA) — the blocker fix. The
    # rationale must NOT contain a numeric-score sentence; it
    # must contain the canonical gate-signal text.
    bra_rationale = by_iso[SECOND_COUNTRY_ISO3][
        header.index("rationale_short")
    ]
    assert not _NUMERIC_SCORE_PATTERN.search(bra_rationale), (
        "insufficient-data row rationale must NOT contain a "
        "numeric score (reviewer blocker). "
        f"got: {bra_rationale!r}"
    )
    assert "no score emitted" in bra_rationale.lower(), (
        "insufficient-data rationale must carry the canonical "
        f"gate-signal text 'no score emitted'. got: {bra_rationale!r}"
    )


__all__ = [
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SECOND_COUNTRY_REGION",
    "_NUMERIC_SCORE_PATTERN",
    "_seed_mexico_and_brazil",
]  # end __all__
