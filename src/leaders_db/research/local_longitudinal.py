"""Auditable longitudinal summaries for Local Evidence Package v3."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from .local_prior_schema import LocalPriorFact

LONGITUDINAL_TRANSFORM_VERSION = "local_longitudinal_v1"


class LocalLongitudinalSignal(BaseModel):
    """One reconstructable indicator summary with explicit limitations."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    field_key: str
    unit: str | None
    scale: str | None
    target_year: int
    target_value: float | None
    changes: dict[str, float | None]
    pre_accession_trend_per_year: float | None
    tenure_trend_per_year: float | None
    tenure_minus_inherited_trend: float | None
    recent_three_year_trend_per_year: float | None
    acceleration_vs_tenure_trend: float | None
    tenure_average: float | None
    cumulative_tenure_value: float | None
    volatility: float | None
    observation_count: int
    coverage_ratio: float
    observed_years: tuple[int, ...]
    source_observation_ids: tuple[str, ...]
    source_uncertainty: tuple[dict[str, Any], ...]
    formula: str
    transformation_version: str = LONGITUDINAL_TRANSFORM_VERSION
    expected_policy_lag: str
    causal_distance_warning: str = (
        "Country-level trajectory is contextual and may be causally distant from ruler action."
    )
    attribution_limitation: str = (
        "No derived signal automatically establishes ruler credit, blame, or a score."
    )


def derive_longitudinal_signals(
    facts: Sequence[LocalPriorFact | dict[str, Any]],
) -> tuple[LocalLongitudinalSignal, ...]:
    grouped: dict[str, list[LocalPriorFact]] = defaultdict(list)
    for raw_fact in facts:
        fact = (
            raw_fact
            if isinstance(raw_fact, LocalPriorFact)
            else LocalPriorFact.model_validate(raw_fact)
        )
        if isinstance(fact.value, bool) or not isinstance(fact.value, int | float):
            continue
        if not math.isfinite(float(fact.value)):
            continue
        grouped[fact.field_key].append(fact)

    signals: list[LocalLongitudinalSignal] = []
    for field_key, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item.year)
        target_rows = [item for item in rows if item.period_role == "target"]
        if not target_rows:
            continue
        index = len(signals) + 1
        target_year = max(item.year for item in target_rows)
        values_by_year = {item.year: float(item.value) for item in rows}
        target_value = values_by_year.get(target_year)
        pre_rows = [item for item in rows if item.period_role == "pre_accession"]
        tenure_rows = [item for item in rows if item.period_role in {"tenure", "target"}]
        pre_trend = _slope(pre_rows)
        tenure_trend = _slope(tenure_rows)
        recent_trend = _slope([item for item in tenure_rows if item.year >= target_year - 3])
        signals.append(
            LocalLongitudinalSignal(
                signal_id=f"LS{index:03d}",
                field_key=field_key,
                unit=_one_or_none(item.unit for item in rows),
                scale=_one_or_none(item.scale for item in rows),
                target_year=target_year,
                target_value=target_value,
                changes={
                    f"{years}_year": _change(values_by_year, target_year, years)
                    for years in (1, 3, 5, 10)
                },
                pre_accession_trend_per_year=pre_trend,
                tenure_trend_per_year=tenure_trend,
                tenure_minus_inherited_trend=(
                    None if pre_trend is None or tenure_trend is None else tenure_trend - pre_trend
                ),
                recent_three_year_trend_per_year=recent_trend,
                acceleration_vs_tenure_trend=(
                    None
                    if recent_trend is None or tenure_trend is None
                    else recent_trend - tenure_trend
                ),
                tenure_average=(
                    statistics.fmean(float(item.value) for item in tenure_rows)
                    if tenure_rows
                    else None
                ),
                cumulative_tenure_value=_cumulative_value(field_key, tenure_rows),
                volatility=(
                    statistics.pstdev(float(item.value) for item in tenure_rows)
                    if len(tenure_rows) >= 2
                    else None
                ),
                observation_count=len(rows),
                coverage_ratio=len({item.year for item in rows})
                / (max(item.year for item in rows) - min(item.year for item in rows) + 1),
                observed_years=tuple(item.year for item in rows),
                source_observation_ids=tuple(
                    dict.fromkeys(
                        observation_id
                        for item in rows
                        for observation_id in item.source_observation_ids
                    )
                ),
                source_uncertainty=tuple(
                    item.uncertainty for item in rows if item.uncertainty is not None
                ),
                formula=(
                    "changes[target_n]=value(target_year)-value(target_year-n), exact years only; "
                    "trends=ordinary-least-squares slope(value~year); tenure_average=arithmetic "
                    "mean; volatility=population standard deviation"
                ),
                expected_policy_lag=_expected_policy_lag(field_key),
            )
        )
    return tuple(signals)


def _change(values_by_year: dict[int, float], target_year: int, years: int) -> float | None:
    target = values_by_year.get(target_year)
    baseline = values_by_year.get(target_year - years)
    return None if target is None or baseline is None else target - baseline


def _slope(rows: Sequence[LocalPriorFact]) -> float | None:
    if len(rows) < 2:
        return None
    years = [float(item.year) for item in rows]
    values = [float(item.value) for item in rows]
    mean_year = statistics.fmean(years)
    mean_value = statistics.fmean(values)
    denominator = sum((year - mean_year) ** 2 for year in years)
    if denominator == 0:
        return None
    return (
        sum(
            (year - mean_year) * (value - mean_value)
            for year, value in zip(years, values, strict=True)
        )
        / denominator
    )


def _cumulative_value(field_key: str, rows: Sequence[LocalPriorFact]) -> float | None:
    if not (
        field_key.endswith(("_events", "_fatalities")) or field_key == "military_spend_constant_usd"
    ):
        return None
    return sum(float(item.value) for item in rows)


def _expected_policy_lag(field_key: str) -> str:
    if field_key.endswith(("_events", "_fatalities")):
        return "same-year exposure; attribution requires dated actor evidence"
    if field_key.startswith("military_spend"):
        return "budget decisions commonly precede observed expenditure by 0-2 years"
    if field_key in {"life_expectancy", "under5_mortality", "hdi"}:
        return "multi-year outcome lag; typically 2-10 years"
    return "indicator-specific lag not yet configured"


def _one_or_none(values: Sequence[str | None] | Any) -> str | None:
    distinct = {value for value in values if value is not None}
    return next(iter(distinct)) if len(distinct) == 1 else None


__all__ = [
    "LONGITUDINAL_TRANSFORM_VERSION",
    "LocalLongitudinalSignal",
    "derive_longitudinal_signals",
]
