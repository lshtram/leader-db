"""Unified-source World Bank Poverty and Inequality Platform (PIP)
adapter.

This package hosts the World Bank PIP clean adapter rebuilt
under the clean ``leaders_db.sources`` interface. The adapter
is the next feasible clean-interface-only source after
``ctbto_treaty_status`` and follows the documented Phase C
protocol for clean migrations: no legacy
``leaders_db.ingest.STAGE2_ADAPTERS`` wiring, no live network
fetch (the unified adapter is offline / cache-only in this
slice), no manual propagation of source metadata, and a
runtime-local ``metadata.json`` next to the cached export.

The World Bank PIP is the World-Bank-maintained public
database of poverty, inequality, and distribution indicators,
served through the documented PIP API at
``https://pip.worldbank.org/api`` (CSV / JSON endpoints) and
the PIP home page at ``https://pip.worldbank.org/``. The
unified adapter supports BOTH cached shapes per the task
brief:

1. **Direct CSV** -- a plain CSV file at
   ``data/raw/world_bank_poverty_inequality_platform/pip_stats.csv``
   carrying the canonical 11-column PIP schema (country_code /
   country_name / year / reporting_level / welfare_type /
   poverty_line / headcount / poverty_gap / gini /
   version_id / ppp_version).
2. **Cached JSON wrapper** -- a JSON array of objects at
   ``data/raw/world_bank_poverty_inequality_platform/pip_stats.json``
   carrying the same 11-column PIP schema as object keys. The
   JSON fallback shape mirrors the canonical CSV schema.

The adapter validates the parsed header against the 11
canonical required columns
(``country_code`` / ``country_name`` / ``year`` /
``reporting_level`` / ``welfare_type`` / ``poverty_line`` /
``headcount`` / ``poverty_gap`` / ``gini`` / ``version_id`` /
``ppp_version``) and refuses to
emit any observations when a required column is missing (a
missing required column is a schema contract violation -- the
transform layer MUST NOT silently emit partial output on a
schema contract violation). Bundle metadata must also declare
the canonical PIP ``version_id`` and ``ppp_version`` values, and
every row must match that release / PPP basis before transform.

Public surface
--------------

- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY` /
  :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION`
  /
  :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR`
  /
  :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR`
  -- the canonical slug + version stamp + 1960-2024 coverage
  envelope.
- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL` /
  :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_API_URL` -- the
  canonical PIP citation landing page + the canonical PIP
  backend API URL.
- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY`
  / :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT`
  -- the canonical citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md``
  ``world_bank_poverty_inequality_platform`` section).
- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY`
  / :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES`
  -- the single observation family the descriptor advertises.
- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES` /
  the 3 indicator constants -- the canonical catalog.
- :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS` /
  :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS`
  -- the schema contract for the cached CSV / JSON header.
- :func:`build_world_bank_poverty_inequality_platform_descriptor`
  -- factory for the canonical :class:`SourceDescriptor`.
- :class:`WorldBankPovertyInequalityPlatformAdapter` -- the
  unified :class:`SourceAdapter` implementation.
- :func:`create_world_bank_poverty_inequality_platform_adapter`
  -- explicit factory.
- :func:`register_world_bank_poverty_inequality_platform` --
  explicit registration helper for tests and future
  composition.
- :class:`WorldBankPipSchemaError` -- structured failure raised
  when the cached CSV / JSON header is missing required
  columns.
"""

from __future__ import annotations

from ._constants import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_API_URL,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILE_NAMES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION,
)
from ._descriptor import (
    build_world_bank_poverty_inequality_platform_descriptor,
)
from ._raw_read import (
    WorldBankPipSchemaError,
    read_world_bank_poverty_inequality_platform_cache,
)
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    emit_world_bank_poverty_inequality_platform_observations,
    indicator_codes,
    required_columns,
)
from .adapter import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY,
    WorldBankPovertyInequalityPlatformAdapter,
    create_world_bank_poverty_inequality_platform_adapter,
    register_world_bank_poverty_inequality_platform,
)

__all__ = [
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_API_URL",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILE_NAMES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION",
    "WorldBankPipSchemaError",
    "WorldBankPovertyInequalityPlatformAdapter",
    "build_world_bank_poverty_inequality_platform_descriptor",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_world_bank_poverty_inequality_platform_adapter",
    "emit_world_bank_poverty_inequality_platform_observations",
    "indicator_codes",
    "read_world_bank_poverty_inequality_platform_cache",
    "register_world_bank_poverty_inequality_platform",
    "required_columns",
]
