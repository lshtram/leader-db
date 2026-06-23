"""Shared warning-code constants for source contract tests."""

from __future__ import annotations

MISSING_RAW = "missing_raw"
MISSING_METADATA = "missing_metadata"
COUNTRY_ABSENT = "country_absent"
YEAR_ABSENT = "year_absent"
INDICATOR_NULL = "indicator_null"
UNSUPPORTED_FILTER = "unsupported_filter"
MANUAL_GATE = "manual_gate"
NETWORK_CACHE_UNAVAILABLE = "network_cache_unavailable"
SOURCE_NOT_IMPLEMENTED = "source_not_implemented"

__all__ = [
    "COUNTRY_ABSENT",
    "INDICATOR_NULL",
    "MANUAL_GATE",
    "MISSING_METADATA",
    "MISSING_RAW",
    "NETWORK_CACHE_UNAVAILABLE",
    "SOURCE_NOT_IMPLEMENTED",
    "UNSUPPORTED_FILTER",
    "YEAR_ABSENT",
]
