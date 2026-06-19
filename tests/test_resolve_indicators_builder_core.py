"""Core behavior tests for the Stage 5 evidence-bundle builder (Phase E).

These tests exercise the production seam
:func:`leaders_db.resolve.indicators.build_category_evidence_bundle`
against real ORM rows on the per-test isolated SQLite fixture for
the **happy path** and the **error contract** — i.e. everything
that is not specifically about missingness reasons, wrong-source
exclusion, or deterministic tie-breakers (those live in the
sibling modules).

Coverage pinned here:

- (a) Direct-year observation included with raw locator and source-key
      derivation.
- (b) Proxy-year (2022 → 2023) selection when the plan allows a
      1-year gap.
- (h) Minimum-viable-evidence property reflects the distinct source
      count from the plan's expected sources.
- (i) Error contract: unsupported category, empty category, missing
      country all raise :class:`ValueError` with self-explanatory
      messages.
- :class:`IndicatorSpec` validation guards (empty / ``None``
  ``source_key``).

Wrong-source / client-source / missingness-reason / partial-registration
tests live in :mod:`tests.test_resolve_indicators_builder_missing`;
deterministic tie-breaker tests live in
:mod:`tests.test_resolve_indicators_builder_selection`.

The shared fixtures live in :mod:`tests._resolve_indicators_factories`
so the plan/source-key contract tests can reuse the same helpers
without recreating them.
"""

from __future__ import annotations

import pytest

from leaders_db.db.engine import init_database
from leaders_db.db.session import session_scope
from leaders_db.resolve.indicators import build_category_evidence_bundle
from leaders_db.score.evidence import (
    Direction,
    TemporalKind,
)
from leaders_db.score.evidence_types import IndicatorRole, IndicatorSpec
from leaders_db.score.source_plans import (
    DEFAULT_AUTHORITY_SCORE,
    DEFAULT_SPECIFICITY_SCORE,
    INTEGRITY_PLAN,
)

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    TARGET_YEAR,
    UNDP_SOURCE_NAME,
    VDEM_SOURCE_NAME,
    WGI_SOURCE_NAME,
    add_observation,
    seed_country,
    upsert_source,
)

# ---------------------------------------------------------------------------
# (a) Direct-year observation included with locator
# ---------------------------------------------------------------------------


def test_social_wellbeing_includes_exact_year_observation_with_locator(
    database_url: str,
) -> None:
    """A direct-year UNDP HDI observation for 2023 is in the bundle."""
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        undp = upsert_source(session, source_name=UNDP_SOURCE_NAME)
        add_observation(
            session,
            source_id=undp.id,
            country_id=country.id,
            year=2023,
            variable_name="undp_hdi_hdi",
            raw_value="0.781",
            normalized_value=0.781,
            unit="index",
            source_row_reference="undp_hdi:MEX:2023:hdi",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    hdi_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "undp_hdi_hdi"
    ]
    assert len(hdi_obs) == 1
    obs = hdi_obs[0]

    assert obs.observation_year == 2023
    assert obs.target_year == 2023
    assert obs.temporal_kind is TemporalKind.DIRECT

    assert obs.source_key == "undp_hdi"
    assert obs.source_name == UNDP_SOURCE_NAME

    assert obs.source_row_reference == "undp_hdi:MEX:2023:hdi"
    assert obs.has_locator is True

    assert obs.raw_value == "0.781"
    assert obs.numeric_value == pytest.approx(0.781)
    assert obs.normalized_value == pytest.approx(0.781)
    assert obs.unit == "index"

    assert obs.direction is Direction.HIGHER_IS_BETTER

    assert obs.authority_score == DEFAULT_AUTHORITY_SCORE
    assert obs.specificity_score == DEFAULT_SPECIFICITY_SCORE


# ---------------------------------------------------------------------------
# (b) Proxy-year (2022 → 2023) selection
# ---------------------------------------------------------------------------


def test_integrity_bundle_selects_2022_as_proxy_for_2023_when_allowed(
    database_url: str,
) -> None:
    """An integrity observation for 2022 is selected as a 2023 proxy."""
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=2022,
            variable_name="wgi_control_of_corruption",
            raw_value="-0.7",
            normalized_value=None,
            unit="z_score",
            source_row_reference="wgi:MEX:2022:ControlofCorruption",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    wgi_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "wgi_control_of_corruption"
    ]
    assert len(wgi_obs) == 1
    obs = wgi_obs[0]

    assert obs.observation_year == 2022
    assert obs.target_year == 2023
    assert obs.temporal_kind is TemporalKind.PROXY

    assert obs.source_key == "wgi"
    assert obs.raw_value == "-0.7"
    assert obs.numeric_value == pytest.approx(-0.7)
    assert obs.has_locator is True


