"""Pydantic query-spec contracts for visualization requests."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class VizGrain(str, Enum):
    """Supported semantic grains for chart-ready outputs."""

    COUNTRY_YEAR = "country_year"
    RULER_YEAR = "ruler_year"
    CATEGORY_SCORE = "category_score"


class AggregationKind(str, Enum):
    """Supported aggregation vocabulary."""

    NONE = "none"
    COUNT = "count"
    SUM = "sum"
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    WEIGHTED_MEAN = "weighted_mean"


class TransformKind(str, Enum):
    """Supported transform vocabulary."""

    IDENTITY = "identity"
    ROLLING_MEAN = "rolling_mean"
    YEAR_OVER_YEAR_CHANGE = "year_over_year_change"
    INDEX_TO_BASE_YEAR = "index_to_base_year"
    PER_CAPITA = "per_capita"
    LOG10 = "log10"
    MIN_MAX_NORMALIZE = "min_max_normalize"


class FilterOperator(str, Enum):
    """Small filter vocabulary for semantic query specs."""

    EQ = "eq"
    IN = "in"
    GTE = "gte"
    LTE = "lte"


class TimeRange(BaseModel):
    """Inclusive year range for a semantic query."""

    start_year: int = Field(ge=1900, le=2100)
    end_year: int = Field(ge=1900, le=2100)

    @model_validator(mode="after")
    def _end_year_not_before_start(self) -> TimeRange:
        if self.end_year < self.start_year:
            raise ValueError(
                f"end_year ({self.end_year}) must be >= start_year ({self.start_year})"
            )
        return self


class FilterSpec(BaseModel):
    """One field-level filter in a semantic query."""

    field: str = Field(min_length=1)
    operator: FilterOperator
    value: Any


class AggregationSpec(BaseModel):
    """Requested aggregation and grouping fields."""

    kind: AggregationKind = AggregationKind.NONE
    group_by: tuple[str, ...] = Field(default_factory=tuple)
    weight_metric_id: str | None = None

    @model_validator(mode="after")
    def _weighted_mean_requires_weight_metric_id(self) -> AggregationSpec:
        if self.kind == AggregationKind.WEIGHTED_MEAN and self.weight_metric_id is None:
            raise ValueError(
                "AggregationSpec(kind='weighted_mean') requires weight_metric_id"
            )
        return self


class TransformSpec(BaseModel):
    """Requested transform for one or more metrics."""

    kind: TransformKind = TransformKind.IDENTITY
    metric_ids: tuple[str, ...] = Field(default_factory=tuple)
    window: int | None = Field(default=None, ge=1)
    base_year: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def _per_capita_requires_explicit_pairing(self) -> TransformSpec:
        if self.kind == TransformKind.PER_CAPITA:
            raise ValueError(
                "TransformSpec(kind='per_capita') is not supported yet; "
                "per_capita requires explicit compatible numerator/denominator "
                "pairing fields and must not be inferred silently"
            )
        return self

    @model_validator(mode="after")
    def _metric_ids_must_exist_in_registry(self) -> TransformSpec:
        if not self.metric_ids:
            return self
        from .metrics import lookup_metric

        for metric_id in self.metric_ids:
            if lookup_metric(metric_id) is None:
                raise ValueError(
                    f"TransformSpec.metric_ids contains unknown metric_id "
                    f"'{metric_id}' (not present in metric registry)"
                )
        return self

    @model_validator(mode="after")
    def _transform_requires_arguments(self) -> TransformSpec:
        if self.kind == TransformKind.ROLLING_MEAN and self.window is None:
            raise ValueError("TransformSpec(kind='rolling_mean') requires window")
        if self.kind == TransformKind.INDEX_TO_BASE_YEAR and self.base_year is None:
            raise ValueError("TransformSpec(kind='index_to_base_year') requires base_year")
        return self


class QuerySpec(BaseModel):
    """Top-level read-only semantic query contract."""

    grain: VizGrain
    metric_ids: tuple[str, ...] = Field(min_length=1)
    time_range: TimeRange | None = None
    filters: tuple[FilterSpec, ...] = Field(default_factory=tuple)
    aggregation: AggregationSpec = Field(default_factory=AggregationSpec)
    transforms: tuple[TransformSpec, ...] = Field(default_factory=tuple)
    include_provenance: bool = True
    include_attribution: bool = True

    @model_validator(mode="after")
    def _validate_metrics_grain_and_capabilities(self) -> QuerySpec:
        from .metrics import lookup_metric

        resolved = []
        for metric_id in self.metric_ids:
            metric = lookup_metric(metric_id)
            if metric is None:
                raise ValueError(
                    f"Unknown metric_id '{metric_id}' (not present in metric registry)"
                )
            if metric.grain != self.grain:
                raise ValueError(
                    f"Metric '{metric_id}' has grain '{metric.grain.value}'; "
                    f"QuerySpec requested grain '{self.grain.value}'"
                )
            resolved.append(metric)
        if self.aggregation.kind == AggregationKind.WEIGHTED_MEAN:
            weight_id = self.aggregation.weight_metric_id
            assert weight_id is not None
            weight = lookup_metric(weight_id)
            if weight is None:
                raise ValueError(
                    f"Unknown weight_metric_id '{weight_id}' (not present in metric registry)"
                )
            if weight.client_matrix_policy == "reference_only":
                raise ValueError(
                    f"weight_metric_id '{weight_id}' is a reference_only metric; "
                    f"client-matrix values cannot feed evidence-like aggregation roles"
                )
        for metric in resolved:
            if self.aggregation.kind not in metric.allowed_aggregations:
                allowed = [a.value for a in metric.allowed_aggregations]
                raise ValueError(
                    f"Aggregation '{self.aggregation.kind.value}' is not allowed "
                    f"for metric '{metric.metric_id}' (allowed: {allowed})"
                )
        for transform in self.transforms:
            self._assert_transform_targets_are_selected(transform)
            targets = transform.metric_ids if transform.metric_ids else self.metric_ids
            for metric in resolved:
                if metric.metric_id not in targets:
                    continue
                if transform.kind not in metric.allowed_transforms:
                    allowed = [t.value for t in metric.allowed_transforms]
                    raise ValueError(
                        f"Transform '{transform.kind.value}' is not allowed "
                        f"for metric '{metric.metric_id}' (allowed: {allowed})"
                    )
        return self

    def _assert_transform_targets_are_selected(self, transform: TransformSpec) -> None:
        if not transform.metric_ids:
            return
        selected = set(self.metric_ids)
        non_selected = [m for m in transform.metric_ids if m not in selected]
        if non_selected:
            raise ValueError(
                f"TransformSpec(metric_ids={list(transform.metric_ids)!r}) targets "
                f"metrics not selected by QuerySpec (selected: {list(self.metric_ids)}); "
                f"non_selected: {non_selected}"
            )


__all__ = [
    "AggregationKind",
    "AggregationSpec",
    "FilterOperator",
    "FilterSpec",
    "QuerySpec",
    "TimeRange",
    "TransformKind",
    "TransformSpec",
    "VizGrain",
]
