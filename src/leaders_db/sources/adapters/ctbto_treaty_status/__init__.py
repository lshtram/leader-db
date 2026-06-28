"""Unified-source CTBTO Treaty Status adapter.

This package hosts the CTBTO States Signatories clean adapter
rebuilt under the clean ``leaders_db.sources`` interface. The
adapter is the next feasible clean-interface-only source
after ``iaea_safeguards`` and follows the documented Phase C
protocol for clean migrations: no legacy
``leaders_db.ingest.STAGE2_ADAPTERS`` wiring, no live network
fetch (the unified adapter is offline / cache-only in this
slice), no manual propagation of source metadata, and a
runtime-local ``metadata.json`` next to the cached States
Signatories export.

The CTBTO States Signatories page is the public record of
which States have signed and ratified the Comprehensive
Nuclear-Test-Ban Treaty (CTBT). The page is at
``https://www.ctbto.org/our-mission/states-signatories`` and
exposes a table with documented columns ``Region`` /
``State`` / ``Signature Date`` / ``Ratification Date``. The
canonical probed stamp is "status as of 13 March 2024" (the
date of the latest ratifying state Papua New Guinea;
totals: 196 total States, 187 signed, 178 ratified; latest
signatory Somalia 2023-09-08).

This source captures treaty-status evidence -- the
source-derived signature status (``"signed"`` iff a signature
date is present in the cached row, ``"not_signed"``
otherwise) and the source-derived ratification status
(``"ratified"`` iff a ratification date is present in the
cached row, ``"not_ratified"`` otherwise). The source is NOT
a per-country nuclear-behaviour score or proof of compliance
/ non-compliance by itself.

Public surface
--------------

- :data:`CTBTO_TREATY_STATUS_SOURCE_KEY` /
  :data:`CTBTO_TREATY_STATUS_DEFAULT_VERSION` /
  :data:`CTBTO_TREATY_STATUS_COVERAGE_START_YEAR` /
  :data:`CTBTO_TREATY_STATUS_COVERAGE_END_YEAR` /
  :data:`CTBTO_TREATY_STATUS_SNAPSHOT_DATE` -- the
  canonical slug + version stamp + 2024 single-year coverage
  envelope + snapshot date stamp.
- :data:`CTBTO_TREATY_STATUS_HOMEPAGE_URL` /
  :data:`CTBTO_TREATY_STATUS_TERMS_URL` -- the canonical
  CTBTO States Signatories page URL + the canonical CTBTO
  terms-of-use URL (the clean adapter never invokes either
  URL at runtime).
- :data:`CTBTO_TREATY_STATUS_ATTRIBUTION_KEY` /
  :data:`CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT` -- the
  canonical citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` ``ctbto_treaty_status``
  section).
- :data:`CTBTO_TREATY_STATUS_OBSERVATION_FAMILY` /
  :data:`CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES` -- the
  single observation family the descriptor advertises.
- :data:`CTBTO_TREATY_STATUS_INDICATOR_CODES` / the 2
  indicator constants -- the canonical source-derived
  catalog (one per date-bearing column in the cached CTBTO
  table).
- :data:`CTBTO_TREATY_STATUS_REQUIRED_COLUMNS` -- the schema
  contract for the cached CSV / HTML header.
- :func:`build_ctbto_treaty_status_descriptor` -- factory
  for the canonical :class:`SourceDescriptor`.
- :class:`CtbtoTreatyStatusAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_ctbto_treaty_status_adapter` -- explicit
  factory.
- :func:`register_ctbto_treaty_status` -- explicit
  registration helper for tests and future composition.
- :class:`CtbtoTreatyStatusSchemaError` -- structured failure
  raised when the cached CSV / HTML header is missing
  required columns.
"""

from __future__ import annotations

