"""Tests for the Stage 9 all-countries CSV writer
(:func:`leaders_db.score.stage9.write_score_results_csv`).

The all-countries batch seam
(:func:`leaders_db.score.stage9.score_category_for_all_countries`)
returns a :class:`tuple` of :class:`ScoreResult`; this file is the
sibling test surface that pins the CSV writer's data-shape contract
(header columns, NA sentinel for insufficient rows, missingness
columns, pipe-separated review flags, atomic-rename, parent
directory creation). The attribution-block contract — the
``# Attribution: ...`` comment block at the top of the file — lives
in the sibling :mod:`tests.test_score_stage9_csv` and
:mod:`tests.test_score_stage9_attribution` modules; the helper
:func:`tests.test_score_stage9_batch._read_csv_rows` strips the
``#``-prefixed rows so the data-shape assertions in this file see
only the canonical :data:`SCORE_RESULTS_CSV_COLUMNS` shape.

The split mirrors the production split:

- :mod:`tests.test_score_stage9_batch` — the all-countries batch
  seam (``score_category_for_all_countries``) and the shared
  seed / CSV-reader helpers that both this file and
  :mod:`tests.test_score_stage9_csv` import;
- :mod:`tests.test_score_stage9_batch_csv` — this file, the
  writer's data-shape contract (NA sentinel, missingness
  columns, review-flags encoding, parent-directory creation,
  atomic-rename);
- :mod:`tests.test_score_stage9_csv` — the writer's
  attribution-block contract (comment emission, prefix stability,
  header-after-comments byte-for-byte match, pandas round-trip,
  explicit ``category_key=`` override, unknown-category
  defensive path).

The tests cover:

- :func:`write_score_results_csv` writes the literal ``"NA"``
  sentinel for both score columns on insufficient-data rows;
- the canonical :data:`SCORE_RESULTS_CSV_COLUMNS` header is
  byte-for-byte stable across the dense + empty bundle;
- the missingness-investigation columns are populated for both
  scored and insufficient rows;
- ``review_flags`` is pipe-separated, empty for the scored row
  and the documented set for the empty-bundle insufficient row;
- parent directories are created if missing;
- the atomic-rename pattern leaves no temp file behind.

Style invariants (per ``docs/coding-guidelines.md``): type hints,
no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db.score.results import ScoreResult
from leaders_db.score.stage9 import (
    SCORE_RESULTS_CSV_COLUMNS,
    write_score_results_csv,
)

from ._resolve_indicators_factories import TARGET_YEAR
from .test_score_stage9_batch import (
    SECOND_COUNTRY_NAME,
    _read_csv_rows,
    _seed_mexico_and_brazil,
)

# ---------------------------------------------------------------------------
# Local helper: seed + batch + write
# ---------------------------------------------------------------------------


def _write_two_country_csv(
    database_url: str, tmp_path: Path
) -> tuple[Path, tuple[ScoreResult, ...]]:
    """Seed two countries, run the batch seam, and write the CSV.

    Returns the resolved output path and the scored result tuple
    so the caller can assert on the row contents independently of
    the CSV byte format.
    """
    from leaders_db.db.session import session_scope
    from leaders_db.score.stage9 import score_category_for_all_countries

    _seed_mexico_and_brazil(database_url)
    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )
    output_path = write_score_results_csv(results, tmp_path / "scores.csv")
    return output_path, results


# ---------------------------------------------------------------------------
# NA sentinel
# ---------------------------------------------------------------------------


def test_write_score_results_csv_writes_na_for_missing_scores(
    database_url: str, tmp_path: Path
) -> None:
    """Insufficient-data rows write the literal string ``"NA"`` for the score columns."""
    output_path, results = _write_two_country_csv(database_url, tmp_path)

    header, rows = _read_csv_rows(output_path)
    by_iso = {row[header.index("iso3")]: row for row in rows}
    bra_row = by_iso["BRA"]
    assert bra_row[header.index("system_proposed_score_1_10")] == "NA"
    assert bra_row[header.index("normalized_score_0_1")] == "NA"
    assert bra_row[header.index("score_status")] == "insufficient_data"
    assert bra_row[header.index("is_insufficient_data")] == "True"
    # And the scored country must have a real score, never NA.
    mex_row = by_iso["MEX"]
    assert mex_row[header.index("system_proposed_score_1_10")] != "NA"
    assert mex_row[header.index("normalized_score_0_1")] != "NA"
    assert mex_row[header.index("score_status")] == "scored"
    assert mex_row[header.index("is_insufficient_data")] == "False"
    # The tuple round-trips: every emitted :class:`ScoreResult`
    # has a row and every row maps back to a result.
    assert {r.iso3 for r in results} == set(by_iso)


# ---------------------------------------------------------------------------
# Header / column shape
# ---------------------------------------------------------------------------


def test_write_score_results_csv_carries_missingness_columns(
    database_url: str, tmp_path: Path
) -> None:
    """The CSV carries the missingness-investigation columns."""
    output_path, _ = _write_two_country_csv(database_url, tmp_path)

    header, _ = _read_csv_rows(output_path)
    for column in (
        "iso3",
        "country_name",
        "year",
        "category_key",
        "system_proposed_score_1_10",
        "normalized_score_0_1",
        "score_status",
        "is_insufficient_data",
        "human_review_required",
        "review_flags",
        "observed_count",
        "expected_count",
        "missing_count",
        "missing_primary_count",
        "observation_ref_count",
        "rationale_short",
    ):
        assert column in header, f"missing column {column!r} in CSV header"
    assert header == list(SCORE_RESULTS_CSV_COLUMNS)


def test_write_score_results_csv_missingness_counts_are_populated(
    database_url: str, tmp_path: Path
) -> None:
    """The missingness counts are populated for both scored and insufficient rows."""
    output_path, _ = _write_two_country_csv(database_url, tmp_path)

    header, rows = _read_csv_rows(output_path)
    by_iso = {row[header.index("iso3")]: row for row in rows}
    bra = by_iso["BRA"]
    # Empty bundle: expected > 0, observed == 0, missing > 0.
    assert int(bra[header.index("observed_count")]) == 0
    assert int(bra[header.index("expected_count")]) > 0
    assert int(bra[header.index("missing_count")]) > 0
    # The plan carries at least one primary indicator (UNDP HDI);
    # the missing_primary_count surfaces it for the review queue.
    assert int(bra[header.index("missing_primary_count")]) >= 1

    mex = by_iso["MEX"]
    # Dense bundle: observed > 0 and missing < expected.
    assert int(mex[header.index("observed_count")]) > 0
    assert int(mex[header.index("expected_count")]) > 0
    assert int(mex[header.index("observation_ref_count")]) == 10


def test_write_score_results_csv_review_flags_pipe_separated(
    database_url: str, tmp_path: Path
) -> None:
    """``review_flags`` is pipe-separated; empty for the scored row."""
    output_path, _ = _write_two_country_csv(database_url, tmp_path)

    header, rows = _read_csv_rows(output_path)
    by_iso = {row[header.index("iso3")]: row for row in rows}
    bra_flags = by_iso["BRA"][header.index("review_flags")]
    # The empty-bundle social_wellbeing path always fires
    # INSUFFICIENT_DATA + SPARSE_DATA per the scorer contract.
    assert "insufficient_data" in bra_flags.split("|")
    assert "sparse_data" in bra_flags.split("|")
    # And the scored Mexico row must have empty flags (dense
    # 4-source bundle; no review signal).
    assert by_iso["MEX"][header.index("review_flags")] == ""


# ---------------------------------------------------------------------------
# File-system contract
# ---------------------------------------------------------------------------


def test_write_score_results_csv_creates_parent_directories(
    tmp_path: Path,
) -> None:
    """The writer creates parent directories if they are missing."""
    output_path = tmp_path / "nested" / "dir" / "scores.csv"
    result = ScoreResult(
        category_key="social_wellbeing",
        iso3="BRA",
        year=2022,
        leader_name=SECOND_COUNTRY_NAME,
        normalized_score_0_1=None,
        system_proposed_score_1_10=None,
        is_insufficient_data=True,
        human_review_required=True,
    )
    written = write_score_results_csv((result,), output_path)
    assert written == output_path.resolve()
    assert written.exists()
    assert written.parent.is_dir()


def test_write_score_results_csv_atomic_no_partial_files(
    database_url: str, tmp_path: Path,
) -> None:
    """No temp file is left behind after the atomic-rename write."""
    output_path, _ = _write_two_country_csv(database_url, tmp_path)
    parent = output_path.parent
    leftover = [p for p in parent.iterdir() if p.name.startswith(".")]
    assert leftover == []


__all__ = [
    "_write_two_country_csv",
]
