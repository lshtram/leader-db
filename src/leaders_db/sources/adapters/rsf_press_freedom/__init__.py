"""Unified-source Reporters Without Borders (RSF) World
Press Freedom Index adapter.

This package hosts the ninth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 7 and
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, and Political Terror
Scale. The adapter implements the canonical
``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` +
``transform``) and reuses the legacy reader /
transform / catalog under
``leaders_db.ingest.rsf_press_freedom_csv`` and
``leaders_db.ingest.rsf_press_freedom_io`` via lazy
imports so the package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved.

The RSF World Press Freedom Index unified path is
local-file only (no network). The canonical bundle
is ``data/raw/rsf_press_freedom/`` with 24 annual
CSVs (2002-2010 + 2012-2026; the direct ``2011.csv``
is absent -- RSF's combined 2011/2012 edition is
represented by the 2012 CSV; its ``Year (N)`` column
reads ``"2011-12"``).

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``rsf_press_freedom`` (CLI
dispatch key + adapter key + attribution key). The
data-lake folder is also ``rsf_press_freedom/`` (the
slug is the folder name; no source-key / folder-
alias reconciliation is needed, unlike ``pts`` /
``political_terror_scale`` where the slug differs
from the folder). The descriptor's
``source_id.slug`` is ``"rsf_press_freedom"``.

Public surface
--------------

- :data:`RSF_PRESS_FREEDOM_SOURCE_KEY` /
  :data:`RSF_PRESS_FREEDOM_DEFAULT_VERSION` /
  canonical bundle file names
  (``RSF_PRESS_FREEDOM_METADATA_NAME`` +
  :data:`RSF_PRESS_FREEDOM_CSV_NAME_PATTERN`).
- :data:`RSF_PRESS_FREEDOM_COVERAGE_START_YEAR` /
  :data:`RSF_PRESS_FREEDOM_COVERAGE_END_YEAR` /
  :data:`RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR` /
  :data:`RSF_PRESS_FREEDOM_AVAILABLE_YEARS` -- the
  2002-2026 coverage envelope + the documented 2011
  missing / direct-CSV caveat.
- :data:`RSF_PRESS_FREEDOM_ATTRIBUTION_KEY` /
  :data:`RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT` -- the
  canonical citation text (Rule #15; byte-identical
  to the legacy ``RSF_PRESS_FREEDOM_ATTRIBUTION``
  constant in
  ``src/leaders_db/ingest/rsf_press_freedom_io.py``
  and to the ``rsf_press_freedom`` section in
  ``docs/sources/attributions.md``).
- The single observation family:
  :data:`RSF_PRESS_FREEDOM_OBSERVATION_FAMILY`
  (``political_freedom_country_year``).
- The 7 indicator names:
  :data:`RSF_PRESS_FREEDOM_INDICATOR_SCORE` /
  :data:`RSF_PRESS_FREEDOM_INDICATOR_RANK` +
  :data:`RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT` /
  :data:`RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT` /
  :data:`RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT` /
  :data:`RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT` /
  :data:`RSF_PRESS_FREEDOM_INDICATOR_SAFETY` (and the
  7-tuple :data:`RSF_PRESS_FREEDOM_INDICATOR_NAMES`).
- :data:`RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE` --
  the structured warning code for the documented 2011
  missing / direct-CSV caveat.
- :data:`RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022` /
  :data:`RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022` --
  the pre/post-2022 schema group constants
  preserved on every observation's
  ``extension["rsf_schema_group"]`` field.
- :func:`build_rsf_press_freedom_descriptor` --
  factory for the canonical
  :class:`SourceDescriptor`.
- :class:`RSFPressFreedomAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_rsf_press_freedom_adapter` -- explicit
  factory. Callers wire it into an
  :class:`InMemorySourceRegistry` via
  :func:`register_rsf_press_freedom` or directly.
  The package does NOT auto-register on import (the
  registry is passive by design -- see
  ``docs/architecture/sources.md`` §10.1).
- :func:`register_rsf_press_freedom` -- explicit
  registration helper for tests and future
  composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._constants import (
    RSF_PRESS_FREEDOM_ATTRIBUTION_KEY,
    RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT,
    RSF_PRESS_FREEDOM_AVAILABLE_YEARS,
    RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS,
    RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH,
    RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
    RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
    RSF_PRESS_FREEDOM_CSV_NAME_PATTERN,
    RSF_PRESS_FREEDOM_DEFAULT_VERSION,
    RSF_PRESS_FREEDOM_HOMEPAGE_URL,
    RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_NAMES,
    RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_RANK,
    RSF_PRESS_FREEDOM_INDICATOR_SAFETY,
    RSF_PRESS_FREEDOM_INDICATOR_SCORE,
    RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT,
    RSF_PRESS_FREEDOM_METADATA_NAME,
    RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH,
    RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR,
    RSF_PRESS_FREEDOM_OBSERVATION_FAMILY,
    RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
    RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES,
    RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE,
    _csv_asset_id_for_year,
)
from ._descriptor import build_rsf_press_freedom_descriptor
from ._files_validators import (
    _check_year_files_entry,
    _checksum_match_blocker,
    _find_files_entry,
)
from ._helpers import (
    _find_spec_for_variable,
    _is_component_raw_column,
    _parse_source_row_reference,
    _resolve_actual_column_name,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    REQUIRED_METADATA_FIELDS,
    RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP,
    RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP,
    UNSUPPORTED_VERSION,
    _ingestion_status_blocker,
    _local_files_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)
from ._metadata_version_validators import (
    _files_blocker,
    _metadata_source_version_blocker,
)
from ._missing_values import (
    _coerce_rank_value,
    _coerce_score_value,
    _is_missing,
    _normalize_decimal,
    _raw_cell_text,
)
from ._observation_builder import build_observation
from ._observation_helpers import (
    RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS,
    RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022,
    RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022,
    RSF_PRESS_FREEDOM_TRANSFORM_NAME,
    _default_asset_id_for_year,
    _default_source_version,
    _detect_schema_group,
    _indicator_names,
    _raw_columns,
    _resolve_value_type,
)
from ._pipeline import transform_rsf_press_freedom_observations
from ._raw_read import (
    _bundle_dir,
    _csv_name_for_year,
    _csv_path_for_year,
    _metadata_path,
    _resolve_years_for_request,
    read_rsf_press_freedom_csv,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._registration import (
    RSF_PRESS_FREEDOM_ADAPTER_FACTORY,
    create_rsf_press_freedom_adapter,
    register_rsf_press_freedom,
)
from ._transform import emit_rsf_press_freedom_observations
from ._year_validators import (
    _check_year_2011,
    _check_year_csv_presence,
    _check_year_csvs,
    _resolve_years_for_validation,
)
from .adapter import RSFPressFreedomAdapter

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "DEFAULT_CATALOG_PATH",
    "REQUIRED_METADATA_FIELDS",
    "RSF_PRESS_FREEDOM_ADAPTER_FACTORY",
    "RSF_PRESS_FREEDOM_ATTRIBUTION_KEY",
    "RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT",
    "RSF_PRESS_FREEDOM_AVAILABLE_YEARS",
    "RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS",
    "RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP",
    "RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP",
    "RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH",
    "RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS",
    "RSF_PRESS_FREEDOM_COVERAGE_END_YEAR",
    "RSF_PRESS_FREEDOM_COVERAGE_START_YEAR",
    "RSF_PRESS_FREEDOM_CSV_NAME_PATTERN",
    "RSF_PRESS_FREEDOM_DEFAULT_VERSION",
    "RSF_PRESS_FREEDOM_HOMEPAGE_URL",
    "RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_NAMES",
    "RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_RANK",
    "RSF_PRESS_FREEDOM_INDICATOR_SAFETY",
    "RSF_PRESS_FREEDOM_INDICATOR_SCORE",
    "RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT",
    "RSF_PRESS_FREEDOM_METADATA_NAME",
    "RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH",
    "RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR",
    "RSF_PRESS_FREEDOM_OBSERVATION_FAMILY",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_RANK",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE",
    "RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022",
    "RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES",
    "RSF_PRESS_FREEDOM_TRANSFORM_NAME",
    "RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE",
    "UNSUPPORTED_VERSION",
    "RSFPressFreedomAdapter",
    "_bundle_dir",
    "_check_year_2011",
    "_check_year_csv_presence",
    "_check_year_csvs",
    "_check_year_files_entry",
    "_checksum_match_blocker",
    "_coerce_rank_value",
    "_coerce_score_value",
    "_csv_asset_id_for_year",
    "_csv_name_for_year",
    "_csv_path_for_year",
    "_default_asset_id_for_year",
    "_default_source_version",
    "_detect_schema_group",
    "_files_blocker",
    "_find_files_entry",
    "_find_spec_for_variable",
    "_indicator_names",
    "_ingestion_status_blocker",
    "_is_component_raw_column",
    "_is_missing",
    "_local_files_blocker",
    "_metadata_path",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_normalize_decimal",
    "_parse_source_row_reference",
    "_presence_blocker",
    "_raw_cell_text",
    "_raw_columns",
    "_read_metadata_payload",
    "_required_fields_blocker",
    "_resolve_actual_column_name",
    "_resolve_value_type",
    "_resolve_years_for_request",
    "_resolve_years_for_validation",
    "build_observation",
    "build_rsf_press_freedom_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_rsf_press_freedom_adapter",
    "emit_rsf_press_freedom_observations",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "read_rsf_press_freedom_csv",
    "register_rsf_press_freedom",
    "transform_rsf_press_freedom_observations",
]
