from __future__ import annotations

from sqlalchemy import create_engine, text

from leaders_db.chronicle.country_scope import CountryScopeEntry
from leaders_db.db.engine import init_database
from leaders_db.research.slice_runner import Slice1Request, run_slice_1_question_year
from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceId,
    TransformLocator,
)
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_q2_1_slice_1_all_countries_persists_one_row_per_scope_entry(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    result = run_slice_1_question_year(
        request=Slice1Request(question_id="2.1", year=2022),
        country_scope={
            "CAN": _scope("CAN", "Canada"),
            "FRA": _scope("FRA", "France"),
            "USA": _scope("USA", "United States"),
        },
        evidence_repository=InMemoryEvidenceRepository(
            observations=(
                _ucdp_observation("CAN", 2022, "ucdp_state_based_events", 0),
                _ucdp_observation("CAN", 2022, "ucdp_state_based_fatalities", 0),
                _ucdp_observation("USA", 2022, "ucdp_state_based_events", 1),
                _ucdp_observation("USA", 2022, "ucdp_state_based_fatalities", 3),
            )
        ),
        results_bind=engine,
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT iso3, answer_boolean, coverage_status
                FROM research_question_answers
                WHERE question_id = '2.1' AND year = 2022
                ORDER BY iso3
                """
            )
        ).mappings().all()

    assert result.status == "completed"
    assert result.answer_count == 3
    assert result.persisted_count == 3
    assert [dict(row) for row in rows] == [
        {"iso3": "CAN", "answer_boolean": 0, "coverage_status": "direct"},
        {"iso3": "FRA", "answer_boolean": None, "coverage_status": "missing"},
        {"iso3": "USA", "answer_boolean": 1, "coverage_status": "direct"},
    ]


def test_q2_1_runner_reuses_same_surface_for_direct_and_proxy_years(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    scope = {"UKR": _scope("UKR", "Ukraine")}
    repository = InMemoryEvidenceRepository(
        observations=(
            _ucdp_observation("UKR", 2022, "ucdp_state_based_events", 0),
            _ucdp_observation("UKR", 2022, "ucdp_state_based_fatalities", 0),
        )
    )

    direct = run_slice_1_question_year(
        request=Slice1Request(question_id="2.1", year=2022),
        country_scope=scope,
        evidence_repository=repository,
        results_bind=engine,
    )
    proxy = run_slice_1_question_year(
        request=Slice1Request(question_id="2.1", year=2023, proxy_year=2022),
        country_scope=scope,
        evidence_repository=repository,
        results_bind=engine,
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT year, evidence_year, coverage_status
                FROM research_question_answers
                WHERE question_id = '2.1'
                ORDER BY year
                """
            )
        ).mappings().all()

    assert direct.answer_count == 1
    assert proxy.answer_count == 1
    assert [dict(row) for row in rows] == [
        {"year": 2022, "evidence_year": 2022, "coverage_status": "direct"},
        {"year": 2023, "evidence_year": 2022, "coverage_status": "proxy"},
    ]


def test_country_subset_selection_limits_handler_and_persistence(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    result = run_slice_1_question_year(
        request=Slice1Request(question_id="2.1", year=2022, countries=("USA", "CAN")),
        country_scope={
            "CAN": _scope("CAN", "Canada"),
            "FRA": _scope("FRA", "France"),
            "USA": _scope("USA", "United States"),
        },
        evidence_repository=InMemoryEvidenceRepository(
            observations=(
                _ucdp_observation("CAN", 2022, "ucdp_state_based_events", 0),
                _ucdp_observation("CAN", 2022, "ucdp_state_based_fatalities", 0),
                _ucdp_observation("FRA", 2022, "ucdp_state_based_events", 9),
                _ucdp_observation("FRA", 2022, "ucdp_state_based_fatalities", 9),
                _ucdp_observation("USA", 2022, "ucdp_state_based_events", 1),
                _ucdp_observation("USA", 2022, "ucdp_state_based_fatalities", 0),
            )
        ),
        results_bind=engine,
    )

    with engine.connect() as conn:
        iso3s = conn.execute(
            text("SELECT iso3 FROM research_question_answers ORDER BY iso3")
        ).scalars().all()

    assert result.answer_count == 2
    assert iso3s == ["CAN", "USA"]


def test_unsupported_question_returns_infrastructure_gaps_without_throwing() -> None:
    result = run_slice_1_question_year(
        request=Slice1Request(question_id="9.9", year=2022),
        country_scope={"USA": _scope("USA", "United States")},
        evidence_repository=InMemoryEvidenceRepository(observations=()),
        results_bind=None,
    )

    assert result.status == "blocked"
    assert result.answer_count == 0
    assert result.persisted_count == 0
    assert result.infrastructure_gaps == (
        "missing_question_registry_entry",
        "unsupported_question_handler",
    )


def test_q2_1_runner_rerun_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    kwargs = {
        "request": Slice1Request(question_id="2.1", year=2022),
        "country_scope": {"USA": _scope("USA", "United States")},
        "evidence_repository": InMemoryEvidenceRepository(
            observations=(
                _ucdp_observation("USA", 2022, "ucdp_state_based_events", 1),
                _ucdp_observation("USA", 2022, "ucdp_state_based_fatalities", 0),
            )
        ),
        "results_bind": engine,
    }

    first = run_slice_1_question_year(**kwargs)
    second = run_slice_1_question_year(**kwargs)

    with engine.connect() as conn:
        answer_count = conn.execute(
            text("SELECT COUNT(*) FROM research_question_answers")
        ).scalar_one()
        link_count = conn.execute(
            text("SELECT COUNT(*) FROM research_answer_evidence_links")
        ).scalar_one()

    assert first.persisted_count == 1
    assert second.persisted_count == 1
    assert answer_count == 1
    assert link_count == 2


def _scope(iso3: str, country_name: str) -> CountryScopeEntry:
    return CountryScopeEntry(
        iso3=iso3,
        country_name=country_name,
        start_year=1900,
        end_year=None,
        source="fixture",
    )


def _ucdp_observation(
    iso3: str,
    year: int,
    indicator_code: str,
    value: int,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug="ucdp"),
        observation_id=f"ucdp:{iso3}:{year}:{indicator_code}",
        observation_family="international_peace_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
        year=year,
        country_code=iso3,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit="count",
        scale=None,
        source_version="GED 23.1",
        raw_locator=RawLocator(asset_id="ucdp:fixture"),
        transform_locator=TransformLocator(transform_name="fixture"),
    )
