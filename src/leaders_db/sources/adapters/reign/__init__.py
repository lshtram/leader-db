"""REIGN 2021-8 clean source adapter."""

from __future__ import annotations

from ._constants import (
    REIGN_ATTRIBUTION_KEY,
    REIGN_ATTRIBUTION_TEXT,
    REIGN_COVERAGE_END_YEAR,
    REIGN_COVERAGE_START_YEAR,
    REIGN_CSV_NAME,
    REIGN_DEFAULT_VERSION,
    REIGN_HOMEPAGE_URL,
    REIGN_INDICATORS,
    REIGN_OBSERVATION_FAMILY,
    REIGN_SOURCE_KEY,
    REIGN_SUPPORTED_FAMILIES,
)
from ._descriptor import build_reign_descriptor
from .adapter import (
    REIGN_ADAPTER_FACTORY,
    ReignAdapter,
    create_reign_adapter,
    register_reign,
)

__all__ = [
    "REIGN_ADAPTER_FACTORY",
    "REIGN_ATTRIBUTION_KEY",
    "REIGN_ATTRIBUTION_TEXT",
    "REIGN_COVERAGE_END_YEAR",
    "REIGN_COVERAGE_START_YEAR",
    "REIGN_CSV_NAME",
    "REIGN_DEFAULT_VERSION",
    "REIGN_HOMEPAGE_URL",
    "REIGN_INDICATORS",
    "REIGN_OBSERVATION_FAMILY",
    "REIGN_SOURCE_KEY",
    "REIGN_SUPPORTED_FAMILIES",
    "ReignAdapter",
    "build_reign_descriptor",
    "create_reign_adapter",
    "register_reign",
]
