from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import create_engine
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.research.local_evidence_summary import (
    RulerPeriodEvidenceRequest,
    summarize_ruler_period_evidence,
)
from leaders_db.research.sql_repository import SqlEvidenceRepository, write_observations
from leaders_db.sources import NormalizedObservation, RawLocator, SourceId, TransformLocator
from leaders_db.sources.concepts import (
    CONCEPT_GDP_PER_CAPITA,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
)

runner = CliRunner()


def test_summarize_ruler_period_groups_local_sql_concept_evidence(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                observation_id="wdi-ken-1964-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                year=1964,
                value=108.1,
                unit="current_usd_per_person",
            ),
            _observation(
                observation_id="wdi-ken-1965-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                year=1965,
                value=104.2,
                unit="current_usd_per_person",
            ),
            _observation(
                observation_id="wdi-ken-1964-pop",
                indicator_code=WDI_POPULATION_INDICATOR_CODE,
                year=1964,
                value=9_200_000,
                unit="persons",
            ),
        ),
    )

    summary = summarize_ruler_period_evidence(
        SqlEvidenceRepository(engine),
        RulerPeriodEvidenceRequest(
            country="KEN",
            leader="Jomo Kenyatta",
            start_year=1964,
            end_year=1966,
            concepts=(CONCEPT_GDP_PER_CAPITA,),
        ),
    )

    assert summary["request"] == {
        "country": "KEN",
        "leader": "Jomo Kenyatta",
        "start_year": 1964,
        "end_year": 1966,
        "concepts": ["gdp_per_capita"],
        "leader_matching": "not_attempted",
        "client_matrix_policy": "excluded_as_evidence",
    }
    observations = summary["available_observations"]
    assert observations["gdp_per_capita"]["KEN"]["1964"]["world_bank_wdi"][0][
        "value"
    ] == 108.1
    assert observations["gdp_per_capita"]["KEN"]["1965"]["world_bank_wdi"][0][
        "input_observation_ids"
    ] == ["wdi-ken-1965-gdppc"]
    coverage = summary["coverage"]["gdp_per_capita"]
    assert coverage["observation_count"] == 2
    assert coverage["source_count"] == 1
    assert coverage["years_with_observations"] == [1964, 1965]
    assert coverage["missing_years"] == [1966]


def test_summarize_ruler_period_defaults_report_evidence_gaps(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)

    summary = summarize_ruler_period_evidence(
        SqlEvidenceRepository(engine),
        RulerPeriodEvidenceRequest(
            country="KEN",
            leader=None,
            start_year=1964,
            end_year=1964,
        ),
    )

    assert summary["request"]["concepts"] == [
        "gdp_per_capita",
        "population",
        "gdp_total",
    ]
    assert summary["coverage"]["gdp_per_capita"]["coverage_status"] == "missing"
    warning_codes = [warning["code"] for warning in summary["warnings"]]
    assert warning_codes.count("evidence_gap") == 3


def test_evidence_summarize_ruler_period_cli_outputs_json(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url)
    write_observations(
        engine,
        (
            _observation(
                observation_id="wdi-ken-1964-gdppc",
                indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                year=1964,
                value=108.1,
                unit="current_usd_per_person",
            ),
        ),
    )

    result = runner.invoke(
        app,
        [
            "evidence",
            "summarize-ruler-period",
            "--country",
            "KEN",
            "--leader",
            "Jomo Kenyatta",
            "--start-year",
            "1964",
            "--end-year",
            "1964",
            "--concept",
            "gdp_per_capita,population",
            "--output",
            "json",
            "--db-url",
            database_url,
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["request"]["leader"] == "Jomo Kenyatta"
    assert payload["request"]["concepts"] == ["gdp_per_capita", "population"]
    assert payload["available_observations"]["gdp_per_capita"]["KEN"]["1964"][
        "world_bank_wdi"
    ][0]["value"] == 108.1
    assert payload["coverage"]["population"]["coverage_status"] == "missing"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--country", "", "--start-year", "1964", "--end-year", "1964"], "country"),
        (["--country", "KEN", "--start-year", "1965", "--end-year", "1964"], "end_year"),
    ],
)
def test_evidence_summarize_ruler_period_cli_validates_inputs(
    database_url: str,
    args: list[str],
    expected: str,
) -> None:
    init_database(database_url)

    result = runner.invoke(
        app,
        ["evidence", "summarize-ruler-period", *args, "--db-url", database_url],
    )

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert expected in combined


def _observation(
    *,
    observation_id: str,
    indicator_code: str,
    year: int,
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
        year=year,
        country_code="KEN",
        country_name="Kenya",
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=None,
        source_version="fixture",
        raw_locator=RawLocator(asset_id="wdi-fixture", json_pointer=f"/{year}"),
        transform_locator=TransformLocator(transform_name="fixture_transform"),
    )
