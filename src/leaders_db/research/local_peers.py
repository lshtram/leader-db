"""Transparent multi-definition peer comparisons for longitudinal signals."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .local_longitudinal import LocalLongitudinalSignal

PeerGroupKind = Literal[
    "geographic_region",
    "income_group",
    "regime_type",
    "conflict_exposure",
    "state_capacity_band",
]


class PeerGroupDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PeerGroupKind
    label: str
    peer_iso3s: tuple[str, ...]
    definition_year: int
    definition_basis: str


class PeerChangeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    peer_group_kind: PeerGroupKind
    peer_group_label: str
    horizon: str
    country_change: float | None
    peer_median_change: float | None
    country_minus_peer: float | None
    eligible_peer_count: int
    observed_peer_count: int
    peer_coverage: float
    definition_year: int
    definition_basis: str
    future_information_used: Literal[False] = False


class PeerSensitivitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    horizon: str
    available_group_count: int
    country_minus_peer_min: float | None
    country_minus_peer_max: float | None
    disagreement_warning: str | None


def compare_peer_changes(
    *,
    country_signal: LocalLongitudinalSignal,
    peer_signals: Mapping[str, Sequence[LocalLongitudinalSignal]],
    groups: Sequence[PeerGroupDefinition],
) -> tuple[tuple[PeerChangeComparison, ...], tuple[PeerSensitivitySummary, ...]]:
    comparisons: list[PeerChangeComparison] = []
    for group in groups:
        if group.definition_year > country_signal.target_year:
            raise ValueError("peer definitions cannot use post-target information")
        eligible = tuple(dict.fromkeys(group.peer_iso3s))
        for horizon, country_change in country_signal.changes.items():
            peer_changes = [
                signal.changes[horizon]
                for iso3 in eligible
                for signal in peer_signals.get(iso3, ())
                if signal.field_key == country_signal.field_key
                and signal.target_year == country_signal.target_year
                and signal.changes.get(horizon) is not None
            ]
            median = statistics.median(peer_changes) if peer_changes else None
            comparisons.append(
                PeerChangeComparison(
                    field_key=country_signal.field_key,
                    peer_group_kind=group.kind,
                    peer_group_label=group.label,
                    horizon=horizon,
                    country_change=country_change,
                    peer_median_change=median,
                    country_minus_peer=(
                        None
                        if country_change is None or median is None
                        else country_change - median
                    ),
                    eligible_peer_count=len(eligible),
                    observed_peer_count=len(peer_changes),
                    peer_coverage=(len(peer_changes) / len(eligible) if eligible else 0.0),
                    definition_year=group.definition_year,
                    definition_basis=group.definition_basis,
                )
            )
    summaries = tuple(
        _sensitivity(country_signal.field_key, horizon, comparisons)
        for horizon in country_signal.changes
    )
    return tuple(comparisons), summaries


def _sensitivity(
    field_key: str,
    horizon: str,
    comparisons: Sequence[PeerChangeComparison],
) -> PeerSensitivitySummary:
    values = [
        item.country_minus_peer
        for item in comparisons
        if item.horizon == horizon and item.country_minus_peer is not None
    ]
    disagreement = None
    if values and min(values) < 0 < max(values):
        disagreement = "Peer definitions disagree on whether relative change is favorable."
    return PeerSensitivitySummary(
        field_key=field_key,
        horizon=horizon,
        available_group_count=len(values),
        country_minus_peer_min=min(values) if values else None,
        country_minus_peer_max=max(values) if values else None,
        disagreement_warning=disagreement,
    )


__all__ = [
    "PeerChangeComparison",
    "PeerGroupDefinition",
    "PeerGroupKind",
    "PeerSensitivitySummary",
    "compare_peer_changes",
]
