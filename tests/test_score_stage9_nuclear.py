"""Stage 9 production seam tests for the ``nuclear`` category.

Closes the reviewer blocker "production Stage 9 proof gap"
for the nuclear scorer. The single-category seam
(:func:`leaders_db.score.stage9.score_category_for_country`) is
the social-wellbeing happy path in :mod:`tests.test_score_stage9`;
this file is the sibling that covers the same end-to-end
production path for the ``nuclear`` category — seeding an
isolated SQLite DB with FAS + SIPRI Yearbook Ch.7
``source_observations`` rows, then calling
``score_category_for_country`` and
``score_category_for_all_countries`` to prove the chain
returns a :class:`~leaders_db.score.results.ScoreResult`.
Brazil (``BRA``) is seeded with no observations so the batch
path proves the insufficient-data branch end-to-end against
the real DB + real bundle builder.

The all-countries batch seam + CSV-facing proof for the
insufficient-data rationale contract live in the focused
sibling :mod:`tests.test_score_stage9_nuclear_batch`.
"""

from __future__ import annotations

from sqlalchemy import select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country
from leaders_db.db.session import session_scope
from leaders_db.score.results import ReviewFlag, ScoreResult
from leaders_db.score.stage9 import (
    score_category_for_all_countries,
    score_category_for_country,
)

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    TARGET_YEAR,
    add_observation,
    seed_country,
    upsert_source,
)

# Source names match the production ``register_*_source``
# calls so :func:`canonical_source_key` resolves them.
FAS_SOURCE_NAME: str = "Federation of American Scientists Nuclear Notebook (test)"
SIPRI_YEARBOOK_CH7_SOURCE_NAME: str = (
    "SIPRI Yearbook Chapter 7 (World Nuclear Forces) (test)"
)

# ``USA`` is the realistic nuclear-armed test country;
# ``BRA`` is inserted *after* ``USA`` so the iso3 ordering
# of the batch result is exercised (``BRA < USA``
# lexicographically).
NUCLEAR_COUNTRY_ISO3: str = "USA"
NUCLEAR_COUNTRY_NAME: str = "United States"
NUCLEAR_COUNTRY_REGION: str = "NAM"
NUCLEAR_COUNTRY_NAME_NORMALIZED: str = "united states"
SECOND_COUNTRY_ISO3: str = "BRA"
SECOND_COUNTRY_NAME: str = "Brazil"
SECOND_COUNTRY_REGION: str = "LAC"
SECOND_COUNTRY_NAME_NORMALIZED: str = "brazil"

# Per-source ``(variable_name, normalized_value)`` pairs to
# seed for the dense nuclear bundle. All 8 NUCLEAR_PLAN
# indicators populated across 2 sources.
NUCLEAR_SEED: tuple = (
    (
        FAS_SOURCE_NAME,
        "fas",
        (
            ("fas_operational_strategic", 0.30),
            ("fas_operational_nonstrategic", 0.40),
            ("fas_reserve_nondeployed", 0.45),
            ("fas_military_stockpile", 0.35),
            ("fas_total_inventory", 0.25),
        ),
    ),
    (
        SIPRI_YEARBOOK_CH7_SOURCE_NAME,
        "sipri_yearbook_ch7",
        (
            (
                "sipri_yearbook_ch7_nuclear_warheads_total_inventory",
                0.40,
            ),
            (
                "sipri_yearbook_ch7_nuclear_warheads_deployed",
                0.55,
            ),
            (
                "sipri_yearbook_ch7_nuclear_warheads_retired",
                0.65,
            ),
        ),
    ),
)


