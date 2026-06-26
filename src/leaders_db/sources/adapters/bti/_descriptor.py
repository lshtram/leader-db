"""Bertelsmann Transformation Index (BTI) canonical
:class:`SourceDescriptor` factory.

This module owns the :func:`build_bti_descriptor`
factory. The static constants (source key, default
version, attribution text, observation families,
coverage envelope, the 12 indicator names + raw
columns) live in :mod:`._constants` and
:mod:`._indicator_constants`; the constants are
re-exported from this module (and from the package
root) so callers can ``from
leaders_db.sources.adapters.bti._descriptor import
BTI_SOURCE_KEY`` without knowing which submodule the
symbol lives in.

The full rationale (source-type semantics,
observation-family shape, attribution, biennial
sheet/year mapping, direction hint) is documented in
:mod:`._constants` and :mod:`._indicator_constants`.
This module's docstring focuses on the descriptor
factory's contract.

The descriptor advertises ``source_type="dataset"``
and ``requires_network=False`` so downstream query
code and the runner can refuse to dispatch network
I/O unconditionally for BTI (the unified adapter is
local-file only by design; see
``docs/architecture/sources.md`` §11 SRC-TYPE-001).
The descriptor's coverage hint documents the biennial
2002-2025 envelope + the per-edition year-to-sheet
mapping so downstream code is never surprised by it.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# Re-export the static constants from
# :mod:`._constants` + :mod:`._indicator_constants`
# so callers can ``from
# leaders_db.sources.adapters.bti._descriptor import
# BTI_SOURCE_KEY`` (the canonical module-level
# re-export contract; the constants' canonical
# definitions live in the sibling modules).
from ._constants import (
    BTI_ATTRIBUTION_KEY,
    BTI_ATTRIBUTION_TEXT,
    BTI_COVERAGE_END_YEAR,
    BTI_COVERAGE_START_YEAR,
    BTI_DEFAULT_VERSION,
    BTI_HOMEPAGE_URL,
    BTI_METADATA_NAME,
    BTI_METADATA_VERSION_MISMATCH,
    BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING,
    BTI_OBSERVATION_FAMILY_EFFECTIVENESS,
    BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    BTI_SOURCE_KEY,
    BTI_SUPPORTED_FAMILIES,
    BTI_XLSX_ASSET_ID,
    BTI_XLSX_NAME,
    UNSUPPORTED_VERSION,
)
from ._indicator_constants import (
    BTI_INDICATOR_DEMOCRACY_STATUS,
    BTI_INDICATOR_GOVERNANCE_INDEX,
    BTI_INDICATOR_GOVERNANCE_PERFORMANCE,
    BTI_INDICATOR_NAMES,
    BTI_INDICATOR_Q1_STATENESS,
    BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION,
    BTI_INDICATOR_Q3_RULE_OF_LAW,
    BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_INDICATOR_Q7_MARKET_COMPETITION,
    BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE,
    BTI_INDICATOR_STATUS_INDEX,
    BTI_RAW_COLUMN_DEMOCRACY_STATUS,
    BTI_RAW_COLUMN_GOVERNANCE_INDEX,
    BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE,
    BTI_RAW_COLUMN_Q1_STATENESS,
    BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION,
    BTI_RAW_COLUMN_Q3_RULE_OF_LAW,
    BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_RAW_COLUMN_Q7_MARKET_COMPETITION,
    BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE,
    BTI_RAW_COLUMN_STATUS_INDEX,
    BTI_RAW_COLUMNS,
)


def build_bti_descriptor() -> SourceDescriptor:
    """Build the canonical BTI
    :class:`SourceDescriptor`.

    The descriptor is the static metadata the
    registry exposes for source discovery
    (SRC-ID-003). The values mirror the canonical
    catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"``
    and ``requires_network=False`` so downstream
    query code and the runner can refuse to
    dispatch network I/O unconditionally for BTI
    (the unified adapter is local-file only by
    design; see ``docs/architecture/sources.md``
    §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=BTI_SOURCE_KEY),
        display_name=(
            "Bertelsmann Transformation Index (BTI) 2026"
        ),
        source_type="dataset",
        supported_observation_families=BTI_SUPPORTED_FAMILIES,
        default_version=BTI_DEFAULT_VERSION,
        homepage_url=BTI_HOMEPAGE_URL,
        attribution_key=BTI_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=BTI_COVERAGE_START_YEAR,
            end_year=BTI_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-edition biennial expert-coded "
                "governance / political-transformation / "
                "economic-transformation indicators. The "
                "canonical cumulative xlsx is staged at "
                "`data/raw/bti/BTI_2006-2026_Scores.xlsx` "
                "(12 sheets: one BTI edition per sheet "
                "from BTI 2006_old through BTI 2026; "
                "137-159 countries per edition; 123 columns "
                "of composite indices + Q1-Q17 question "
                "fields + trend / classification columns). "
                "BTI is biennial: each edition covers the "
                "~2-year period preceding publication "
                "(BTI 2024 covers 2022-2023; BTI 2026 "
                "covers 2024-2025). For the prototype "
                "target year 2023, the canonical mapping "
                "resolves to the `BTI 2024` sheet (covers "
                "2022-2023). The 12 catalog indicators span "
                "3 observation families: "
                "`effectiveness_country_year` (2: "
                "Governance Index + Governance Performance), "
                "`political_freedom_country_year` (7: "
                "Status Index + Democracy Status + Q1-Q5 "
                "political transformation questions), and "
                "`economic_wellbeing_country_year` (3: Q6 + "
                "Q7 + Q11 economic transformation "
                "questions). BTI is the canonical "
                "governance / effectiveness source for the "
                "prototype (per "
                "`docs/sources/registry.md` §1), NOT a full "
                "political-freedom replacement -- "
                "complementing V-Dem + World Bank WGI. All "
                "12 indicators share raw_scale=1-10 with "
                "10 = best (higher_is_better=True). The "
                "Stage 5 score module preserves the raw "
                "1-10 value verbatim and emits a per-source "
                "direction hint. No HTTP layer "
                "(`requires_network=False`); free public "
                "dataset; cite Bertelsmann Stiftung 2026."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "BTI_ATTRIBUTION_KEY",
    "BTI_ATTRIBUTION_TEXT",
    "BTI_COVERAGE_END_YEAR",
    "BTI_COVERAGE_START_YEAR",
    "BTI_DEFAULT_VERSION",
    "BTI_HOMEPAGE_URL",
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
    "BTI_METADATA_NAME",
    "BTI_METADATA_VERSION_MISMATCH",
    "BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING",
    "BTI_OBSERVATION_FAMILY_EFFECTIVENESS",
    "BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
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
    "BTI_SOURCE_KEY",
    "BTI_SUPPORTED_FAMILIES",
    "BTI_XLSX_ASSET_ID",
    "BTI_XLSX_NAME",
    "UNSUPPORTED_VERSION",
    "build_bti_descriptor",
]
