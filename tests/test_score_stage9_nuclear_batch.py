"""Stage 9 all-countries batch seam tests for the ``nuclear`` category.

Sibling of :mod:`tests.test_score_stage9_nuclear` (the
single-country seam + sparse-bundle insufficient-data proof).
Splitting the batch-seam proof into its own focused module
keeps the single-country file under the 400-line convention
while still being one test module per production seam family.

A CSV-facing proof pins the reviewer-blocker remediation that
insufficient-data ``rationale_short`` strings do **not** state
or imply a numeric score. The Stage 9 CSV writer
(:func:`leaders_db.score.stage9.write_score_results_csv`) carries
``rationale_short`` as the last column of
:data:`SCORE_RESULTS_CSV_COLUMNS`; the test seeds USA + BRA,
writes the CSV, and asserts the BRA row's ``rationale_short``
column does not contain a numeric-score pattern and does
contain the canonical "no score emitted" gate-signal text.
The companion unit test for the same contract (without the CSV
layer) lives in :mod:`tests.test_score_nuclear_insufficient_flags`
under the focused-file convention.

Style invariants (per ``docs/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import re
from pathlib import Path

from leaders_db.db.session import session_scope
from leaders_db.score.stage9 import (
    score_category_for_all_countries,
    write_score_results_csv,
)

from .test_score_stage9_batch import _read_csv_rows
from .test_score_stage9_nuclear import (
    SECOND_COUNTRY_ISO3,
    SECOND_COUNTRY_NAME,
    SECOND_COUNTRY_NAME_NORMALIZED,
    SECOND_COUNTRY_REGION,
    _seed_usa_and_brazil,
)

# Matches a numeric-score sentence the rubric used to interpolate
# into insufficient-data rationales (e.g. "score 1/10"). Pinning
# this in the CSV-facing proof catches any future regression that
# re-introduces a placeholder score on the insufficient-data path.
_NUMERIC_SCORE_PATTERN: re.Pattern[str] = re.compile(r"\bscore\s+\d+/10\b")


# ---------------------------------------------------------------------------
# All-countries batch seam (re-pinned from the sibling file)
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_nuclear_returns_one_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_usa_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=2023,
            category_key="nuclear",
        )

    iso3s = tuple(r.iso3 for r in results)
    assert iso3s == (SECOND_COUNTRY_ISO3, "USA")
    for r in results:
        assert r.category_key == "nuclear"
        assert r.year == 2023


# ---------------------------------------------------------------------------
# CSV-facing proof: insufficient-data rationale has no numeric score
# ---------------------------------------------------------------------------


def test_write_score_results_csv_nuclear_insufficient_rationale_has_no_numeric_score(
    database_url: str,
    tmp_path: Path,
) -> None:
    """The Stage 9 CSV's ``rationale_short`` column for an insufficient-data row
    does **not** contain a numeric score.

    Closes the reviewer blocker: the rubric used to interpolate
    ``score_1_10=1`` as a placeholder for the insufficient-data
    path. The fix suppresses the score sentence entirely on the
    insufficient-data path so the rationale carries the
    canonical gate-signal text and the explicit "non-nuclear /
    no nuclear-source evidence" wording.
    """
    _seed_usa_and_brazil(database_url)
    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=2023,
            category_key="nuclear",
        )

    output_path = write_score_results_csv(
        results, tmp_path / "nuclear.csv"
    )
    header, rows = _read_csv_rows(output_path)
    by_iso = {row[header.index("iso3")]: row for row in rows}

    # Scored row (USA) — the numeric score IS expected here; this
    # is the happy-path round-trip proof.
    usa_rationale = by_iso["USA"][header.index("rationale_short")]
    assert _NUMERIC_SCORE_PATTERN.search(usa_rationale), (
        "scored row rationale must surface the numeric score "
        f"(got: {usa_rationale!r})"
    )

    # Insufficient-data row (BRA) — the blocker fix. The
    # rationale must NOT contain a numeric-score sentence; it
    # must contain the canonical gate-signal text.
    bra_rationale = by_iso[SECOND_COUNTRY_ISO3][header.index("rationale_short")]
    assert not _NUMERIC_SCORE_PATTERN.search(bra_rationale), (
        "insufficient-data row rationale must NOT contain a "
        "numeric score (reviewer blocker). "
        f"got: {bra_rationale!r}"
    )
    assert "no score emitted" in bra_rationale.lower(), (
        "insufficient-data rationale must carry the canonical "
        f"gate-signal text 'no score emitted'. got: {bra_rationale!r}"
    )
    # The nuclear-specific "non-nuclear" wording is the second
    # half of the nuclear-specialization explicit signal.
    assert "non-nuclear" in bra_rationale.lower(), (
        "non-nuclear rationale must say 'non-nuclear' so a "
        "reviewer can distinguish it from sparse data. "
        f"got: {bra_rationale!r}"
    )


__all__ = [
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SECOND_COUNTRY_NAME_NORMALIZED",
    "SECOND_COUNTRY_REGION",
    "_NUMERIC_SCORE_PATTERN",
]  # end __all__
