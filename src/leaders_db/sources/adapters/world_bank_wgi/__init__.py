"""Unified-source World Bank Worldwide Governance Indicators adapter.

This package hosts the fourth source rebuilt under the clean
``leaders_db.sources`` interface (docs/architecture/sources.md
§7.1 priority 4 and docs/requirements/sources.md §12 SRC-MIG-005),
after PWT, Maddison Project, and World Bank WDI. The adapter
implements the canonical ``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` + ``transform``)
and reuses the legacy reader / transform under
:mod:`leaders_db.ingest.wgi` and :mod:`leaders_db.ingest.wgi_io`
via lazy imports so the package boundary documented in
docs/architecture/sources.md §10.1 is preserved. The WGI unified
path is local-file only (no network): the canonical bundle is
``data/raw/world_bank_wgi/wgidataset.xlsx`` + ``metadata.json``
and the adapter never invokes the network.

Public surface
--------------

- :data:`WORLD_BANK_WGI_SOURCE_KEY` /
  :data:`WORLD_BANK_WGI_DEFAULT_VERSION` / canonical bundle file
  names.
- :data:`WORLD_BANK_WGI_COVERAGE_START_YEAR` /
  :data:`WORLD_BANK_WGI_COVERAGE_END_YEAR` -- the 1996-2022
  coverage envelope (the legacy xlsx ends at 2022; "2023" in the
  doc refers to the release year).
- :data:`WORLD_BANK_WGI_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` and to the legacy
  :data:`WGI_ATTRIBUTION` constant in
  ``src/leaders_db/ingest/wgi_io.py``).
- :func:`build_world_bank_wgi_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`WGIAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_world_bank_wgi_adapter` -- explicit factory.
  Callers wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_world_bank_wgi` or directly. The package does
  NOT auto-register on import (the registry is passive by design
  -- see docs/architecture/sources.md §10.1).
- :func:`register_world_bank_wgi` -- explicit registration
  helper for tests and future composition.
"""

from __future__ import annotations

from ._descriptor import (
    WORLD_BANK_WGI_ATTRIBUTION_KEY,
    WORLD_BANK_WGI_ATTRIBUTION_TEXT,
    WORLD_BANK_WGI_COVERAGE_END_YEAR,
    WORLD_BANK_WGI_COVERAGE_START_YEAR,
    WORLD_BANK_WGI_DEFAULT_VERSION,
    WORLD_BANK_WGI_HOMEPAGE_URL,
    WORLD_BANK_WGI_METADATA_NAME,
    WORLD_BANK_WGI_OBSERVATION_FAMILY,
    WORLD_BANK_WGI_SOURCE_KEY,
    WORLD_BANK_WGI_SUPPORTED_FAMILIES,
    WORLD_BANK_WGI_XLSX_NAME,
    build_world_bank_wgi_descriptor,
)
from ._metadata_validators import (
    REQUIRED_METADATA_FIELDS_LEGACY_KEYS,
    REQUIRED_METADATA_FIELDS_PRIMARY_KEYS,
)
from ._readiness import (
    UNSUPPORTED_VERSION,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    WORLD_BANK_WGI_TRANSFORM_NAME,
    WORLD_BANK_WGI_XLSX_ASSET_ID,
    emit_world_bank_wgi_observations,
)
from .adapter import (
    WORLD_BANK_WGI_ADAPTER_FACTORY,
    WGIAdapter,
    create_world_bank_wgi_adapter,
    register_world_bank_wgi,
)

__all__ = [
    "REQUIRED_METADATA_FIELDS_LEGACY_KEYS",
    "REQUIRED_METADATA_FIELDS_PRIMARY_KEYS",
    "UNSUPPORTED_VERSION",
    "WORLD_BANK_WGI_ADAPTER_FACTORY",
    "WORLD_BANK_WGI_ATTRIBUTION_KEY",
    "WORLD_BANK_WGI_ATTRIBUTION_TEXT",
    "WORLD_BANK_WGI_COVERAGE_END_YEAR",
    "WORLD_BANK_WGI_COVERAGE_START_YEAR",
    "WORLD_BANK_WGI_DEFAULT_VERSION",
    "WORLD_BANK_WGI_HOMEPAGE_URL",
    "WORLD_BANK_WGI_METADATA_NAME",
    "WORLD_BANK_WGI_OBSERVATION_FAMILY",
    "WORLD_BANK_WGI_SOURCE_KEY",
    "WORLD_BANK_WGI_SUPPORTED_FAMILIES",
    "WORLD_BANK_WGI_TRANSFORM_NAME",
    "WORLD_BANK_WGI_XLSX_ASSET_ID",
    "WORLD_BANK_WGI_XLSX_NAME",
    "WGIAdapter",
    "build_world_bank_wgi_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_world_bank_wgi_adapter",
    "emit_world_bank_wgi_observations",
    "register_world_bank_wgi",
]
