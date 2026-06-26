"""CIRIGHTS clean source adapter."""

from __future__ import annotations

from ._constants import (
    CIRIGHTS_ATTRIBUTION_KEY,
    CIRIGHTS_ATTRIBUTION_TEXT,
    CIRIGHTS_COVERAGE_END_YEAR,
    CIRIGHTS_COVERAGE_START_YEAR,
    CIRIGHTS_DEFAULT_VERSION,
    CIRIGHTS_HOMEPAGE_URL,
    CIRIGHTS_INDICATORS,
    CIRIGHTS_OBSERVATION_FAMILY,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_SUPPORTED_FAMILIES,
    CIRIGHTS_XLSX_NAME,
)
from ._descriptor import build_cirights_descriptor
from .adapter import (
    CIRIGHTS_ADAPTER_FACTORY,
    CirightsAdapter,
    create_cirights_adapter,
    register_cirights,
)

__all__ = [
    "CIRIGHTS_ADAPTER_FACTORY",
    "CIRIGHTS_ATTRIBUTION_KEY",
    "CIRIGHTS_ATTRIBUTION_TEXT",
    "CIRIGHTS_COVERAGE_END_YEAR",
    "CIRIGHTS_COVERAGE_START_YEAR",
    "CIRIGHTS_DEFAULT_VERSION",
    "CIRIGHTS_HOMEPAGE_URL",
    "CIRIGHTS_INDICATORS",
    "CIRIGHTS_OBSERVATION_FAMILY",
    "CIRIGHTS_PROXY_REQUESTED_YEAR",
    "CIRIGHTS_PROXY_YEAR",
    "CIRIGHTS_SOURCE_KEY",
    "CIRIGHTS_SUPPORTED_FAMILIES",
    "CIRIGHTS_XLSX_NAME",
    "CirightsAdapter",
    "build_cirights_descriptor",
    "create_cirights_adapter",
    "register_cirights",
]
