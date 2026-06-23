"""Constants and small helpers shared by the 2023 vertical-slice module.

Kept in its own file so :mod:`slice_2023` stays under the documented
line caps (this is a 400-line-or-less convention used across the
project). The constants here are slice-only and are NOT intended to
graduate into the real Stage 3 alias table; they exist because the
slice is allowed to use a fixed ISO3 map per architecture doc §6.
"""

from __future__ import annotations

from datetime import date
from typing import Final

# Slice-owned markers per architecture doc §4. Every slice-owned row
# carries one of these so the idempotent rerun can find and delete only
# its own rows without touching anything else.
SLICE_NOTE_PREFIX: Final[str] = "vertical_slice_2023:"
SLICE_RULER_SPELLS_DATASET: Final[str] = "vertical_slice_client_seed"
SLICE_INCLUSION_REASON: Final[str] = "vertical_slice_2023_selected_country"
SLICE_OBSERVATION_NOTE: Final[str] = (
    f"{SLICE_NOTE_PREFIX}client_only_seeded"
)

# Fixed ISO3 map for the slice (architecture doc §6).
SLICE_ISO3_BY_CLIENT_NAME: Final[dict[str, str]] = {
    "mexico": "MEX",
    "nigeria": "NGA",
    "united states": "USA",
}

# Preferred display name per ISO3 (architecture doc §6). Used when
# creating ``Country`` rows for the slice.
SLICE_PREFERRED_NAME_BY_ISO3: Final[dict[str, str]] = {
    "MEX": "Mexico",
    "NGA": "Nigeria",
    "USA": "United States",
}

# Default scope per architecture doc §10. These defaults are slice-only;
# the real Stage 3-15 pipeline must not hard-code country or category
# lists at the production layer.
DEFAULT_COUNTRIES: Final[tuple[str, ...]] = ("MEX", "NGA", "USA")
DEFAULT_CATEGORIES: Final[tuple[str, ...]] = (
    "social_wellbeing",
    "integrity",
)

# Source-row-reference prefixes that carry an ISO3 suffix (architecture
# doc §6). Only observations whose prefix is in this set are linked to a
# country by the slice.
ISO3_LINK_PREFIXES: Final[tuple[str, ...]] = (
    "wdi",
    "wgi",
    "undp_hdi",
    "vdem",
)

# Mapping from category_key to the (source_variable_name, preferred_year,
# fallback_year) tuple used by the scoring layer. Anything not in this
# map is not scored by the slice.
CATEGORY_INPUT_MAP: Final[dict[str, tuple[str, int, int]]] = {
    # social_wellbeing uses UNDP HDI. Architecture §8 says 2022 is an
    # accepted proxy for target year 2023 (1-year-gap, the CIRIGHTS /
    # Leader Survival pattern that the UNDP HDI Stage 2 adapter also
    # uses).
    "social_wellbeing": ("undp_hdi_hdi", 2023, 2022),
    # integrity uses WGI Control of Corruption. 2023 preferred, 2022
    # accepted as documented proxy.
    "integrity": ("wgi_control_of_corruption", 2023, 2022),
}

# Per-source attribution blocks the slice ships in its public output.
# Pulled from :mod:`docs.source-attributions` per Always-On Rule #15.
# Wording must stay aligned with ``docs/sources/attributions.md``.
UNDP_HDI_ATTRIBUTION: Final[str] = (
    "UNDP. 2024. *Human Development Report 2023-2024*. "
    "United Nations Development Programme. https://hdr.undp.org/"
)
WGI_ATTRIBUTION: Final[str] = (
    "World Bank. 2023. Worldwide Governance Indicators. "
    "Washington, D.C.: The World Bank. https://info.worldbank.org/governance/wgi/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)
CLIENT_ATTRIBUTION: Final[str] = (
    "Client-supplied 2023 matrix (internal; not for redistribution)."
)

# Confidence component values for the slice (architecture doc §8).
# Each category uses the same authority (80) and specificity (80); the
# agreement and temporal_fit differ only when a proxy year is used.
COMPONENT_AGREEMENT: Final[int] = 60
COMPONENT_AUTHORITY_UNDP: Final[int] = 80
COMPONENT_AUTHORITY_WGI: Final[int] = 80
COMPONENT_SPECIFICITY: Final[int] = 80
COMPONENT_TEMPORAL_FIT_DIRECT: Final[int] = 100
COMPONENT_TEMPORAL_FIT_PROXY: Final[int] = 80

# Slice confidence floor for ruler spells / ruler years (single-source
# client-only seeding).
SLICE_SEED_CONFIDENCE: Final[int] = 40

# Slice outputs directory (architecture doc §9).
OUTPUT_DIR_NAME: Final[str] = "vertical_slice_2023"
OUTPUT_SCORES_CSV: Final[str] = "vertical_slice_scores.csv"
OUTPUT_COMPARISON_CSV: Final[str] = "vertical_slice_comparison.csv"
OUTPUT_SUMMARY_MD: Final[str] = "vertical_slice_summary.md"
# Multi-year source-only time-series CSV. Written only when the caller passes
# a ``years=`` sequence (or the ``--years`` CLI flag). This file is the
# source-of-truth for the multi-year extension; the DB rows remain 2023-only.
OUTPUT_TIMESERIES_CSV: Final[str] = "vertical_slice_timeseries.csv"


def placeholder_date_for(year_started: int | None, target_year: int) -> date:
    """Return a deterministic placeholder date for a ruler spell start.

    Architecture §7 says the slice uses ``year_started`` if parseable and
    falls back to ``<target_year>-01-01`` with a slice note when the
    year cannot be parsed. The slice never invents a month or day.
    """
    if year_started is None:
        return date(target_year, 1, 1)
    try:
        return date(int(year_started), 1, 1)
    except (TypeError, ValueError):
        return date(target_year, 1, 1)


__all__ = [
    "CATEGORY_INPUT_MAP",
    "CLIENT_ATTRIBUTION",
    "COMPONENT_AGREEMENT",
    "COMPONENT_AUTHORITY_UNDP",
    "COMPONENT_AUTHORITY_WGI",
    "COMPONENT_SPECIFICITY",
    "COMPONENT_TEMPORAL_FIT_DIRECT",
    "COMPONENT_TEMPORAL_FIT_PROXY",
    "DEFAULT_CATEGORIES",
    "DEFAULT_COUNTRIES",
    "ISO3_LINK_PREFIXES",
    "OUTPUT_COMPARISON_CSV",
    "OUTPUT_DIR_NAME",
    "OUTPUT_SCORES_CSV",
    "OUTPUT_SUMMARY_MD",
    "OUTPUT_TIMESERIES_CSV",
    "SLICE_INCLUSION_REASON",
    "SLICE_ISO3_BY_CLIENT_NAME",
    "SLICE_NOTE_PREFIX",
    "SLICE_OBSERVATION_NOTE",
    "SLICE_PREFERRED_NAME_BY_ISO3",
    "SLICE_RULER_SPELLS_DATASET",
    "SLICE_SEED_CONFIDENCE",
    "UNDP_HDI_ATTRIBUTION",
    "WGI_ATTRIBUTION",
    "placeholder_date_for",
]
