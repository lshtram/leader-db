"""Constants for the clean REIGN source adapter."""

from __future__ import annotations

REIGN_SOURCE_KEY = "reign"
REIGN_ATTRIBUTION_KEY = "reign"
REIGN_DEFAULT_VERSION = "2021-8 (August 2021 release, final)"
REIGN_HOMEPAGE_URL = "https://oefdatascience.github.io/REIGN.github.io/"
REIGN_METADATA_NAME = "metadata.json"
REIGN_CSV_NAME = "REIGN_2021_8.csv"
REIGN_CSV_ASSET_ID = f"{REIGN_SOURCE_KEY}:{REIGN_CSV_NAME}"

REIGN_OBSERVATION_FAMILY = "leader_identity_month"
REIGN_SUPPORTED_FAMILIES = (REIGN_OBSERVATION_FAMILY,)
REIGN_COVERAGE_START_YEAR = 1950
REIGN_COVERAGE_END_YEAR = 2021

REIGN_ATTRIBUTION_TEXT = "REIGN dataset (Bell 2016), snapshot of August 2021."
REIGN_TRANSFORM_NAME = "reign_2021_8_leader_month_v1"

REIGN_CHECKSUM_MISMATCH = "reign_checksum_mismatch"
REIGN_LOCAL_FILES_INVALID = "reign_local_files_invalid"
REIGN_METADATA_VERSION_MISMATCH = "reign_metadata_version_mismatch"
REIGN_UNSUPPORTED_VERSION = "unsupported_version"

REIGN_INDICATORS = (
    "reign_leader",
    "reign_government",
    "reign_elected",
    "reign_age",
    "reign_male",
    "reign_tenure_months",
    "reign_political_violence",
    "reign_irregular",
)

__all__ = [
    "REIGN_ATTRIBUTION_KEY",
    "REIGN_ATTRIBUTION_TEXT",
    "REIGN_CHECKSUM_MISMATCH",
    "REIGN_COVERAGE_END_YEAR",
    "REIGN_COVERAGE_START_YEAR",
    "REIGN_CSV_ASSET_ID",
    "REIGN_CSV_NAME",
    "REIGN_DEFAULT_VERSION",
    "REIGN_HOMEPAGE_URL",
    "REIGN_INDICATORS",
    "REIGN_LOCAL_FILES_INVALID",
    "REIGN_METADATA_NAME",
    "REIGN_METADATA_VERSION_MISMATCH",
    "REIGN_OBSERVATION_FAMILY",
    "REIGN_SOURCE_KEY",
    "REIGN_SUPPORTED_FAMILIES",
    "REIGN_TRANSFORM_NAME",
    "REIGN_UNSUPPORTED_VERSION",
]
