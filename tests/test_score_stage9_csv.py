"""Tests for the Stage 9 CSV writer — direct writer path through the
all-countries batch seam.

The all-countries CSV is an exported artifact under
``data/outputs/``; per AGENTS.md rule #15 ("carry source
attribution forward in every public output") and
``docs/source-attributions.md`` §3.2 / §3.6, the writer must
carry the source attribution block for the contributing
sources as a ``# Attribution: <text>`` comment block at the
top of the file. The block is the small but contractually
important glue between the score module and the docs — without
it a downstream consumer cannot answer "where did these numbers
come from?" without re-reading ``docs/source-attributions.md``.

Scope
-----

The tests live in a sibling test file so the canonical
``test_score_stage9_batch.py`` (the all-countries batch seam
+ CSV row format / atomic-rename contract) and
``test_score_stage9_attribution.py`` (the helper unit tests)
stay under the 400-line convention while still being one test
module per production seam family. The split mirrors the
``stage9_batch`` / ``stage9_batch_csv`` /
``stage9_csv`` / ``stage9_csv_categories`` /
``stage9_attribution`` pattern:

- :mod:`tests.test_score_stage9_batch` — the all-countries
  batch seam and the CSV row format / atomic-rename contract
  (no attribution assertions);
- :mod:`tests.test_score_stage9_batch_csv` — the CSV writer's
  data-shape contract (NA sentinel, missingness columns,
  review-flags encoding, parent-directory creation,
  atomic-rename);
- :mod:`tests.test_score_stage9_csv` — this file, the direct
  writer path through the all-countries batch seam (full
  social_wellbeing attribution block emission, comment
  prefix stability, data header byte-for-byte match, pandas
  round-trip);
- :mod:`tests.test_score_stage9_csv_categories` — the CSV
  writer's per-category CLI explicit ``category_key=`` contract
  (one test per registered category, the explicit-override
  semantics, the unknown-category defensive path);
- :mod:`tests.test_score_stage9_attribution` — the
  :func:`build_attribution_comment_lines` helper unit tests
  (helper does the right thing in isolation from the writer).

The tests cover:

- :func:`leaders_db.score.stage9.write_score_results_csv`
  writes the attribution block to the direct-writer path
  (no kwarg, derived from the first :class:`ScoreResult`);
- the attribution lines are ``# Attribution:`` prefixed so
  ``csv.reader`` filtering and pandas ``read_csv(comment="#")``
  both skip them cleanly;
- the data header remains byte-for-byte equal to
  :data:`SCORE_RESULTS_CSV_COLUMNS` after the attribution
  block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from leaders_db.db.session import session_scope
from leaders_db.score._attributions import ATTRIBUTION_COMMENT_PREFIX
from leaders_db.score.stage9 import (
    SCORE_RESULTS_CSV_COLUMNS,
    score_category_for_all_countries,
    write_score_results_csv,
)

from ._resolve_indicators_factories import TARGET_YEAR

# Reuse the comment-skipping CSV parser and the seed factory from
# the batch test file so this file does not duplicate the seed /
# reader helpers.
from .test_score_stage9_batch import (
    _read_attribution_lines,
    _read_csv_rows,
    _seed_mexico_and_brazil,
)


def _write_two_country_csv(
    database_url: str, tmp_path: Path
) -> tuple[Path, tuple]:
    """Seed two countries, run the batch seam, and write the CSV.

    Mirror of the helper in ``test_score_stage9_batch``; defined
    here so the writer tests can run as a standalone file
    without re-importing the sibling's private
    ``_write_two_country_csv``. The implementation is
    byte-for-byte identical and intentionally not extracted into
    ``_resolve_indicators_factories`` — the seed factory is owned
    by the batch seam's test surface, and the writer tests reuse
    it through the same test module.
    """
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
# Writer attribution (direct writer path)
# ---------------------------------------------------------------------------


def test_write_score_results_csv_includes_social_wellbeing_attribution(
    database_url: str, tmp_path: Path
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per expected source.

    This is the direct-writer path test for AGENTS.md rule #15:
    without an explicit ``category_key`` kwarg, the writer
    derives the category from the first :class:`ScoreResult`
    (``social_wellbeing`` for the seeded batch) and emits the
    full attribution block. ``client_existing`` is not present.
    """
    output_path, _ = _write_two_country_csv(database_url, tmp_path)

    attribution_lines = _read_attribution_lines(output_path)
    # Exactly one line per expected social_wellbeing source.
    assert len(attribution_lines) == 4
    # Every expected source's canonical attribution substring
    # appears in the block. Order is stable (matches the
    # mapping); the test does not pin order so a future edit
    # that reorders the mapping only requires updating the doc.
    expected_phrases = [
        "UNDP HDR 2023-24",
        "WHO Global Health Observatory",
        "World Bank WDI",
        "V-Dem v16",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    # ``client_existing`` must NOT appear (rule #6).
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


def test_write_score_results_csv_attribution_lines_are_comment_prefixed(
    database_url: str, tmp_path: Path
) -> None:
    """Every attribution line starts with the canonical ``# Attribution:`` prefix.

    Downstream consumers (``csv.reader`` filtering, pandas
    ``read_csv(comment="#")``, hand inspection) all key off the
    prefix; if the writer emits ``// Attribution`` or
    ``Attribution:`` without the ``#`` the skip logic breaks.
    """
    output_path, _ = _write_two_country_csv(database_url, tmp_path)
    attribution_lines = _read_attribution_lines(output_path)
    assert attribution_lines, "no attribution lines found"
    for line in attribution_lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX), (
            f"attribution line missing prefix {ATTRIBUTION_COMMENT_PREFIX!r}: "
            f"{line!r}"
        )
        assert "Attribution: " in line, (
            f"attribution line missing 'Attribution: ' marker: {line!r}"
        )


