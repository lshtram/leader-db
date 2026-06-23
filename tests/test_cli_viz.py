"""CLI tests for generic visualization agent access."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from leaders_db.cli import app

runner = CliRunner()


def test_cli_help_lists_viz_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.stdout
    assert "viz-metrics" in result.stdout
    assert "viz-query" in result.stdout
    assert "viz-build-superset-db" in result.stdout


def test_viz_metrics_lists_seed_registry() -> None:
    result = runner.invoke(app, ["viz-metrics"])

    assert result.exit_code == 0, result.stdout
    assert "chronicle.population" in result.stdout
    assert "country_year" in result.stdout


def test_viz_query_groups_population_by_year_and_regime(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)
    fact_path = data_dir / "viz_country_year_metrics.csv"
    _write_country_year_metric_facts(fact_path)

    spec_path = tmp_path / "population_by_regime.json"
    spec_path.write_text(
        json.dumps(
            {
                "metric": "chronicle.population",
                "group_by": ["year", "political_regime_bucket"],
                "aggregation": "sum",
                "filters": {"existence_status": "exists"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "viz-query",
            "--spec",
            str(spec_path),
            "--output",
            "csv",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    rows = list(csv.DictReader(result.stdout.splitlines()))
    assert rows == [
        {
            "year": "2023",
            "political_regime_bucket": "democracy",
            "metric_id": "chronicle.population",
            "value": "30.0",
            "aggregation": "sum",
            "metric_label": "Population",
            "value_unit": "persons",
        },
        {
            "year": "2023",
            "political_regime_bucket": "non_democracy",
            "metric_id": "chronicle.population",
            "value": "30.0",
            "aggregation": "sum",
            "metric_label": "Population",
            "value_unit": "persons",
        },
    ]


def test_viz_query_can_write_csv_file(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_country_year_metric_facts(data_dir / "viz_country_year_metrics.csv")

    spec_path = tmp_path / "population_by_regime.json"
    spec_path.write_text(
        json.dumps(
            {
                "metric": "chronicle.population",
                "group_by": ["year", "political_regime_bucket"],
                "aggregation": "sum",
                "filters": {"existence_status": "exists"},
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "result.csv"

    result = runner.invoke(
        app,
        [
            "viz-query",
            "--spec",
            str(spec_path),
            "--output",
            str(output_path),
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output_path.is_file()
    assert "wrote 2 rows" in result.stdout


def test_viz_query_rejects_unimplemented_transforms(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_country_year_metric_facts(data_dir / "viz_country_year_metrics.csv")

    spec_path = tmp_path / "unsupported_transform.json"
    spec_path.write_text(
        json.dumps(
            {
                "metric": "chronicle.population",
                "aggregation": "none",
                "transforms": [{"kind": "log10"}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "viz-query",
            "--spec",
            str(spec_path),
            "--output",
            "csv",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "log10" in combined
    assert "not allowed" in combined


def test_viz_build_superset_db_writes_sqlite_artifact(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_country_year_metric_facts(data_dir / "viz_country_year_metrics.csv")
    _write_metric_catalog(data_dir / "viz_metric_catalog.csv")
    output_path = tmp_path / "superset_viz.sqlite"

    result = runner.invoke(
        app,
        [
            "viz-build-superset-db",
            "--data-dir",
            str(data_dir),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output_path.is_file()
    assert "viz_country_year_metrics: 4 rows" in result.stdout
    assert "viz_metric_catalog: 1 rows" in result.stdout
    assert "container SQLAlchemy URI" in result.stdout

    with sqlite3.connect(output_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        row_count = connection.execute(
            "select count(*) from viz_country_year_metrics"
        ).fetchone()[0]

    assert "viz_country_year_metrics" in table_names
    assert "viz_metric_catalog" in table_names
    assert "viz_superset_metadata" in table_names
    assert row_count == 4


def test_viz_build_superset_db_requires_core_fact_csv(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "viz-build-superset-db",
            "--data-dir",
            str(data_dir),
            "--output",
            str(tmp_path / "superset_viz.sqlite"),
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "viz_country_year_metrics.csv" in combined


def test_viz_build_superset_db_refuses_to_overwrite_source_csv(
    isolated_data_lake: Path,
) -> None:
    data_dir = isolated_data_lake / "data" / "processed" / "viz" / "country-year-chronicle"
    data_dir.mkdir(parents=True, exist_ok=True)
    source_csv = data_dir / "viz_country_year_metrics.csv"
    _write_country_year_metric_facts(source_csv)
    original_content = source_csv.read_text(encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "viz-build-superset-db",
            "--data-dir",
            str(data_dir),
            "--output",
            str(source_csv),
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "Refusing to write Superset SQLite DB over source CSV export" in combined
    assert source_csv.read_text(encoding="utf-8") == original_content


def _write_country_year_metric_facts(path: Path) -> None:
    rows = [
        {
            "metric_id": "chronicle.population",
            "year": 2023,
            "country_iso3": "AAA",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 10.0,
        },
        {
            "metric_id": "chronicle.population",
            "year": 2023,
            "country_iso3": "BBB",
            "political_regime_bucket": "democracy",
            "existence_status": "exists",
            "value": 20.0,
        },
        {
            "metric_id": "chronicle.population",
            "year": 2023,
            "country_iso3": "CCC",
            "political_regime_bucket": "non_democracy",
            "existence_status": "exists",
            "value": 30.0,
        },
        {
            "metric_id": "chronicle.population",
            "year": 2023,
            "country_iso3": "DDD",
            "political_regime_bucket": "non_democracy",
            "existence_status": "not_yet_existing",
            "value": 1000.0,
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_metric_catalog(path: Path) -> None:
    rows = [
        {
            "metric_id": "chronicle.population",
            "label": "Population",
            "unit": "persons",
        }
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
