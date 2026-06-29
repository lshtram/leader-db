from __future__ import annotations

import json

from sqlalchemy import create_engine, inspect, text

from leaders_db.db.engine import init_database
from leaders_db.research.question_2_1 import Question21AnswerRow
from leaders_db.research.results_store import Q2_1_METHOD_VERSION, persist_q2_1_answers


def test_research_results_migration_creates_tables(database_url: str) -> None:
    init_database(database_url)

    inspector = inspect(create_engine(database_url))
    tables = set(inspector.get_table_names())

    assert {
        "research_questions",
        "research_question_answers",
        "research_answer_evidence_links",
        "chapter_scores",
    }.issubset(tables)
    answer_columns = {c["name"] for c in inspector.get_columns("research_question_answers")}
    assert {
        "question_id",
        "year",
        "iso3",
        "answer_boolean",
        "coverage_status",
        "evidence_year",
        "warning_codes_json",
        "caveats_json",
    }.issubset(answer_columns)


def test_persist_q2_1_rows_inserts_metadata_answers_and_evidence(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    persist_q2_1_answers(engine, [_row()])

    with engine.connect() as conn:
        question = conn.execute(text("SELECT * FROM research_questions")).mappings().one()
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        links = conn.execute(
            text("SELECT * FROM research_answer_evidence_links ORDER BY source_observation_id")
        ).mappings().all()

    assert question["question_id"] == "2.1"
    assert question["chapter_id"] == "2"
    assert question["answer_type"] == "boolean"
    assert question["method_version"] == Q2_1_METHOD_VERSION
    assert answer["question_id"] == "2.1"
    assert answer["year"] == 2022
    assert answer["iso3"] == "USA"
    assert answer["ruler_name"] == "Joe Example"
    assert answer["answer_boolean"] == 1
    assert answer["coverage_status"] == "direct"
    assert answer["evidence_year"] == 2022
    assert json.loads(answer["warning_codes_json"]) == ["fixture_warning"]
    assert json.loads(answer["caveats_json"]) == ["fixture caveat"]
    assert json.loads(answer["answer_json"]) == {
        "ruler_source": "fixture",
        "state_based_events": 1.0,
        "state_based_fatalities": 0.0,
    }
    assert [link["source_observation_id"] for link in links] == [
        "ucdp:USA:2022:ucdp_state_based_events",
        "ucdp:USA:2022:ucdp_state_based_fatalities",
    ]
    assert {link["source_slug"] for link in links} == {"ucdp"}
    assert {link["evidence_role"] for link in links} == {"primary"}


def test_persist_q2_1_rerun_updates_answer_and_refreshes_links(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    persist_q2_1_answers(engine, [_row(answer=True)])

    persist_q2_1_answers(
        engine,
        [
            _row(
                answer=False,
                events=0.0,
                fatalities=0.0,
                observation_ids=("ucdp:USA:2022:ucdp_state_based_events",),
                warnings=(),
                caveats=("updated caveat",),
            )
        ],
    )

    with engine.connect() as conn:
        answer_count = conn.execute(
            text("SELECT COUNT(*) FROM research_question_answers")
        ).scalar_one()
        link_count = conn.execute(
            text("SELECT COUNT(*) FROM research_answer_evidence_links")
        ).scalar_one()
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()

    assert answer_count == 1
    assert link_count == 1
    assert answer["answer_boolean"] == 0
    assert json.loads(answer["warning_codes_json"]) == []
    assert json.loads(answer["caveats_json"]) == ["updated caveat"]
    assert link["source_observation_id"] == "ucdp:USA:2022:ucdp_state_based_events"


def test_persisted_rows_are_queryable_by_question_and_year(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    persist_q2_1_answers(engine, [_row(), _row(iso3="CAN", country_name="Canada")])

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT iso3, country_name, answer_boolean, coverage_status
                FROM research_question_answers
                WHERE question_id = :question_id AND year = :year
                ORDER BY iso3
                """
            ),
            {"question_id": "2.1", "year": 2022},
        ).mappings().all()

    assert [dict(row) for row in rows] == [
        {
            "iso3": "CAN",
            "country_name": "Canada",
            "answer_boolean": 1,
            "coverage_status": "direct",
        },
        {
            "iso3": "USA",
            "country_name": "United States",
            "answer_boolean": 1,
            "coverage_status": "direct",
        },
    ]


def _row(
    *,
    iso3: str = "USA",
    country_name: str = "United States",
    answer: bool | None = True,
    events: float | None = 1.0,
    fatalities: float | None = 0.0,
    observation_ids: tuple[str, ...] = (
        "ucdp:USA:2022:ucdp_state_based_events",
        "ucdp:USA:2022:ucdp_state_based_fatalities",
    ),
    warnings: tuple[str, ...] = ("fixture_warning",),
    caveats: tuple[str, ...] = ("fixture caveat",),
) -> Question21AnswerRow:
    return Question21AnswerRow(
        question_id="2.1",
        year=2022,
        iso3=iso3,
        country_name=country_name,
        ruler_name="Joe Example",
        ruler_source="fixture",
        answer=answer,
        state_based_events=events,
        state_based_fatalities=fatalities,
        evidence_year=2022,
        coverage_status="direct",
        source_observation_ids=observation_ids,
        warning_codes=warnings,
        caveats=caveats,
    )
