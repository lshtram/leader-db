"""Visualization semantic-layer CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from ..viz.executor import CsvVizDataProvider, execute_query
from ..viz.metrics import get_metric_registry
from ..viz.query_spec import (
    AggregationKind,
    FilterOperator,
    QuerySpec,
)
from ..viz.superset_db import build_superset_sqlite_db
from ..viz.superset_growth_tables import build_growth_tables
from ._app import app


@app.command("viz-metrics")
def viz_metrics_cmd(
    output: str = typer.Option(
        "table",
        "--output",
        help="Output format: table or json.",
    ),
) -> None:
    """List metric IDs available to the generic visualization query layer."""
    registry = get_metric_registry()
    if output == "json":
        payload = [metric.model_dump(mode="json") for metric in registry.values()]
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if output != "table":
        raise typer.BadParameter("--output must be 'table' or 'json'")

    for metric in registry.values():
        typer.echo(
            f"{metric.metric_id}\t{metric.grain.value}\t{metric.value_column}\t{metric.label}"
        )


@app.command("viz-query")
def viz_query_cmd(
    spec: Path = typer.Option(
        ...,
        "--spec",
        help="Path to a JSON semantic query spec.",
    ),
    output: str = typer.Option(
        "csv",
        "--output",
        help=(
            "Output mode. Use 'csv' or 'json' to print to stdout, or pass a "
            "file path to write CSV there."
        ),
    ),
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        help=(
            "Directory containing viz_country_year_metrics.csv. Defaults to "
            "data/processed/viz/country-year-chronicle under the project root."
        ),
    ),
) -> None:
    """Run a generic read-only visualization query for agents/scripts."""
    query = _load_query_spec(spec)
    frame = execute_query(query, CsvVizDataProvider(base_dir=data_dir))

    if output == "csv":
        sys.stdout.write(frame.to_csv(index=False))
        return
    if output == "json":
        typer.echo(frame.to_json(orient="records"))
        return

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    typer.echo(f"wrote {len(frame)} rows to {output_path}")


@app.command("viz-build-superset-db")
def viz_build_superset_db_cmd(
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        help=(
            "Directory containing viz CSV exports. Defaults to "
            "data/processed/viz/country-year-chronicle under the project root."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help=(
            "SQLite output path. Defaults to superset_viz.sqlite inside "
            "the selected data directory."
        ),
    ),
) -> None:
    """Build the read-only SQLite artifact consumed by local Superset."""
    try:
        result = build_superset_sqlite_db(data_dir=data_dir, output_path=output)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"wrote Superset SQLite DB: {result.output_path}")
    for table_name in result.tables_written:
        typer.echo(f"  {table_name}: {result.rows_by_table[table_name]} rows")
    typer.echo(f"host SQLAlchemy URI: {result.sqlalchemy_uri}")
    typer.echo(
        "container SQLAlchemy URI (compose): "
        "sqlite:////leaders-db-viz/superset_viz.sqlite"
    )


@app.command("viz-build-growth-tables")
def viz_build_growth_tables_cmd(
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        help=(
            "Directory containing viz_country_year_metrics.csv. Defaults to "
            "data/processed/viz/country-year-chronicle under the project root."
        ),
    ),
    rebuild_db: bool = typer.Option(
        True,
        "--rebuild-db/--no-rebuild-db",
        help=(
            "After writing the derived CSVs, also rebuild the Superset "
            "SQLite DB so the new tables are visible to dashboards."
        ),
    ),
) -> None:
    """Build the derived CSV tables and refresh the Superset SQLite DB.

    Produces three derived CSVs (country-year growth, regime-year
    aggregates, country-latest leaderboard) on top of the canonical
    ``viz_country_year_metrics.csv`` and, by default, rebuilds the
    Superset-facing SQLite artifact so the new tables are visible.
    """
    from ..viz.superset_db import (
        build_superset_sqlite_db as _build_superset_sqlite_db,
    )
    from ..viz.superset_db import (
        default_viz_data_dir,
    )

    resolved_data_dir = data_dir if data_dir is not None else default_viz_data_dir()
    result = build_growth_tables(data_dir=resolved_data_dir)
    typer.echo(
        f"wrote derived tables under {result.output_dir}:\n"
        f"  {result.growth_csv.name}: {result.growth_rows} rows\n"
        f"  {result.regime_aggregates_csv.name}: {result.regime_aggregates_rows} rows\n"
        f"  {result.country_latest_csv.name}: {result.country_latest_rows} rows"
    )
    if rebuild_db:
        db_result = _build_superset_sqlite_db(data_dir=resolved_data_dir)
        typer.echo(f"rebuilt Superset SQLite DB: {db_result.output_path}")
        for table_name in db_result.tables_written:
            typer.echo(f"  {table_name}: {db_result.rows_by_table[table_name]} rows")


@app.command("viz-run-investigation-slice")
def viz_run_investigation_slice_cmd(
    question: str = typer.Option(
        ...,
        "--question",
        help=(
            "Constrained investigation question key. Supported: "
            "gdp-per-capita-major-powers."
        ),
    ),
    countries: str | None = typer.Option(
        None,
        "--countries",
        help=(
            "Comma-separated ISO-3 country codes. When omitted, the "
            "slice uses the canonical country list for the question."
        ),
    ),
    start_year: int = typer.Option(
        1950,
        "--start-year",
        help="Inclusive start year for the slice scope.",
    ),
    end_year: int = typer.Option(
        2023,
        "--end-year",
        help="Inclusive end year for the slice scope.",
    ),
    raw_root: Path = typer.Option(
        Path("data/raw"),
        "--raw-root",
        help=(
            "Root directory containing the per-source raw bundles "
            "(data/raw/<source>/)."
        ),
    ),
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        help=(
            "Directory where the slice writes its CSV/HTML outputs "
            "and where the Superset SQLite artifact is rebuilt. "
            "Defaults to data/processed/viz/country-year-chronicle."
        ),
    ),
    superset_db: Path | None = typer.Option(
        None,
        "--superset-db",
        help=(
            "Override the Superset SQLite output path. Defaults to "
            "<data-dir>/superset_viz.sqlite."
        ),
    ),
    no_rebuild_superset_db: bool = typer.Option(
        False,
        "--no-rebuild-superset-db",
        help=(
            "Skip rebuilding the Superset SQLite artifact after the "
            "slice finishes. Useful when the caller plans to run "
            "``viz-build-superset-db`` separately."
        ),
    ),
) -> None:
    """Run a constrained investigation question through the source architecture.

    The slice wires PWT, Maddison, and WDI through the unified
    :class:`SourceIngestRunner`, extracts the
    ``gdp_per_capita`` concept across all three sources via the
    semantic catalog, writes a chart-ready long-form CSV and a
    deterministic static HTML+SVG line chart, and (by default)
    refreshes the read-only Superset-facing SQLite artifact so the
    new table is visible to local Superset dashboards.

    Supported ``--question`` keys are restricted to a small registry
    in :mod:`leaders_db.viz.investigation_slice`; unknown keys fail
    fast rather than silently producing an empty artefact.
    """
    # Map the documented kebab-case CLI form to the canonical
    # underscore form the module exposes.
    question_key = question.replace("-", "_")
    resolved_countries: tuple[str, ...]
    if countries is None:
        # Lazy import: keeps the CLI option metadata surface cheap.
        from ..viz.investigation_slice import SUPPORTED_QUESTIONS

        if question_key not in SUPPORTED_QUESTIONS:
            typer.echo(
                f"Unknown question {question!r}; supported: "
                f"{list(SUPPORTED_QUESTIONS)}",
                err=True,
            )
            raise typer.Exit(code=2)
        resolved_countries = SUPPORTED_QUESTIONS[question_key].display_countries
    else:
        resolved_countries = tuple(
            code.strip().upper() for code in countries.split(",")
            if code.strip()
        )

    # Lazy import: keeps the existing command dispatch lightweight
    # and preserves the package boundary.
    from ..viz.investigation_slice import (
        InvestigationSliceRequest,
        UnknownInvestigationQuestionError,
        run_investigation_slice,
    )
    from ..viz.superset_db import default_viz_data_dir

    resolved_data_dir = (
        data_dir if data_dir is not None else default_viz_data_dir()
    )

    slice_request = InvestigationSliceRequest(
        question_key=question_key,
        countries=resolved_countries,
        start_year=start_year,
        end_year=end_year,
        raw_root=raw_root,
        data_dir=resolved_data_dir,
        superset_db_path=superset_db,
        rebuild_superset_db=not no_rebuild_superset_db,
    )

    try:
        result = run_investigation_slice(slice_request)
    except UnknownInvestigationQuestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(
        f"slice {result.question.question_key!r} for "
        f"{result.countries} ({result.start_year}-{result.end_year}):"
    )
    typer.echo(f"  concept rows: {result.total_concept_rows}")
    for row in result.source_coverage:
        typer.echo(
            f"  source {row.source_id}: requested={row.requested} "
            f"emitted={row.emitted} ready={row.readiness_ready} "
            f"warnings={len(row.warnings)}"
        )
    typer.echo(f"  csv: {result.csv_path}")
    typer.echo(f"  html: {result.html_path}")
    if result.superset_db_path is not None:
        typer.echo(
            f"  superset sqlite: {result.superset_db_path} "
            f"(tables: {', '.join(result.superset_db_tables)})"
        )
    else:
        typer.echo(
            "  superset sqlite: skipped (viz_country_year_metrics.csv "
            "not present; run a chronicle build first)"
        )


def _load_query_spec(path: Path) -> QuerySpec:
    if not path.is_file():
        raise typer.BadParameter(f"query spec does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        normalized = _normalize_query_spec_payload(raw)
        return QuerySpec.model_validate(normalized)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"query spec is not valid JSON: {exc}") from exc
    except ValidationError as exc:
        raise typer.BadParameter(f"query spec failed validation: {exc}") from exc


def _normalize_query_spec_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept the compact Increment 3 spec form and expand to QuerySpec.

    The documented user/agent-friendly form is intentionally terse:
    ``metric``, top-level ``aggregation`` / ``group_by``, and a filter map.
    Internally we keep the richer Increment 1 Pydantic contract.
    """
    payload = dict(raw)
    metric_id = payload.pop("metric", None)
    if metric_id is not None and "metric_ids" not in payload:
        payload["metric_ids"] = [metric_id]
    metric_ids = tuple(payload.get("metric_ids") or [])
    if not metric_ids:
        raise typer.BadParameter("query spec requires 'metric' or 'metric_ids'")

    if "grain" not in payload:
        registry = get_metric_registry()
        first_metric = registry.get(str(metric_ids[0]))
        if first_metric is None:
            raise typer.BadParameter(f"unknown metric: {metric_ids[0]}")
        payload["grain"] = first_metric.grain.value

    aggregation = payload.get("aggregation", AggregationKind.NONE.value)
    if isinstance(aggregation, str):
        payload["aggregation"] = {
            "kind": aggregation,
            "group_by": payload.pop("group_by", []),
        }

    filters = payload.get("filters", [])
    if isinstance(filters, dict):
        payload["filters"] = [
            {"field": field, "operator": FilterOperator.EQ.value, "value": value}
            for field, value in filters.items()
        ]

    time_range = payload.get("time_range")
    if isinstance(time_range, list | tuple) and len(time_range) == 2:
        payload["time_range"] = {
            "start_year": time_range[0],
            "end_year": time_range[1],
        }

    return payload


__all__ = [
    "viz_build_growth_tables_cmd",
    "viz_build_superset_db_cmd",
    "viz_metrics_cmd",
    "viz_query_cmd",
    "viz_run_investigation_slice_cmd",
]
