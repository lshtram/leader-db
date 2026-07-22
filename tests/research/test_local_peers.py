from __future__ import annotations

import pytest

from leaders_db.research.local_longitudinal import LocalLongitudinalSignal
from leaders_db.research.local_peers import PeerGroupDefinition, compare_peer_changes


def _signal(change: float) -> LocalLongitudinalSignal:
    return LocalLongitudinalSignal(
        signal_id="LS001",
        field_key="indicator",
        unit="points",
        scale=None,
        target_year=2022,
        target_value=20.0,
        changes={"1_year": change, "3_year": None, "5_year": None, "10_year": None},
        pre_accession_trend_per_year=None,
        tenure_trend_per_year=None,
        tenure_minus_inherited_trend=None,
        recent_three_year_trend_per_year=None,
        acceleration_vs_tenure_trend=None,
        tenure_average=None,
        cumulative_tenure_value=None,
        volatility=None,
        observation_count=2,
        coverage_ratio=1.0,
        observed_years=(2021, 2022),
        source_observation_ids=("obs",),
        source_uncertainty=(),
        formula="fixture",
        expected_policy_lag="fixture",
    )


def test_peer_comparison_preserves_disagreement_and_coverage() -> None:
    comparisons, sensitivity = compare_peer_changes(
        country_signal=_signal(5.0),
        peer_signals={"AAA": (_signal(1.0),), "BBB": (_signal(3.0),)},
        groups=(
            PeerGroupDefinition(
                kind="geographic_region",
                label="Region",
                peer_iso3s=("AAA", "BBB", "CCC"),
                definition_year=2000,
                definition_basis="classification fixed at accession",
            ),
            PeerGroupDefinition(
                kind="income_group",
                label="Income",
                peer_iso3s=("AAA",),
                definition_year=2000,
                definition_basis="classification fixed at accession",
            ),
        ),
    )

    one_year = [item for item in comparisons if item.horizon == "1_year"]
    assert one_year[0].peer_median_change == 2.0
    assert one_year[0].country_minus_peer == 3.0
    assert one_year[0].peer_coverage == pytest.approx(2 / 3)
    assert one_year[0].future_information_used is False
    assert sensitivity[0].available_group_count == 2


def test_peer_definition_rejects_future_information() -> None:
    with pytest.raises(ValueError, match="post-target"):
        compare_peer_changes(
            country_signal=_signal(5.0),
            peer_signals={},
            groups=(
                PeerGroupDefinition(
                    kind="regime_type",
                    label="Future-defined",
                    peer_iso3s=(),
                    definition_year=2023,
                    definition_basis="invalid fixture",
                ),
            ),
        )
