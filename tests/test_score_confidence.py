"""Confidence formula tests (requirement §11).

The fixed weights 0.35 / 0.25 / 0.25 / 0.15 are normative; these tests
pin the formula so a one-off script cannot silently introduce a different
weighting. The cases cover:

- All components at maximum → confidence 100.
- All components at zero → confidence 0.
- A canonical "two agree, one missing, decent authority" ruler-year
  falls in the ``good`` band per §11.
- The default weights sum to 1.0 within float tolerance.
- Custom weights are accepted but the sum must still be 1.0.
"""

from __future__ import annotations

import pytest

from leaders_db.llm.schemas import ScoreBand
from leaders_db.score.confidence import (
    WEIGHT_AGREEMENT,
    WEIGHT_AUTHORITY,
    WEIGHT_SPECIFICITY,
    WEIGHT_TEMPORAL_FIT,
    ConfidenceInputs,
    ConfidenceWeights,
    compute_confidence,
    default_weights,
)


def test_default_weights_match_section_11() -> None:
    w = default_weights()
    assert w.agreement == pytest.approx(0.35, abs=1e-9)
    assert w.authority == pytest.approx(0.25, abs=1e-9)
    assert w.specificity == pytest.approx(0.25, abs=1e-9)
    assert w.temporal_fit == pytest.approx(0.15, abs=1e-9)


def test_module_constants_match_section_11() -> None:
    assert WEIGHT_AGREEMENT == 0.35
    assert WEIGHT_AUTHORITY == 0.25
    assert WEIGHT_SPECIFICITY == 0.25
    assert WEIGHT_TEMPORAL_FIT == 0.15


def test_all_max_components_give_confidence_100() -> None:
    out = compute_confidence(
        ConfidenceInputs(agreement=100, authority=100, specificity=100, temporal_fit=100)
    )
    assert out == 100


def test_all_zero_components_give_confidence_0() -> None:
    out = compute_confidence(
        ConfidenceInputs(agreement=0, authority=0, specificity=0, temporal_fit=0)
    )
    assert out == 0


def test_canonical_case_in_good_band() -> None:
    """Two sources agree, decent authority and specificity, exact year."""
    out = compute_confidence(
        ConfidenceInputs(agreement=80, authority=80, specificity=80, temporal_fit=100)
    )
    # 0.35*80 + 0.25*80 + 0.25*80 + 0.15*100 = 28 + 20 + 20 + 15 = 83
    assert out == 83
    band = ScoreBand.GOOD
    from leaders_db.llm.schemas import band_for_confidence

    assert band_for_confidence(out) == band


def test_inputs_reject_out_of_range() -> None:
    with pytest.raises(ValueError):
        ConfidenceInputs(agreement=-1, authority=50, specificity=50, temporal_fit=50)
    with pytest.raises(ValueError):
        ConfidenceInputs(agreement=101, authority=50, specificity=50, temporal_fit=50)


def test_custom_weights_rejected_when_not_summing_to_one() -> None:
    with pytest.raises(ValueError):
        ConfidenceWeights(agreement=0.5, authority=0.5, specificity=0.5, temporal_fit=0.5)


def test_compute_confidence_is_clipped() -> None:
    # Force a > 100 result by passing components above 100 (rejected by the
    # model) so this is a no-op test that documents the contract.
    with pytest.raises(ValueError):
        ConfidenceInputs(agreement=150, authority=80, specificity=80, temporal_fit=80)
