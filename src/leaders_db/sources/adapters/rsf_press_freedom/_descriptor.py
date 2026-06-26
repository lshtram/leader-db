"""Unified-source Reporters Without Borders (RSF) World
Press Freedom Index canonical
:class:`SourceDescriptor`.

This module owns the
:func:`build_rsf_press_freedom_descriptor` factory.
The static constants (source key, default version,
attribution text, observation family, coverage
envelope, the 7 indicator names) live in
:mod:`._constants`; the constants are re-exported
from this module (and from the package root) so
callers can ``from
leaders_db.sources.adapters.rsf_press_freedom
._descriptor import RSF_PRESS_FREEDOM_SOURCE_KEY``
without knowing which submodule the symbol lives in.

The full rationale (source-type semantics,
observation-family shape, attribution, direction
hint) is documented in :mod:`._constants`. This
module's docstring focuses on the descriptor
factory's contract.

The descriptor advertises ``source_type="dataset"``
and ``requires_network=False`` so downstream query
code and the runner can refuse to dispatch network
I/O unconditionally for RSF (the unified adapter is
local-file only by design; see
``docs/architecture/sources.md`` §11 SRC-TYPE-001).
The descriptor's coverage hint documents the 2011
missing/direct-CSV caveat so downstream code is
never surprised by it.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    RSF_PRESS_FREEDOM_ATTRIBUTION_KEY,
    RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
    RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
    RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
    RSF_PRESS_FREEDOM_DEFAULT_VERSION,
    RSF_PRESS_FREEDOM_HOMEPAGE_URL,
    RSF_PRESS_FREEDOM_OBSERVATION_FAMILY,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES,
)

# Re-export the static constants so callers can import
# them from :mod:`._descriptor` (the package's primary
# public surface for the static metadata).
__all__ = [
    "RSF_PRESS_FREEDOM_ATTRIBUTION_KEY",
    "RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT",
    "RSF_PRESS_FREEDOM_COVERAGE_END_YEAR",
    "RSF_PRESS_FREEDOM_COVERAGE_START_YEAR",
    "RSF_PRESS_FREEDOM_DEFAULT_VERSION",
    "RSF_PRESS_FREEDOM_HOMEPAGE_URL",
    "RSF_PRESS_FREEDOM_OBSERVATION_FAMILY",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES",
    "build_rsf_press_freedom_descriptor",
]


def build_rsf_press_freedom_descriptor() -> SourceDescriptor:
    """Build the canonical RSF World Press Freedom Index
    :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry
    exposes for source discovery (SRC-ID-003). The
    values mirror the canonical catalog and citation
    block in ``docs/sources/attributions.md`` (Rule
    #15).

    The descriptor advertises ``source_type="dataset"``
    and ``requires_network=False`` so downstream query
    code and the runner can refuse to dispatch network
    I/O unconditionally for RSF (the unified adapter is
    local-file only by design; see
    ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    The descriptor's coverage hint documents the 2011
    missing/direct-CSV caveat so downstream code is
    never surprised by it.
    """
    return SourceDescriptor(
        source_id=SourceId(slug=RSF_PRESS_FREEDOM_SOURCE_KEY),
        display_name=(
            "Reporters Without Borders (RSF) World "
            "Press Freedom Index 2026"
        ),
        source_type="dataset",
        supported_observation_families=(
            RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES
        ),
        default_version=RSF_PRESS_FREEDOM_DEFAULT_VERSION,
        homepage_url=RSF_PRESS_FREEDOM_HOMEPAGE_URL,
        attribution_key=RSF_PRESS_FREEDOM_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
            end_year=RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year press/media-freedom sub-signal "
                "for political freedom (NOT a full "
                "political-freedom replacement). 24 local "
                "annual CSVs (2002-2010 + 2012-2026); direct "
                "`2011.csv` is absent -- RSF's combined "
                "2011/2012 edition is represented by the 2012 "
                "file (its `Year (N)` column reads `2011-12`). "
                "The 7 catalog indicators span 2002-2026 "
                "(score + rank) and 2022+ only (5 "
                "component-context scores: political, economic, "
                "legal, social, safety). Pre-2022 and 2022+ "
                "schema/methodology differs -- the unified "
                "transform preserves the raw cell text "
                "verbatim and carries the pre/post-2022 schema "
                "distinction via the per-row "
                "`extension.rsf_schema_group` field (1 = "
                "pre-2022 16-col wide format; 2+ = post-2022 "
                "22-26 col wide format). The score direction "
                "is higher_is_better=True (higher RSF score = "
                "better press-freedom situation); the rank "
                "direction is higher_is_better=False (rank 1 "
                "= best). The canonical CSVs are staged at "
                "`data/raw/rsf_press_freedom/rsf_press_freedom_<year>.csv` "
                "(semicolon-delimited, comma decimal "
                "separator, mixed `utf-8-sig` / `cp1252` "
                "encoding per year; the 2022 file carries 181 "
                "blank separator rows that the reader drops). "
                "No HTTP layer (`requires_network=False`); "
                "free public dataset; cite Reporters Without "
                "Borders / Reporters sans frontières 2026."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )
