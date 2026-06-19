"""Missingness + wrong-source tests for the Stage 5 evidence-bundle builder.

Coverage pinned here:

- (c) Owning-source rule: wrong-source rows silently dropped
      (WGI-as-VDem-owner regression) — pin at bundle layer and
      :func:`collect_indicator_observations` helper layer.
- (d) ``SOURCE_NOT_IMPLEMENTED`` vs ``TARGET_YEAR_ABSENT`` reasons.
- (e) Partial-source registration splits the reasons correctly.
- (f) Client 2023 matrix source is never used as evidence.
- REQUIRED indicators land in ``primary_missing_observations``
  with ``PRIMARY`` severity.

Shared fixtures in :mod:`tests._resolve_indicators_factories`.
Tie-breaker tests in :mod:`tests.test_resolve_indicators_builder_selection`.
"""

from __future__ import annotations

from sqlalchemy import select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country, Source
from leaders_db.db.session import session_scope
from leaders_db.resolve.indicators import build_category_evidence_bundle
from leaders_db.resolve.indicators_collection import collect_indicator_observations
from leaders_db.score.evidence import MissingReason, MissingSeverity
from leaders_db.score.source_plans import INTEGRITY_PLAN, SOCIAL_WELLBEING_PLAN

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    CPI_SOURCE_NAME,
    TARGET_YEAR,
    UNDP_SOURCE_NAME,
    VDEM_SOURCE_NAME,
    WDI_SOURCE_NAME,
    WGI_SOURCE_NAME,
    WHO_SOURCE_NAME,
    add_observation,
    seed_country,
    upsert_source,
)


def _source_id_for(database_url: str, source_name: str) -> int:
    """Return the :class:`Source` row id for ``source_name``."""
    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.source_name == source_name)
        ).scalar_one()
        return int(row.id)


# --- (c) Owning-source rule: wrong-source row is silently dropped ---


def test_wrong_source_row_is_dropped_and_indicator_reported_missing(
    database_url: str,
) -> None:
    """A non-owning source's row for ``vdem_v2x_corr`` is silently dropped.

    Regression fix: the WGI row is dropped; ``vdem_v2x_corr`` is
    reported missing with ``TARGET_YEAR_ABSENT``.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)
        # Cross-source contamination: WGI row for V-Dem-owned var.
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.20",
            normalized_value=0.20,
            source_row_reference="wgi:MEX:2023:v2x_corr",
        )
        # WGI does own its own variable — that one must surface.
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
        _ = vdem  # registered but no row yet

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    cross_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "vdem_v2x_corr"
    ]
    assert cross_obs == []

    vdem_missing = [
        m
        for m in bundle.missing
        if m.variable_name == "vdem_v2x_corr"
    ]
    assert len(vdem_missing) == 1
    assert vdem_missing[0].source_key == "vdem"
    assert vdem_missing[0].reason is MissingReason.TARGET_YEAR_ABSENT

    wgi_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "wgi_control_of_corruption"
    ]
    assert len(wgi_obs) == 1
    assert wgi_obs[0].source_key == "wgi"


def test_wrong_source_row_is_dropped_via_collect_helper(
    database_url: str,
) -> None:
    """``collect_indicator_observations`` ignores non-owning rows.

    Pins the contract at the helper layer.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        upsert_source(session, source_name=VDEM_SOURCE_NAME)
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.20",
            normalized_value=0.20,
            source_row_reference="wgi:MEX:2023:v2x_corr",
        )

    plan = INTEGRITY_PLAN
    spec = next(
        s for s in plan.expected_indicators if s.variable_name == "vdem_v2x_corr"
    )
    source_ids = {
        "wgi": _source_id_for(database_url, WGI_SOURCE_NAME),
        "vdem": _source_id_for(database_url, VDEM_SOURCE_NAME),
    }

    observations: list = []
    missing: list = []
    with session_scope(database_url) as session:
        country_row = session.execute(
            select(Country).where(Country.iso3 == COUNTRY_ISO3)
        ).scalar_one()
        collect_indicator_observations(
            session,
            country=country_row,
            target_year=TARGET_YEAR,
            spec=spec,
            plan=plan,
            expected_source_ids=source_ids,
            observations=observations,
            missing=missing,
        )

    assert observations == []
    assert len(missing) == 1
    assert missing[0].source_key == "vdem"
    assert missing[0].reason is MissingReason.TARGET_YEAR_ABSENT


# --- (d) Missingness reasons: SOURCE_NOT_IMPLEMENTED vs TARGET_YEAR_ABSENT ---


def test_missing_source_not_implemented_when_owning_source_absent(
    database_url: str,
) -> None:
    """Owning source not registered → ``SOURCE_NOT_IMPLEMENTED``.

    Register WGI only; V-Dem and TI CPI are absent. Indicators
    owned by an absent source carry ``SOURCE_NOT_IMPLEMENTED``;
    indicators owned by the registered source carry
    ``TARGET_YEAR_ABSENT``.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        upsert_source(session, source_name=WGI_SOURCE_NAME)

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    absent_owners = {"vdem", "ti_cpi"}
    for missing in bundle.missing:
        if missing.source_key in absent_owners:
            assert missing.reason is MissingReason.SOURCE_NOT_IMPLEMENTED
        elif missing.source_key == "wgi":
            assert missing.reason is MissingReason.TARGET_YEAR_ABSENT
        else:  # pragma: no cover — defensive: catches contract drift
            raise AssertionError(
                f"unexpected source_key on missing: {missing.source_key!r}"
            )

    assert {m.variable_name for m in bundle.missing} == set(
        INTEGRITY_PLAN.expected_variables
    )


def test_missing_target_year_absent_when_owning_source_registered_no_row(
    database_url: str,
) -> None:
    """All expected sources registered, no observations → TARGET_YEAR_ABSENT."""
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        # Register every expected source but no observations.
        for name in (
            UNDP_SOURCE_NAME,
            WGI_SOURCE_NAME,
            WDI_SOURCE_NAME,
            VDEM_SOURCE_NAME,
            WHO_SOURCE_NAME,
            CPI_SOURCE_NAME,
        ):
            upsert_source(session, source_name=name)

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    assert bundle.available_count == 0
    reasons = {m.reason for m in bundle.missing}
    assert reasons == {MissingReason.TARGET_YEAR_ABSENT}


# --- (e) Partial-source registration: only UNDP registered for social_wellbeing ---


def test_partial_source_registration_splits_missing_reasons(
    database_url: str,
) -> None:
    """Only UNDP registered → UNDP vars TARGET_YEAR_ABSENT, others SOURCE_NOT_IMPLEMENTED.

    The review's exact scenario: only UNDP is in the DB.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        upsert_source(session, source_name=UNDP_SOURCE_NAME)

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    by_reason: dict[MissingReason, list[str]] = {}
    for m in bundle.missing:
        by_reason.setdefault(m.reason, []).append(m.variable_name)

    undp_owned = {
        "undp_hdi_hdi",
        "undp_hdi_life_expectancy",
        "undp_hdi_expected_years_schooling",
        "undp_hdi_mean_years_schooling",
        "undp_hdi_gni_per_capita",
    }
    assert set(by_reason.get(MissingReason.TARGET_YEAR_ABSENT, [])) == undp_owned
    absent_owned = undp_owned ^ set(SOCIAL_WELLBEING_PLAN.expected_variables)
    assert (
        set(by_reason.get(MissingReason.SOURCE_NOT_IMPLEMENTED, []))
        == absent_owned
    )

    # Every MissingObservation.source_key matches its variable's
    # owning source (not a generic primary source).
    spec_by_var = {
        s.variable_name: s for s in SOCIAL_WELLBEING_PLAN.expected_indicators
    }
    for m in bundle.missing:
        assert m.source_key == spec_by_var[m.variable_name].source_key


# --- (f) Client 2023 matrix source is never used as evidence ---


def test_client_source_is_ignored_even_when_variable_matches(
    database_url: str,
) -> None:
    """A ``client_existing`` row is never used as evidence.

    Bundle must include the WGI observation and must **not**
    include the client row.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        client = upsert_source(
            session,
            source_name="client_existing_2023_matrix (test)",
        )
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        # The client row tries to claim the WGI-owned variable.
        add_observation(
            session,
            source_id=client.id,
            country_id=country.id,
            year=2023,
            variable_name="wgi_control_of_corruption",
            raw_value="9",
            normalized_value=0.9,
            source_row_reference="client:MEX:2023:wgi",
        )
        # WGI's real variable (control of corruption) for 2023.
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

    for obs in bundle.observations:
        assert "client" not in obs.source_key
        assert obs.source_row_reference is None or (
            "client:" not in obs.source_row_reference
        )
    wgi_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "wgi_control_of_corruption"
    ]
    assert len(wgi_obs) == 1
    assert wgi_obs[0].source_key == "wgi"


# --- Required indicator severity surfaces in primary_missing_observations ---


def test_primary_missing_observations_surfaces_required_variable(
    database_url: str,
) -> None:
    """REQUIRED indicators missing in the bundle land in ``primary_missing_observations``."""
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_country(session)
        # Register UNDP but add no observations → hdi REQUIRED
        # indicator must surface with PRIMARY severity.
        upsert_source(session, source_name=UNDP_SOURCE_NAME)

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="social_wellbeing",
        )

    hdi_missing = [
        m for m in bundle.missing if m.variable_name == "undp_hdi_hdi"
    ]
    assert len(hdi_missing) == 1
    assert hdi_missing[0].severity is MissingSeverity.PRIMARY
    assert hdi_missing[0] in bundle.primary_missing_observations
    # The owning source key is the indicator's owning source, not
    # a generic primary source.
    assert hdi_missing[0].source_key == "undp_hdi"
