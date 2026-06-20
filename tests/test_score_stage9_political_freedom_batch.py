"""Stage 9 all-countries batch seam tests for the ``political_freedom`` category.

Sibling of :mod:`tests.test_score_stage9_political_freedom` (the
single-country seam + sparse-bundle insufficient-data proof).
Splitting the batch-seam proof into its own focused module keeps
the single-country file under the 400-line convention while still
being one test module per production seam family. The same split
pattern is used by :mod:`tests.test_score_stage9_nuclear` /
:mod:`tests.test_score_stage9_nuclear_batch` and the per-category
batch siblings.

The tests cover the three batch-seam contracts for the
``political_freedom`` category:

- one :class:`ScoreResult` per :class:`Country` row, ordered by
  ``iso3`` (the deterministic order, independent of insertion
  order);
- the dense MEX row emits a real (non-insufficient) score with
  16 observation refs across the three seeded sources
  (``vdem`` / ``bti`` / ``rsf_press_freedom``);
- the BRA row (no observations) emits ``is_insufficient_data=True``
  with the ``INSUFFICIENT_DATA`` + ``SPARSE_DATA`` review flags
  and a populated :class:`MissingnessSummary` (16 expected /
  0 observed).

The helpers (``_seed_mexico_political_freedom_bundle``,
``_seed_mexico_and_brazil``) and constants are imported from the
sibling :mod:`tests.test_score_stage9_political_freedom` so the
seed shape stays single-sourced.

Style invariants (per ``docs/coding-guidelines.md``): type hints,
no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.db.session import session_scope
from leaders_db.score.results import ReviewFlag, ScoreResult
from leaders_db.score.stage9 import score_category_for_all_countries

from .test_score_stage9_political_freedom import (
    COUNTRY_ISO3,
    SECOND_COUNTRY_ISO3,
    TARGET_YEAR,
    _seed_mexico_and_brazil,
)

# ---------------------------------------------------------------------------
# All-countries batch seam (re-pinned from the sibling file)
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_political_freedom_returns_one_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    iso3s = tuple(r.iso3 for r in results)
    # Ordered by iso3 — BRA < MEX lexicographically — so the
    # deterministic order is independent of insertion order.
    assert iso3s == (SECOND_COUNTRY_ISO3, COUNTRY_ISO3)
    for r in results:
        assert isinstance(r, ScoreResult)
        assert r.category_key == "political_freedom"
        assert r.year == TARGET_YEAR


def test_score_category_for_all_countries_political_freedom_scored_country_has_score(
    database_url: str,
) -> None:
    """The dense MEX row in the batch gets a real (non-insufficient) score."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    mex = next(r for r in results if r.iso3 == COUNTRY_ISO3)
    assert mex.is_insufficient_data is False
    assert mex.system_proposed_score_1_10 is not None
    assert 1 <= mex.system_proposed_score_1_10 <= 10
    assert 0.0 <= (mex.normalized_score_0_1 or 0.0) <= 1.0
    # 16 indicators × 1 ref each = 16 refs total.
    assert len(mex.observation_refs) == 16
    assert mex.review_flags == ()
    assert mex.human_review_required is False


def test_score_category_for_all_countries_political_freedom_missing_country_has_insufficient(
    database_url: str,
) -> None:
    """A Country row with no observations emits ``is_insufficient_data=True``.

    End-to-end proof that the insufficient-data branch — including
    the BLOCKER-1 fix that derives ``MISSING_PRIMARY_SOURCE`` /
    ``SPARSE_DATA`` / ``LOW_CONFIDENCE`` from the bundle on top of
    the ``INSUFFICIENT_DATA`` gate — fires correctly through the
    batch seam + bundle builder + dispatcher + scorer chain.
    """
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    bra = next(r for r in results if r.iso3 == SECOND_COUNTRY_ISO3)
    assert bra.is_insufficient_data is True
    assert bra.system_proposed_score_1_10 is None
    assert bra.normalized_score_0_1 is None
    assert bra.human_review_required is True
    # INSUFFICIENT_DATA is the gate signal; SPARSE_DATA rides along
    # because observed_ratio (0/16) is below the 0.5 threshold.
    assert ReviewFlag.INSUFFICIENT_DATA in bra.review_flags
    assert ReviewFlag.SPARSE_DATA in bra.review_flags
    assert bra.observation_refs == ()
    # Missingness summary is the missingness-investigation artifact;
    # the batch seam relies on the dispatcher to populate it even
    # for the empty-bundle path.
    assert bra.missingness is not None
    assert bra.missingness.total_expected == 16
    assert bra.missingness.total_observed == 0


__all__ = [
    "test_score_category_for_all_countries_political_freedom_missing_country_has_insufficient",
    "test_score_category_for_all_countries_political_freedom_returns_one_per_country",
    "test_score_category_for_all_countries_political_freedom_scored_country_has_score",
]
