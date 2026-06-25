"""Read-only semantic query contracts for visualization consumers."""

from __future__ import annotations

from .executor import CsvVizDataProvider, VizDataProvider, execute_query
from .investigation_slice import (
    INVESTIGATION_CSV_COLUMNS,
    SUPPORTED_QUESTION_KEYS,
    SUPPORTED_QUESTIONS,
    InvestigationQuestion,
    InvestigationSliceRequest,
    InvestigationSliceResult,
    SourceCoverageRow,
    UnknownInvestigationQuestionError,
    run_investigation_slice,
)
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
from .superset_growth_tables import (
    GrowthTableBuildResult,
    build_country_latest_metrics,
    build_country_year_growth,
    build_growth_tables,
    build_regime_year_aggregates,
)

__all__ = [
    "INVESTIGATION_CSV_COLUMNS",
    "SUPPORTED_QUESTIONS",
    "SUPPORTED_QUESTION_KEYS",
    "VIZ_OUTPUT_REQUIRED_COLUMNS",
    "AggregationKind",
    "AggregationSpec",
    "CsvVizDataProvider",
    "FilterOperator",
    "FilterSpec",
    "GrowthTableBuildResult",
    "InvestigationQuestion",
    "InvestigationSliceRequest",
    "InvestigationSliceResult",
    "MetricDefinition",
    "QuerySpec",
    "SourceCoverageRow",
    "SupersetDbBuildResult",
    "TimeRange",
    "TransformKind",
    "TransformSpec",
    "UnknownInvestigationQuestionError",
    "VizDataProvider",
    "VizGrain",
    "build_country_latest_metrics",
    "build_country_year_growth",
    "build_growth_tables",
    "build_regime_year_aggregates",
    "build_superset_sqlite_db",
    "default_superset_db_path",
    "default_viz_data_dir",
    "execute_query",
    "get_metric_registry",
    "initial_metric_definitions",
    "lookup_metric",
    "run_investigation_slice",
]
