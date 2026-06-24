"""Unified-source World Bank World Development Indicators adapter.

This package hosts the third source rebuilt under the clean
``leaders_db.sources`` interface (docs/architecture/sources.md
§7.1 priority 3 and docs/requirements/sources.md §12 SRC-MIG-005),
after the PWT 10.01 and Maddison Project Database 2023 adapters.
The adapter reads staged cache files through the local
cache-only path and does not invoke the legacy reader or HTTP
path for supported policies. It reuses the legacy catalog
loader under :mod:`leaders_db.ingest.wdi_io` for schema
compatibility only; imports are lazy so the
``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved.

Public surface
--------------

- :data:`WORLD_BANK_WDI_SOURCE_KEY` /
  :data:`WORLD_BANK_WDI_DEFAULT_VERSION` / canonical bundle /
  cache file names.
- :data:`WORLD_BANK_WDI_COVERAGE_START_YEAR` -- the documented
  1960+ coverage envelope.
- :data:`WORLD_BANK_WDI_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` and to the legacy
  :data:`WDI_ATTRIBUTION` constant in
  ``src/leaders_db/ingest/wdi_io.py``).
- :func:`build_world_bank_wdi_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`WDIAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_world_bank_wdi_adapter` -- explicit factory.
  Callers wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_world_bank_wdi` or directly. The package
  does NOT auto-register on import (the registry is passive
  by design -- see docs/architecture/sources.md §10.1).
- :func:`register_world_bank_wdi` -- explicit registration
  helper for tests and future composition.
"""

from __future__ import annotations

from ._descriptor import (
    WORLD_BANK_WDI_ATTRIBUTION_KEY,
    WORLD_BANK_WDI_ATTRIBUTION_TEXT,
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_COVERAGE_END_YEAR,
    WORLD_BANK_WDI_COVERAGE_START_YEAR,
    WORLD_BANK_WDI_DEFAULT_CACHE_POLICY,
    WORLD_BANK_WDI_DEFAULT_VERSION,
    WORLD_BANK_WDI_HOMEPAGE_URL,
    WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX,
    WORLD_BANK_WDI_METADATA_NAME,
    WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC,
    WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL,
    WORLD_BANK_WDI_SOURCE_KEY,
    WORLD_BANK_WDI_SUPPORTED_FAMILIES,
    build_world_bank_wdi_descriptor,
)
from ._transform import (
    WORLD_BANK_WDI_CACHE_ASSET_ID,
    WORLD_BANK_WDI_TRANSFORM_NAME,
)
from .adapter import (
    WDI_ADAPTER_FACTORY,
    WDIAdapter,
    create_world_bank_wdi_adapter,
    register_world_bank_wdi,
)

__all__ = [
    "WDI_ADAPTER_FACTORY",
    "WORLD_BANK_WDI_ATTRIBUTION_KEY",
    "WORLD_BANK_WDI_ATTRIBUTION_TEXT",
    "WORLD_BANK_WDI_CACHE_ASSET_ID",
    "WORLD_BANK_WDI_CACHE_DIR_NAME",
    "WORLD_BANK_WDI_COVERAGE_END_YEAR",
    "WORLD_BANK_WDI_COVERAGE_START_YEAR",
    "WORLD_BANK_WDI_DEFAULT_CACHE_POLICY",
    "WORLD_BANK_WDI_DEFAULT_VERSION",
    "WORLD_BANK_WDI_HOMEPAGE_URL",
    "WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX",
    "WORLD_BANK_WDI_METADATA_NAME",
    "WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC",
    "WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL",
    "WORLD_BANK_WDI_SOURCE_KEY",
    "WORLD_BANK_WDI_SUPPORTED_FAMILIES",
    "WORLD_BANK_WDI_TRANSFORM_NAME",
    "WDIAdapter",
    "build_world_bank_wdi_descriptor",
    "create_world_bank_wdi_adapter",
    "register_world_bank_wdi",
]
