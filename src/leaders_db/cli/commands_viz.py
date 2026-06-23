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


__all__ = ["viz_build_superset_db_cmd", "viz_metrics_cmd", "viz_query_cmd"]
