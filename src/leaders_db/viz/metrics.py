"""Metric registry contracts for the visualization semantic layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .query_spec import AggregationKind, TransformKind, VizGrain


class MetricDefinition(BaseModel):
    """Declarative metric metadata; not a calculation implementation."""

    metric_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    grain: VizGrain
    value_column: str = Field(min_length=1)
    unit: str | None = None
    source_tables: tuple[str, ...] = Field(default_factory=tuple)
    required_columns: tuple[str, ...] = Field(default_factory=tuple)
    default_aggregation: AggregationKind = AggregationKind.NONE
    allowed_aggregations: tuple[AggregationKind, ...] = (AggregationKind.NONE,)
    allowed_transforms: tuple[TransformKind, ...] = (TransformKind.IDENTITY,)
    attribution_source_keys: tuple[str, ...] = Field(default_factory=tuple)
    client_matrix_policy: Literal["excluded", "reference_only"] = "excluded"


def initial_metric_definitions() -> tuple[MetricDefinition, ...]:
    """Return the seed metric registry definitions."""
    return (
        MetricDefinition(
            metric_id="score.system_proposed_1_10",
            label="System proposed score",
            grain=VizGrain.CATEGORY_SCORE,
            value_column="system_proposed_score",
            unit="score_1_10",
            source_tables=("ruler_scores",),
            required_columns=("country_iso3", "year", "category_key"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.MEAN),
            allowed_transforms=(TransformKind.IDENTITY,),
        ),
        MetricDefinition(
            metric_id="score.confidence_0_100",
            label="Confidence",
            grain=VizGrain.CATEGORY_SCORE,
            value_column="confidence_score",
            unit="score_0_100",
            source_tables=("validation_results",),
            required_columns=("country_iso3", "year", "category_key"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.MEAN),
            allowed_transforms=(TransformKind.IDENTITY,),
        ),
        MetricDefinition(
            metric_id="score.delta_vs_client",
            label="Delta vs client reference",
            grain=VizGrain.CATEGORY_SCORE,
            value_column="score_delta_vs_client",
            unit="score_points",
            source_tables=("ruler_scores",),
            required_columns=("country_iso3", "year", "category_key"),
            client_matrix_policy="reference_only",
        ),
        MetricDefinition(
            metric_id="chronicle.population",
            label="Population",
            grain=VizGrain.COUNTRY_YEAR,
            value_column="population",
            unit="persons",
            source_tables=("country_year_chronicle",),
            required_columns=("country_iso3", "year"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.SUM),
            allowed_transforms=(TransformKind.IDENTITY,),
            attribution_source_keys=("maddison_project", "wdi", "vdem"),
        ),
        MetricDefinition(
            metric_id="chronicle.gdp_per_capita",
            label="GDP per capita",
            grain=VizGrain.COUNTRY_YEAR,
            value_column="gdp_per_capita",
            unit="source_native",
            source_tables=("country_year_chronicle",),
            required_columns=("country_iso3", "year"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.MEAN),
            allowed_transforms=(TransformKind.IDENTITY,),
            attribution_source_keys=("maddison_project", "wdi", "vdem"),
        ),
        MetricDefinition(
            metric_id="chronicle.gdp",
            label="GDP",
            grain=VizGrain.COUNTRY_YEAR,
            value_column="gdp",
            unit="source_native",
            source_tables=("country_year_chronicle",),
            required_columns=("country_iso3", "year"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.SUM, AggregationKind.MEAN),
            allowed_transforms=(TransformKind.IDENTITY,),
            attribution_source_keys=("maddison_project", "wdi", "vdem"),
        ),
        MetricDefinition(
            metric_id="chronicle.political_regime_bucket",
            label="Political regime bucket",
            grain=VizGrain.COUNTRY_YEAR,
            value_column="political_regime_bucket",
            unit="category",
            source_tables=("country_year_chronicle",),
            required_columns=("country_iso3", "year"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.COUNT),
            allowed_transforms=(TransformKind.IDENTITY,),
            attribution_source_keys=("vdem",),
        ),
        MetricDefinition(
            metric_id="chronicle.existence_status",
            label="Existence status",
            grain=VizGrain.COUNTRY_YEAR,
            value_column="existence_status",
            unit="status",
            source_tables=("country_year_chronicle",),
            required_columns=("country_iso3", "year"),
            allowed_aggregations=(AggregationKind.NONE, AggregationKind.COUNT),
            allowed_transforms=(TransformKind.IDENTITY,),
            attribution_source_keys=("vdem",),
        ),
    )


def get_metric_registry() -> dict[str, MetricDefinition]:
    """Return a fresh ``{metric_id: MetricDefinition}`` seed registry mapping."""
    return {m.metric_id: m for m in initial_metric_definitions()}


def lookup_metric(metric_id: str) -> MetricDefinition | None:
    """Return the ``MetricDefinition`` for ``metric_id`` or ``None`` if unknown."""
    return get_metric_registry().get(metric_id)


__all__ = [
    "MetricDefinition",
    "get_metric_registry",
    "initial_metric_definitions",
    "lookup_metric",
]
