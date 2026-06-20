"""Tests for the Stage 9 all-countries batch seam
(:func:`leaders_db.score.stage9.score_category_for_all_countries`).

The single-country seam
(:func:`leaders_db.score.stage9.score_category_for_country`) lives in
:mod:`tests.test_score_stage9`; this file is the sibling that
covers the batch path. Splitting the two keeps each file under
the 400-line convention while still being one test module per
production seam family.

The CSV export helper
(:func:`leaders_db.score.stage9.write_score_results_csv`) has
three focused sibling test surfaces:

- :mod:`tests.test_score_stage9_batch_csv` — the CSV writer's
  data-shape contract (NA sentinel, missingness columns,
  review-flags encoding, parent-directory creation,
  atomic-rename);
- :mod:`tests.test_score_stage9_csv` — the CSV writer's
  attribution-block contract via the direct writer path
  through the all-countries batch seam (the
  ``# Attribution: ...`` comment block for the derived
  ``social_wellbeing`` category, comment-prefix stability,
  header byte-for-byte match, pandas round-trip);
- :mod:`tests.test_score_stage9_csv_categories` — the CSV
  writer's per-category CLI explicit ``category_key=`` contract
  (one test per registered category, the explicit-override
  semantics, the unknown-category defensive path).

The two sibling test files share the seed factory
(:func:`_seed_mexico_and_brazil`) and the comment-skipping
helpers (:func:`_read_csv_rows`, :func:`_read_attribution_lines`)
defined here, so a future attribution-block change is exercised
against the same fixture / reader as the data-shape tests.

The batch seam is the canonical reusable pattern for per-category
vertical slices. The tests seed two countries — ``MEX`` with the
dense social-wellbeing bundle (a real score) and ``BRA`` with no
observations (a clean insufficient-data result) — and assert the
batch returns one :class:`ScoreResult` per country in ``iso3``
order.

The tests fail if either the bundle builder or the dispatcher is
removed — both are real production seams, not test-only stubs.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country
from leaders_db.db.session import session_scope
from leaders_db.score.results import ScoreResult
from leaders_db.score.stage9 import score_category_for_all_countries

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    TARGET_YEAR,
    UNDP_SOURCE_NAME,
    VDEM_SOURCE_NAME,
    WDI_SOURCE_NAME,
    WHO_SOURCE_NAME,
    add_observation,
    seed_country,
    upsert_source,
)

# ---------------------------------------------------------------------------
# Fixture: two countries, one dense and one empty.
# ---------------------------------------------------------------------------

SECOND_COUNTRY_ISO3: str = "BRA"
SECOND_COUNTRY_NAME: str = "Brazil"
SECOND_COUNTRY_REGION: str = "LAC"


def _seed_mexico_and_brazil(database_url: str) -> None:
    """Seed MEX (dense) + BRA (no observations) for batch-seam tests.

    ``BRA`` is intentionally inserted *after* ``MEX`` in the seed
    loop so the iso3 ordering of the resulting tuple is
    exercised, not just the insertion order of the seeded rows
    (the seam orders by ``iso3`` and ``BRA < MEX`` lexicographically).
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        mexico = seed_country(session)
        brazil = Country(
            iso3=SECOND_COUNTRY_ISO3,
            country_name=SECOND_COUNTRY_NAME,
            country_name_normalized="brazil",
            region=SECOND_COUNTRY_REGION,
        )
        session.add(brazil)
        session.flush()

        undp = upsert_source(session, source_name=UNDP_SOURCE_NAME)
        who = upsert_source(session, source_name=WHO_SOURCE_NAME)
        wdi = upsert_source(session, source_name=WDI_SOURCE_NAME)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)

        # Dense Mexico bundle — same shape as the single-country
        # happy-path test, 10 observations across 4 sources.
        for var, value in (
            ("undp_hdi_hdi", 0.78),
            ("undp_hdi_life_expectancy", 0.70),
            ("undp_hdi_expected_years_schooling", 0.75),
            ("undp_hdi_mean_years_schooling", 0.65),
            ("undp_hdi_gni_per_capita", 0.70),
        ):
            add_observation(
                session,
                source_id=undp.id,
                country_id=mexico.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"undp_hdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        for var, value in (
            ("who_gho_under5_mortality", 0.85),
            ("who_gho_dtp3_immunization", 0.85),
        ):
            add_observation(
                session,
                source_id=who.id,
                country_id=mexico.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"who_gho_api:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        for var, value in (
            ("wdi_literacy_rate_adult", 0.95),
            ("wdi_gini_index", 0.60),
        ):
            add_observation(
                session,
                source_id=wdi.id,
                country_id=mexico.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"world_bank_wdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        add_observation(
            session,
            source_id=vdem.id,
            country_id=mexico.id,
            year=TARGET_YEAR,
            variable_name="vdem_v2x_egal",
            raw_value="0.5500",
            normalized_value=0.55,
            unit="index",
            source_row_reference=f"vdem:{COUNTRY_ISO3}:{TARGET_YEAR}:v2x_egal",
        )


