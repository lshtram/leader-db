"""PWT constants + canonical :class:`SourceDescriptor` factory.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, coverage envelope, attribution text, homepage
URL, observation family), the per-column unit-label mapping for
the 11 catalog numeric columns, and the
:func:`build_pwt_descriptor` factory.

Split out of :mod:`leaders_db.sources.adapters.pwt.adapter` so
the adapter class module stays focused on the lifecycle methods.
The constants are also re-exported from
:mod:`leaders_db.sources.adapters.pwt` (the package root) so
callers can ``from leaders_db.sources.adapters.pwt import
PWT_SOURCE_KEY`` without knowing which submodule the symbol
lives in.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical PWT constants
# ---------------------------------------------------------------------------

PWT_SOURCE_KEY: str = "pwt"
PWT_XLSX_NAME: str = "pwt1001.xlsx"
PWT_METADATA_NAME: str = "metadata.json"
PWT_DATA_SHEET_NAME: str = "Data"
PWT_DEFAULT_VERSION: str = "10.01"
PWT_COVERAGE_START_YEAR: int = 1950
PWT_COVERAGE_END_YEAR: int = 2019
PWT_HOMEPAGE_URL: str = (
    "https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt1001"
)
PWT_ATTRIBUTION_KEY: str = "pwt"
PWT_ATTRIBUTION_TEXT: str = (
    "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)."
)
PWT_OBSERVATION_FAMILY: str = "economic_country_year"
PWT_SUPPORTED_FAMILIES: tuple[str, ...] = (PWT_OBSERVATION_FAMILY,)

# Asset id used for the ``pwt1001.xlsx`` raw asset across all
# observation locators in a single run.
PWT_XLSX_ASSET_ID: str = f"{PWT_SOURCE_KEY}:{PWT_XLSX_NAME}"

# Column-name -> unit label mapping for the canonical 11 catalog
# numeric columns. Values are best-effort unit hints only;
# downstream consumers must not treat them as authoritative
# (Rule #8: no invented metadata).
PWT_COLUMN_UNITS: dict[str, str] = {
    "rgdpe": "2017_usd",
    "rgdpo": "2017_usd",
    "pop": "persons",
    "emp": "persons",
    "avh": "hours_per_worker_per_year",
    "hc": "index_0_to_1",
    "ccon": "2017_usd",
    "cda": "2017_usd",
    "ctfp": "index_usa_2017_equals_1",
    "rkna": "2017_usd",
    "rtfpna": "index_2017_equals_1",
}


def build_pwt_descriptor() -> SourceDescriptor:
    """Build the canonical PWT :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the legacy
    Stage 2 constants + the canonical citation block in
    ``docs/sources/attributions.md`` (Rule #15).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=PWT_SOURCE_KEY),
        display_name="Penn World Table 10.01",
        source_type="dataset",
        supported_observation_families=PWT_SUPPORTED_FAMILIES,
        default_version=PWT_DEFAULT_VERSION,
        homepage_url=PWT_HOMEPAGE_URL,
        attribution_key=PWT_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=PWT_COVERAGE_START_YEAR,
            end_year=PWT_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year economic accounts; 183 economies, "
                "1950-2019; PPP-based real GDP, population, "
                "employment, hours, human capital, consumption, "
                "TFP, capital stock."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "PWT_ATTRIBUTION_KEY",
    "PWT_ATTRIBUTION_TEXT",
    "PWT_COLUMN_UNITS",
    "PWT_COVERAGE_END_YEAR",
    "PWT_COVERAGE_START_YEAR",
    "PWT_DATA_SHEET_NAME",
    "PWT_DEFAULT_VERSION",
    "PWT_HOMEPAGE_URL",
    "PWT_METADATA_NAME",
    "PWT_OBSERVATION_FAMILY",
    "PWT_SOURCE_KEY",
    "PWT_SUPPORTED_FAMILIES",
    "PWT_XLSX_ASSET_ID",
    "PWT_XLSX_NAME",
    "build_pwt_descriptor",
]
