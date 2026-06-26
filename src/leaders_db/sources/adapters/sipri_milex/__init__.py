"""SIPRI Military Expenditure Database clean source adapter."""

from __future__ import annotations

from ._constants import (
    SIPRI_MILEX_ATTRIBUTION_KEY,
    SIPRI_MILEX_ATTRIBUTION_TEXT,
    SIPRI_MILEX_COVERAGE_END_YEAR,
    SIPRI_MILEX_COVERAGE_START_YEAR,
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_HOMEPAGE_URL,
    SIPRI_MILEX_INDICATORS,
    SIPRI_MILEX_OBSERVATION_FAMILY,
    SIPRI_MILEX_SOURCE_KEY,
    SIPRI_MILEX_SUPPORTED_FAMILIES,
    SIPRI_MILEX_XLSX_NAME,
)
from ._descriptor import build_sipri_milex_descriptor
from .adapter import (
    SIPRI_MILEX_ADAPTER_FACTORY,
    SipriMilexAdapter,
    create_sipri_milex_adapter,
    register_sipri_milex,
)

__all__ = [
    "SIPRI_MILEX_ADAPTER_FACTORY",
    "SIPRI_MILEX_ATTRIBUTION_KEY",
    "SIPRI_MILEX_ATTRIBUTION_TEXT",
    "SIPRI_MILEX_COVERAGE_END_YEAR",
    "SIPRI_MILEX_COVERAGE_START_YEAR",
    "SIPRI_MILEX_DEFAULT_VERSION",
    "SIPRI_MILEX_HOMEPAGE_URL",
    "SIPRI_MILEX_INDICATORS",
    "SIPRI_MILEX_OBSERVATION_FAMILY",
    "SIPRI_MILEX_SOURCE_KEY",
    "SIPRI_MILEX_SUPPORTED_FAMILIES",
    "SIPRI_MILEX_XLSX_NAME",
    "SipriMilexAdapter",
    "build_sipri_milex_descriptor",
    "create_sipri_milex_adapter",
    "register_sipri_milex",
]