def _seed_usa_nuclear_bundle(database_url: str) -> None:
    """Seed USA 2023 with FAS + SIPRI Yearbook Ch.7 observations.

    Two distinct sources — the plan's ``minimum_viable_sources
    = 1`` with margin. All 8 NUCLEAR_PLAN indicators populated
    so the bundle builder emits a usable bundle.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = session.execute(
            select(Country).where(Country.iso3 == NUCLEAR_COUNTRY_ISO3)
        ).scalar_one_or_none()
        if country is None:
            country = Country(
                iso3=NUCLEAR_COUNTRY_ISO3,
                country_name=NUCLEAR_COUNTRY_NAME,
                country_name_normalized=NUCLEAR_COUNTRY_NAME_NORMALIZED,
                region=NUCLEAR_COUNTRY_REGION,
            )
            session.add(country)
            session.flush()
        for source_name, source_short, rows in NUCLEAR_SEED:
            source_row = upsert_source(session, source_name=source_name)
            for variable_name, normalized in rows:
                add_observation(
                    session,
                    source_id=source_row.id,
                    country_id=country.id,
                    year=TARGET_YEAR,
                    variable_name=variable_name,
                    raw_value=f"{normalized:.4f}",
                    normalized_value=normalized,
                    unit="index",
                    source_row_reference=(
                        f"{source_short}:{NUCLEAR_COUNTRY_ISO3}:"
                        f"{TARGET_YEAR}:{variable_name}"
                    ),
                )


def _seed_usa_and_brazil(database_url: str) -> None:
    """Seed USA (dense nuclear bundle) + BRA (no observations)."""
    _seed_usa_nuclear_bundle(database_url)
    with session_scope(database_url) as session:
        brazil = Country(
            iso3=SECOND_COUNTRY_ISO3,
            country_name=SECOND_COUNTRY_NAME,
            country_name_normalized=SECOND_COUNTRY_NAME_NORMALIZED,
            region=SECOND_COUNTRY_REGION,
        )
        session.add(brazil)
        session.flush()


# ---------------------------------------------------------------------------
# Single-country seam
# ---------------------------------------------------------------------------


def test_score_category_for_country_nuclear_returns_score_result(
    database_url: str,
) -> None:
    """The seam composes bundle-builder + dispatcher and returns a ScoreResult.

    Boundary test: fails if the ``nuclear`` entry is dropped
    from :data:`leaders_db.score.dispatch._SCORERS` or the
    bundle builder is replaced with a stub.
    """
    _seed_usa_nuclear_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=NUCLEAR_COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    assert isinstance(result, ScoreResult)
    assert result.category_key == "nuclear"
    assert result.iso3 == NUCLEAR_COUNTRY_ISO3
    assert result.year == TARGET_YEAR


def test_score_category_for_country_nuclear_emits_observation_refs(
    database_url: str,
) -> None:
    """The seam produces a result with one observation ref per indicator."""
    _seed_usa_nuclear_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=NUCLEAR_COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    assert result.is_insufficient_data is False
    assert len(result.observation_refs) == 8
    assert {ref.source_key for ref in result.observation_refs} == {
        "fas",
        "sipri_yearbook_ch7",
    }


def test_score_category_for_country_nuclear_emits_concrete_score(
    database_url: str,
) -> None:
    """The seam emits a 1..10 score for the dense USA seed."""
    _seed_usa_nuclear_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=NUCLEAR_COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    # The NUCLEAR_CASE population-split flag fires on the
    # scored path because the bundle carries usable FAS /
    # SIPRI Yearbook Ch.7 observations.
    assert ReviewFlag.NUCLEAR_CASE in result.review_flags
    assert result.human_review_required is True


def test_score_category_for_country_nuclear_components_cover_groups(
    database_url: str,
) -> None:
    """The seam emits one :class:`ScoreComponent` per rubric group."""
    _seed_usa_nuclear_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=NUCLEAR_COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    by_group: dict[str, int] = {}
    for component in result.components:
        _, _, group_key = component.component_key.partition("__")
        by_group[group_key] = by_group.get(group_key, 0) + 1
    assert by_group == {
        "fas_nuclear_forces": 5,
        "sipri_yearbook_ch7_nuclear_forces": 3,
    }


# ---------------------------------------------------------------------------
# Sparse / insufficient-data paths
# ---------------------------------------------------------------------------


def test_score_category_for_country_nuclear_handles_sparse_bundle(
    database_url: str,
) -> None:
    """A bundle below the minimum-viable threshold emits an insufficient-data result.

    Seed zero sources — the typical non-nuclear state case
    (~190 of ~200 prototype countries have no FAS / SIPRI
    Yearbook Ch.7 row at all).
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert result.normalized_score_0_1 is None
    assert result.human_review_required is True
    assert result.observation_refs == ()
    assert result.components == ()
    # The nuclear-specific rationale wording explicitly says
    # "non-nuclear state".
    assert "non-nuclear" in result.rationale_short.lower()
    # The NUCLEAR_CASE flag does NOT fire on the
    # insufficient-data path.
    assert ReviewFlag.NUCLEAR_CASE not in result.review_flags


