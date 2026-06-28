from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine

from leaders_db.db.engine import init_database
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
)
from leaders_db.viz import concept_metric_mappings, publish_concept_metrics
from leaders_db.viz.metrics import lookup_metric
from leaders_db.viz.output_contract import VIZ_OUTPUT_REQUIRED_COLUMNS


def test_concept_metric_mappings_appear_in_viz_metric_registry() -> None:
    mappings = concept_metric_mappings()

    by_concept = {mapping.concept_key: mapping for mapping in mappings}

    assert by_concept[CONCEPT_GDP_PER_CAPITA].metric_id == "concept.gdp_per_capita"
    assert by_concept[CONCEPT_GDP_PER_CAPITA].source_precedence == (
        "world_bank_wdi",
        "maddison_project",
        "pwt",
    )
    metric = lookup_metric("concept.gdp_per_capita")
    assert metric is not None
    assert metric.source_tables == ("normalized_observations",)
    assert metric.attribution_source_keys == ("world_bank_wdi", "maddison_project", "pwt")


def test_publish_concept_metrics_from_sql_repository(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                observation_id="wdi-usa-2020-gdppc",
                value=65000.0,
                unit="current_usd_per_person",
            ),
        ),
    )

    result = publish_concept_metrics(
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )

    rows = result.metric_rows.to_dict("records")
    assert len(rows) == 1
    row = rows[0]
    assert set(VIZ_OUTPUT_REQUIRED_COLUMNS).issubset(result.metric_rows.columns)
    assert row["metric_id"] == "concept.gdp_per_capita"
    assert row["metric_label"] == "GDP per capita (concept)"
    assert row["country_iso3"] == "USA"
    assert row["year"] == 2020
    assert row["value"] == 65000.0
    assert row["value_unit"] == "current_usd_per_person"
    assert row["source_keys"] == "world_bank_wdi"
    assert row["source_row_references"] == "wdi-usa-2020-gdppc"
    assert row["coverage_status"] == "available"

    diagnostics = result.coverage
    by_source = {diagnostic.source_id.slug: diagnostic for diagnostic in diagnostics}
    assert set(by_source) == {"world_bank_wdi", "maddison_project", "pwt"}
    assert by_source["world_bank_wdi"].concept_key == CONCEPT_GDP_PER_CAPITA
    assert by_source["world_bank_wdi"].metric_id == "concept.gdp_per_capita"
    assert by_source["world_bank_wdi"].observation_rows == 1
    assert by_source["world_bank_wdi"].concept_rows == 1
    assert by_source["world_bank_wdi"].coverage_status == "available"
    assert by_source["maddison_project"].observation_rows == 0
    assert by_source["maddison_project"].concept_rows == 0
    assert by_source["maddison_project"].coverage_status == "missing"
    assert by_source["pwt"].coverage_status == "missing"


def test_publish_concept_metrics_reports_missing_coverage(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                observation_id="wdi-usa-2020-pop",
                value=331_000_000,
                unit="persons",
            ),
        ),
    )

    result = publish_concept_metrics(
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
    )

    assert result.metric_rows.empty
    by_source = {diagnostic.source_id.slug: diagnostic for diagnostic in result.coverage}
    assert set(by_source) == {"world_bank_wdi", "maddison_project", "pwt"}
    diagnostic = by_source["world_bank_wdi"]
    assert diagnostic.observation_rows == 1
    assert diagnostic.concept_rows == 0
    assert diagnostic.coverage_status == "missing"
    assert by_source["maddison_project"].observation_rows == 0
    assert by_source["pwt"].coverage_status == "missing"


def test_publish_concept_metrics_reports_explicit_empty_source_request(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)

    result = publish_concept_metrics(
        SqlEvidenceRepository(engine),
        concept_keys=(CONCEPT_GDP_PER_CAPITA,),
        source_ids=(SourceId(slug="world_bank_wdi"),),
    )

    assert result.metric_rows.empty
    assert len(result.coverage) == 1
    diagnostic = result.coverage[0]
    assert diagnostic.source_id.slug == "world_bank_wdi"
    assert diagnostic.observation_rows == 0
    assert diagnostic.concept_rows == 0
    assert diagnostic.coverage_status == "missing"


def _observation(
    *,
    indicator_code: str,
    observation_id: str,
    value: Any,
    unit: str,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug="world_bank_wdi"),
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
        raw_locator=RawLocator(asset_id="wdi-fixture", json_pointer="/0"),
        transform_locator=TransformLocator(transform_name="fixture_transform"),
    )