# ---------------------------------------------------------------------------
# All-countries batch seam
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_returns_one_result_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    iso3s = tuple(r.iso3 for r in results)
    # Ordered by iso3 — BRA < MEX lexicographically — so the
    # deterministic order is independent of insertion order.
    assert iso3s == ("BRA", "MEX")
    for r in results:
        assert isinstance(r, ScoreResult)
        assert r.category_key == "social_wellbeing"
        assert r.year == TARGET_YEAR


def test_score_category_for_all_countries_scored_country_has_score(
    database_url: str,
) -> None:
    """The dense MEX row in the batch gets a real (non-insufficient) score."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    by_iso = {r.iso3: r for r in results}
    mex = by_iso["MEX"]
    assert mex.is_insufficient_data is False
    assert mex.system_proposed_score_1_10 is not None
    assert 1 <= mex.system_proposed_score_1_10 <= 10
    assert mex.normalized_score_0_1 is not None
    assert 0.0 <= mex.normalized_score_0_1 <= 1.0
    assert len(mex.observation_refs) == 10


def test_score_category_for_all_countries_missing_country_has_insufficient(
    database_url: str,
) -> None:
    """A Country row with no observations emits ``is_insufficient_data=True``."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    by_iso = {r.iso3: r for r in results}
    bra = by_iso["BRA"]
    assert bra.is_insufficient_data is True
    assert bra.system_proposed_score_1_10 is None
    assert bra.normalized_score_0_1 is None
    assert bra.human_review_required is True
    assert bra.observation_refs == ()
    # Missingness summary is the missingness-investigation artifact;
    # the batch seam relies on the dispatcher to populate it even
    # for the empty-bundle path.
    assert bra.missingness is not None
    assert bra.missingness.total_expected > 0
    assert bra.missingness.total_observed == 0


def test_score_category_for_all_countries_results_is_tuple(
    database_url: str,
) -> None:
    """The batch seam returns a real ``tuple`` (not a generator) for reuse."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    assert isinstance(results, tuple)
    # Iteration must be repeatable — the CSV writer walks the
    # sequence; a future caller might also compute a summary.
    first_pass = [r.iso3 for r in results]
    second_pass = [r.iso3 for r in results]
    assert first_pass == second_pass


def test_score_category_for_all_countries_empty_db_returns_empty_tuple(
    database_url: str,
) -> None:
    """A DB with no ``Country`` rows returns an empty tuple (not an error)."""
    init_database(database_url)
    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )
    assert results == ()


# ---------------------------------------------------------------------------
# Shared CSV-reader helpers used by the writer test siblings
# ---------------------------------------------------------------------------
#
# :mod:`tests.test_score_stage9_batch_csv` (data-shape),
# :mod:`tests.test_score_stage9_csv` (direct writer-path
# attribution), and :mod:`tests.test_score_stage9_csv_categories`
# (per-category CLI explicit ``category_key=``) all import these
# helpers, so they live in the canonical batch module to avoid a
# circular import. The CSV writer and column tuple are imported
# directly by the sibling writer-test modules.

__all__ = [
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SECOND_COUNTRY_REGION",
    "_is_comment_row",
    "_read_attribution_lines",
    "_read_csv_rows",
    "_seed_mexico_and_brazil",
]


def _read_csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """Parse ``path`` into ``(header, rows)`` for table-style assertions.

    The CSV opens with one ``# Attribution: ...`` comment line per
    contributing source (per AGENTS.md rule #15). This helper
    filters them out so the assertions see the canonical data
    shape (header + one row per :class:`ScoreResult`). The
    attribution block itself is exercised separately by
    :func:`_read_attribution_lines` so the two contracts — "the
    comment block is present and correct" and "the data header
    matches :data:`SCORE_RESULTS_CSV_COLUMNS`" — are pinned by
    two independent code paths instead of one shared parser.
    """
    import csv as _csv

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(_csv.reader(fh))
    data_rows = [row for row in rows if not _is_comment_row(row)]
    return data_rows[0], data_rows[1:]


def _read_attribution_lines(path: Path) -> list[str]:
    """Return the raw lines from ``path`` whose first column starts with ``#``.

    The CSV opens with one ``# Attribution: <text>`` line per
    contributing source for the category. The function returns
    those raw lines (one ``str`` per attribution source) in file
    order so the test can assert presence and ordering.
    """
    lines: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.rstrip("\r\n")
            if stripped.startswith("#"):
                lines.append(stripped)
            else:
                # The attribution block is contiguous at the top of
                # the file; the first non-``#`` line is the data
                # header (or the first data row on empty results),
                # so stop scanning once we cross the boundary.
                break
    return lines


def _is_comment_row(row: list[str]) -> bool:
    """Return ``True`` if ``row`` is an attribution comment row.

    Comment rows are emitted by the writer as single-cell rows
    whose cell starts with the literal ``#`` character; the
    canonical ``csv.writer`` round-trip preserves the cell
    verbatim so a stripped first cell is a sufficient check.
    """
    return bool(row) and row[0].startswith("#")
