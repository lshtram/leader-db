"""Scoring module — category scoring and the fixed confidence formula.

Confidence is normative (REQ-CONF-001, requirement §11):

    confidence = 0.35 * agreement + 0.25 * authority
                 + 0.25 * specificity + 0.15 * temporal_fit

The weights are constants and must not be invented in a one-off script.
Per-category scoring modules live next to this file:

- ``political_freedom.py``   — V-Dem + Freedom House + EIU/Polity/BMR
- ``economic.py``            — World Bank WDI
- ``corruption.py``          — Transparency CPI + WGI corruption
- ``domestic_violence.py``   — PTS + CIRIGHTS + UCDP one-sided violence
- ``peace.py``               — UCDP + COW/MID + SIPRI military expenditure
- ``nuclear.py``             — FAS + SIPRI nuclear + NTI (lighter module)

Each per-category module is a stub during Phase A (infrastructure).
"""

from __future__ import annotations

from .normalization import (
    clamp01,
    clamp_int_0_10,
    normalize_0_1_to_0_10,
    normalize_0_10_to_0_1,
    normalize_pct_to_0_1,
)
from .confidence import (
    ConfidenceInputs,
    ConfidenceWeights,
    compute_confidence,
    default_weights,
)

__all__ = [
    "clamp01",
    "clamp_int_0_10",
    "normalize_0_1_to_0_10",
    "normalize_0_10_to_0_1",
    "normalize_pct_to_0_1",
    "ConfidenceInputs",
    "ConfidenceWeights",
    "compute_confidence",
    "default_weights",
]