from ._constants import (
    CTBTO_TREATY_STATUS_ATTRIBUTION_KEY,
    CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT,
    CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
    CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_YEAR,
    CTBTO_TREATY_STATUS_CSV_ASSET_ID,
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_HOMEPAGE_URL,
    CTBTO_TREATY_STATUS_HTML_ASSET_ID,
    CTBTO_TREATY_STATUS_HTML_NAME,
    CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_CODES,
    CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS,
    CTBTO_TREATY_STATUS_LOCAL_FILE_NAMES,
    CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
    CTBTO_TREATY_STATUS_METADATA_NAME,
    CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
    CTBTO_TREATY_STATUS_OBSERVATION_FAMILY,
    CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN,
    CTBTO_TREATY_STATUS_REQUIRED_COLUMNS,
    CTBTO_TREATY_STATUS_SCHEMA_ERROR,
    CTBTO_TREATY_STATUS_SNAPSHOT_DATE,
    CTBTO_TREATY_STATUS_SOURCE_KEY,
    CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED,
    CTBTO_TREATY_STATUS_STATUS_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_SCALE,
    CTBTO_TREATY_STATUS_STATUS_SIGNED,
    CTBTO_TREATY_STATUS_STATUS_UNIT,
    CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES,
    CTBTO_TREATY_STATUS_TERMS_URL,
    CTBTO_TREATY_STATUS_TRANSFORM_NAME,
    CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY,
    CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION,
)
from ._descriptor import build_ctbto_treaty_status_descriptor
from ._raw_read import (
    CtbtoTreatyStatusSchemaError,
    read_ctbto_treaty_status_cache,
)
from ._readiness import (
    bundle_dir,
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
    csv_path,
    html_path,
    metadata_path,
    read_metadata,
    resolve_selected_cache_path,
)
from ._transform import (
    emit_ctbto_treaty_status_observations,
    indicator_codes,
    required_columns,
)
from .adapter import (
    CTBTO_TREATY_STATUS_ADAPTER_FACTORY,
    CtbtoTreatyStatusAdapter,
    create_ctbto_treaty_status_adapter,
    register_ctbto_treaty_status,
)

__all__ = [
    "CTBTO_TREATY_STATUS_ADAPTER_FACTORY",
    "CTBTO_TREATY_STATUS_ATTRIBUTION_KEY",
    "CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT",
    "CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH",
    "CTBTO_TREATY_STATUS_COVERAGE_END_YEAR",
    "CTBTO_TREATY_STATUS_COVERAGE_START_YEAR",
    "CTBTO_TREATY_STATUS_COVERAGE_YEAR",
    "CTBTO_TREATY_STATUS_CSV_ASSET_ID",
    "CTBTO_TREATY_STATUS_CSV_NAME",
    "CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY",
    "CTBTO_TREATY_STATUS_DEFAULT_VERSION",
    "CTBTO_TREATY_STATUS_HOMEPAGE_URL",
    "CTBTO_TREATY_STATUS_HTML_ASSET_ID",
    "CTBTO_TREATY_STATUS_HTML_NAME",
    "CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS",
    "CTBTO_TREATY_STATUS_INDICATOR_CODES",
    "CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS",
    "CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS",
    "CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID",
    "CTBTO_TREATY_STATUS_LOCAL_FILE_NAMES",
    "CTBTO_TREATY_STATUS_METADATA_NAME",
    "CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH",
    "CTBTO_TREATY_STATUS_OBSERVATION_FAMILY",
    "CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN",
    "CTBTO_TREATY_STATUS_REQUIRED_COLUMNS",
    "CTBTO_TREATY_STATUS_SCHEMA_ERROR",
    "CTBTO_TREATY_STATUS_SNAPSHOT_DATE",
    "CTBTO_TREATY_STATUS_SOURCE_KEY",
    "CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED",
    "CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED",
    "CTBTO_TREATY_STATUS_STATUS_RATIFIED",
    "CTBTO_TREATY_STATUS_STATUS_SCALE",
    "CTBTO_TREATY_STATUS_STATUS_SIGNED",
    "CTBTO_TREATY_STATUS_STATUS_UNIT",
    "CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES",
    "CTBTO_TREATY_STATUS_TERMS_URL",
    "CTBTO_TREATY_STATUS_TRANSFORM_NAME",
    "CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY",
    "CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION",
    "CtbtoTreatyStatusAdapter",
    "CtbtoTreatyStatusSchemaError",
    "build_ctbto_treaty_status_descriptor",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_ctbto_treaty_status_adapter",
    "csv_path",
    "emit_ctbto_treaty_status_observations",
    "html_path",
    "indicator_codes",
    "metadata_path",
    "read_ctbto_treaty_status_cache",
    "read_metadata",
    "register_ctbto_treaty_status",
    "required_columns",
    "resolve_selected_cache_path",
]
