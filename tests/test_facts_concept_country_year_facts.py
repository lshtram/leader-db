from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country, CountryYear, CountryYearFact
from leaders_db.facts import publish_concept_country_year_facts
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_POPULATION,
    PWT_POPULATION_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
)


def test_publish_concept_country_year_facts_selects_preferred_numeric_source(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="pwt",
                indicator_code=PWT_POPULATION_INDICATOR_CODE,
                observation_id="pwt-usa-2020-pop",
                value=330_000,
                unit="thousands_of_persons",
            ),
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
        run_id="test-run",
    )

    assert result.rows_created == 1
    assert result.rows_updated == 0
    assert result.total_rows == 1
    assert result.field_counts == {CONCEPT_POPULATION: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_POPULATION
        assert fact.field_label == "Country population"
        assert fact.selected_value_number == 331_000_000
        assert fact.selected_value_text == "331000000"
        assert fact.adjudication_status == "auto_resolved"
        assert fact.confidence_score == 80
        assert fact.source_slugs_json == '["world_bank_wdi","pwt"]'
        assert fact.source_observation_ids_json == (
            '["wdi-usa-2020-pop","pwt-usa-2020-pop"]'
        )
        selected = json.loads(fact.selected_value_json or "{}")
        assert selected["source_slug"] == "world_bank_wdi"
        candidates = json.loads(fact.candidate_values_json)
        assert [candidate["source_slug"] for candidate in candidates] == [
            "world_bank_wdi",
            "pwt",
        ]


def test_publish_concept_country_year_facts_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                observation_id="wdi-usa-2020-gdppc",
                value=65000.0,
                unit="current_usd_per_person",
            ),
        ),
    )

    first = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )
    second = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )

    assert first.rows_created == 1
    assert second.rows_created == 0
    assert second.rows_updated == 0
    with Session(engine) as session:
        facts = session.scalars(select(CountryYearFact)).all()
    assert len(facts) == 1


def test_publish_concept_country_year_facts_skips_rows_outside_scope(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
    )

    assert result.rows_created == 0
    assert result.skipped_without_country_year == 1
    with Session(engine) as session:
        assert session.scalars(select(CountryYearFact)).all() == []


def test_publish_concept_country_year_facts_persists_missing_values_for_review(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
    write_observations(
        engine,
        (
            _observation(
                source_slug="world_bank_wdi",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop-missing",
                value=None,
                value_type="missing",
                unit="persons",
            ),
        ),
    )

    result = publish_concept_country_year_facts(
        engine,
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_POPULATION,),
    )

    assert result.rows_created == 1
    assert result.adjudication_status_counts == {"needs_review": 1}
    assert [warning.code for warning in result.warnings] == ["missing_value"]
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.value_type == "missing"
        assert fact.selected_value_number is None
        assert fact.adjudication_status == "needs_review"
        assert fact.review_reason == "selected concept value is missing"
        assert fact.recommended_next_action == "review missing concept value"
        warnings = json.loads(fact.warnings_json)
        assert warnings[0]["code"] == "missing_value"


def _seed_country_year(engine: Any) -> None:
    with Session(engine) as session:
        country = Country(
            iso3="USA",
            country_name="United States",
            country_name_normalized="united states",
            notes=None,
        )
        session.add(country)
        session.flush()
        session.add(
            CountryYear(
                country_id=country.id,
                year=2020,
                included_in_project=True,
                inclusion_reason="test fixture",
            )
        )
        session.commit()


def _observation(
    *,
    source_slug: str,
    indicator_code: str,
    observation_id: str,
    value: Any,
    unit: str,
    value_type: str = "numeric",
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=observation_id,
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type=value_type,
        year=2020,
        country_code="USA",
        country_name="United States",
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=None,
        source_version="fixture",
        raw_locator=RawLocator(asset_id=f"{source_slug}-fixture", json_pointer="/0"),
        transform_locator=TransformLocator(transform_name="fixture_transform"),
    )
