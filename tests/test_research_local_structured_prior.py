from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.local_structured_prior import (
    CLIENT_MATRIX_SOURCE_SLUGS,
    OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS,
    POLITICAL_FREEDOM_PRIOR_FIELD_KEYS,
    LeaderPriorMetadata,
    LocalPriorPeriod,
    LocalStructuredPriorRequest,
    build_local_structured_prior,
)


def test_v3_local_prior_includes_baseline_tenure_and_target_without_future_data(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    for country_year_id, year in enumerate((1998, 2000, 2021, 2022, 2023), start=1):
        _insert_country_year(
            engine,
            country_id=1,
            country_year_id=country_year_id,
            iso3="RUS",
            name="Russia",
            year=year,
        )
        _insert_fact(
            engine,
            country_id=1,
            country_year_id=country_year_id,
            year=year,
            field_key="military_spend_share_gdp",
            value_type="number",
            selected_value_number=float(year),
            source_slugs=("sipri_milex",),
            source_observation_ids=(f"sipri:RUS:{year}:share",),
            confidence_score=80,
        )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="2B.8",
            iso3="RUS",
            period=LocalPriorPeriod(year=2022),
            leader=LeaderPriorMetadata(name="Vladimir Putin", accession_year=2000),
        ),
    )

    assert artifact.method_version == "local_structured_prior_v3"
    assert [(fact.year, fact.period_role) for fact in artifact.local_facts] == [
        (1998, "pre_accession"),
        (2000, "tenure"),
        (2021, "tenure"),
        (2022, "target"),
    ]
    assert all(fact.year <= 2022 for fact in artifact.local_facts)


