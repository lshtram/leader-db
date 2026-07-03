"""Tests for I3 country-year grid infrastructure."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import build_engine, init_database
from leaders_db.db.models import Country, CountryYear
from leaders_db.scope import country_year_grid
from leaders_db.scope.country_year_grid import (
    CountryDefinition,
    build_country_year_coverage_report,
    build_country_year_grid,
    coverage_report_to_json,
    load_country_universe,
)

runner = CliRunner()


def _country_universe() -> tuple[CountryDefinition, ...]:
    return (
        CountryDefinition("FRA", "France", "france"),
        CountryDefinition("KEN", "Kenya", "kenya"),
    )


def _scope_policy_universe() -> tuple[CountryDefinition, ...]:
    return (
        CountryDefinition("FRA", "France", "france"),
        CountryDefinition(
            "GUM",
            "Guam",
            "guam",
            included_in_project=False,
            scope_exclusion_reason="test non-sovereign territory exclusion",
        ),
    )


def _yugoslav_lifecycle_universe() -> tuple[CountryDefinition, ...]:
    return (
        CountryDefinition(
            "SVN",
            "Slovenia",
            "slovenia",
            valid_from_year=1991,
            entity_type="successor_state",
            predecessor_codes=("YUG",),
            notes="test lifecycle seed",
        ),
        CountryDefinition(
            "YUG",
            "Yugoslavia",
            "yugoslavia",
            valid_from_year=1918,
            valid_to_year=2002,
            entity_type="historical_state",
            successor_codes=("SVN",),
            notes="test lifecycle seed",
        ),
    )


def test_build_country_year_grid_populates_fresh_db(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    result = build_country_year_grid(
        engine,
        start_year=2022,
        end_year=2023,
        countries=_country_universe(),
    )

    assert result.countries_created == 2
    assert result.country_years_created == 4

    with engine.connect() as conn:
        countries = conn.execute(select(Country.iso3).order_by(Country.iso3)).scalars().all()
        country_years = conn.execute(select(CountryYear.year)).scalars().all()

    assert countries == ["FRA", "KEN"]
    assert sorted(country_years) == [2022, 2022, 2023, 2023]


def test_build_country_year_grid_is_idempotent(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    first = build_country_year_grid(
        engine,
        start_year=2020,
        end_year=2021,
        countries=_country_universe(),
    )
    second = build_country_year_grid(
        engine,
        start_year=2020,
        end_year=2021,
        countries=_country_universe(),
    )

    assert first.country_years_created == 4
    assert second.countries_created == 0
    assert second.country_years_created == 0

    report = build_country_year_coverage_report(engine)
    assert report.total_countries == 2
    assert report.total_country_years == 4
    assert report.min_year == 2020
    assert report.max_year == 2021


def test_lifecycle_seed_excludes_slovenia_before_birth(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    result = build_country_year_grid(
        engine,
        start_year=1900,
        end_year=1991,
        countries=_yugoslav_lifecycle_universe(),
    )

    assert result.country_years_created == 184
    with engine.connect() as conn:
        rows = conn.execute(
            select(Country.iso3, CountryYear.year)
            .join(CountryYear, CountryYear.country_id == Country.id)
            .order_by(Country.iso3, CountryYear.year)
        ).all()

    assert ("SVN", 1900) in rows
    assert ("SVN", 1991) in rows
    with engine.connect() as conn:
        stale_row = conn.execute(
            select(CountryYear.included_in_project, CountryYear.inclusion_reason)
            .join(Country, Country.id == CountryYear.country_id)
            .where(Country.iso3 == "SVN", CountryYear.year == 1900)
        ).one()

    assert stale_row.included_in_project is False
    assert "outside the packaged lifecycle interval" in stale_row.inclusion_reason


def test_lifecycle_seed_excludes_yugoslavia_after_dissolution(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    build_country_year_grid(
        engine,
        start_year=2002,
        end_year=2003,
        countries=_yugoslav_lifecycle_universe(),
    )

    with engine.connect() as conn:
        rows = conn.execute(
            select(Country.iso3, CountryYear.year)
            .join(CountryYear, CountryYear.country_id == Country.id)
            .order_by(Country.iso3, CountryYear.year)
        ).all()

    assert ("YUG", 2002) in rows
    assert ("YUG", 2003) in rows
    with engine.connect() as conn:
        stale_row = conn.execute(
            select(CountryYear.included_in_project, CountryYear.inclusion_reason)
            .join(Country, Country.id == CountryYear.country_id)
            .where(Country.iso3 == "YUG", CountryYear.year == 2003)
        ).one()

    assert stale_row.included_in_project is False
    assert "outside the packaged lifecycle interval" in stale_row.inclusion_reason


def test_packaged_lifecycle_excludes_pse_before_observer_state_anchor(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    pse = tuple(country for country in load_country_universe() if country.iso3 == "PSE")

    build_country_year_grid(engine, start_year=2011, end_year=2012, countries=pse)

    with engine.connect() as conn:
        rows = conn.execute(
            select(CountryYear.year, CountryYear.included_in_project, CountryYear.inclusion_reason)
            .join(Country, Country.id == CountryYear.country_id)
            .where(Country.iso3 == "PSE")
            .order_by(CountryYear.year)
        ).all()

    assert rows[0].year == 2011
    assert rows[0].included_in_project is False
    assert "lifecycle=2012-present" in rows[0].inclusion_reason
    assert rows[1].year == 2012
    assert rows[1].included_in_project is True
    assert "entity_type=current_state_lifecycle" in rows[1].inclusion_reason


def test_scope_policy_excludes_non_sovereign_entries_from_included_coverage(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    build_country_year_grid(
        engine,
        start_year=2023,
        end_year=2023,
        countries=_scope_policy_universe(),
    )

    payload = coverage_report_to_json(build_country_year_coverage_report(engine))
    with engine.connect() as conn:
        rows = conn.execute(
            select(Country.iso3, CountryYear.included_in_project, CountryYear.inclusion_reason)
            .join(CountryYear, CountryYear.country_id == Country.id)
            .order_by(Country.iso3)
        ).all()

    assert payload["total_country_years"] == 2
    assert payload["included_country_years"] == 1
    assert payload["excluded_country_years"] == 1
    assert rows == [
        ("FRA", True, country_year_grid.DEFAULT_INCLUSION_REASON),
        ("GUM", False, "test non-sovereign territory exclusion"),
    ]


def test_lifecycle_rebuild_marks_stale_out_of_lifecycle_rows_excluded(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    build_country_year_grid(
        engine,
        start_year=1900,
        end_year=1900,
        countries=(CountryDefinition("SVN", "Slovenia", "slovenia"),),
    )
    second = build_country_year_grid(
        engine,
        start_year=1900,
        end_year=1900,
        countries=_yugoslav_lifecycle_universe(),
    )

    assert second.country_years_updated == 1
    with engine.connect() as conn:
        row = conn.execute(
            select(CountryYear.included_in_project, CountryYear.inclusion_reason)
            .join(Country, Country.id == CountryYear.country_id)
            .where(Country.iso3 == "SVN", CountryYear.year == 1900)
        ).one()

    assert row.included_in_project is False
    assert "outside the packaged lifecycle interval" in row.inclusion_reason


def test_build_country_year_grid_rejects_invalid_range(database_url: str) -> None:
    init_database(database_url)

    with pytest.raises(ValueError, match="start_year"):
        build_country_year_grid(
            build_engine(database_url),
            start_year=2024,
            end_year=2023,
            countries=_country_universe(),
        )


def test_country_year_coverage_report_includes_limits(database_url: str) -> None:
    init_database(database_url)
    engine = build_engine(database_url)
    build_country_year_grid(
        engine,
        start_year=2023,
        end_year=2023,
        countries=_country_universe(),
    )

    payload = coverage_report_to_json(build_country_year_coverage_report(engine))

    assert payload["total_countries"] == 2
    assert payload["total_country_years"] == 2
    assert payload["included_country_years"] == 2
    assert payload["excluded_country_years"] == 0
    assert payload["min_year"] == 2023
    assert payload["max_year"] == 2023
    assert any("packaged year-level lifecycle seed" in item for item in payload["limitations"])
    assert any(
        "not a complete global historical-state ontology" in item
        for item in payload["limitations"]
    )


def test_scope_cli_build_and_coverage_use_explicit_range(database_url: str) -> None:
    init_database(database_url)

    build_result = runner.invoke(
        app,
        [
            "scope",
            "build-country-years",
            "--start-year",
            "2022",
            "--end-year",
            "2023",
            "--db-url",
            database_url,
        ],
    )

    assert build_result.exit_code == 0, build_result.stdout
    assert "range: 2022-2023" in build_result.stdout
    assert "countries_created:" in build_result.stdout

    coverage_result = runner.invoke(
        app,
        ["scope", "country-year-coverage", "--db-url", database_url, "--json"],
    )

    assert coverage_result.exit_code == 0, coverage_result.stdout
    payload = json.loads(coverage_result.stdout)
    assert payload["min_year"] == 2022
    assert payload["max_year"] == 2023
    assert payload["total_country_years"] == payload["total_countries"] * 2
    assert payload["included_country_years"] < payload["total_country_years"]
    assert payload["excluded_country_years"] > 0


def test_country_universe_falls_back_when_pycountry_is_missing(monkeypatch) -> None:
    def _missing_pycountry(name: str):
        if name == "pycountry":
            raise ModuleNotFoundError(name)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(country_year_grid, "import_module", _missing_pycountry)

    countries = load_country_universe()

    assert len(countries) > 200
    assert countries == tuple(sorted(countries, key=lambda country: country.iso3))
    assert any(country.iso3 == "KEN" for country in countries)
    assert any(country.iso3 == "USA" for country in countries)
    assert any(country.iso3 == "YUG" and country.valid_to_year == 2002 for country in countries)


def test_lifecycle_seed_contains_representative_post_1950_statehood_cases() -> None:
    countries = {country.iso3: country for country in load_country_universe()}

    expected_starts = {
        "ARE": 1971,
        "BGD": 1971,
        "CPV": 1975,
        "CZE": 1993,
        "ERI": 1993,
        "FSM": 1986,
        "KNA": 1983,
        "LCA": 1979,
        "NAM": 1990,
        "SSD": 2011,
        "SVK": 1993,
        "TLS": 2002,
    }
    for iso3, expected_year in expected_starts.items():
        assert countries[iso3].valid_from_year == expected_year

    assert countries["CSK"].valid_to_year == 1992
    assert countries["SUN"].valid_to_year == 1991
    assert countries["YUG"].valid_to_year == 2002


def test_lifecycle_grid_marks_czechoslovakia_after_dissolution_audit_only(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    countries = tuple(country for country in load_country_universe() if country.iso3 == "CSK")
    build_country_year_grid(engine, start_year=1992, end_year=1993, countries=countries)

    with engine.connect() as conn:
        rows = {
            year: (included, reason)
            for year, included, reason in conn.execute(
                select(
                    CountryYear.year,
                    CountryYear.included_in_project,
                    CountryYear.inclusion_reason,
                )
                .join(Country, Country.id == CountryYear.country_id)
                .where(Country.iso3 == "CSK")
            ).all()
        }

    assert rows[1992][0] is True
    assert rows[1993][0] is False
    assert "outside the packaged lifecycle interval" in rows[1993][1]


def test_lifecycle_grid_marks_representative_pre_statehood_rows_audit_only(
    database_url: str,
) -> None:
    init_database(database_url)
    engine = build_engine(database_url)

    target_codes = {"BGD", "CPV", "ERI", "KNA", "SSD", "TLS"}
    countries = tuple(
        country for country in load_country_universe() if country.iso3 in target_codes
    )
    build_country_year_grid(engine, start_year=1950, end_year=2011, countries=countries)

    with engine.connect() as conn:
        rows = {
            (iso3, year): (included, reason)
            for iso3, year, included, reason in conn.execute(
                select(
                    Country.iso3,
                    CountryYear.year,
                    CountryYear.included_in_project,
                    CountryYear.inclusion_reason,
                )
                .join(CountryYear, CountryYear.country_id == Country.id)
                .where(Country.iso3.in_(target_codes))
            ).all()
        }

    assert rows[("BGD", 1970)][0] is False
    assert rows[("BGD", 1971)][0] is True
    assert rows[("CPV", 1974)][0] is False
    assert rows[("CPV", 1975)][0] is True
    assert rows[("ERI", 1992)][0] is False
    assert rows[("ERI", 1993)][0] is True
    assert rows[("KNA", 1982)][0] is False
    assert rows[("KNA", 1983)][0] is True
    assert rows[("SSD", 2010)][0] is False
    assert rows[("SSD", 2011)][0] is True
    assert rows[("TLS", 2001)][0] is False
    assert rows[("TLS", 2002)][0] is True
    assert "outside the packaged lifecycle interval" in rows[("SSD", 2010)][1]


def test_scope_cli_fails_friendly_when_db_uninitialized(database_url: str) -> None:
    result = runner.invoke(
        app,
        ["scope", "country-year-coverage", "--db-url", database_url, "--json"],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert "local scope database is not initialized" in payload["error"]
    assert "leaders-db init-db" in payload["error"]
    assert "no such table" not in payload["error"].lower()
