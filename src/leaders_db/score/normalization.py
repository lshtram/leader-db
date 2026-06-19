"""Score normalization helpers.

Indicators arrive on a heterogeneous set of scales (0–1, 0–10, percentage,
percentile rank, raw counts). Before any per-category scoring module can
combine them, they must be projected onto a common scale. This module
contains the small, side-effect-free, fully typed helpers used by the
category modules.

Conventions:

- 0–1 scale: continuous, e.g. V-Dem indices, percentile ranks.
- 0–10 scale: integer, the scoring scale the client matrix uses.
- Percentage: 0–100 scale (CPI scores, growth rates, …).

The helpers are pure functions that return new values and never mutate
inputs.
"""

from __future__ import annotations


def clamp01(x: float) -> float:
    """Clamp ``x`` to the closed interval [0.0, 1.0]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def clamp_int_0_10(x: int) -> int:
    """Clamp ``x`` to the closed integer interval [0, 10]."""
    if x < 0:
        return 0
    if x > 10:
        return 10
    return int(x)


def normalize_0_1_to_0_10(x: float) -> int:
    """Project a 0–1 value onto the 0–10 integer scale, rounded half-up.

    >>> normalize_0_1_to_0_10(0.0)
    0
    >>> normalize_0_1_to_0_10(1.0)
    10
    >>> normalize_0_1_to_0_10(0.55)
    6
    """
    return clamp_int_0_10(round(x * 10))


def normalize_0_10_to_0_1(x: int | float) -> float:
    """Project a 0–10 value onto the 0–1 scale."""
    return clamp01(float(x) / 10.0)


def normalize_pct_to_0_1(x: float, *, lo: float = 0.0, hi: float = 100.0) -> float:
    """Linearly normalize a value from ``[lo, hi]`` onto the 0–1 scale.

    Values outside the range are clamped. Defaults assume the input is a
    percentage 0–100.
    """
    if hi == lo:
        raise ValueError("hi must differ from lo")
    return clamp01((x - lo) / (hi - lo))
