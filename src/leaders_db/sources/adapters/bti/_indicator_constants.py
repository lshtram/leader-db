"""Unified-source BTI indicator-name + raw-column
constants.

This module owns the 12 BTI indicator
``variable_name`` values and the 12 BTI xlsx raw
column names (whitespace-padded verbatim from the
xlsx header row; the legacy reader matches them by
``str(cell).strip()`` so trailing whitespace does not
break the match). Split out of :mod:`._descriptor`
so the descriptor module stays focused on the
canonical :func:`build_bti_descriptor` factory and
respects the documented 400-line convention.

The constants are also re-exported from
:mod:`._descriptor` (and from
:mod:`leaders_db.sources.adapters.bti`, the package
root) so callers can ``from
leaders_db.sources.adapters.bti import
BTI_INDICATOR_NAMES`` without knowing which submodule
the symbol lives in.

Indicator-name provenance
-------------------------

The 12 indicator ``variable_name`` values are the
canonical names from the BTI indicator catalog at
``src/leaders_db/ingest/catalogs/bti.csv``. The names
match the catalog byte-for-byte:

- ``bti_governance_index`` -- G | Governance Index
  (effectiveness)
- ``bti_governance_performance`` -- GII | Governance
  Performance (effectiveness)
- ``bti_status_index`` -- S | Status Index
  (political_freedom)
- ``bti_democracy_status`` -- SI | Democracy Status
  (political_freedom)
- ``bti_q1_stateness`` -- Q1 | Stateness
  (political_freedom)
- ``bti_q2_political_participation`` -- Q2 |
  Political Participation (political_freedom)
- ``bti_q3_rule_of_law`` -- Q3 | Rule of Law
  (political_freedom)
- ``bti_q4_democratic_institutions`` -- Q4 |
  Stability of Democratic Institutions
  (political_freedom)
- ``bti_q5_political_social_integration`` -- Q5 |
  Political and Social Integration
  (political_freedom)
- ``bti_q6_socioeconomic_development`` -- Q6 |
  Level of Socioeconomic Development
  (economic_wellbeing)
- ``bti_q7_market_competition`` -- Q7 |
  Organization of the Market and Competition
  (economic_wellbeing)
- ``bti_q11_economic_performance`` -- Q11 | Economic
  Performance (economic_wellbeing)

Raw-column provenance
---------------------

The 12 raw column names are the verbatim xlsx
header strings (with leading whitespace; the legacy
reader matches them by ``str(cell).strip()`` so
trailing whitespace does not break the match).
The legacy
:func:`leaders_db.ingest.bti_xlsx._resolve_columns`
helper uses the trimmed comparison.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Indicator ``variable_name`` constants
# ---------------------------------------------------------------------------

# Canonical slug for the indicator family. Used by
# the per-row emission loop + the public surface.
BTI_INDICATOR_GOVERNANCE_INDEX: str = "bti_governance_index"
BTI_INDICATOR_GOVERNANCE_PERFORMANCE: str = (
    "bti_governance_performance"
)
BTI_INDICATOR_STATUS_INDEX: str = "bti_status_index"
BTI_INDICATOR_DEMOCRACY_STATUS: str = "bti_democracy_status"
BTI_INDICATOR_Q1_STATENESS: str = "bti_q1_stateness"
BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION: str = (
    "bti_q2_political_participation"
)
BTI_INDICATOR_Q3_RULE_OF_LAW: str = "bti_q3_rule_of_law"
BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS: str = (
    "bti_q4_democratic_institutions"
)
BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION: str = (
    "bti_q5_political_social_integration"
)
BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT: str = (
    "bti_q6_socioeconomic_development"
)
BTI_INDICATOR_Q7_MARKET_COMPETITION: str = (
    "bti_q7_market_competition"
)
BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE: str = (
    "bti_q11_economic_performance"
)

BTI_INDICATOR_NAMES: tuple[str, ...] = (
    BTI_INDICATOR_GOVERNANCE_INDEX,
    BTI_INDICATOR_GOVERNANCE_PERFORMANCE,
    BTI_INDICATOR_STATUS_INDEX,
    BTI_INDICATOR_DEMOCRACY_STATUS,
    BTI_INDICATOR_Q1_STATENESS,
    BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION,
    BTI_INDICATOR_Q3_RULE_OF_LAW,
    BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_INDICATOR_Q7_MARKET_COMPETITION,
    BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE,
)

# ---------------------------------------------------------------------------
# Raw-column name constants (verbatim from the xlsx
# header row)
# ---------------------------------------------------------------------------

BTI_RAW_COLUMN_GOVERNANCE_INDEX: str = "  G | Governance Index"
BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE: str = (
    "  GII | Governance Performance"
)
BTI_RAW_COLUMN_STATUS_INDEX: str = "  S | Status Index"
BTI_RAW_COLUMN_DEMOCRACY_STATUS: str = "  SI | Democracy Status"
BTI_RAW_COLUMN_Q1_STATENESS: str = "  Q1 | Stateness"
BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION: str = (
    "  Q2 | Political Participation"
)
BTI_RAW_COLUMN_Q3_RULE_OF_LAW: str = "  Q3 | Rule of Law"
BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS: str = (
    "  Q4 | Stability of Democratic Institutions"
)
BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION: str = (
    "  Q5 | Political and Social Integration"
)
BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT: str = (
    "  Q6 | Level of Socioeconomic Development"
)
BTI_RAW_COLUMN_Q7_MARKET_COMPETITION: str = (
    "  Q7 | Organization of the Market and Competition"
)
BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE: str = (
    "  Q11 | Economic Performance"
)

BTI_RAW_COLUMNS: tuple[str, ...] = (
    BTI_RAW_COLUMN_GOVERNANCE_INDEX,
    BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE,
    BTI_RAW_COLUMN_STATUS_INDEX,
    BTI_RAW_COLUMN_DEMOCRACY_STATUS,
    BTI_RAW_COLUMN_Q1_STATENESS,
    BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION,
    BTI_RAW_COLUMN_Q3_RULE_OF_LAW,
    BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_RAW_COLUMN_Q7_MARKET_COMPETITION,
    BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE,
)


__all__ = [
    "BTI_INDICATOR_DEMOCRACY_STATUS",
    "BTI_INDICATOR_GOVERNANCE_INDEX",
    "BTI_INDICATOR_GOVERNANCE_PERFORMANCE",
    "BTI_INDICATOR_NAMES",
    "BTI_INDICATOR_Q1_STATENESS",
    "BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION",
    "BTI_INDICATOR_Q3_RULE_OF_LAW",
    "BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS",
    "BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION",
    "BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT",
    "BTI_INDICATOR_Q7_MARKET_COMPETITION",
    "BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE",
    "BTI_INDICATOR_STATUS_INDEX",
    "BTI_RAW_COLUMNS",
    "BTI_RAW_COLUMN_DEMOCRACY_STATUS",
    "BTI_RAW_COLUMN_GOVERNANCE_INDEX",
    "BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE",
    "BTI_RAW_COLUMN_Q1_STATENESS",
    "BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION",
    "BTI_RAW_COLUMN_Q3_RULE_OF_LAW",
    "BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS",
    "BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION",
    "BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT",
    "BTI_RAW_COLUMN_Q7_MARKET_COMPETITION",
    "BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE",
    "BTI_RAW_COLUMN_STATUS_INDEX",
]
