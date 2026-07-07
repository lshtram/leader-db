from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.facts import publish_concept_country_year_facts
from leaders_db.research.country_year_fact_answers import (
    COUNTRY_YEAR_FACTS_METHOD_VERSION,
    MISSING_FACT_WARNING,
    PARTIAL_FACT_WARNING,
    build_country_year_fact_answers,
)
from leaders_db.research.results_store import ResearchQuestionMetadata, persist_research_answers
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator


def test_build_country_year_fact_answers_emits_direct_numeric_and_missing_rows(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_country_year(engine, country_id=2, iso3="CAN", name="Canada", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="gdp_per_capita",
        value_type="number",
        selected_value_number=76399.0,
        source_slugs=("world_bank_wdi",),
        source_observation_ids=("wdi:USA:2023:gdp_per_capita",),
        confidence_score=92,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="5.1",
        year=2023,
        country_scope={
            "CAN": {"country_name": "Canada", "start_year": 1950, "end_year": None},
            "USA": {"country_name": "United States", "start_year": 1950, "end_year": None},
        },
    )

    assert [(row.iso3, row.coverage_status) for row in rows] == [
        ("CAN", "missing"),
        ("USA", "direct"),
    ]
    missing, direct = rows
    assert missing.warning_codes == (MISSING_FACT_WARNING,)
    assert direct.answer_numeric == 76399.0
    assert direct.confidence_score == 0.92
    assert direct.evidence_links[0].source_slug == "world_bank_wdi"
    assert direct.evidence_links[0].source_observation_id == "wdi:USA:2023:gdp_per_capita"


def test_build_country_year_fact_answers_bundles_multi_concept_questions(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="nuclear_military_stockpile",
        value_type="number",
        selected_value_number=3708.0,
        source_slugs=("fas",),
        source_observation_ids=("fas:USA:2023:stockpile",),
        confidence_score=80,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="nuclear_reserve_nondeployed",
        value_type="number",
        selected_value_number=1938.0,
        source_slugs=("fas",),
        source_observation_ids=("fas:USA:2023:reserve",),
        confidence_score=70,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="1.7",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.answer_numeric is None
    assert row.coverage_status == "direct"
    assert row.confidence_score == 0.75
    assert [fact["field_key"] for fact in row.answer_json["facts"]] == [
        "nuclear_military_stockpile",
        "nuclear_reserve_nondeployed",
    ]
    assert row.answer_json["stockpile_warheads"] == 3708.0
    assert row.answer_json["reserve_nondeployed_warheads"] == 1938.0
    assert row.answer_json["stockpile_plus_reserve_warheads"] == 5646.0
    assert row.answer_json["stockpile_share_of_stockpile_plus_reserve"] == 3708.0 / 5646.0
    assert row.answer_text == "military stockpile: 3708; reserve/nondeployed: 1938"
    assert {link.source_observation_id for link in row.evidence_links} == {
        "fas:USA:2023:stockpile",
        "fas:USA:2023:reserve",
    }


def test_build_country_year_fact_answers_marks_partial_multi_concept_questions(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="nuclear_military_stockpile",
        value_type="number",
        selected_value_number=3708.0,
        source_slugs=("fas",),
        source_observation_ids=("fas:USA:2023:stockpile",),
        confidence_score=80,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="1.7",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.coverage_status == "partial"
    assert PARTIAL_FACT_WARNING in row.warning_codes
    assert row.answer_json["missing_field_keys"] == ("nuclear_reserve_nondeployed",)
    assert row.answer_json["stockpile_warheads"] == 3708.0
    assert row.answer_json["reserve_nondeployed_warheads"] is None
    assert row.answer_text == "military stockpile: 3708"


def test_build_country_year_fact_answers_shapes_internationalized_conflict_boolean(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_country_year(engine, country_id=2, iso3="CAN", name="Canada", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="internationalized_conflict_events",
        value_type="number",
        selected_value_number=3.0,
        source_slugs=("ucdp",),
        source_observation_ids=("ucdp:USA:2023:internationalized_conflict",),
        confidence_score=86,
    )
    _insert_fact(
        engine,
        country_id=2,
        country_year_id=2,
        year=2023,
        field_key="internationalized_conflict_events",
        value_type="number",
        selected_value_number=0.0,
        source_slugs=("ucdp",),
        source_observation_ids=("ucdp:CAN:2023:internationalized_conflict",),
        confidence_score=86,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="2.2",
        year=2023,
        country_scope={
            "CAN": {"country_name": "Canada"},
            "USA": {"country_name": "United States"},
        },
    )

    can, usa = rows
    assert can.answer_boolean is False
    assert can.answer_json["internationalized_conflict_events"] == 0.0
    assert can.answer_text == "internationalized conflict events: 0"
    assert usa.answer_boolean is True
    assert usa.answer_json["internationalized_conflict_events"] == 3.0
    assert usa.answer_text == "internationalized conflict events: 3"


def test_build_country_year_fact_answers_shapes_nuclear_possession_boolean(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_country_year(engine, country_id=2, iso3="CAN", name="Canada", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="nuclear_total_inventory",
        value_type="number",
        selected_value_number=5244.0,
        source_slugs=("fas",),
        source_observation_ids=("fas:USA:2023:total_inventory",),
        confidence_score=80,
    )
    _insert_fact(
        engine,
        country_id=2,
        country_year_id=2,
        year=2023,
        field_key="nuclear_total_inventory",
        value_type="number",
        selected_value_number=0.0,
        source_slugs=("fas",),
        source_observation_ids=("fas:CAN:2023:total_inventory",),
        confidence_score=80,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="1.1",
        year=2023,
        country_scope={
            "CAN": {"country_name": "Canada"},
            "USA": {"country_name": "United States"},
        },
    )

    can, usa = rows
    assert can.answer_boolean is False
    assert can.answer_json["nuclear_total_inventory"] == 0.0
    assert can.answer_text == "nuclear total inventory: 0"
    assert usa.answer_boolean is True
    assert usa.answer_json["nuclear_total_inventory"] == 5244.0
    assert usa.answer_text == "nuclear total inventory: 5244"


def test_build_country_year_fact_answers_shapes_military_spending_scale(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="military_spend_constant_usd",
        value_type="number",
        selected_value_number=916_000.0,
        source_slugs=("sipri_milex",),
        source_observation_ids=("sipri_milex:USA:2023:constant_usd",),
        confidence_score=80,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="military_spend_per_capita",
        value_type="number",
        selected_value_number=2700.0,
        source_slugs=("sipri_milex",),
        source_observation_ids=("sipri_milex:USA:2023:per_capita",),
        confidence_score=80,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="2.6",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    row = rows[0]
    assert row.coverage_status == "direct"
    assert row.answer_numeric is None
    assert row.answer_json["military_spend_constant_usd"] == 916_000.0
    assert row.answer_json["military_spend_per_capita"] == 2700.0
    assert row.answer_text == "constant USD: 916000; per capita: 2700"


def test_build_country_year_fact_answers_keeps_partial_military_spending_scale_json_only(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="military_spend_constant_usd",
        value_type="number",
        selected_value_number=916_000.0,
        source_slugs=("sipri_milex",),
        source_observation_ids=("sipri_milex:USA:2023:constant_usd",),
        confidence_score=80,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="2.6",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    row = rows[0]
    assert row.coverage_status == "partial"
    assert PARTIAL_FACT_WARNING in row.warning_codes
    assert row.answer_numeric is None
    assert row.answer_json["missing_field_keys"] == ("military_spend_per_capita",)
    assert row.answer_json["military_spend_constant_usd"] == 916_000.0
    assert row.answer_json["military_spend_per_capita"] is None
    assert row.answer_text == "constant USD: 916000"


def test_build_country_year_fact_answers_preserves_per_observation_source_slugs(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="public_power_private_gain",
        value_type="number",
        selected_value_number=74.0,
        source_slugs=("world_bank_wgi", "transparency_cpi"),
        source_observation_ids=("wgi:USA:2023:cc", "cpi:USA:2023:score"),
        confidence_score=90,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="7.1",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert {
        (link.source_slug, link.source_observation_id) for link in rows[0].evidence_links
    } == {
        ("world_bank_wgi", "wgi:USA:2023:cc"),
        ("transparency_cpi", "cpi:USA:2023:score"),
    }


def test_build_country_year_fact_answers_shapes_single_fact_evidence_bundle(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="public_power_private_gain",
        value_type="number",
        selected_value_number=74.0,
        source_slugs=("world_bank_wgi",),
        source_observation_ids=("wgi:USA:2023:cc",),
        confidence_score=90,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="7.1",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    row = rows[0]
    assert row.coverage_status == "direct"
    assert row.answer_numeric is None
    assert row.answer_json["public_power_private_gain"] == 74.0
    assert row.answer_text == "Public Power Private Gain: 74"


def test_build_country_year_fact_answers_shapes_categorical_question_fields(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="regime_classification_cross_source",
        value_type="categorical",
        selected_value_number=None,
        selected_value_text="consistent_democracy",
        source_slugs=("vdem",),
        source_observation_ids=("vdem:USA:2023:regime",),
        confidence_score=88,
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="4.10",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    row = rows[0]
    assert row.coverage_status == "direct"
    assert row.answer_numeric is None
    assert row.answer_json["regime_classification_cross_source"] == "consistent_democracy"
    assert row.answer_text == "Regime Classification Cross Source: consistent_democracy"


def test_build_country_year_fact_answers_reads_production_published_number_facts(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    write_observations(
        engine,
        (
            NormalizedObservation(
                source_id=SourceId(slug="world_bank_wdi"),
                observation_id="wdi:USA:2023:gdp_per_capita",
                observation_family="economic_wellbeing_country_year",
                indicator_code="wdi_gdp_per_capita",
                value=76399.0,
                value_type="numeric",
                year=2023,
                country_code="USA",
                country_name="United States",
                leader_id=None,
                leader_name=None,
                unit="current_usd",
                scale=None,
                source_version="fixture",
                raw_locator=RawLocator(asset_id="wdi:fixture"),
                transform_locator=TransformLocator(transform_name="fixture"),
            ),
        ),
    )
    publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=("gdp_per_capita",),
        run_id="test-run",
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="5.1",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert len(rows) == 1
    assert rows[0].answer_numeric == 76399.0
    assert rows[0].coverage_status == "direct"


def test_build_country_year_fact_answers_shapes_production_internationalized_conflict_fact(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    write_observations(
        engine,
        (
            NormalizedObservation(
                source_id=SourceId(slug="ucdp"),
                observation_id="ucdp:USA:2023:intl_events",
                observation_family="international_peace_country_year",
                indicator_code="ucdp_intl_events",
                value=3.0,
                value_type="numeric",
                year=2023,
                country_code=None,
                country_name="United States of America",
                leader_id=None,
                leader_name=None,
                unit="events",
                scale=None,
                source_version="fixture",
                raw_locator=RawLocator(asset_id="ucdp:fixture"),
                transform_locator=TransformLocator(transform_name="fixture"),
            ),
        ),
    )
    publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=("internationalized_conflict_events",),
        run_id="test-run",
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="2.2",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert len(rows) == 1
    assert rows[0].coverage_status == "direct"
    assert rows[0].answer_boolean is True
    assert rows[0].answer_json["internationalized_conflict_events"] == 3.0
    assert rows[0].answer_text == "internationalized conflict events: 3"
    assert rows[0].evidence_links[0].source_slug == "ucdp"


def test_build_country_year_fact_answers_shapes_production_nuclear_inventory_fact(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    write_observations(
        engine,
        (
            NormalizedObservation(
                source_id=SourceId(slug="fas"),
                observation_id="fas:USA:2023:total_inventory",
                observation_family="nuclear_country_year",
                indicator_code="fas_total_inventory",
                value=5244.0,
                value_type="numeric",
                year=2023,
                country_code="USA",
                country_name="United States",
                leader_id=None,
                leader_name=None,
                unit="warheads",
                scale=None,
                source_version="fixture",
                raw_locator=RawLocator(asset_id="fas:fixture"),
                transform_locator=TransformLocator(transform_name="fixture"),
            ),
        ),
    )
    publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=("nuclear_total_inventory",),
        run_id="test-run",
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="1.1",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    assert len(rows) == 1
    assert rows[0].coverage_status == "direct"
    assert rows[0].answer_boolean is True
    assert rows[0].answer_json["nuclear_total_inventory"] == 5244.0
    assert rows[0].answer_text == "nuclear total inventory: 5244"
    assert rows[0].evidence_links[0].source_slug == "fas"


def test_build_country_year_fact_answers_shapes_production_military_spending_scale(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(
        engine,
        country_id=1,
        iso3="USA",
        name="United States of America",
        year=2023,
    )
    write_observations(
        engine,
        (
            NormalizedObservation(
                source_id=SourceId(slug="sipri_milex"),
                observation_id="sipri_milex:USA:2023:constant_usd",
                observation_family="international_peace_country_year",
                indicator_code="sipri_milex_constant_usd",
                value=916_000.0,
                value_type="numeric",
                year=2023,
                country_code=None,
                country_name="United States of America",
                leader_id=None,
                leader_name=None,
                unit="usd_millions_constant_2022",
                scale=None,
                source_version="fixture",
                raw_locator=RawLocator(asset_id="sipri_milex:fixture"),
                transform_locator=TransformLocator(transform_name="fixture"),
            ),
            NormalizedObservation(
                source_id=SourceId(slug="sipri_milex"),
                observation_id="sipri_milex:USA:2023:per_capita",
                observation_family="international_peace_country_year",
                indicator_code="sipri_milex_per_capita",
                value=2700.0,
                value_type="numeric",
                year=2023,
                country_code=None,
                country_name="United States of America",
                leader_id=None,
                leader_name=None,
                unit="usd_per_capita",
                scale=None,
                source_version="fixture",
                raw_locator=RawLocator(asset_id="sipri_milex:fixture"),
                transform_locator=TransformLocator(transform_name="fixture"),
            ),
        ),
    )
    publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=("military_spend_constant_usd", "military_spend_per_capita"),
        run_id="test-run",
    )

    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="2.6",
        year=2023,
        country_scope={"USA": {"country_name": "United States of America"}},
    )

    assert len(rows) == 1
    assert rows[0].coverage_status == "direct"
    assert rows[0].answer_json["military_spend_constant_usd"] == 916_000.0
    assert rows[0].answer_json["military_spend_per_capita"] == 2700.0
    assert rows[0].answer_text == "constant USD: 916000; per capita: 2700"
    assert {link.source_slug for link in rows[0].evidence_links} == {"sipri_milex"}


def test_country_year_fact_answers_persist_through_generic_contract(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2023)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2023,
        field_key="gdp_per_capita",
        value_type="number",
        selected_value_number=76399.0,
        source_slugs=("world_bank_wdi",),
        source_observation_ids=("wdi:USA:2023:gdp_per_capita",),
        confidence_score=92,
    )
    rows = build_country_year_fact_answers(
        bind=engine,
        question_id="5.1",
        year=2023,
        country_scope={"USA": {"country_name": "United States"}},
    )

    persist_research_answers(
        engine,
        ResearchQuestionMetadata(
            question_id="5.1",
            chapter_id="5",
            question_text="How prosperous is the average resident in market-rate terms?",
            answer_type="numeric",
            category_key="economic_wellbeing",
            method_version=COUNTRY_YEAR_FACTS_METHOD_VERSION,
        ),
        rows,
    )

    with engine.connect() as conn:
        answer = conn.execute(text("SELECT * FROM research_question_answers")).mappings().one()
        link = conn.execute(text("SELECT * FROM research_answer_evidence_links")).mappings().one()

    assert answer["question_id"] == "5.1"
    assert answer["answer_numeric"] == 76399.0
    assert json.loads(answer["answer_json"])["facts"][0]["field_key"] == "gdp_per_capita"
    assert link["source_slug"] == "world_bank_wdi"


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


def _insert_fact(
    engine: object,
    *,
    country_id: int,
    country_year_id: int,
    year: int,
    field_key: str,
    value_type: str,
    selected_value_number: float | None,
    source_slugs: tuple[str, ...],
    source_observation_ids: tuple[str, ...],
    confidence_score: int,
    selected_value_text: str | None = None,
) -> None:
    selected_value = selected_value_number if selected_value_text is None else selected_value_text
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_year_id, country_id, year, field_key, field_label, value_type,
                    selected_value_number, selected_value_text, selected_value_json,
                    candidate_values_json,
                    selection_rule,
                    adjudication_status, confidence_score, quality_signals_json,
                    warnings_json, rationale, recommended_next_action,
                    source_slugs_json, source_observation_ids_json, producer,
                    method_version
                ) VALUES (
                    :country_year_id, :country_id, :year, :field_key, :field_label,
                    :value_type, :selected_value_number, :selected_value_text, :selected_value_json,
                    :candidate_values_json, 'test_rule', 'selected',
                    :confidence_score, '{}', '[]', 'Selected fixture fact.', 'none',
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
                "value_type": value_type,
                "selected_value_number": selected_value_number,
                "selected_value_text": selected_value_text,
                "confidence_score": confidence_score,
                "selected_value_json": json.dumps(
                    _candidate_payload(
                        source_slugs[0],
                        (source_observation_ids[0],),
                        selected_value,
                    )
                ),
                "candidate_values_json": json.dumps(
                    tuple(
                        _candidate_payload(source_slug, (observation_id,), selected_value)
                        for source_slug, observation_id in zip(
                            source_slugs,
                            source_observation_ids,
                            strict=True,
                        )
                    )
                ),
                "source_slugs_json": json.dumps(source_slugs),
                "source_observation_ids_json": json.dumps(source_observation_ids),
            },
        )


def _candidate_payload(
    source_slug: str,
    input_observation_ids: tuple[str, ...],
    value: object,
) -> dict[str, object]:
    return {
        "concept_key": "fixture",
        "source_slug": source_slug,
        "value": value,
        "value_type": "numeric"
        if isinstance(value, int | float)
        else "missing"
        if value is None
        else "categorical",
        "unit": None,
        "scale": None,
        "source_version": "fixture",
        "source_indicator_codes": ["fixture_indicator"],
        "input_observation_ids": list(input_observation_ids),
        "mapping_type": "direct",
        "quality_flags": [],
        "warnings": [],
    }
