"""UNDP HDI clean source adapter."""

from __future__ import annotations

from ._constants import (
    UNDP_HDI_ATTRIBUTION_KEY,
    UNDP_HDI_ATTRIBUTION_TEXT,
    UNDP_HDI_COVERAGE_END_YEAR,
    UNDP_HDI_COVERAGE_START_YEAR,
    UNDP_HDI_CSV_NAME,
    UNDP_HDI_DEFAULT_VERSION,
    UNDP_HDI_HOMEPAGE_URL,
    UNDP_HDI_INDICATORS,
    UNDP_HDI_OBSERVATION_FAMILY,
    UNDP_HDI_PROXY_REQUESTED_YEAR,
    UNDP_HDI_PROXY_YEAR,
    UNDP_HDI_SOURCE_KEY,
    UNDP_HDI_SUPPORTED_FAMILIES,
)
from ._descriptor import build_undp_hdi_descriptor
from .adapter import (
    UNDP_HDI_ADAPTER_FACTORY,
    UndpHdiAdapter,
    create_undp_hdi_adapter,
    register_undp_hdi,
)

__all__ = [
    "UNDP_HDI_ADAPTER_FACTORY",
    "UNDP_HDI_ATTRIBUTION_KEY",
    "UNDP_HDI_ATTRIBUTION_TEXT",
    "UNDP_HDI_COVERAGE_END_YEAR",
    "UNDP_HDI_COVERAGE_START_YEAR",
    "UNDP_HDI_CSV_NAME",
    "UNDP_HDI_DEFAULT_VERSION",
    "UNDP_HDI_HOMEPAGE_URL",
    "UNDP_HDI_INDICATORS",
    "UNDP_HDI_OBSERVATION_FAMILY",
    "UNDP_HDI_PROXY_REQUESTED_YEAR",
    "UNDP_HDI_PROXY_YEAR",
    "UNDP_HDI_SOURCE_KEY",
    "UNDP_HDI_SUPPORTED_FAMILIES",
    "UndpHdiAdapter",
    "build_undp_hdi_descriptor",
    "create_undp_hdi_adapter",
    "register_undp_hdi",
]
