"""Unified-source Bertelsmann Transformation Index (BTI) adapter.

This package hosts the tenth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 8 and
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, Political Terror Scale,
and Reporters Without Borders (RSF). The adapter
implements the canonical ``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` +
``transform``) and reuses the legacy reader /
transform / catalog under
``leaders_db.ingest.bti`` /
``leaders_db.ingest.bti_io`` /
``leaders_db.ingest.bti_xlsx`` via lazy imports so
the package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved.

The BTI unified path is local-file only (no network).
The canonical bundle is ``data/raw/bti/`` with the
cumulative ``BTI_2006-2026_Scores.xlsx`` (12 edition
sheets: one BTI edition per sheet from ``BTI 2006_old``
through ``BTI 2026``; 137-159 countries per edition;
123 columns) + the optional ``BTI2026_Codebook.pdf`` +
``metadata.json``.

Biennial sheet/year mapping
---------------------------

BTI is biennial: each edition covers the ~2-year
period preceding publication. For the prototype target
year 2023, the canonical mapping resolves to the
``"BTI 2024"`` sheet (covers 2022-2023). The
per-edition covered interval map is documented in
:data:`leaders_db.ingest.bti_io._BTI_EDITION_COVERED_INTERVAL`
and resolved at runtime via
:func:`leaders_db.ingest.bti_io.sheet_for_year`.

Public surface
--------------

- :data:`BTI_SOURCE_KEY` /
  :data:`BTI_DEFAULT_VERSION` /
  :data:`BTI_HOMEPAGE_URL` / canonical bundle file
  names (:data:`BTI_METADATA_NAME` +
  :data:`BTI_XLSX_NAME`).
- :data:`BTI_COVERAGE_START_YEAR` /
  :data:`BTI_COVERAGE_END_YEAR` -- the 2002-2025
  biennial coverage envelope (the union of
  per-edition covered intervals).
- :data:`BTI_ATTRIBUTION_KEY` /
  :data:`BTI_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to the
  legacy ``BTI_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/bti_io.py`` and to the
  ``bti`` section in
  ``docs/sources/attributions.md``).
- The 3 observation families:
  :data:`BTI_OBSERVATION_FAMILY_EFFECTIVENESS` /
  :data:`BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM` /
  :data:`BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING`
  (and the 3-tuple :data:`BTI_SUPPORTED_FAMILIES`).
- The 12 indicator names:
  :data:`BTI_INDICATOR_GOVERNANCE_INDEX` /
  :data:`BTI_INDICATOR_GOVERNANCE_PERFORMANCE` /
  :data:`BTI_INDICATOR_STATUS_INDEX` /
  :data:`BTI_INDICATOR_DEMOCRACY_STATUS` /
  :data:`BTI_INDICATOR_Q1_STATENESS` /
  :data:`BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION` /
  :data:`BTI_INDICATOR_Q3_RULE_OF_LAW` /
  :data:`BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS` /
  :data:`BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION` /
  :data:`BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT` /
  :data:`BTI_INDICATOR_Q7_MARKET_COMPETITION` /
  :data:`BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE` (and
  the 12-tuple :data:`BTI_INDICATOR_NAMES`).
- The 12 raw column names:
  :data:`BTI_RAW_COLUMN_GOVERNANCE_INDEX` / ... /
  :data:`BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE`
  (and the 12-tuple :data:`BTI_RAW_COLUMNS`).
- :data:`BTI_XLSX_ASSET_ID` -- the canonical raw
  asset id used for every observation's
  :class:`RawLocator` in a single run.
- :data:`BTI_METADATA_VERSION_MISMATCH` /
  :data:`BTI_CHECKSUM_MISMATCH` -- structured warning
  codes used to surface a bundle ``source_version``
  mismatch / xlsx SHA-256 mismatch per the
  documented "no silent errors" contract.
- :func:`build_bti_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`BTIAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_bti_adapter` -- explicit factory.
  Callers wire it into an
  :class:`InMemorySourceRegistry` via
  :func:`register_bti` or directly. The package does
  NOT auto-register on import (the registry is
  passive by design -- see
  ``docs/architecture/sources.md`` §10.1).
- :func:`register_bti` -- explicit registration
  helper for tests and future composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._checksum_validators import (
    BTI_CHECKSUM_MISMATCH,
    _checksum_match_blocker,
    _checksum_shape_blocker,
)
from ._constants import (
    BTI_ATTRIBUTION_KEY,
    BTI_ATTRIBUTION_TEXT,
    BTI_COVERAGE_END_YEAR,
    BTI_COVERAGE_START_YEAR,
    BTI_DEFAULT_VERSION,
    BTI_HOMEPAGE_URL,
    BTI_METADATA_NAME,
    BTI_METADATA_VERSION_MISMATCH,
    BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING,
    BTI_OBSERVATION_FAMILY_EFFECTIVENESS,
    BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    BTI_SOURCE_KEY,
    BTI_SUPPORTED_FAMILIES,
    BTI_XLSX_ASSET_ID,
    BTI_XLSX_NAME,
    UNSUPPORTED_VERSION,
)
from ._descriptor import build_bti_descriptor
from ._indicator_constants import (
    BTI_INDICATOR_DEMOCRACY_STATUS,
    BTI_INDICATOR_GOVERNANCE_INDEX,
    BTI_INDICATOR_GOVERNANCE_PERFORMANCE,
    BTI_INDICATOR_NAMES,
    BTI_INDICATOR_Q1_STATENESS,
    BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION,
    BTI_INDICATOR_Q3_RULE_OF_LAW,
    BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_INDICATOR_Q7_MARKET_COMPETITION,
    BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE,
    BTI_INDICATOR_STATUS_INDEX,
    BTI_RAW_COLUMN_DEMOCRACY_STATUS,
    BTI_RAW_COLUMN_GOVERNANCE_INDEX,
    BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE,
    BTI_RAW_COLUMN_Q1_STATENESS,
    BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION,
    BTI_RAW_COLUMN_Q3_RULE_OF_LAW,
    BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS,
    BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION,
    BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT,
    BTI_RAW_COLUMN_Q7_MARKET_COMPETITION,
    BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE,
    BTI_RAW_COLUMN_STATUS_INDEX,
    BTI_RAW_COLUMNS,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    CANONICAL_LOCAL_FILES_OPTIONAL,
    CANONICAL_LOCAL_FILES_PRIMARY,
    REQUIRED_METADATA_FIELDS,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _positive_int_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)
from ._missing_values import (
    _coerce_float,
    _raw_value_to_string,
    _resolve_value_type,
)
from ._observation_builder import (
    BTI_TRANSFORM_NAME,
    _default_asset_id,
    _default_source_version,
    _xlsx_name,
    build_observation,
)
from ._pipeline import transform_bti_observations
from ._raw_read import (
    _bundle_dir,
    _metadata_path,
    _resolve_xlsx_override,
    _xlsx_path,
    read_bti_xlsx,
)
from ._raw_read import (
    _read_metadata_payload as _raw_read_metadata_payload,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    emit_bti_observations,
)
from ._transform_helpers import (
    _build_raw_long_lookup,
    _canonical_asset_id,
    _canonical_source_version,
    _locate_row_index,
    _resolve_sheet_name,
    _resolve_target_year,
)
from .adapter import (
    BTI_ADAPTER_FACTORY,
    BTIAdapter,
    create_bti_adapter,
    register_bti,
)

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "BTI_ADAPTER_FACTORY",
    "BTI_ATTRIBUTION_KEY",
    "BTI_ATTRIBUTION_TEXT",
    "BTI_CHECKSUM_MISMATCH",
    "BTI_COVERAGE_END_YEAR",
    "BTI_COVERAGE_START_YEAR",
    "BTI_DEFAULT_VERSION",
    "BTI_HOMEPAGE_URL",
    "BTI_INDICATOR_DEMOCRACY_STATUS",
    "BTI_INDICATOR_GOVERNANCE_INDEX",
    "BTI_INDICATOR_GOVERNANCE_PERFORMANCE",
    "BTI_INDICATOR_NAMES",
    "BTI_INDICATOR_Q1_STATENESS",
    "BTI_INDICATOR_Q2_POLITICAL_PARTICIPATION",
    "BTI_INDICATOR_Q3_RULE_OF_LAW",
    "BTI_INDICATOR_Q4_DEMOCRATIC_INSTITUTIONS",
    "BTI_INDICATOR_Q5_POLITICAL_SOCIAL_INTEGRATION",
    "BTI_INDICATOR_Q6_SOCIOECONOMIC_DEVELOPMENT",
    "BTI_INDICATOR_Q7_MARKET_COMPETITION",
    "BTI_INDICATOR_Q11_ECONOMIC_PERFORMANCE",
    "BTI_INDICATOR_STATUS_INDEX",
    "BTI_METADATA_NAME",
    "BTI_METADATA_VERSION_MISMATCH",
    "BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING",
    "BTI_OBSERVATION_FAMILY_EFFECTIVENESS",
    "BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
    "BTI_RAW_COLUMNS",
    "BTI_RAW_COLUMN_DEMOCRACY_STATUS",
    "BTI_RAW_COLUMN_GOVERNANCE_INDEX",
    "BTI_RAW_COLUMN_GOVERNANCE_PERFORMANCE",
    "BTI_RAW_COLUMN_Q1_STATENESS",
    "BTI_RAW_COLUMN_Q2_POLITICAL_PARTICIPATION",
    "BTI_RAW_COLUMN_Q3_RULE_OF_LAW",
    "BTI_RAW_COLUMN_Q4_DEMOCRATIC_INSTITUTIONS",
    "BTI_RAW_COLUMN_Q5_POLITICAL_SOCIAL_INTEGRATION",
    "BTI_RAW_COLUMN_Q6_SOCIOECONOMIC_DEVELOPMENT",
    "BTI_RAW_COLUMN_Q7_MARKET_COMPETITION",
    "BTI_RAW_COLUMN_Q11_ECONOMIC_PERFORMANCE",
    "BTI_RAW_COLUMN_STATUS_INDEX",
    "BTI_SOURCE_KEY",
    "BTI_SUPPORTED_FAMILIES",
    "BTI_TRANSFORM_NAME",
    "BTI_XLSX_ASSET_ID",
    "BTI_XLSX_NAME",
    "CANONICAL_LOCAL_FILES_OPTIONAL",
    "CANONICAL_LOCAL_FILES_PRIMARY",
    "DEFAULT_CATALOG_PATH",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "BTIAdapter",
    "_build_raw_long_lookup",
    "_bundle_dir",
    "_canonical_asset_id",
    "_canonical_source_version",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
    "_coerce_float",
    "_default_asset_id",
    "_default_source_version",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_locate_row_index",
    "_metadata_path",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_positive_int_blocker",
    "_presence_blocker",
    "_raw_read_metadata_payload",
    "_raw_value_to_string",
    "_read_metadata_payload",
    "_required_fields_blocker",
    "_resolve_sheet_name",
    "_resolve_target_year",
    "_resolve_value_type",
    "_resolve_xlsx_override",
    "_xlsx_name",
    "_xlsx_path",
    "build_bti_descriptor",
    "build_observation",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_bti_adapter",
    "emit_bti_observations",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "read_bti_xlsx",
    "register_bti",
    "transform_bti_observations",
]
