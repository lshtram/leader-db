"""Freedom House Freedom in the World clean source adapter."""

from __future__ import annotations

from ._constants import (
    FREEDOM_HOUSE_ATTRIBUTION_KEY,
    FREEDOM_HOUSE_ATTRIBUTION_TEXT,
    FREEDOM_HOUSE_COVERAGE_END_YEAR,
    FREEDOM_HOUSE_COVERAGE_START_YEAR,
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_HOMEPAGE_URL,
    FREEDOM_HOUSE_INDICATORS,
    FREEDOM_HOUSE_OBSERVATION_FAMILY,
    FREEDOM_HOUSE_RATINGS_XLSX_NAME,
    FREEDOM_HOUSE_SOURCE_KEY,
    FREEDOM_HOUSE_SUPPORTED_FAMILIES,
)
from ._descriptor import build_freedom_house_descriptor
from .adapter import (
    FREEDOM_HOUSE_ADAPTER_FACTORY,
    FreedomHouseAdapter,
    create_freedom_house_adapter,
    register_freedom_house,
)

__all__ = [
    "FREEDOM_HOUSE_ADAPTER_FACTORY",
    "FREEDOM_HOUSE_ATTRIBUTION_KEY",
    "FREEDOM_HOUSE_ATTRIBUTION_TEXT",
    "FREEDOM_HOUSE_COVERAGE_END_YEAR",
    "FREEDOM_HOUSE_COVERAGE_START_YEAR",
    "FREEDOM_HOUSE_DEFAULT_VERSION",
    "FREEDOM_HOUSE_HOMEPAGE_URL",
    "FREEDOM_HOUSE_INDICATORS",
    "FREEDOM_HOUSE_OBSERVATION_FAMILY",
    "FREEDOM_HOUSE_RATINGS_XLSX_NAME",
    "FREEDOM_HOUSE_SOURCE_KEY",
    "FREEDOM_HOUSE_SUPPORTED_FAMILIES",
    "FreedomHouseAdapter",
    "build_freedom_house_descriptor",
    "create_freedom_house_adapter",
    "register_freedom_house",
]
