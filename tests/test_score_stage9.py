"""Tests for the Stage 9 production seam
(:func:`leaders_db.score.stage9.score_category_for_country`).

The seam composes :func:`leaders_db.resolve.indicators.build_category_evidence_bundle`
with :func:`leaders_db.score.dispatch.score_category_bundle` so a
single call turns ``(session, country, year, category_key)`` into a
:class:`ScoreResult`. These tests seed an isolated SQLite DB with
the minimum rows the Stage 5 builder needs to emit a usable
bundle for the canonical social-wellbeing category (Mexico 2023),
then verify the seam returns the right shape.

The tests fail if either the bundle builder or the dispatcher is
removed — both are real production seams, not test-only stubs.
"""

from __future__ import annotations

import pytest

from leaders_db.db.engine import init_database
from leaders_db.db.session import session_scope
from leaders_db.score.results import ScoreResult
from leaders_db.score.stage9 import score_category_for_country

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


def _seed_mexico_social_wellbeing_bundle(database_url: str) -> None:
    """Stage enough rows for ``social_wellbeing`` Mexico 2023.

    Four distinct sources (``undp_hdi``, ``who_gho_api``,
    ``world_bank_wdi``, ``vdem``) — well above the plan's
    ``minimum_viable_sources = 2``. The seeded observation set is
    the same shape as
    :func:`tests._social_wellbeing_factories.realistic_mexico_observations`
    so the bundle and the scorer see a realistic enough picture to
    emit a real (non-insufficient-data) result.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        undp = upsert_source(session, source_name=UNDP_SOURCE_NAME)
        who = upsert_source(session, source_name=WHO_SOURCE_NAME)
        wdi = upsert_source(session, source_name=WDI_SOURCE_NAME)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)

        # UNDP HDI composite + components.
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
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"undp_hdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        # WHO GHO API — two distinct indicators.
        for var, value in (
            ("who_gho_under5_mortality", 0.85),
            ("who_gho_dtp3_immunization", 0.85),
        ):
            add_observation(
                session,
                source_id=who.id,
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"who_gho_api:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        # World Bank WDI — literacy + gini.
        for var, value in (
            ("wdi_literacy_rate_adult", 0.95),
            ("wdi_gini_index", 0.60),
        ):
            add_observation(
                session,
                source_id=wdi.id,
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"world_bank_wdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        # V-Dem egalitarian.
        add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="vdem_v2x_egal",
            raw_value="0.5500",
            normalized_value=0.55,
            unit="index",
            source_row_reference=f"vdem:{COUNTRY_ISO3}:{TARGET_YEAR}:v2x_egal",
        )


# ---------------------------------------------------------------------------
# Happy-path production seam
# ---------------------------------------------------------------------------


def test_score_category_for_country_returns_score_result(
    database_url: str,
) -> None:
    """The seam composes bundle-builder + dispatcher and returns a ScoreResult.

    Boundary test: fails if either
    :func:`build_category_evidence_bundle` or
    :func:`score_category_bundle` is removed/replaced with a stub.
    """
    _seed_mexico_social_wellbeing_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    assert isinstance(result, ScoreResult)
    assert result.category_key == "social_wellbeing"
    assert result.iso3 == COUNTRY_ISO3
    assert result.year == TARGET_YEAR


def test_score_category_for_country_emits_observation_refs(
    database_url: str,
) -> None:
    """The seam produces a result with the seeded observation refs."""
    _seed_mexico_social_wellbeing_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    # The realistic seed is 10 observations across 4 distinct
    # sources — well above the plan's ``minimum_viable_sources = 2``,
    # so the result is a real (non-insufficient-data) score with
    # 10 observation refs.
    assert result.is_insufficient_data is False
    assert result.observation_refs  # non-empty
    assert len(result.observation_refs) == 10
    # Every observation ref is a real source key from the seeded
    # set; the dispatcher dispatched to the social_wellbeing scorer
    # which carries per-source refs.
    source_keys = {ref.source_key for ref in result.observation_refs}
    assert {"undp_hdi", "who_gho_api", "world_bank_wdi", "vdem"} <= source_keys


def test_score_category_for_country_emits_concrete_score(
    database_url: str,
) -> None:
    """The seam emits a 1..10 score for the dense Mexico seed."""
    _seed_mexico_social_wellbeing_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0


# ---------------------------------------------------------------------------
# Sparse / insufficient-data paths
# ---------------------------------------------------------------------------


def test_score_category_for_country_handles_sparse_bundle(
    database_url: str,
) -> None:
    """A bundle below the minimum-viable threshold emits an insufficient-data result."""
    # Seed exactly ONE source with a usable observation. The
    # social_wellbeing plan requires ``minimum_viable_sources = 2``
    # so a single-source bundle must come back as
    # ``is_insufficient_data = True`` with no score.
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        undp = upsert_source(session, source_name=UNDP_SOURCE_NAME)
        add_observation(
            session,
            source_id=undp.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="undp_hdi_hdi",
            raw_value="0.78",
            normalized_value=0.78,
            unit="index",
            source_row_reference=f"undp_hdi:{COUNTRY_ISO3}:{TARGET_YEAR}:hdi",
        )

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert result.normalized_score_0_1 is None
    assert result.human_review_required is True
    # The result carries the empty observation_refs tuple — the
    # insufficient-data path emits no scoring components.
    assert result.observation_refs == ()


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


def test_score_category_for_country_missing_country_raises(
    database_url: str,
) -> None:
    """An unknown country raises ``ValueError`` from the underlying builder."""
    init_database(database_url)
    with session_scope(database_url) as session:
        with pytest.raises(ValueError) as excinfo:
            score_category_for_country(
                session,
                country_iso3="ZZZ",
                year=TARGET_YEAR,
                category_key="social_wellbeing",
            )
    assert "ZZZ" in str(excinfo.value)


def test_score_category_for_country_unsupported_category_raises(
    database_url: str,
) -> None:
    """An unsupported category raises ``ValueError`` from the dispatcher.

    The dispatcher's error message must list the supported set so
    the next caller can pick the right category without reading the
    package source.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        with pytest.raises(ValueError) as excinfo:
            score_category_for_country(
                session,
                country_iso3=COUNTRY_ISO3,
                year=TARGET_YEAR,
                category_key="political_freedom",
            )
    message = str(excinfo.value)
    assert "political_freedom" in message
    assert "social_wellbeing" in message
