from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from leaders_db.db.engine import init_database
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import (
    WDI_GDP_CURRENT_USD_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
)
from leaders_db.viz import (
    ECONOMIC_TRENDS_CSV_NAME,
    EconomicTrendRequest,
    build_economic_trend_table,
    build_superset_sqlite_db,
    write_economic_trend_csv,
)


def test_build_economic_trend_table_from_sql_concept_metrics(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                observation_id="wdi-usa-2020-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                value=63_000.0,
                unit="current_usd_per_person",
                year=2020,
                country_code="USA",
            ),
            _observation(
                observation_id="wdi-usa-2020-pop",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                value=331_000_000,
                unit="persons",
                year=2020,
                country_code="USA",
            ),
            _observation(
                observation_id="wdi-usa-2020-gdp",
                indicator_code=WDI_GDP_CURRENT_USD_INDICATOR_CODE,
                value=20_900_000_000_000.0,
                unit="current_usd",
                year=2020,
                country_code="USA",
            ),
            _observation(
                observation_id="wdi-usa-2021-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                value=70_000.0,
                unit="current_usd_per_person",
                year=2021,
                country_code="USA",
            ),
            _observation(
                observation_id="wdi-can-2020-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                value=43_000.0,
                unit="current_usd_per_person",
                year=2020,
                country_code="CAN",
            ),
            _observation(
                observation_id="wdi-usa-2019-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                value=65_000.0,
                unit="current_usd_per_person",
                year=2019,
                country_code="USA",
            ),
        ),
    )

    result = build_economic_trend_table(
        SqlEvidenceRepository(engine),
        EconomicTrendRequest(countries=("usa",), start_year=2020, end_year=2021),
    )

    rows = result.trend_rows[
        ["metric_id", "year", "country_iso3", "value", "source_row_references"]
    ].to_dict("records")
    assert rows == [
        {
            "metric_id": "concept.gdp_per_capita",
            "year": 2020,
            "country_iso3": "USA",
            "value": 63_000.0,
            "source_row_references": "wdi-usa-2020-gdppc",
        },
        {
            "metric_id": "concept.gdp_total",
            "year": 2020,
            "country_iso3": "USA",
            "value": 20_900_000_000_000.0,
            "source_row_references": "wdi-usa-2020-gdp",
        },
        {
            "metric_id": "concept.population",
            "year": 2020,
            "country_iso3": "USA",
            "value": 331_000_000,
            "source_row_references": "wdi-usa-2020-pop",
        },
        {
            "metric_id": "concept.gdp_per_capita",
            "year": 2021,
            "country_iso3": "USA",
            "value": 70_000.0,
            "source_row_references": "wdi-usa-2021-gdppc",
        },
    ]
    assert set(result.trend_rows["country_iso3"]) == {"USA"}
    assert set(result.trend_rows["source_keys"]) == {"world_bank_wdi"}
    assert {diagnostic.metric_id for diagnostic in result.coverage} == {
        "concept.gdp_per_capita",
        "concept.population",
        "concept.gdp_total",
    }


def test_write_economic_trend_csv_is_loaded_by_superset_builder(
    database_url: str,
    tmp_path: Path,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                observation_id="wdi-usa-2020-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                value=63_000.0,
                unit="current_usd_per_person",
                year=2020,
                country_code="USA",
            ),
        ),
    )
    data_dir = tmp_path / "viz"
    data_dir.mkdir()
    _write_required_core_csv(data_dir / "viz_country_year_metrics.csv")

    output_path = data_dir / ECONOMIC_TRENDS_CSV_NAME
    trend_result = write_economic_trend_csv(
        SqlEvidenceRepository(engine),
        EconomicTrendRequest(countries=("USA",), start_year=2020, end_year=2020),
        output_path,
    )
    db_result = build_superset_sqlite_db(data_dir=data_dir)

    assert trend_result.csv_path == output_path
    assert output_path.is_file()
    assert "viz_economic_trends" in db_result.tables_written
    with sqlite3.connect(db_result.output_path) as connection:
        row_count = connection.execute(
            "select count(*) from viz_economic_trends"
        ).fetchone()[0]
    assert row_count == 1


def _observation(
    *,
    observation_id: str,
    indicator_code: str,
    value: Any,
    unit: str,
    year: int,
    country_code: str,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug="world_bank_wdi"),
        observation_id=observation_id,
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=country_code,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=None,
        source_version="fixture",
        raw_locator=RawLocator(asset_id="wdi-fixture", json_pointer=f"/{observation_id}"),
        transform_locator=TransformLocator(transform_name="fixture_transform"),
    )


def _write_required_core_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["metric_id", "year", "country_iso3", "value"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "metric_id": "chronicle.population",
                "year": 2020,
                "country_iso3": "USA",
                "value": 331_000_000,
            }
        )
