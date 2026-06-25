"""Unified-source Varieties of Democracy (V-Dem) adapter.

This package hosts the fifth source rebuilt under the clean
``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 5 and
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI, and
World Bank WGI. The adapter implements the canonical
``SourceAdapter`` Protocol (``descriptor`` + ``check_ready``
+ ``read_raw`` + ``transform``) and reuses the legacy
reader / transform under :mod:`leaders_db.ingest.vdem_io`
via lazy imports so the package boundary documented in
docs/architecture/sources.md §10.1 is preserved. The V-Dem
unified path is local-file only (no network): the canonical
bundle is ``data/raw/vdem/V-Dem-CY-Full+Others-v16.csv`` +
``metadata.json`` + the original zip, and the adapter never
invokes the network.

Public surface
--------------

- :data:`VDEM_SOURCE_KEY` / :data:`VDEM_DEFAULT_VERSION` /
  canonical bundle file names (``VDEM_CSV_NAME``,
  ``VDEM_ZIP_NAME``, ``VDEM_METADATA_NAME``).
- :data:`VDEM_COVERAGE_START_YEAR` /
  :data:`VDEM_COVERAGE_END_YEAR` -- the 1789-2025 coverage
  envelope.
- :data:`VDEM_ATTRIBUTION_TEXT` -- the canonical citation
  text (Rule #15; byte-identical to the legacy
  ``VDEM_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/vdem_io.py`` and to the
  ``vdem`` section in ``docs/sources/attributions.md``).
- The five observation families:
  :data:`VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM` /
  :data:`VDEM_OBSERVATION_FAMILY_GOVERNANCE` /
  :data:`VDEM_OBSERVATION_FAMILY_CORRUPTION` /
  :data:`VDEM_OBSERVATION_FAMILY_REPRESSION` /
  :data:`VDEM_OBSERVATION_FAMILY_SOCIAL`.
- :func:`build_vdem_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`VDemAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_vdem_adapter` -- explicit factory. Callers
  wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_vdem` or directly. The package does NOT
  auto-register on import (the registry is passive by
  design -- see docs/architecture/sources.md §10.1).
- :func:`register_vdem` -- explicit registration helper
  for tests and future composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._descriptor import (
    VDEM_ATTRIBUTION_KEY,
    VDEM_ATTRIBUTION_TEXT,
    VDEM_COVERAGE_END_YEAR,
    VDEM_COVERAGE_START_YEAR,
    VDEM_CSV_ASSET_ID,
    VDEM_CSV_NAME,
    VDEM_DEFAULT_VERSION,
    VDEM_HOMEPAGE_URL,
    VDEM_METADATA_NAME,
    VDEM_OBSERVATION_FAMILY_CORRUPTION,
    VDEM_OBSERVATION_FAMILY_GOVERNANCE,
    VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    VDEM_OBSERVATION_FAMILY_REPRESSION,
    VDEM_OBSERVATION_FAMILY_SOCIAL,
    VDEM_SOURCE_KEY,
    VDEM_SUPPORTED_FAMILIES,
    VDEM_ZIP_NAME,
    build_vdem_descriptor,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    REQUIRED_METADATA_FIELDS,
    UNSUPPORTED_VERSION,
    VDEM_CHECKSUM_MISMATCH,
)
from ._missing_values import (
    VDEM_MISSING_SENTINEL,
    VDEM_MISSING_STRINGS,
    coerce_float,
    is_real_number,
    raw_value_to_string,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    VDEM_TRANSFORM_NAME,
    emit_vdem_observations,
)
from .adapter import (
    VDEM_ADAPTER_FACTORY,
    VDemAdapter,
    create_vdem_adapter,
    register_vdem,
)

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "DEFAULT_CATALOG_PATH",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "VDEM_ADAPTER_FACTORY",
    "VDEM_ATTRIBUTION_KEY",
    "VDEM_ATTRIBUTION_TEXT",
    "VDEM_CHECKSUM_MISMATCH",
    "VDEM_COVERAGE_END_YEAR",
    "VDEM_COVERAGE_START_YEAR",
    "VDEM_CSV_ASSET_ID",
    "VDEM_CSV_NAME",
    "VDEM_DEFAULT_VERSION",
    "VDEM_HOMEPAGE_URL",
    "VDEM_METADATA_NAME",
    "VDEM_MISSING_SENTINEL",
    "VDEM_MISSING_STRINGS",
    "VDEM_OBSERVATION_FAMILY_CORRUPTION",
    "VDEM_OBSERVATION_FAMILY_GOVERNANCE",
    "VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
    "VDEM_OBSERVATION_FAMILY_REPRESSION",
    "VDEM_OBSERVATION_FAMILY_SOCIAL",
    "VDEM_SOURCE_KEY",
    "VDEM_SUPPORTED_FAMILIES",
    "VDEM_TRANSFORM_NAME",
    "VDEM_ZIP_NAME",
    "VDemAdapter",
    "build_vdem_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "coerce_float",
    "collect_request_scoping_warnings",
    "create_vdem_adapter",
    "emit_vdem_observations",
    "is_real_number",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "raw_value_to_string",
    "register_vdem",
]
