from __future__ import annotations

import pytest

from leaders_db.research.local_longitudinal import derive_longitudinal_signals
from leaders_db.research.local_prior_schema import LocalPriorFact


def _fact(year: int, value: float, role: str) -> LocalPriorFact:
    return LocalPriorFact(
        year=year,
        field_key="indicator",
        label="Indicator",
        value=value,
        value_type="number",
        source_slugs=["source"],
        source_observation_ids=[f"source:RUS:{year}:indicator"],
        confidence=80,
        period_role=role,
        unit="points",
    )


def test_longitudinal_signal_is_reconstructable_and_does_not_interpolate() -> None:
    signal = derive_longitudinal_signals(
        (
            _fact(1998, 10.0, "pre_accession"),
            _fact(1999, 12.0, "pre_accession"),
            _fact(2000, 20.0, "tenure"),
            _fact(2012, 30.0, "tenure"),
            _fact(2017, 35.0, "tenure"),
            _fact(2019, 38.0, "tenure"),
            _fact(2021, 41.0, "tenure"),
            _fact(2022, 43.0, "target"),
        )
    )[0]

    assert signal.target_value == 43.0
    assert signal.changes == {
        "1_year": 2.0,
        "3_year": 5.0,
        "5_year": 8.0,
        "10_year": 13.0,
    }
    assert signal.pre_accession_trend_per_year == pytest.approx(2.0)
    assert signal.tenure_trend_per_year is not None
    assert signal.tenure_minus_inherited_trend is not None
    assert signal.recent_three_year_trend_per_year is not None
    assert signal.acceleration_vs_tenure_trend is not None
    assert signal.coverage_ratio == pytest.approx(8 / 25)
    assert signal.cumulative_tenure_value is None
    assert signal.observed_years[-1] == 2022
    assert len(signal.source_observation_ids) == 8
    assert "exact years only" in signal.formula


def test_longitudinal_signal_leaves_missing_exact_change_null() -> None:
    signal = derive_longitudinal_signals(
        (_fact(2020, 10.0, "tenure"), _fact(2022, 15.0, "target"))
    )[0]

    assert signal.changes == {
        "1_year": None,
        "3_year": None,
        "5_year": None,
        "10_year": None,
    }


def test_longitudinal_signal_skips_series_without_target_observation() -> None:
    signals = derive_longitudinal_signals(
        (_fact(2017, 10.0, "tenure"), _fact(2018, 12.0, "tenure"))
    )

    assert signals == ()


def test_longitudinal_signal_excludes_post_target_context() -> None:
    signal = derive_longitudinal_signals(
        (
            _fact(2021, 10.0, "tenure"),
            _fact(2022, 12.0, "target"),
            _fact(2023, 99.0, "post_target"),
        )
    )[0]

    assert signal.target_value == 12.0
    assert signal.observation_count == 2
    assert signal.observed_years == (2021, 2022)
    assert signal.tenure_average == pytest.approx(11.0)
