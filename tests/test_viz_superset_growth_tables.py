"""Tests for the derived Superset growth tables generator."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from leaders_db.viz.superset_growth_tables import (
    COUNTRY_LATEST_COLUMNS,
    GROWTH_COLUMNS,
    REGIME_AGGREGATES_COLUMNS,
    build_country_latest_metrics,
    build_country_year_growth,
    build_growth_tables,
    build_regime_year_aggregates,
)


def _write_fact_csv(path: Path) -> None:
    rows = [
        {
            "metric_id": "chronicle.population",
            "year_date": "2020-01-01",
            "year": 2020,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 100.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": "2021-01-01",
            "year": 2021,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 110.0,
        },
        {
            "metric_id": "chronicle.gdp_per_capita",
            "year_date": "2020-01-01",
            "year": 2020,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 5000.0,
        },
        {
            "metric_id": "chronicle.gdp_per_capita",
            "year_date": "2021-01-01",
            "year": 2021,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 5500.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": "2020-01-01",
            "year": 2020,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 200.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": "2021-01-01",
            "year": 2021,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 220.0,
        },
        {
            "metric_id": "chronicle.gdp_per_capita",
            "year_date": "2020-01-01",
            "year": 2020,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 3000.0,
        },
        {
            "metric_id": "chronicle.gdp_per_capita",
            "year_date": "2021-01-01",
            "year": 2021,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 3300.0,
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fact_dataframe() -> pd.DataFrame:
    rows = [
        {
            "metric_id": "chronicle.population",
            "year_date": pd.Timestamp("2020-01-01"),
            "year": 2020,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 100.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": pd.Timestamp("2021-01-01"),
            "year": 2021,
            "country_iso3": "AAA",
            "country_name": "Aaa",
            "political_regime": "Full democracy",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 110.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": pd.Timestamp("2020-01-01"),
            "year": 2020,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 200.0,
        },
        {
            "metric_id": "chronicle.population",
            "year_date": pd.Timestamp("2021-01-01"),
            "year": 2021,
            "country_iso3": "BBB",
            "country_name": "Bbb",
            "political_regime": "Authoritarian",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 220.0,
        },
    ]
    return pd.DataFrame(rows)


def test_build_country_year_growth_computes_yoy(tmp_path: Path) -> None:
    fact = _fact_dataframe()
    growth = build_country_year_growth(fact)
    assert list(growth.columns) == list(GROWTH_COLUMNS)
    aaa = growth[(growth.country_iso3 == "AAA") & (growth.metric_id == "chronicle.population")]
    assert len(aaa) == 2
    assert pd.isna(aaa.iloc[0]["prev_value"])
    assert aaa.iloc[0]["yoy_pct_growth"] != aaa.iloc[0]["yoy_pct_growth"]  # NaN
    assert aaa.iloc[1]["prev_value"] == pytest.approx(100.0)
    assert aaa.iloc[1]["yoy_abs_change"] == pytest.approx(10.0)
    assert aaa.iloc[1]["yoy_pct_growth"] == pytest.approx(0.10)
    assert aaa.iloc[1]["decade"] == 2020


def test_build_country_year_growth_breaks_on_unit_switch() -> None:
    fact = pd.DataFrame(
        [
            {
                "metric_id": "chronicle.gdp",
                "metric_unit": "vdem_latent_gdp_units",
                "metric_source": "vdem",
                "metric_method": "",
                "year_date": pd.Timestamp("2020-01-01"),
                "year": 2020,
                "country_iso3": "AAA",
                "country_name": "Aaa",
                "political_regime": "Full democracy",
                "political_regime_bucket": "democracy",
                "existence_status": "exists",
                "value": 10.0,
            },
            {
                "metric_id": "chronicle.gdp",
                "metric_unit": "2011_intl_dollars",
                "metric_source": "maddison_project",
                "metric_method": "",
                "year_date": pd.Timestamp("2021-01-01"),
                "year": 2021,
                "country_iso3": "AAA",
                "country_name": "Aaa",
                "political_regime": "Full democracy",
                "political_regime_bucket": "democracy",
                "existence_status": "exists",
                "value": 10000.0,
            },
            {
                "metric_id": "chronicle.gdp",
                "metric_unit": "2011_intl_dollars",
                "metric_source": "maddison_project",
                "metric_method": "",
                "year_date": pd.Timestamp("2022-01-01"),
                "year": 2022,
                "country_iso3": "AAA",
                "country_name": "Aaa",
                "political_regime": "Full democracy",
                "political_regime_bucket": "democracy",
                "existence_status": "exists",
                "value": 11000.0,
            },
        ]
    )
    rows = build_country_year_growth(fact).sort_values("year").reset_index(drop=True)

    assert pd.isna(rows.loc[0, "yoy_pct_growth"])
    assert pd.isna(rows.loc[1, "yoy_pct_growth"])
    assert rows.loc[2, "prev_value"] == pytest.approx(10000.0)
    assert rows.loc[2, "yoy_pct_growth"] == pytest.approx(0.10)


def test_build_country_year_growth_breaks_on_year_gap() -> None:
    fact = pd.DataFrame(
        [
            {
                "metric_id": "chronicle.population",
                "metric_unit": "persons",
                "metric_source": "vdem",
                "metric_method": "",
                "year_date": pd.Timestamp("1971-01-01"),
                "year": 1971,
                "country_iso3": "QAT",
                "country_name": "Qatar",
                "political_regime": "Authoritarian",
                "political_regime_bucket": "non_democracy",
                "existence_status": "exists",
                "value": 24921.0,
            },
            {
                "metric_id": "chronicle.population",
                "metric_unit": "persons",
                "metric_source": "vdem",
                "metric_method": "",
                "year_date": pd.Timestamp("2024-01-01"),
                "year": 2024,
                "country_iso3": "QAT",
                "country_name": "Qatar",
                "political_regime": "Authoritarian",
                "political_regime_bucket": "non_democracy",
                "existence_status": "exists",
                "value": 2857822.0,
            },
        ]
    )
    rows = build_country_year_growth(fact).sort_values("year").reset_index(drop=True)

    assert pd.isna(rows.loc[1, "prev_value"])
    assert pd.isna(rows.loc[1, "yoy_pct_growth"])


def test_build_regime_year_aggregates_emits_two_granularities() -> None:
    fact = _fact_dataframe()
    growth = build_country_year_growth(fact)
    aggregates = build_regime_year_aggregates(fact, growth=growth)
    assert list(aggregates.columns) == list(REGIME_AGGREGATES_COLUMNS)

    bucket_rows = aggregates[aggregates.political_regime_bucket != ""]
    regime_rows = aggregates[aggregates.political_regime != ""]

    assert not bucket_rows.empty
    assert not regime_rows.empty

    demo_2020 = bucket_rows[
        (bucket_rows.year == 2020)
        & (bucket_rows.political_regime_bucket == "democracy")
        & (bucket_rows.metric_id == "chronicle.population")
    ]
    assert demo_2020.iloc[0]["mean_value"] == pytest.approx(100.0)
    assert demo_2020.iloc[0]["n_countries"] == 1

    nondemo_2020 = bucket_rows[
        (bucket_rows.year == 2020)
        & (bucket_rows.political_regime_bucket == "non_democracy")
        & (bucket_rows.metric_id == "chronicle.population")
    ]
    assert nondemo_2020.iloc[0]["mean_value"] == pytest.approx(200.0)

    demo_2021 = bucket_rows[
        (bucket_rows.year == 2021) & (bucket_rows.political_regime_bucket == "democracy")
    ]
    assert demo_2021.iloc[0]["prev_mean_value"] == pytest.approx(100.0)
    assert demo_2021.iloc[0]["mean_yoy_pct_growth"] == pytest.approx(0.10)


def test_build_country_latest_metrics_emits_one_row_per_country() -> None:
    fact = _fact_dataframe()
    latest = build_country_latest_metrics(fact)
    assert list(latest.columns) == list(COUNTRY_LATEST_COLUMNS)
    assert set(latest.country_iso3) == {"AAA", "BBB"}
    aaa = latest[latest.country_iso3 == "AAA"].iloc[0]
    assert aaa["latest_year"] == 2021
    assert aaa["latest_population"] == pytest.approx(110.0)
    assert aaa["population_rank"] == 2  # BBB larger
    bbb = latest[latest.country_iso3 == "BBB"].iloc[0]
    assert bbb["population_rank"] == 1


def test_build_growth_tables_writes_three_csvs(tmp_path: Path) -> None:
    fact_path = tmp_path / "viz_country_year_metrics.csv"
    _write_fact_csv(fact_path)
    result = build_growth_tables(data_dir=tmp_path)

    assert result.growth_csv.is_file()
    assert result.regime_aggregates_csv.is_file()
    assert result.country_latest_csv.is_file()
    assert result.growth_rows > 0
    assert result.regime_aggregates_rows > 0
    assert result.country_latest_rows == 2

    growth_df = pd.read_csv(result.growth_csv)
    assert list(growth_df.columns) == list(GROWTH_COLUMNS)


def test_build_growth_tables_requires_fact_csv(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Required source fact CSV is missing"):
        build_growth_tables(data_dir=tmp_path)


def test_build_growth_tables_is_idempotent(tmp_path: Path) -> None:
    fact_path = tmp_path / "viz_country_year_metrics.csv"
    _write_fact_csv(fact_path)
    first = build_growth_tables(data_dir=tmp_path)
    second = build_growth_tables(data_dir=tmp_path)
    assert first.growth_rows == second.growth_rows
    assert first.regime_aggregates_rows == second.regime_aggregates_rows
    assert first.country_latest_rows == second.country_latest_rows
