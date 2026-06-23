"""Generic read-only execution over visualization CSV fact tables."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from ..paths import processed_dir
from .metrics import lookup_metric
from .query_spec import AggregationKind, FilterOperator, QuerySpec, TransformKind


class VizDataProvider(Protocol):
    """Read-only provider boundary for semantic query execution."""

    def country_year_metrics(self) -> pd.DataFrame:
        """Return long-form country-year metric facts."""


class CsvVizDataProvider:
    """Read visualization CSV artifacts from ``data/processed/viz``.

    The provider is deliberately small and read-only. It lets agents and
    tests execute semantic queries without requiring Superset, a browser, or
    database write permissions.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (
            base_dir
            if base_dir is not None
            else processed_dir("viz") / "country-year-chronicle"
        )

    def country_year_metrics(self) -> pd.DataFrame:
        """Load ``viz_country_year_metrics.csv`` from the provider base dir."""
        path = self.base_dir / "viz_country_year_metrics.csv"
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing visualization fact table: {path}. Run the Chronicle "
                "analytic export first or pass --data-dir to viz-query."
            )
        return pd.read_csv(path)


def execute_query(spec: QuerySpec, provider: VizDataProvider) -> pd.DataFrame:
    """Execute a generic semantic query against a read-only provider.

    Increment 3 intentionally supports the core ``country_year`` fact table
    first. It does not add bespoke tables for each dashboard question; grouped
    outputs such as population by regime are derived from the same generic
    filter/aggregate path.
    """
    if spec.grain.value != "country_year":
        raise NotImplementedError(
            "viz-query currently supports country_year metrics only"
        )
    _reject_unsupported_transforms(spec)

    frame = provider.country_year_metrics().copy()
    _require_columns(frame, ["metric_id", "value"])
    frame = frame[frame["metric_id"].isin(spec.metric_ids)]

    if spec.time_range is not None:
        _require_columns(frame, ["year"])
        frame = frame[
            (frame["year"] >= spec.time_range.start_year)
            & (frame["year"] <= spec.time_range.end_year)
        ]

    for filter_spec in spec.filters:
        _require_columns(frame, [filter_spec.field])
        frame = _apply_filter(frame, filter_spec.field, filter_spec.operator, filter_spec.value)

    result = _aggregate(frame, spec)
    return result.reset_index(drop=True)


def _reject_unsupported_transforms(spec: QuerySpec) -> None:
    unsupported = [
        transform.kind.value
        for transform in spec.transforms
        if transform.kind != TransformKind.IDENTITY
    ]
    if unsupported:
        raise NotImplementedError(
            "viz-query transform execution is not implemented yet; "
            f"unsupported transforms requested: {unsupported}"
        )


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"visualization fact table is missing required columns: {missing}")


def _apply_filter(
    frame: pd.DataFrame,
    field: str,
    operator: FilterOperator,
    value: object,
) -> pd.DataFrame:
    if operator == FilterOperator.EQ:
        return frame[frame[field] == value]
    if operator == FilterOperator.IN:
        if not isinstance(value, list | tuple | set):
            raise ValueError(f"filter '{field}' with operator 'in' requires a list value")
        return frame[frame[field].isin(value)]
    if operator == FilterOperator.GTE:
        return frame[frame[field] >= value]
    if operator == FilterOperator.LTE:
        return frame[frame[field] <= value]
    raise ValueError(f"unsupported filter operator: {operator.value}")


def _aggregate(frame: pd.DataFrame, spec: QuerySpec) -> pd.DataFrame:
    aggregation = spec.aggregation.kind
    group_by = list(spec.aggregation.group_by)
    grouping_columns = [*group_by, "metric_id"]
    _require_columns(frame, group_by)

    if aggregation == AggregationKind.NONE:
        return _attach_metric_labels(frame)

    if aggregation == AggregationKind.COUNT:
        grouped = frame.groupby(grouping_columns, dropna=False).size()
    elif aggregation == AggregationKind.SUM:
        grouped = frame.groupby(grouping_columns, dropna=False)["value"].sum()
    elif aggregation == AggregationKind.MEAN:
        grouped = frame.groupby(grouping_columns, dropna=False)["value"].mean()
    elif aggregation == AggregationKind.MEDIAN:
        grouped = frame.groupby(grouping_columns, dropna=False)["value"].median()
    elif aggregation == AggregationKind.MIN:
        grouped = frame.groupby(grouping_columns, dropna=False)["value"].min()
    elif aggregation == AggregationKind.MAX:
        grouped = frame.groupby(grouping_columns, dropna=False)["value"].max()
    else:
        raise NotImplementedError(
            f"viz-query aggregation '{aggregation.value}' is not implemented yet"
        )

    result = grouped.reset_index(name="value")
    result["aggregation"] = aggregation.value
    return _attach_metric_labels(result)


def _attach_metric_labels(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["metric_label"] = result["metric_id"].map(_metric_label)
    result["value_unit"] = result["metric_id"].map(_metric_unit)
    return result


def _metric_label(metric_id: object) -> str:
    metric = lookup_metric(str(metric_id))
    return metric.label if metric is not None else ""


def _metric_unit(metric_id: object) -> str:
    metric = lookup_metric(str(metric_id))
    return metric.unit if metric is not None and metric.unit is not None else ""


__all__ = ["CsvVizDataProvider", "VizDataProvider", "execute_query"]
