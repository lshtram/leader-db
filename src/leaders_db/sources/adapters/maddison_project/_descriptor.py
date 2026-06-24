"""Maddison Project Database 2023 constants + canonical :class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, coverage envelope, attribution text, homepage
URL, observation family), the proxy mapping constants, the
per-indicator unit-label mapping for the 3 catalog indicators,
and the :func:`build_maddison_project_descriptor` factory.

Split out of :mod:`leaders_db.sources.adapters.maddison_project.adapter`
so the adapter class module stays focused on the lifecycle
methods. The constants are also re-exported from
:mod:`leaders_db.sources.adapters.maddison_project` (the package
root) so callers can ``from
leaders_db.sources.adapters.maddison_project import
MADDISON_PROJECT_SOURCE_KEY`` without knowing which submodule
the symbol lives in.

The canonical default version ``"2023"`` matches the legacy
``sources.version`` stamp that
:func:`leaders_db.ingest.maddison_project_db.register_maddison_project_source`
writes to the ``sources`` table (the legacy DB writer hardcodes
``version = "2023"`` regardless of the bundle metadata, per the
historical Maddison Project Database 2023 release convention).
The verbose ``"2023 release (Bolt and van Zanden 2024)"``
descriptor remains in the staged bundle ``notes`` field as the
human-readable audit trail.
"""
from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical Maddison Project constants
# ---------------------------------------------------------------------------

MADDISON_PROJECT_SOURCE_KEY: str = "maddison_project"
MADDISON_PROJECT_XLSX_NAME: str = "mpd2023.xlsx"
MADDISON_PROJECT_METADATA_NAME: str = "metadata.json"
MADDISON_PROJECT_SHEET_NAME: str = "Full data"
MADDISON_PROJECT_DEFAULT_VERSION: str = "2023"

# The Maddison 2023 release's "Full data" sheet covers years 1
# through 2022. The catalog indicator list is documented in
# ``src/leaders_db/ingest/catalogs/maddison_project.csv``.
MADDISON_PROJECT_COVERAGE_START_YEAR: int = 1
MADDISON_PROJECT_COVERAGE_END_YEAR: int = 2022

# The Maddison Project homepage (canonical page). The Stage 2
# attribution block in ``docs/sources/attributions.md`` references
# the same URL.
MADDISON_PROJECT_HOMEPAGE_URL: str = (
    "https://www.rug.nl/ggdc/historicaldevelopment/maddison/"
    "releases/maddison-project-database-2023"
)

# The 1-year-gap proxy mapping: a request for ``years=(2023,)``
# is documented to map to ``year=2022`` data (same pattern as
# CIRIGHTS / UNDP HDI / Leader Survival). The proxy is surfaced
# as a structured warning + the per-observation ``quality_flags``
# tuple + the per-observation ``extension`` payload so it can
# never be silently lost. Years beyond 2022 (e.g. 2024) emit
# zero observations plus a structured ``YEAR_ABSENT`` warning
# (no multi-year stale-proxy fill, per
# ``docs/requirements/sources.md`` §7 SRC-COV-002 / SRC-COV-003).
MADDISON_PROJECT_PROXY_REQUESTED_YEAR: int = 2023
MADDISON_PROJECT_PROXY_YEAR: int = 2022

MADDISON_PROJECT_ATTRIBUTION_KEY: str = "maddison_project"