# ---------------------------------------------------------------------------
# (h) Minimum-viable-evidence property
# ---------------------------------------------------------------------------


def test_minimum_viable_evidence_is_false_with_one_source(
    database_url: str,
) -> None:
    """One source is below the plan's ``minimum_viable_sources=2`` threshold."""
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=2023,
            variable_name="wgi_control_of_corruption",
            raw_value="0.10",
            normalized_value=0.10,
            source_row_reference="wgi:MEX:2023:ControlofCorruption",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    assert INTEGRITY_PLAN.minimum_viable_sources == 2
    assert bundle.has_minimum_viable_evidence is False


def test_minimum_viable_evidence_is_true_with_two_distinct_sources(
    database_url: str,
) -> None:
    """Two distinct sources with observations meet the threshold."""
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=2023,
            variable_name="wgi_control_of_corruption",
            raw_value="0.10",
            normalized_value=0.10,
            source_row_reference="wgi:MEX:2023:ControlofCorruption",
        )
        add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.25",
            normalized_value=0.25,
            source_row_reference="vdem:MEX:2023:v2x_corr",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    distinct_sources = {obs.source_key for obs in bundle.observations}
    assert distinct_sources == {"wgi", "vdem"}
    assert bundle.has_minimum_viable_evidence is True


# ---------------------------------------------------------------------------
# (i) Error contract
# ---------------------------------------------------------------------------


def test_unsupported_category_raises_clear_value_error(
    database_url: str,
) -> None:
    """An unknown ``category_key`` raises ``ValueError`` listing the supported keys."""
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)

    with session_scope(database_url) as session:
        with pytest.raises(ValueError) as excinfo:
            build_category_evidence_bundle(
                session,
                country_iso3=COUNTRY_ISO3,
                year=TARGET_YEAR,
                category_key="totally_made_up_category",
            )
    message = str(excinfo.value)
    # Error must point the caller at every supported category and
    # the extension point (the ``category_plans`` subpackage + the
    # ``CATEGORY_SOURCE_PLANS`` registry). All 8 categories are
    # listed in the error message per the contract.
    for cat in (
        "nuclear",
        "international_peace",
        "domestic_violence",
        "political_freedom",
        "economic_wellbeing",
        "social_wellbeing",
        "integrity",
        "effectiveness",
    ):
        assert cat in message, f"error message must mention {cat!r}"
    assert "leaders_db.score.category_plans" in message
    assert "CATEGORY_SOURCE_PLANS" in message


def test_empty_category_key_raises_clear_value_error(
    database_url: str,
) -> None:
    """An empty ``category_key`` raises ``ValueError``."""
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        with pytest.raises(ValueError):
            build_category_evidence_bundle(
                session,
                country_iso3=COUNTRY_ISO3,
                year=TARGET_YEAR,
                category_key="",
            )


def test_missing_country_raises_clear_value_error(database_url: str) -> None:
    """A country that is not in the DB raises ``ValueError``."""
    init_database(database_url)
    with session_scope(database_url) as session:
        with pytest.raises(ValueError) as excinfo:
            build_category_evidence_bundle(
                session,
                country_iso3="ZZZ",
                year=TARGET_YEAR,
                category_key="integrity",
            )
    message = str(excinfo.value)
    assert "ZZZ" in message


# ---------------------------------------------------------------------------
# IndicatorSpec validation guards (the dataclass itself)
# ---------------------------------------------------------------------------


def test_indicator_spec_rejects_empty_source_key() -> None:
    """An empty-string ``source_key`` on IndicatorSpec raises ``ValueError``."""
    with pytest.raises(ValueError):
        IndicatorSpec(
            variable_name="vdem_v2x_corr",
            role=IndicatorRole.REQUIRED,
            direction=Direction.LOWER_IS_BETTER,
            source_key="",
        )


def test_indicator_spec_accepts_none_source_key() -> None:
    """A ``None`` ``source_key`` is allowed (plan-level fallback path)."""
    spec = IndicatorSpec(
        variable_name="vdem_v2x_corr",
        role=IndicatorRole.REQUIRED,
        direction=Direction.LOWER_IS_BETTER,
    )
    assert spec.source_key is None
