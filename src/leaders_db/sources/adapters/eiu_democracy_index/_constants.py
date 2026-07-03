"""Constants for the EIU Democracy Index clean-source adapter."""

from __future__ import annotations

EIU_DEMOCRACY_INDEX_SOURCE_KEY = "eiu_democracy_index"
EIU_DEMOCRACY_INDEX_METADATA_NAME = "metadata.json"
EIU_DEMOCRACY_INDEX_PDF_PATTERN = "democracy-index-{year}.pdf"
EIU_DEMOCRACY_INDEX_DEFAULT_VERSION = (
    "2006, 2008, 2010-2019, 2021-2024 public reports staged 2026-06-29; "
    "2020 still missing"
)
EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT = (
    "Economist Intelligence Unit Democracy Index "
    "(The Economist Intelligence Unit, report year {year})."
)
EIU_DEMOCRACY_INDEX_HOMEPAGE_URL = (
    "https://www.eiu.com/n/global-themes/democracy-index/"
)
EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY = "political_freedom_country_year"
EIU_DEMOCRACY_INDEX_ADAPTER_VERSION = "eiu_democracy_index_clean_v1"
EIU_DEMOCRACY_INDEX_COVERAGE_START_YEAR = 2006
EIU_DEMOCRACY_INDEX_COVERAGE_END_YEAR = 2024
EIU_DEMOCRACY_INDEX_EXPECTED_ABSENT_YEARS = (2007, 2009)

EIU_DEMOCRACY_INDEX_INDICATORS = (
    "eiu_democracy_index_overall_score",
    "eiu_democracy_index_rank",
    "eiu_democracy_index_rank_change",
    "eiu_democracy_index_electoral_process_pluralism",
    "eiu_democracy_index_functioning_government",
    "eiu_democracy_index_political_participation",
    "eiu_democracy_index_political_culture",
    "eiu_democracy_index_civil_liberties",
    "eiu_democracy_index_regime_type",
)

EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF = "eiu_democracy_index_missing_requested_pdf"
EIU_DEMOCRACY_INDEX_LOCAL_FILES_INVALID = "eiu_democracy_index_local_files_invalid"
EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH = "eiu_democracy_index_checksum_mismatch"
EIU_DEMOCRACY_INDEX_METADATA_VERSION_MISMATCH = (
    "eiu_democracy_index_metadata_version_mismatch"
)
EIU_DEMOCRACY_INDEX_PDF_TEXT_UNAVAILABLE = "eiu_democracy_index_pdf_text_unavailable"
EIU_DEMOCRACY_INDEX_UNSUPPORTED_VERSION = "unsupported_version"

__all__ = [
    "EIU_DEMOCRACY_INDEX_ADAPTER_VERSION",
    "EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT",
    "EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH",
    "EIU_DEMOCRACY_INDEX_COVERAGE_END_YEAR",
    "EIU_DEMOCRACY_INDEX_COVERAGE_START_YEAR",
    "EIU_DEMOCRACY_INDEX_DEFAULT_VERSION",
    "EIU_DEMOCRACY_INDEX_EXPECTED_ABSENT_YEARS",
    "EIU_DEMOCRACY_INDEX_HOMEPAGE_URL",
    "EIU_DEMOCRACY_INDEX_INDICATORS",
    "EIU_DEMOCRACY_INDEX_LOCAL_FILES_INVALID",
    "EIU_DEMOCRACY_INDEX_METADATA_NAME",
    "EIU_DEMOCRACY_INDEX_METADATA_VERSION_MISMATCH",
    "EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF",
    "EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY",
    "EIU_DEMOCRACY_INDEX_PDF_PATTERN",
    "EIU_DEMOCRACY_INDEX_PDF_TEXT_UNAVAILABLE",
    "EIU_DEMOCRACY_INDEX_SOURCE_KEY",
    "EIU_DEMOCRACY_INDEX_UNSUPPORTED_VERSION",
]
