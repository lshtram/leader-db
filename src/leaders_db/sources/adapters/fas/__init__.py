"""FAS (Federation of American Scientists) Nuclear Notebook clean source adapter.

The :class:`FasAdapter` is the next source rebuilt under the clean
``leaders_db.sources`` interface (``docs/architecture/sources.md``
§7.1 priority 18, ``docs/requirements/sources.md`` §12 SRC-MIG-005),
after PWT, Maddison, WDI, WGI, V-Dem, UCDP, Transparency CPI, PTS,
RSF, BTI, Freedom House, Archigos, REIGN, SIPRI Milex, SIPRI
Yearbook Ch.7, CIRIGHTS, UNDP HDI, and WHO GHO API.

The clean adapter reads the staged local HTML cache
(``<raw_root>/fas/fas_status.html``) through lazy legacy parser
imports. The adapter NEVER falls through to HTTP in this slice --
the readiness gate enforces ``cache_policy="offline_only"`` /
``"prefer_cache"`` and rejects the unsupported ``"refresh"`` /
``"no_cache"`` policies with a structured
``unsupported_cache_policy`` error.
"""

from __future__ import annotations

from ._constants import (
    FAS_ATTRIBUTION_KEY,
    FAS_ATTRIBUTION_TEXT,
    FAS_CHECKSUM_MISMATCH,
    FAS_COVERAGE_END_YEAR,
    FAS_COVERAGE_START_YEAR,
    FAS_DEFAULT_CACHE_POLICY,
    FAS_DEFAULT_VERSION,
    FAS_HOMEPAGE_URL,
    FAS_HTML_ASSET_ID,
    FAS_HTML_NAME,
    FAS_INDICATORS,
    FAS_LOCAL_FILES_INVALID,
    FAS_METADATA_NAME,
    FAS_METADATA_VERSION_MISMATCH,
    FAS_OBSERVATION_FAMILY,
    FAS_PUBLISHER_URL,
    FAS_RAW_COLUMNS,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
    FAS_SUPPORTED_FAMILIES,
    FAS_TRANSFORM_NAME,
    FAS_UNSUPPORTED_CACHE_POLICY,
    FAS_UNSUPPORTED_VERSION,
)
from ._descriptor import build_fas_descriptor
from .adapter import (
    FAS_ADAPTER_FACTORY,
    FasAdapter,
    create_fas_adapter,
    register_fas,
)

__all__ = [
    "FAS_ADAPTER_FACTORY",
    "FAS_ATTRIBUTION_KEY",
    "FAS_ATTRIBUTION_TEXT",
    "FAS_CHECKSUM_MISMATCH",
    "FAS_COVERAGE_END_YEAR",
    "FAS_COVERAGE_START_YEAR",
    "FAS_DEFAULT_CACHE_POLICY",
    "FAS_DEFAULT_VERSION",
    "FAS_HOMEPAGE_URL",
    "FAS_HTML_ASSET_ID",
    "FAS_HTML_NAME",
    "FAS_INDICATORS",
    "FAS_LOCAL_FILES_INVALID",
    "FAS_METADATA_NAME",
    "FAS_METADATA_VERSION_MISMATCH",
    "FAS_OBSERVATION_FAMILY",
    "FAS_PUBLISHER_URL",
    "FAS_RAW_COLUMNS",
    "FAS_SNAPSHOT_YEAR",
    "FAS_SOURCE_KEY",
    "FAS_STATUS_PAGE_URL",
    "FAS_SUPPORTED_FAMILIES",
    "FAS_TRANSFORM_NAME",
    "FAS_UNSUPPORTED_CACHE_POLICY",
    "FAS_UNSUPPORTED_VERSION",
    "FasAdapter",
    "build_fas_descriptor",
    "create_fas_adapter",
    "register_fas",
]
