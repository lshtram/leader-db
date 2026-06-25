"""Build a read-only Superset-facing SQLite database from viz CSV exports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..paths import processed_dir

VIZ_SUPERSET_DB_BASENAME = "superset_viz.sqlite"

VIZ_CSV_TABLES: tuple[tuple[str, str, bool], ...] = (
    ("viz_country_year_metrics.csv", "viz_country_year_metrics", True),
    ("viz_country_year_growth.csv", "viz_country_year_growth", False),
    ("viz_regime_year_aggregates.csv", "viz_regime_year_aggregates", False),
    ("viz_country_latest_metrics.csv", "viz_country_latest_metrics", False),
    ("viz_metric_catalog.csv", "viz_metric_catalog", False),
    ("viz_regime_year_population.csv", "viz_regime_year_population", False),
    ("viz_source_coverage.csv", "viz_source_coverage", False),
    # Investigation-slice output. Optional -- only present when the
    # ``leaders-db viz-run-investigation-slice`` command has been
    # run for the matching ``question_key``. When the CSV exists,
    # the Superset SQLite builder loads it under the canonical
    # ``viz_investigation_<question_key>`` table name; when it is
    # absent the builder skips it (the third tuple slot is the
    # ``required`` flag).
    (
        "viz_investigation_gdp_per_capita_major_powers.csv",
        "viz_investigation_gdp_per_capita_major_powers",
        False,
    ),
)


@dataclass(frozen=True)
class SupersetDbBuildResult:
    """Summary of a Superset SQLite build."""

    output_path: Path
    tables_written: tuple[str, ...]
    rows_by_table: dict[str, int]

    @property
    def sqlalchemy_uri(self) -> str:
        """Return the host-side SQLAlchemy URI for this SQLite database."""
        return f"sqlite:///{self.output_path.resolve()}"


def default_viz_data_dir() -> Path:
    """Return the default directory holding visualization CSV artifacts."""
    return processed_dir("viz") / "country-year-chronicle"


def default_superset_db_path(data_dir: Path | None = None) -> Path:
    """Return the default Superset SQLite path for ``data_dir``."""
    base_dir = data_dir if data_dir is not None else default_viz_data_dir()
    return base_dir / VIZ_SUPERSET_DB_BASENAME


def build_superset_sqlite_db(
    *,
    data_dir: Path | None = None,
    output_path: Path | None = None,
) -> SupersetDbBuildResult:
    """Build a SQLite DB from deterministic visualization CSV exports.

    The resulting file is a derived analytic artifact. Superset should receive it
    through a read-only Docker mount; this function only creates/refreshed the
    local file before Superset starts.
    """
    resolved_data_dir = data_dir if data_dir is not None else default_viz_data_dir()
    resolved_output_path = (
        output_path if output_path is not None else default_superset_db_path(resolved_data_dir)
    )
    _assert_required_csvs_exist(resolved_data_dir)
    _assert_output_does_not_overwrite_source_csv(resolved_data_dir, resolved_output_path)

    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = resolved_output_path.with_suffix(resolved_output_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    rows_by_table: dict[str, int] = {}
    tables_written: list[str] = []
    with sqlite3.connect(tmp_path) as connection:
        for filename, table_name, _required in VIZ_CSV_TABLES:
            csv_path = resolved_data_dir / filename
            if not csv_path.is_file():
                continue
            frame = pd.read_csv(csv_path)
            frame.to_sql(table_name, connection, if_exists="replace", index=False)
            rows_by_table[table_name] = len(frame)
            tables_written.append(table_name)
        _write_metadata_table(connection, resolved_data_dir, tables_written)

    tmp_path.replace(resolved_output_path)
    return SupersetDbBuildResult(
        output_path=resolved_output_path,
        tables_written=tuple(tables_written),
        rows_by_table=rows_by_table,
    )


def _assert_required_csvs_exist(data_dir: Path) -> None:
    missing = [
        filename
        for filename, _table_name, required in VIZ_CSV_TABLES
        if required and not (data_dir / filename).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing required visualization CSV exports in {data_dir}: {missing}. "
            "Run the country-year Chronicle analytic export first."
        )


def _assert_output_does_not_overwrite_source_csv(data_dir: Path, output_path: Path) -> None:
    resolved_output = output_path.resolve()
    source_csv_paths = {
        (data_dir / filename).resolve()
        for filename, _table_name, _required in VIZ_CSV_TABLES
    }
    if resolved_output in source_csv_paths:
        raise ValueError(
            f"Refusing to write Superset SQLite DB over source CSV export: {output_path}. "
            "Choose a .sqlite output path such as superset_viz.sqlite."
        )


def _write_metadata_table(
    connection: sqlite3.Connection,
    data_dir: Path,
    tables_written: list[str],
) -> None:
    metadata = pd.DataFrame(
        [
            {"key": "source_data_dir", "value": str(data_dir.resolve())},
            {"key": "tables_written", "value": ",".join(tables_written)},
            {"key": "access_policy", "value": "mount SQLite file read-only in Superset"},
        ]
    )
    metadata.to_sql("viz_superset_metadata", connection, if_exists="replace", index=False)


__all__ = [
    "VIZ_CSV_TABLES",
    "VIZ_SUPERSET_DB_BASENAME",
    "SupersetDbBuildResult",
    "build_superset_sqlite_db",
    "default_superset_db_path",
    "default_viz_data_dir",
]
