"""Constants for the clean Archigos source adapter."""

from __future__ import annotations

ARCHIGOS_SOURCE_KEY = "archigos"
ARCHIGOS_ATTRIBUTION_KEY = "archigos"
ARCHIGOS_DEFAULT_VERSION = "v4.1 (Stata 14)"
ARCHIGOS_HOMEPAGE_URL = "https://www.rochester.edu/college/faculty/hgoemans/"
ARCHIGOS_METADATA_NAME = "metadata.json"
ARCHIGOS_DTA_NAME = "Archigos_4.1_stata14.dta"
ARCHIGOS_DTA_ASSET_ID = f"{ARCHIGOS_SOURCE_KEY}:{ARCHIGOS_DTA_NAME}"

ARCHIGOS_OBSERVATION_FAMILY = "leader_identity_spell"
ARCHIGOS_SUPPORTED_FAMILIES = (ARCHIGOS_OBSERVATION_FAMILY,)
ARCHIGOS_COVERAGE_START_YEAR = 1840
ARCHIGOS_COVERAGE_END_YEAR = 2015

ARCHIGOS_ATTRIBUTION_TEXT = (
    "Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009)."
)

ARCHIGOS_TRANSFORM_NAME = "archigos_v41_leader_spell_v1"
ARCHIGOS_CHECKSUM_MISMATCH = "archigos_checksum_mismatch"
ARCHIGOS_LOCAL_FILES_INVALID = "archigos_local_files_invalid"
ARCHIGOS_METADATA_VERSION_MISMATCH = "archigos_metadata_version_mismatch"
ARCHIGOS_UNSUPPORTED_VERSION = "unsupported_version"

ARCHIGOS_INDICATORS = (
    "archigos_leader_name",
    "archigos_tenure_start_date",
    "archigos_tenure_end_date",
    "archigos_entry_type",
    "archigos_exit_type",
    "archigos_gender",
)

__all__ = [
    "ARCHIGOS_ATTRIBUTION_KEY",
    "ARCHIGOS_ATTRIBUTION_TEXT",
    "ARCHIGOS_CHECKSUM_MISMATCH",
    "ARCHIGOS_COVERAGE_END_YEAR",
    "ARCHIGOS_COVERAGE_START_YEAR",
    "ARCHIGOS_DEFAULT_VERSION",
    "ARCHIGOS_DTA_ASSET_ID",
    "ARCHIGOS_DTA_NAME",
    "ARCHIGOS_HOMEPAGE_URL",
    "ARCHIGOS_INDICATORS",
    "ARCHIGOS_LOCAL_FILES_INVALID",
    "ARCHIGOS_METADATA_NAME",
    "ARCHIGOS_METADATA_VERSION_MISMATCH",
    "ARCHIGOS_OBSERVATION_FAMILY",
    "ARCHIGOS_SOURCE_KEY",
    "ARCHIGOS_SUPPORTED_FAMILIES",
    "ARCHIGOS_TRANSFORM_NAME",
    "ARCHIGOS_UNSUPPORTED_VERSION",
]
