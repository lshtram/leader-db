"""Read-only semantic query contracts for visualization consumers."""

from __future__ import annotations

from .executor import CsvVizDataProvider, VizDataProvider, execute_query
from .metrics import (
    MetricDefinition,
    get_metric_registry,
    initial_metric_definitions,
    lookup_metric,
)
from .output_contract import VIZ_OUTPUT_REQUIRED_COLUMNS
from .query_spec import (
    AggregationKind,
    AggregationSpec,
    FilterOperator,
    FilterSpec,
    QuerySpec,
    TimeRange,
    TransformKind,
    TransformSpec,
    VizGrain,
)
from .superset_db import (
    SupersetDbBuildResult,
    build_superset_sqlite_db,
    default_superset_db_path,
    default_viz_data_dir,
)

__all__ = [
    "VIZ_OUTPUT_REQUIRED_COLUMNS",
    "AggregationKind",
    "AggregationSpec",
    "CsvVizDataProvider",
    "FilterOperator",
    "FilterSpec",
    "MetricDefinition",
    "QuerySpec",
    "SupersetDbBuildResult",
    "TimeRange",
    "TransformKind",
    "TransformSpec",
    "VizDataProvider",
    "VizGrain",
    "build_superset_sqlite_db",
    "default_superset_db_path",
    "default_viz_data_dir",
    "execute_query",
    "get_metric_registry",
    "initial_metric_definitions",
    "lookup_metric",
]