def test_write_score_results_csv_data_header_stable_after_comments(
    database_url: str, tmp_path: Path
) -> None:
    """The first non-comment line is exactly ``SCORE_RESULTS_CSV_COLUMNS``.

    The data header is the contract every downstream consumer
    keys off (the column indices are used by the test helpers
    and by the Stage 12 comparison / Stage 14 manual-review
    queue). The attribution block is additive metadata only;
    the header must remain byte-for-byte stable.
    """
    output_path, _ = _write_two_country_csv(database_url, tmp_path)
    header, _ = _read_csv_rows(output_path)
    assert header == list(SCORE_RESULTS_CSV_COLUMNS)
    # And the header is the line immediately after the
    # attribution block (no blank lines, no extra metadata).
    with output_path.open(encoding="utf-8") as fh:
        raw_lines = [line.rstrip("\r\n") for line in fh]
    attribution_count = sum(1 for line in raw_lines if line.startswith("#"))
    assert raw_lines[attribution_count] == ",".join(SCORE_RESULTS_CSV_COLUMNS)


def test_write_score_results_csv_parses_with_pandas_comment_prefix(
    database_url: str, tmp_path: Path
) -> None:
    """``pandas.read_csv(comment="#")`` skips the attribution block cleanly.

    The downstream Stage 12 / Stage 14 / Stage 15 consumers use
    pandas to load CSVs; the attribution block must round-trip
    through the canonical ``comment="#"`` parser without losing
    the data header or the data rows.
    """
    pd = pytest.importorskip("pandas")
    output_path, _ = _write_two_country_csv(database_url, tmp_path)
    df = pd.read_csv(output_path, comment="#")
    assert list(df.columns) == list(SCORE_RESULTS_CSV_COLUMNS)
    # 2 country rows (BRA + MEX in iso3 order); the
    # attribution block did not consume any data rows.
    assert len(df) == 2
    assert list(df["iso3"]) == ["BRA", "MEX"]