# ---------------------------------------------------------------------------
# All-countries batch seam
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_nuclear_returns_one_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_usa_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    iso3s = tuple(r.iso3 for r in results)
    # Ordered by iso3 — BRA < USA lexicographically.
    assert iso3s == (SECOND_COUNTRY_ISO3, NUCLEAR_COUNTRY_ISO3)
    for r in results:
        assert isinstance(r, ScoreResult)
        assert r.category_key == "nuclear"
        assert r.year == TARGET_YEAR
    # NUCLEAR_CASE fires only on the scored USA row (not on the
    # insufficient-data BRA row).
    by_iso = {r.iso3: r for r in results}
    assert ReviewFlag.NUCLEAR_CASE in by_iso[NUCLEAR_COUNTRY_ISO3].review_flags
    assert (
        ReviewFlag.NUCLEAR_CASE
        not in by_iso[SECOND_COUNTRY_ISO3].review_flags
    )


def test_score_category_for_all_countries_nuclear_scored_country_has_score(
    database_url: str,
) -> None:
    """The dense USA row in the batch gets a real (non-insufficient) score."""
    _seed_usa_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    usa = next(r for r in results if r.iso3 == NUCLEAR_COUNTRY_ISO3)
    assert usa.is_insufficient_data is False
    assert usa.system_proposed_score_1_10 is not None
    assert 1 <= usa.system_proposed_score_1_10 <= 10
    assert 0.0 <= (usa.normalized_score_0_1 or 0.0) <= 1.0
    assert len(usa.observation_refs) == 8
    assert ReviewFlag.NUCLEAR_CASE in usa.review_flags
    assert usa.human_review_required is True


def test_score_category_for_all_countries_nuclear_missing_country_has_insufficient(
    database_url: str,
) -> None:
    """A Country row with no observations emits ``is_insufficient_data=True``."""
    _seed_usa_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="nuclear",
        )

    bra = next(r for r in results if r.iso3 == SECOND_COUNTRY_ISO3)
    assert bra.is_insufficient_data is True
    assert bra.system_proposed_score_1_10 is None
    assert bra.normalized_score_0_1 is None
    assert bra.human_review_required is True
    # INSUFFICIENT_DATA is the gate signal; SPARSE_DATA rides
    # along because observed_ratio (0/8) is below 0.5.
    assert ReviewFlag.INSUFFICIENT_DATA in bra.review_flags
    assert ReviewFlag.SPARSE_DATA in bra.review_flags
    assert bra.observation_refs == ()
    assert bra.missingness is not None
    assert bra.missingness.total_expected == 8
    assert bra.missingness.total_observed == 0
    # The nuclear-specific rationale wording explicitly says
    # "non-nuclear state" — a non-nuclear state must never
    # receive an invented numeric score.
    assert "non-nuclear" in bra.rationale_short.lower()
    assert ReviewFlag.NUCLEAR_CASE not in bra.review_flags


__all__ = [
    "FAS_SOURCE_NAME",
    "NUCLEAR_COUNTRY_ISO3",
    "NUCLEAR_COUNTRY_NAME",
    "NUCLEAR_SEED",
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SIPRI_YEARBOOK_CH7_SOURCE_NAME",
    "_seed_usa_nuclear_bundle",
]