# Canonical attribution text (Always-On Rule #15; byte-identical
# to the maddison_project section in ``docs/sources/attributions.md``
# and to ``MADDISON_PROJECT_ATTRIBUTION`` in
# ``src/leaders_db/ingest/maddison_project_io.py``).
MADDISON_PROJECT_ATTRIBUTION_TEXT: str = (
    "Bolt, Jutta and Jan Luiten van Zanden (2024), "
    "'Maddison style estimates of the evolution of the world economy: "
    "A new 2023 update', Journal of Economic Surveys, 1-41. "
    "DOI: 10.1111/joes.12618. Licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)

MADDISON_PROJECT_OBSERVATION_FAMILY: str = "economic_country_year"
MADDISON_PROJECT_SUPPORTED_FAMILIES: tuple[str, ...] = (
    MADDISON_PROJECT_OBSERVATION_FAMILY,
)

# Asset id used for the ``mpd2023.xlsx`` raw asset across all
# observation locators in a single run.
MADDISON_PROJECT_XLSX_ASSET_ID: str = (
    f"{MADDISON_PROJECT_SOURCE_KEY}:{MADDISON_PROJECT_XLSX_NAME}"
)

# Sentinel string for the derived total GDP indicator's
# ``raw_column``. The Stage 2 reader recognises the sentinel
# and computes the value at runtime when both ``gdppc`` and
# ``pop`` are non-NULL for the same country-year. The sentinel
# cannot collide with a real xlsx column because the canonical
# Maddison ``Full data`` sheet has only 6 columns.
MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN: str = "__derived_gdp_total__"

# Column-name -> unit label mapping for the canonical 3 catalog
# numeric indicators. Values are best-effort unit hints only;
# downstream consumers must not treat them as authoritative
# (Rule #8: no invented metadata).
MADDISON_PROJECT_COLUMN_UNITS: dict[str, str] = {
    "gdppc": "2011_intl_dollars",
    "pop": "thousands",
    MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN: "derived_2011_intl_dollars",
}

# Transform-name string carried on every NormalizedObservation's
# ``transform_locator``. Surfaces the legacy reader/transform
# pair that produced the observation so downstream scoring can
# audit the parse path.
MADDISON_PROJECT_TRANSFORM_NAME: str = "read_maddison_project"


def build_maddison_project_descriptor() -> SourceDescriptor:
    """Build the canonical Maddison Project :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the legacy
    Stage 2 constants + the canonical citation block in
    ``docs/sources/attributions.md`` (Rule #15).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
        display_name="Maddison Project Database 2023",
        source_type="dataset",
        supported_observation_families=MADDISON_PROJECT_SUPPORTED_FAMILIES,
        default_version=MADDISON_PROJECT_DEFAULT_VERSION,
        homepage_url=MADDISON_PROJECT_HOMEPAGE_URL,
        attribution_key=MADDISON_PROJECT_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=MADDISON_PROJECT_COVERAGE_START_YEAR,
            end_year=MADDISON_PROJECT_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year real-economy history; 169 countries, "
                "1-2022 (no 2023 data in the 2023 release; 2023 "
                "requests proxy to 2022 per the CIRIGHTS / UNDP HDI "
                "/ Leader Survival 1-year-gap pattern). Real GDP "
                "per capita (2011 intl $), population (thousands), "
                "and a derived total real GDP indicator computed "
                "as gdppc * pop * 1000."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "MADDISON_PROJECT_ATTRIBUTION_KEY",
    "MADDISON_PROJECT_ATTRIBUTION_TEXT",
    "MADDISON_PROJECT_COLUMN_UNITS",
    "MADDISON_PROJECT_COVERAGE_END_YEAR",
    "MADDISON_PROJECT_COVERAGE_START_YEAR",
    "MADDISON_PROJECT_DEFAULT_VERSION",
    "MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN",
    "MADDISON_PROJECT_HOMEPAGE_URL",
    "MADDISON_PROJECT_METADATA_NAME",
    "MADDISON_PROJECT_OBSERVATION_FAMILY",
    "MADDISON_PROJECT_PROXY_REQUESTED_YEAR",
    "MADDISON_PROJECT_PROXY_YEAR",
    "MADDISON_PROJECT_SHEET_NAME",
    "MADDISON_PROJECT_SOURCE_KEY",
    "MADDISON_PROJECT_SUPPORTED_FAMILIES",
    "MADDISON_PROJECT_TRANSFORM_NAME",
    "MADDISON_PROJECT_XLSX_ASSET_ID",
    "MADDISON_PROJECT_XLSX_NAME",
    "build_maddison_project_descriptor",
]
