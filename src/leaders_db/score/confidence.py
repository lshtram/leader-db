"""Confidence score formula and helpers (requirement §11).

The formula is fixed and normative:

    confidence = 0.35 * agreement
               + 0.25 * authority
               + 0.25 * specificity
               + 0.15 * temporal_fit

The four component values use the 0/20/40/60/80/100 scales from §11 and
are clipped to that range at the boundary. The output is clipped to the
closed integer interval [0, 100] and banded per §11:

    85–100 high, 70–84 good, 50–69 medium, 30–49 low, 0–29 unreliable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..llm.schemas import ScoreBand, band_for_confidence

# The fixed weights (REQ-CONF-001). Do not import these from anywhere else.
WEIGHT_AGREEMENT: float = 0.35
WEIGHT_AUTHORITY: float = 0.25
WEIGHT_SPECIFICITY: float = 0.25
WEIGHT_TEMPORAL_FIT: float = 0.15

# Sanity invariant: weights must sum to 1.0 (a small epsilon handles float math).
assert abs(WEIGHT_AGREEMENT + WEIGHT_AUTHORITY + WEIGHT_SPECIFICITY + WEIGHT_TEMPORAL_FIT - 1.0) < 1e-9


@dataclass(frozen=True)
class ConfidenceWeights:
    """Configurable weights for the confidence formula.

    The default values are the §11 normative weights. Tests and experiments
    may construct other instances; production code should use
    :func:`default_weights` so the formula is always the same.
    """

    agreement: float = WEIGHT_AGREEMENT
    authority: float = WEIGHT_AUTHORITY
    specificity: float = WEIGHT_SPECIFICITY
    temporal_fit: float = WEIGHT_TEMPORAL_FIT

    def __post_init__(self) -> None:
        total = self.agreement + self.authority + self.specificity + self.temporal_fit
        if not (0.999 <= total <= 1.001):
            raise ValueError(
                f"ConfidenceWeights must sum to 1.0 (got {total:.4f}); "
                f"do not invent alternative weightings"
            )


def default_weights() -> ConfidenceWeights:
    """Return the §11 normative :class:`ConfidenceWeights`."""
    return ConfidenceWeights()


@dataclass(frozen=True)
class ConfidenceInputs:
    """The four §11 component scores, each on the closed integer interval [0, 100]."""

    agreement: int
    authority: int
    specificity: int
    temporal_fit: int

    def __post_init__(self) -> None:
        for name in ("agreement", "authority", "specificity", "temporal_fit"):
            value = getattr(self, name)
            if not 0 <= value <= 100:
                raise ValueError(
                    f"ConfidenceInputs.{name} must be in 0..100 (got {value})"
                )


def compute_confidence(
    inputs: ConfidenceInputs,
    weights: ConfidenceWeights | None = None,
) -> int:
    """Compute the §11 confidence score for the given component values.

    Parameters
    ----------
    inputs:
        The four component scores (each 0..100) per requirement §11.
    weights:
        Optional weights override. Defaults to :func:`default_weights`
        (the §11 normative weighting).

    Returns
    -------
    int
        The weighted score clipped to the closed integer interval [0, 100].
    """
    w = weights or default_weights()
    raw = (
        w.agreement * inputs.agreement
        + w.authority * inputs.authority
        + w.specificity * inputs.specificity
        + w.temporal_fit * inputs.temporal_fit
    )
    return _clip_0_100(round(raw))


def band_for(inputs: ConfidenceInputs) -> ScoreBand:
    """Convenience: compute the confidence and return its band."""
    return band_for_confidence(compute_confidence(inputs))


def _clip_0_100(x: int) -> int:
    if x < 0:
        return 0
    if x > 100:
        return 100
    return x
