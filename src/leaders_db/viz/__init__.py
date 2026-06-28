"""Read-only semantic query contracts for visualization consumers."""

from __future__ import annotations

from .concept_bridge import (
    ConceptCoverageDiagnostic,
    ConceptMetricMapping,
    ConceptMetricPublishResult,
    concept_metric_mappings,
    publish_concept_metrics,
)
from .economic_trends import (
    ECONOMIC_TREND_CONCEPT_KEYS,
    ECONOMIC_TRENDS_CSV_NAME,
    EconomicTrendRequest,
    EconomicTrendResult,
    build_economic_trend_table,
    write_economic_trend_csv,
)
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
    "ECONOMIC_TRENDS_CSV_NAME",
    "ECONOMIC_TREND_CONCEPT_KEYS",
    "INVESTIGATION_CSV_COLUMNS",
    "SUPPORTED_QUESTIONS",
    "SUPPORTED_QUESTION_KEYS",
    "VIZ_OUTPUT_REQUIRED_COLUMNS",
    "AggregationKind",
    "AggregationSpec",
    "ConceptCoverageDiagnostic",
    "ConceptMetricMapping",
    "ConceptMetricPublishResult",
    "CsvVizDataProvider",
    "EconomicTrendRequest",
    "EconomicTrendResult",
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
    "build_economic_trend_table",
    "build_growth_tables",
    "build_regime_year_aggregates",
    "build_superset_sqlite_db",
    "concept_metric_mappings",
    "default_superset_db_path",
    "default_viz_data_dir",
    "execute_query",
    "get_metric_registry",
    "initial_metric_definitions",
    "lookup_metric",
    "publish_concept_metrics",
    "run_investigation_slice",
    "write_economic_trend_csv",
]
