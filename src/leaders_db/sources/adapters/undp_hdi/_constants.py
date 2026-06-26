"""Constants for the clean UNDP HDI source adapter."""

from __future__ import annotations

UNDP_HDI_SOURCE_KEY = "undp_hdi"
UNDP_HDI_ATTRIBUTION_KEY = "undp_hdi"
UNDP_HDI_DEFAULT_VERSION = "2023-24"
UNDP_HDI_HOMEPAGE_URL = "https://hdr.undp.org/"
UNDP_HDI_METADATA_NAME = "metadata.json"
UNDP_HDI_CSV_NAME = "HDR23-24_Composite_indices_complete_time_series.csv"
UNDP_HDI_CSV_ASSET_ID = f"{UNDP_HDI_SOURCE_KEY}:{UNDP_HDI_CSV_NAME}"

UNDP_HDI_OBSERVATION_FAMILY = "social_wellbeing_country_year"
UNDP_HDI_SUPPORTED_FAMILIES = (UNDP_HDI_OBSERVATION_FAMILY,)
UNDP_HDI_COVERAGE_START_YEAR = 1990
UNDP_HDI_COVERAGE_END_YEAR = 2022
UNDP_HDI_PROXY_YEAR = 2022
UNDP_HDI_PROXY_REQUESTED_YEAR = 2023

UNDP_HDI_ATTRIBUTION_TEXT = "UNDP HDR 2023-24 (United Nations Development Programme 2024)."

UNDP_HDI_TRANSFORM_NAME = "undp_hdi_country_year_v1"
UNDP_HDI_CHECKSUM_MISMATCH = "undp_hdi_checksum_mismatch"
UNDP_HDI_LOCAL_FILES_INVALID = "undp_hdi_local_files_invalid"
UNDP_HDI_METADATA_VERSION_MISMATCH = "undp_hdi_metadata_version_mismatch"
UNDP_HDI_UNSUPPORTED_VERSION = "unsupported_version"

UNDP_HDI_INDICATORS = (
    "undp_hdi_hdi",
    "undp_hdi_life_expectancy",
    "undp_hdi_expected_years_schooling",
    "undp_hdi_mean_years_schooling",
    "undp_hdi_gni_per_capita",
)

__all__ = [
    "UNDP_HDI_ATTRIBUTION_KEY",
    "UNDP_HDI_ATTRIBUTION_TEXT",
    "UNDP_HDI_CHECKSUM_MISMATCH",
    "UNDP_HDI_COVERAGE_END_YEAR",
    "UNDP_HDI_COVERAGE_START_YEAR",
    "UNDP_HDI_CSV_ASSET_ID",
    "UNDP_HDI_CSV_NAME",
    "UNDP_HDI_DEFAULT_VERSION",
    "UNDP_HDI_HOMEPAGE_URL",
    "UNDP_HDI_INDICATORS",
    "UNDP_HDI_LOCAL_FILES_INVALID",
    "UNDP_HDI_METADATA_NAME",
    "UNDP_HDI_METADATA_VERSION_MISMATCH",
    "UNDP_HDI_OBSERVATION_FAMILY",
    "UNDP_HDI_PROXY_REQUESTED_YEAR",
    "UNDP_HDI_PROXY_YEAR",
    "UNDP_HDI_SOURCE_KEY",
    "UNDP_HDI_SUPPORTED_FAMILIES",
    "UNDP_HDI_TRANSFORM_NAME",
    "UNDP_HDI_UNSUPPORTED_VERSION",
]
