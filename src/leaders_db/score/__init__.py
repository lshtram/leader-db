"""Scoring module — category scoring, evidence bundles, and the fixed
confidence formula.

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
The Stage 5 evidence bundle contract lives in :mod:`leaders_db.score.evidence`.
The Stage 9-10 scoring result contract lives in
:mod:`leaders_db.score.results` (frozen typed payload shared by every
per-category scorer).
"""

from __future__ import annotations

from .confidence import (
    ConfidenceInputs,
    ConfidenceWeights,
    compute_confidence,
    default_weights,
)
from .dispatch import (
    get_category_scorer,
    score_category_bundle,
    supported_score_categories,
)
from .domestic_violence import score_domestic_violence
from .economic_wellbeing import score_economic_wellbeing
from .effectiveness import score_effectiveness
from .evidence import (
    CategoryEvidenceBundle,
    CategorySourcePlan,
    Direction,
    EvidenceObservation,
    IndicatorRole,
    IndicatorSpec,
    MissingObservation,
    MissingReason,
    MissingSeverity,
    SparseDataPolicy,
    TemporalKind,
)
from .integrity import score_integrity
from .international_peace import score_international_peace
from .normalization import (
    clamp01,
    clamp_int_0_10,
    normalize_0_1_to_0_10,
    normalize_0_10_to_0_1,
    normalize_pct_to_0_1,
)
from .nuclear import score_nuclear
from .political_freedom import score_political_freedom
from .results import (
    MissingnessSummary,
    ReviewFlag,
    ScoreComponent,
    ScoreObservationRef,
    ScoreResult,
)
from .social_wellbeing import (
    CATEGORY_KEY,
    score_social_wellbeing,
)
from .stage9 import (
    SCORE_RESULTS_CSV_COLUMNS,
    score_category_for_all_countries,
    score_category_for_country,
    write_score_results_csv,
)

__all__ = [
    "CATEGORY_KEY",
    "SCORE_RESULTS_CSV_COLUMNS",
    "CategoryEvidenceBundle",
    "CategorySourcePlan",
    "ConfidenceInputs",
    "ConfidenceWeights",
    "Direction",
    "EvidenceObservation",
    "IndicatorRole",
    "IndicatorSpec",
    "MissingObservation",
    "MissingReason",
    "MissingSeverity",
    "MissingnessSummary",
    "ReviewFlag",
    "ScoreComponent",
    "ScoreObservationRef",
    "ScoreResult",
    "SparseDataPolicy",
    "TemporalKind",
    "clamp01",
    "clamp_int_0_10",
    "compute_confidence",
    "default_weights",
    "get_category_scorer",
    "normalize_0_1_to_0_10",
    "normalize_0_10_to_0_1",
    "normalize_pct_to_0_1",
    "score_category_bundle",
    "score_category_for_all_countries",
    "score_category_for_country",
    "score_domestic_violence",
    "score_economic_wellbeing",
    "score_effectiveness",
    "score_integrity",
    "score_international_peace",
    "score_nuclear",
    "score_political_freedom",
    "score_social_wellbeing",
    "supported_score_categories",
    "write_score_results_csv",
]
