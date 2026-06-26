"""Unified-source Reporters Without Borders (RSF) World
Press Freedom Index indicator-name constants.

This module owns the 7 RSF ``variable_name`` constants
+ the canonical 7-tuple ``RSF_PRESS_FREEDOM_INDICATOR_NAMES``
+ the 2 base ``raw_column`` constants + the canonical
2-tuple ``RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS``.

The constants are derived from the canonical RSF
catalog at
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``
and re-exported from :mod:`._constants` (and from
:mod:`leaders_db.sources.adapters.rsf_press_freedom`,
the package root) so callers can ``from
leaders_db.sources.adapters.rsf_press_freedom import
RSF_PRESS_FREEDOM_INDICATOR_SCORE`` without knowing
which submodule the symbol lives in.

Split out of :mod:`._constants` so the constants module
stays under the documented 400-line convention. The
constants are:

- :data:`RSF_PRESS_FREEDOM_INDICATOR_SCORE` --
  ``"rsf_press_freedom_score"`` (2002-2026).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_RANK` --
  ``"rsf_press_freedom_rank"`` (2002-2026).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT` --
  ``"rsf_press_freedom_political_context"``
  (2022+ only).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT` --
  ``"rsf_press_freedom_economic_context"``
  (2022+ only).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT` --
  ``"rsf_press_freedom_legal_context"`` (2022+ only).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT` --
  ``"rsf_press_freedom_social_context"``
  (2022+ only).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_SAFETY` --
  ``"rsf_press_freedom_safety"`` (2022+ only).
- :data:`RSF_PRESS_FREEDOM_INDICATOR_NAMES` -- the
  canonical 7-tuple of the indicator names above.

Two base ``raw_column`` constants + tuple:

- :data:`RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE` --
  ``"score"``.
- :data:`RSF_PRESS_FREEDOM_RAW_COLUMN_RANK` --
  ``"rank"``.
- :data:`RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS` -- the
  canonical 2-tuple of the base raw_columns above.

Two base indicators (score + rank) span the full
2002-2026 envelope; the 5 component-context
indicators are 2022+ only per the documented
pre/post-2022 methodology / schema distinction. The
5 component-context indicators carry the same
``raw_column`` names as their actual headers per the
legacy ``COMPONENT_LOGICAL_TO_HEADER`` map (see
:mod:`._catalog`); the unified descriptor exposes
the 2 base raw_column names for symmetry.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 7 RSF indicator ``variable_name`` values
# ---------------------------------------------------------------------------

RSF_PRESS_FREEDOM_INDICATOR_SCORE: str = (
    "rsf_press_freedom_score"
)
RSF_PRESS_FREEDOM_INDICATOR_RANK: str = (
    "rsf_press_freedom_rank"
)
RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT: str = (
    "rsf_press_freedom_political_context"
)
RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT: str = (
    "rsf_press_freedom_economic_context"
)
RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT: str = (
    "rsf_press_freedom_legal_context"
)
RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT: str = (
    "rsf_press_freedom_social_context"
)
RSF_PRESS_FREEDOM_INDICATOR_SAFETY: str = (
    "rsf_press_freedom_safety"
)
RSF_PRESS_FREEDOM_INDICATOR_NAMES: tuple[str, ...] = (
    RSF_PRESS_FREEDOM_INDICATOR_SCORE,
    RSF_PRESS_FREEDOM_INDICATOR_RANK,
    RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_SAFETY,
)

# ---------------------------------------------------------------------------
# 2 base RSF logical ``raw_column`` names
# ---------------------------------------------------------------------------

RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE: str = "score"
RSF_PRESS_FREEDOM_RAW_COLUMN_RANK: str = "rank"
RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS: tuple[str, ...] = (
    RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE,
    RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
)


__all__ = [
    "RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS",
    "RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_NAMES",
    "RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_RANK",
    "RSF_PRESS_FREEDOM_INDICATOR_SAFETY",
    "RSF_PRESS_FREEDOM_INDICATOR_SCORE",
    "RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_RANK",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE",
]
