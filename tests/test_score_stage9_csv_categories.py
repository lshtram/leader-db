"""Tests for the Stage 9 CSV writer — per-category CLI explicit
``category_key=`` contract.

The all-countries CSV is an exported artifact under
``data/outputs/``; per AGENTS.md rule #15 ("carry source
attribution forward in every public output") and
``docs/sources/attributions.md`` §3.2 / §3.6, the writer must
carry the source attribution block for the contributing
sources as a ``# Attribution: <text>`` comment block at the
top of the file. The block is the small but contractually
important glue between the score module and the docs — without
it a downstream consumer cannot answer "where did these numbers
come from?" without re-reading ``docs/sources/attributions.md``.

Scope
-----

The tests live in a sibling test file so the canonical
``test_score_stage9_csv.py`` (the writer path through the
all-countries batch seam) stays under the 400-line convention
while still being one test module per writer-seam family. The
split mirrors the ``stage9_batch`` / ``stage9_batch_csv`` /
``stage9_csv`` / ``stage9_csv_categories`` /
``stage9_attribution`` pattern:

- :mod:`tests.test_score_stage9_batch` — the all-countries
  batch seam and the CSV row format / atomic-rename contract
  (no attribution assertions);
- :mod:`tests.test_score_stage9_batch_csv` — the CSV writer's
  data-shape contract (NA sentinel, missingness columns,
  review-flags encoding, parent-directory creation,
  atomic-rename);
- :mod:`tests.test_score_stage9_csv` — the writer path through
  the all-countries batch seam (full social_wellbeing
  attribution block emission, comment prefix stability, data
  header byte-for-byte match, pandas round-trip);
- :mod:`tests.test_score_stage9_csv_categories` — this file,
  the per-category CLI explicit ``category_key=`` contract
  (one test per registered category, the explicit-override
  semantics, the unknown-category defensive path);
- :mod:`tests.test_score_stage9_attribution` — the
  :func:`build_attribution_comment_lines` helper unit tests
  (helper does the right thing in isolation from the writer).

The tests cover:

- an explicit ``category_key=`` kwarg drives the attribution
  block (the CLI path) and overrides the result's own
  ``category_key``;
- each registered category (``integrity``, ``effectiveness``,
  ``economic_wellbeing``, ``political_freedom``) emits exactly
  one ``# Attribution: ...`` line per expected source and the
  block never lists ``client_existing`` (AGENTS.md rule #6);
- an unknown ``category_key`` produces no attribution block
  and the data header is the first line of the file.

All tests in this file use the direct single-row writer path
(no database, no batch seam) so they are independent of the
seeded-batch fixtures in :mod:`tests.test_score_stage9_batch`.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db.score.results import ScoreResult
from leaders_db.score.stage9 import (
    SCORE_RESULTS_CSV_COLUMNS,
    write_score_results_csv,
)

# Reuse the second-country constants and the comment-skipping
# CSV parser from the batch test file so this file does not
# duplicate the seed factory or the CSV reader.
from .test_score_stage9_batch import (
    SECOND_COUNTRY_NAME,
    _read_attribution_lines,
    _read_csv_rows,
)

# ---------------------------------------------------------------------------
# Explicit category_key kwarg (CLI path)
# ---------------------------------------------------------------------------


def test_write_score_results_csv_explicit_category_key_overrides_results(
    tmp_path: Path,
) -> None:
    """An explicit ``category_key=`` kwarg drives the attribution block.

    This is the CLI path: the dispatcher already knows the
    category and passes it explicitly so the attribution is
    present even on an empty batch (where ``results[0]`` is
    not available). The test seeds a ``corruption``
    :class:`ScoreResult` (not in the attribution mapping) and
    passes ``category_key="social_wellbeing"`` explicitly; the
    attribution block must reflect the explicit kwarg.
    """
    result = ScoreResult(
        category_key="corruption",
        iso3="BRA",
        year=2022,
        leader_name=SECOND_COUNTRY_NAME,
        normalized_score_0_1=None,
        system_proposed_score_1_10=None,
        is_insufficient_data=True,
        human_review_required=True,
    )
    output_path = tmp_path / "scores.csv"
    written = write_score_results_csv(
        (result,), output_path, category_key="social_wellbeing"
    )
    assert written == output_path.resolve()

    attribution_lines = _read_attribution_lines(output_path)
    # The explicit ``social_wellbeing`` kwarg drives the block
    # even though the result's category_key is ``corruption``.
    assert len(attribution_lines) == 4
    assert any("UNDP HDR 2023-24" in line for line in attribution_lines)
    # And the data row round-trips unchanged — the kwarg only
    # affects the comment block, not the row contents.
    header, rows = _read_csv_rows(output_path)
    assert header == list(SCORE_RESULTS_CSV_COLUMNS)
    assert rows[0][header.index("category_key")] == "corruption"


def test_write_score_results_csv_no_attribution_for_unknown_category(
    tmp_path: Path,
) -> None:
    """An unknown category writes no attribution block — data header is first.

    The writer must not crash on an unknown category (the
    dispatcher fails fast upstream; this is the defensive case
    where the writer is called from a custom path). The data
    header is the first line and the row contents are
    unchanged.
    """
    result = ScoreResult(
        category_key="corruption",
        iso3="BRA",
        year=2022,
        leader_name=SECOND_COUNTRY_NAME,
        normalized_score_0_1=None,
        system_proposed_score_1_10=None,
        is_insufficient_data=True,
        human_review_required=True,
    )
    output_path = tmp_path / "scores.csv"
    write_score_results_csv((result,), output_path)
    attribution_lines = _read_attribution_lines(output_path)
    assert attribution_lines == []
    header, rows = _read_csv_rows(output_path)
    assert header == list(SCORE_RESULTS_CSV_COLUMNS)
    assert rows[0][header.index("iso3")] == "BRA"


# ---------------------------------------------------------------------------
# Per-category attribution blocks
# ---------------------------------------------------------------------------


def test_write_score_results_csv_includes_integrity_attribution(
    tmp_path: Path,
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per integrity source.

    Direct-writer path test for AGENTS.md rule #15: when the
    caller passes ``category_key="integrity"`` explicitly, the
    writer emits the integrity attribution block (3 sources:
    WGI, V-Dem, TI CPI). ``client_existing`` is never listed
    (AGENTS.md rule #6).
    """
    result = ScoreResult(
        category_key="integrity",
        iso3="MEX",
        year=2023,
        leader_name="Andrés Manuel López Obrador",
        normalized_score_0_1=0.55,
        system_proposed_score_1_10=6,
        is_insufficient_data=False,
        human_review_required=False,
    )
    output_path = tmp_path / "integrity_scores.csv"
    write_score_results_csv(
        (result,), output_path, category_key="integrity"
    )

    attribution_lines = _read_attribution_lines(output_path)
    assert len(attribution_lines) == 3
    expected_phrases = [
        "World Bank WGI",
        "V-Dem v16",
        "Transparency International CPI 2023",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


def test_write_score_results_csv_includes_effectiveness_attribution(
    tmp_path: Path,
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per effectiveness source.

    Direct-writer path test for AGENTS.md rule #15: when the
    caller passes ``category_key="effectiveness"`` explicitly,
    the writer emits the effectiveness attribution block (3
    sources: WGI, V-Dem, BTI 2026). ``client_existing`` is
    never listed (AGENTS.md rule #6).
    """
    result = ScoreResult(
        category_key="effectiveness",
        iso3="MEX",
        year=2023,
        leader_name="Andrés Manuel López Obrador",
        normalized_score_0_1=0.58,
        system_proposed_score_1_10=6,
        is_insufficient_data=False,
        human_review_required=False,
    )
    output_path = tmp_path / "effectiveness_scores.csv"
    write_score_results_csv(
        (result,), output_path, category_key="effectiveness"
    )

    attribution_lines = _read_attribution_lines(output_path)
    assert len(attribution_lines) == 3
    expected_phrases = [
        "World Bank WGI",
        "V-Dem v16",
        "BTI 2026",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


def test_write_score_results_csv_includes_economic_wellbeing_attribution(
    tmp_path: Path,
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per economic_wellbeing source.

    Direct-writer path test for AGENTS.md rule #15: when the
    caller passes ``category_key="economic_wellbeing"``
    explicitly, the writer emits the economic_wellbeing
    attribution block (2 sources: WDI, BTI 2026).
    ``client_existing`` is never listed (AGENTS.md rule #6).
    """
    result = ScoreResult(
        category_key="economic_wellbeing",
        iso3="MEX",
        year=2023,
        leader_name="Andrés Manuel López Obrador",
        normalized_score_0_1=0.50,
        system_proposed_score_1_10=5,
        is_insufficient_data=False,
        human_review_required=False,
    )
    output_path = tmp_path / "economic_wellbeing_scores.csv"
    write_score_results_csv(
        (result,), output_path, category_key="economic_wellbeing"
    )

    attribution_lines = _read_attribution_lines(output_path)
    assert len(attribution_lines) == 2
    expected_phrases = [
        "World Bank WDI",
        "BTI 2026",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


def test_write_score_results_csv_includes_political_freedom_attribution(
    tmp_path: Path,
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per political_freedom source.

    Direct-writer path test for AGENTS.md rule #15: when the
    caller passes ``category_key="political_freedom"``
    explicitly, the writer emits the political_freedom
    attribution block (3 sources: V-Dem, RSF, BTI 2026).
    ``client_existing`` is never listed (AGENTS.md rule #6).
    """
    result = ScoreResult(
        category_key="political_freedom",
        iso3="MEX",
        year=2023,
        leader_name="Andrés Manuel López Obrador",
        normalized_score_0_1=0.55,
        system_proposed_score_1_10=6,
        is_insufficient_data=False,
        human_review_required=False,
    )
    output_path = tmp_path / "political_freedom_scores.csv"
    write_score_results_csv(
        (result,), output_path, category_key="political_freedom"
    )

    attribution_lines = _read_attribution_lines(output_path)
    assert len(attribution_lines) == 3
    expected_phrases = [
        "V-Dem v16",
        "RSF World Press Freedom Index",
        "BTI 2026",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


def test_write_score_results_csv_includes_international_peace_attribution(
    tmp_path: Path,
) -> None:
    """The CSV opens with one ``# Attribution: ...`` line per international_peace source.

    Direct-writer path test for AGENTS.md rule #15: when the
    caller passes ``category_key="international_peace"``
    explicitly, the writer emits the international_peace
    attribution block (2 sources: UCDP, SIPRI milex).
    ``client_existing`` is never listed (AGENTS.md rule #6).
    """
    result = ScoreResult(
        category_key="international_peace",
        iso3="MEX",
        year=2023,
        leader_name="Andrés Manuel López Obrador",
        normalized_score_0_1=0.60,
        system_proposed_score_1_10=6,
        is_insufficient_data=False,
        human_review_required=False,
    )
    output_path = tmp_path / "international_peace_scores.csv"
    write_score_results_csv(
        (result,), output_path, category_key="international_peace"
    )

    attribution_lines = _read_attribution_lines(output_path)
    assert len(attribution_lines) == 2
    expected_phrases = [
        "UCDP GED 23.1",
        "SIPRI milex",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CSV header "
            f"(attribution lines: {attribution_lines!r})"
        )
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()
