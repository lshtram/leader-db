from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.db.models import Country, CountryYear, CountryYearFact
from leaders_db.research.sql_repository import write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import CONCEPT_POPULATION, WDI_POPULATION_INDICATOR_CODE

runner = CliRunner()


def test_facts_publish_concepts_cli_writes_country_year_facts(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    _seed_country_year(engine)
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

    result = runner.invoke(
        app,
        [
            "facts",
            "publish-concepts",
            "--concept",
            CONCEPT_POPULATION,
            "--db-url",
            database_url,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["rows_created"] == 1
    assert payload["field_counts"] == {CONCEPT_POPULATION: 1}
    with Session(engine) as session:
        fact = session.scalar(select(CountryYearFact))
        assert fact is not None
        assert fact.field_key == CONCEPT_POPULATION
        assert fact.selected_value_number == 331_000_000


def test_facts_publish_concepts_cli_fails_friendly_when_db_uninitialized(
    isolated_data_lake: Any,
) -> None:
    result = runner.invoke(app, ["facts", "publish-concepts"])

    assert result.exit_code == 1, result.stdout
    assert "The local evidence database is not initialized" in result.stdout


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
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=observation_id,
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
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
