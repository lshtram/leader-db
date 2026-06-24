"""Unified-source Maddison Project Database 2023 adapter.

This package hosts the second source rebuilt under the clean
``leaders_db.sources`` interface (docs/architecture/sources.md
§7.1 priority 2 and docs/requirements/sources.md §12 SRC-MIG-005),
after the PWT 10.01 adapter. The adapter deliberately wraps the
existing legacy reader / catalog loader under
:mod:`leaders_db.ingest.maddison_project_xlsx` so the canonical
Maddison parsing logic is reused without duplication; the legacy
ingest package is imported lazily inside adapter methods only so
the ``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved.

Public surface
--------------

- :data:`MADDISON_PROJECT_SOURCE_KEY` /
  :data:`MADDISON_PROJECT_DEFAULT_VERSION` / canonical bundle
  filenames.
- :data:`MADDISON_PROJECT_COVERAGE_START_YEAR` /
  :data:`MADDISON_PROJECT_COVERAGE_END_YEAR` -- the 1-2022
  coverage envelope.
- :data:`MADDISON_PROJECT_PROXY_REQUESTED_YEAR` /
  :data:`MADDISON_PROJECT_PROXY_YEAR` -- the documented 2023 ->
  2022 1-year-gap proxy mapping.
- :data:`MADDISON_PROJECT_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` and to the legacy
  :data:`MADDISON_PROJECT_ATTRIBUTION` constant in
  ``src/leaders_db/ingest/maddison_project_io.py``).
- :func:`build_maddison_project_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`MaddisonProjectAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_maddison_project_adapter` -- explicit factory.
  Callers wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_maddison_project` or directly. The package
  does NOT auto-register on import (the registry is passive by
  design -- see docs/architecture/sources.md §10.1).
- :func:`register_maddison_project` -- explicit registration
  helper for tests and future composition.
"""

from __future__ import annotations

from ._descriptor import (
    MADDISON_PROJECT_ATTRIBUTION_KEY,
    MADDISON_PROJECT_ATTRIBUTION_TEXT,
    MADDISON_PROJECT_COLUMN_UNITS,
    MADDISON_PROJECT_COVERAGE_END_YEAR,
    MADDISON_PROJECT_COVERAGE_START_YEAR,
    MADDISON_PROJECT_DEFAULT_VERSION,
    MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN,
    MADDISON_PROJECT_HOMEPAGE_URL,
    MADDISON_PROJECT_METADATA_NAME,
    MADDISON_PROJECT_OBSERVATION_FAMILY,
    MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
    MADDISON_PROJECT_PROXY_YEAR,
    MADDISON_PROJECT_SHEET_NAME,
    MADDISON_PROJECT_SOURCE_KEY,
    MADDISON_PROJECT_SUPPORTED_FAMILIES,
    MADDISON_PROJECT_TRANSFORM_NAME,
    MADDISON_PROJECT_XLSX_ASSET_ID,
    MADDISON_PROJECT_XLSX_NAME,
    build_maddison_project_descriptor,
)
from .adapter import (
    MADDISON_PROJECT_ADAPTER_FACTORY,
    MaddisonProjectAdapter,
    create_maddison_project_adapter,
    register_maddison_project,
)

__all__ = [
    "MADDISON_PROJECT_ADAPTER_FACTORY",
    "MADDISON_PROJECT_ATTRIBUTION_KEY",
    "MADDISON_PROJECT_ATTRIBUTION_TEXT",
    "MADDISON_PROJECT_COLUMN_UNITS",
    "MADDISON_PROJECT_COVERAGE_END_YEAR",
    "MADDISON_PROJECT_COVERAGE_START_YEAR",
    "MADDISON_PROJECT_DEFAULT_VERSION",
    "MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN",
    "MADDISON_PROJECT_HOMEPAGE_URL",
    "MADDISON_PROJECT_METADATA_NAME",
    "MADDISON_PROJECT_OBSERVATION_FAMILY",
    "MADDISON_PROJECT_PROXY_REQUESTED_YEAR",
    "MADDISON_PROJECT_PROXY_YEAR",
    "MADDISON_PROJECT_SHEET_NAME",
    "MADDISON_PROJECT_SOURCE_KEY",
    "MADDISON_PROJECT_SUPPORTED_FAMILIES",
    "MADDISON_PROJECT_TRANSFORM_NAME",
    "MADDISON_PROJECT_XLSX_ASSET_ID",
    "MADDISON_PROJECT_XLSX_NAME",
    "MaddisonProjectAdapter",
    "build_maddison_project_descriptor",
    "create_maddison_project_adapter",
    "register_maddison_project",
]
