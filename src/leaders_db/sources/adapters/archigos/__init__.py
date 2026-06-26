"""Archigos v4.1 clean source adapter."""

from __future__ import annotations

from ._constants import (
    ARCHIGOS_ATTRIBUTION_KEY,
    ARCHIGOS_ATTRIBUTION_TEXT,
    ARCHIGOS_COVERAGE_END_YEAR,
    ARCHIGOS_COVERAGE_START_YEAR,
    ARCHIGOS_DEFAULT_VERSION,
    ARCHIGOS_DTA_NAME,
    ARCHIGOS_HOMEPAGE_URL,
    ARCHIGOS_INDICATORS,
    ARCHIGOS_OBSERVATION_FAMILY,
    ARCHIGOS_SOURCE_KEY,
    ARCHIGOS_SUPPORTED_FAMILIES,
)
from ._descriptor import build_archigos_descriptor
from .adapter import (
    ARCHIGOS_ADAPTER_FACTORY,
    ArchigosAdapter,
    create_archigos_adapter,
    register_archigos,
)

__all__ = [
    "ARCHIGOS_ADAPTER_FACTORY",
    "ARCHIGOS_ATTRIBUTION_KEY",
    "ARCHIGOS_ATTRIBUTION_TEXT",
    "ARCHIGOS_COVERAGE_END_YEAR",
    "ARCHIGOS_COVERAGE_START_YEAR",
    "ARCHIGOS_DEFAULT_VERSION",
    "ARCHIGOS_DTA_NAME",
    "ARCHIGOS_HOMEPAGE_URL",
    "ARCHIGOS_INDICATORS",
    "ARCHIGOS_OBSERVATION_FAMILY",
    "ARCHIGOS_SOURCE_KEY",
    "ARCHIGOS_SUPPORTED_FAMILIES",
    "ArchigosAdapter",
    "build_archigos_descriptor",
    "create_archigos_adapter",
    "register_archigos",
]
