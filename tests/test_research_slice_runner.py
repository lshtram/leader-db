from __future__ import annotations

import json

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


def test_structured_country_year_question_runs_through_fact_builder(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_country_year_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="gdp_per_capita_nominal_current_usd",
        selected_value_number=76399.0,
    )

    result = run_slice_1_question_year(
        request=Slice1Request(question_id="5.1", year=2023),
        country_scope={"USA": _scope("USA", "United States")},
        evidence_repository=InMemoryEvidenceRepository(observations=()),
        results_bind=engine,
    )

    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()

    assert result.status == "completed"
    assert result.answer_count == 1
    assert result.persisted_count == 1
    assert answer["question_id"] == "5.1"
    assert answer["answer_numeric"] == 76399.0
    assert answer["coverage_status"] == "direct"
    assert link["source_slug"] == "world_bank_wdi"


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


def _insert_country_year(
    engine: object,
    *,
    country_id: int,
    iso3: str,
    name: str,
    year: int,
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO countries (id, iso3, country_name, country_name_normalized)
                VALUES (:country_id, :iso3, :name, :normalized_name)
                """
            ),
            {
                "country_id": country_id,
                "iso3": iso3,
                "name": name,
                "normalized_name": name.lower(),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO country_years (id, country_id, year, included_in_project)
                VALUES (:country_year_id, :country_id, :year, 1)
                """
            ),
            {"country_year_id": country_id, "country_id": country_id, "year": year},
        )


def _insert_country_year_fact(
    engine: object,
    *,
    country_id: int,
    country_year_id: int,
    year: int,
    field_key: str,
    selected_value_number: float,
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_year_id, country_id, year, field_key, field_label, value_type,
                    selected_value_number, selected_value_json, candidate_values_json,
                    selection_rule,
                    adjudication_status, confidence_score, quality_signals_json,
                    warnings_json, rationale, recommended_next_action,
                    source_slugs_json, source_observation_ids_json, producer,
                    method_version
                ) VALUES (
                    :country_year_id, :country_id, :year, :field_key, :field_label,
                    'number', :selected_value_number, :selected_value_json,
                    :candidate_values_json, 'test_rule', 'selected', 92, '{}', '[]',
                    'Selected fixture fact.', 'none',
                    :source_slugs_json, :source_observation_ids_json, 'test', 'test_v1'
                )
                """
            ),
            {
                "country_year_id": country_year_id,
                "country_id": country_id,
                "year": year,
                "field_key": field_key,
                "field_label": field_key.replace("_", " ").title(),
                "selected_value_number": selected_value_number,
                "selected_value_json": json.dumps(
                    _fact_candidate_payload(selected_value_number)
                ),
                "candidate_values_json": json.dumps(
                    (_fact_candidate_payload(selected_value_number),)
                ),
                "source_slugs_json": json.dumps(("world_bank_wdi",)),
                "source_observation_ids_json": json.dumps(
                    ("wdi:USA:2023:gdp_per_capita_nominal_current_usd",)
                ),
            },
        )


def _fact_candidate_payload(value: float) -> dict[str, object]:
    return {
        "concept_key": "fixture",
        "source_slug": "world_bank_wdi",
        "value": value,
        "value_type": "numeric",
        "unit": None,
        "scale": None,
        "source_version": "fixture",
        "source_indicator_codes": ["fixture_indicator"],
        "input_observation_ids": ["wdi:USA:2023:gdp_per_capita_nominal_current_usd"],
        "mapping_type": "direct",
        "quality_flags": [],
        "warnings": [],
    }
