"""Unified-source Penn World Table 10.01 adapter.

This package hosts the first source rebuilt under the clean
``leaders_db.sources`` interface (docs/architecture/sources.md
§7.1 priority 1 and docs/requirements/sources.md §12 SRC-MIG-005).
The adapter deliberately wraps the existing legacy reader / transform
under :mod:`leaders_db.ingest.sources.pwt` so the canonical PWT
parsing logic is reused without duplication; the legacy ingest
package is imported lazily inside adapter methods only so the
``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved.

Public surface
--------------

- :data:`PWT_SOURCE_KEY` / :data:`PWT_DEFAULT_VERSION` / canonical
  bundle filenames.
- :data:`PWT_COVERAGE_START_YEAR` / :data:`PWT_COVERAGE_END_YEAR`
  -- the 1950-2019 coverage envelope.
- :data:`PWT_ATTRIBUTION_TEXT` -- the canonical citation text
  (Rule #15; byte-identical to ``docs/sources/attributions.md``).
- :func:`build_pwt_descriptor` -- factory for the canonical
  :class:`SourceDescriptor`.
- :class:`PWTAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_pwt_adapter` -- explicit factory. Callers wire it
  into an :class:`InMemorySourceRegistry` via :func:`register_pwt`
  or directly. The package does NOT auto-register on import
  (the registry is passive by design -- see
  docs/architecture/sources.md §10.1).
- :func:`register_pwt` -- explicit registration helper for tests
  and future composition.
"""

from __future__ import annotations

from ._descriptor import (
    PWT_ATTRIBUTION_KEY,
    PWT_ATTRIBUTION_TEXT,
    PWT_COVERAGE_END_YEAR,
    PWT_COVERAGE_START_YEAR,
    PWT_DATA_SHEET_NAME,
    PWT_DEFAULT_VERSION,
    PWT_HOMEPAGE_URL,
    PWT_METADATA_NAME,
    PWT_OBSERVATION_FAMILY,
    PWT_SOURCE_KEY,
    PWT_SUPPORTED_FAMILIES,
    PWT_XLSX_NAME,
    build_pwt_descriptor,
)
from .adapter import (
    PWT_ADAPTER_FACTORY,
    PWTAdapter,
    create_pwt_adapter,
    register_pwt,
)

__all__ = [
    "PWT_ADAPTER_FACTORY",
    "PWT_ATTRIBUTION_KEY",
    "PWT_ATTRIBUTION_TEXT",
    "PWT_COVERAGE_END_YEAR",
    "PWT_COVERAGE_START_YEAR",
    "PWT_DATA_SHEET_NAME",
    "PWT_DEFAULT_VERSION",
    "PWT_HOMEPAGE_URL",
    "PWT_METADATA_NAME",
    "PWT_OBSERVATION_FAMILY",
    "PWT_SOURCE_KEY",
    "PWT_SUPPORTED_FAMILIES",
    "PWT_XLSX_NAME",
    "PWTAdapter",
    "build_pwt_descriptor",
    "create_pwt_adapter",
    "register_pwt",
]