def test_build_local_prior_finds_freedom_house_political_freedom_facts(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="political_liberties",
        value_type="number",
        selected_value_number=1.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:USA:2020:political_rights",),
        confidence_score=88,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="civil_liberties",
        value_type="number",
        selected_value_number=1.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:USA:2020:civil_liberties",),
        confidence_score=88,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="USA",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "evidence_found"
    assert artifact.client_matrix_policy == "excluded_as_evidence"
    assert [fact.field_key for fact in artifact.local_facts] == [
        "civil_liberties",
        "political_liberties",
    ]
    assert {fact.source_slugs[0] for fact in artifact.local_facts} == {"freedom_house"}
    assert any(
        "Do not re-fetch local structured datasets" in item
        for item in artifact.recommended_research_instructions
    )


def test_build_local_prior_empty_state_has_explicit_no_evidence_shape(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="CAN", name="Canada", year=2020)

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="CAN",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "no_evidence_found"
    assert artifact.local_facts == []
    assert artifact.missing_or_empty_reason is not None
    assert "No selected non-client country_year_facts" in artifact.missing_or_empty_reason
    assert artifact.client_matrix_policy == "excluded_as_evidence"


def test_build_local_prior_absent_country_year_scope_is_not_applicable(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO countries (id, iso3, country_name, country_name_normalized)
                VALUES (1, 'USA', 'United States', 'united states')
                """
            )
        )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="USA",
            period=LocalPriorPeriod(year=1999),
        ),
    )

    assert artifact.status == "not_applicable"
    assert artifact.local_facts == []
    assert artifact.missing_or_empty_reason is not None
    assert "No included project country-year exists" in artifact.missing_or_empty_reason


def test_build_local_prior_excluded_country_year_scope_is_not_applicable(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(
        engine,
        country_id=1,
        country_year_id=1,
        iso3="USA",
        name="United States",
        year=2020,
        included=False,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="political_liberties",
        value_type="number",
        selected_value_number=7.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:USA:2020:political_rights",),
        confidence_score=88,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="USA",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "not_applicable"
    assert artifact.local_facts == []
    assert artifact.missing_or_empty_reason is not None
    assert "No included project country-year exists" in artifact.missing_or_empty_reason


def test_build_local_prior_mixed_period_emits_only_included_year_facts(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(
        engine,
        country_id=1,
        country_year_id=1,
        iso3="USA",
        name="United States",
        year=2019,
        included=True,
    )
    _insert_country_year(
        engine,
        country_id=1,
        country_year_id=2,
        iso3="USA",
        name="United States",
        year=2020,
        included=False,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2019,
        field_key="political_liberties",
        value_type="number",
        selected_value_number=1.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:USA:2019:political_rights",),
        confidence_score=88,
    )
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=2,
        year=2020,
        field_key="civil_liberties",
        value_type="number",
        selected_value_number=7.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:USA:2020:civil_liberties",),
        confidence_score=88,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="USA",
            period=LocalPriorPeriod(start_year=2019, end_year=2020),
        ),
    )

    assert artifact.status == "evidence_found"
    assert [(fact.year, fact.field_key) for fact in artifact.local_facts] == [
        (2019, "political_liberties")
    ]


def test_build_local_prior_unknown_question_returns_error_artifact(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="UNKNOWN",
            iso3="USA",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "error"
    assert artifact.local_facts == []
    assert artifact.missing_or_empty_reason is not None
    assert "Unknown methodology question id" in artifact.missing_or_empty_reason
    assert artifact.model_dump(mode="json")["status"] == "error"


@pytest.mark.parametrize("client_source_slug", sorted(CLIENT_MATRIX_SOURCE_SLUGS))
def test_build_local_prior_excludes_client_matrix_source_rows(
    database_url: str, client_source_slug: str
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="USA", name="United States", year=2020)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="political_liberties",
        value_type="number",
        selected_value_number=9.0,
        source_slugs=(client_source_slug,),
        source_observation_ids=(
            f"{client_source_slug}:USA:2020:political_freedom",
        ),
        confidence_score=99,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.1",
            iso3="USA",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "no_evidence_found"
    assert artifact.local_facts == []
    assert artifact.client_matrix_policy == "excluded_as_evidence"


def test_build_local_prior_4b2_uses_same_political_freedom_mapping_as_4b1(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="IND", name="India", year=2020)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="civil_liberties",
        value_type="number",
        selected_value_number=3.0,
        source_slugs=("freedom_house",),
        source_observation_ids=("freedom_house:IND:2020:civil_liberties",),
        confidence_score=80,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.2",
            iso3="IND",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "evidence_found"
    assert artifact.question_text.startswith(
        "Did the ruler refrain from proposing, signing, decreeing"
    )
    assert "civil_liberties" in POLITICAL_FREEDOM_PRIOR_FIELD_KEYS
    assert artifact.local_facts[0].field_key == "civil_liberties"


def test_build_local_prior_4b3_uses_opposition_tolerance_mapping(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_country_year(engine, country_id=1, iso3="BRA", name="Brazil", year=2020)
    _insert_fact(
        engine,
        country_id=1,
        country_year_id=1,
        year=2020,
        field_key="freedom_expression",
        value_type="number",
        selected_value_number=0.62,
        source_slugs=("vdem",),
        source_observation_ids=("vdem:BRA:2020:freedom_expression",),
        confidence_score=85,
    )

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="4B.3",
            iso3="BRA",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "evidence_found"
    assert artifact.question_text.startswith(
        "Did the ruler protect in law and practice opposition"
    )
    assert "freedom_expression" in OPPOSITION_TOLERANCE_PRIOR_FIELD_KEYS
    assert artifact.mapping_note is not None
    assert "opposition/media/protest/civil-society tolerance" in artifact.mapping_note
    assert artifact.local_facts[0].field_key == "freedom_expression"


def _insert_country_year(
    engine: object,
    *,
    country_id: int,
    iso3: str,
    name: str,
    year: int,
    country_year_id: int | None = None,
    included: bool = True,
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO countries (
                    id, iso3, country_name, country_name_normalized
                ) VALUES (:country_id, :iso3, :name, :normalized_name)
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
                VALUES (:country_year_id, :country_id, :year, :included_in_project)
                """
            ),
            {
                "country_year_id": country_year_id or country_id,
                "country_id": country_id,
                "year": year,
                "included_in_project": included,
            },
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
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_year_id, country_id, year, field_key, field_label, value_type,
                    selected_value_number, selected_value_text, selected_value_json,
                    candidate_values_json, selection_rule, adjudication_status,
                    confidence_score, quality_signals_json, warnings_json, rationale,
                    recommended_next_action, source_slugs_json, source_observation_ids_json,
                    producer, method_version
                ) VALUES (
                    :country_year_id, :country_id, :year, :field_key, :field_label,
                    :value_type, :selected_value_number, NULL, NULL, '[]', 'test_rule',
                    'selected', :confidence_score, '{}', '[]', 'Selected fixture fact.',
                    'none', :source_slugs_json, :source_observation_ids_json, 'test', 'test_v1'
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
                "confidence_score": confidence_score,
                "source_slugs_json": json.dumps(source_slugs),
                "source_observation_ids_json": json.dumps(source_observation_ids),
            },
        )
