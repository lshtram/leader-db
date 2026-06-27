"""Unified-source SIPRI Arms Transfers Database adapter.

This package hosts the SIPRI Arms Transfers Database clean
adapter rebuilt under the clean ``leaders_db.sources``
interface. The adapter is the next feasible clean-interface-only
source after ``polity_v`` and follows the documented Phase C
protocol for clean migrations: no legacy
``leaders_db.ingest.STAGE2_ADAPTERS`` wiring, no live network
fetch (the unified adapter is offline / cache-only in this
slice), no manual propagation of source metadata, and a
runtime-local ``metadata.json`` next to the cached export.

The SIPRI Arms Transfers Database is SIPRI's public record of
international transfers of major conventional arms. The data
is delivered through a backend API plus a web app; the
canonical Trade Register export is a CSV file (the public
app's backend API returns a JSON envelope wrapping base64 CSV
bytes). The unified adapter supports BOTH cached shapes per
the task brief:

1. **Direct CSV** -- a plain CSV file at
   ``data/raw/sipri_arms_transfers/trade_register.csv``.
2. **Base64-JSON wrapper** -- a JSON envelope at
   ``data/raw/sipri_arms_transfers/trade_register.json``
   containing base64-encoded CSV bytes.

The adapter validates the parsed header against the 8
canonical required columns (``Supplier`` / ``Recipient`` /
``Order year`` / ``Delivery year`` / ``Designation`` /
``Status`` / ``Numbers delivered`` / ``TIV (delivered)``) and
refuses to emit any observations when a required column is
missing (a missing required column is a schema contract
violation -- the transform layer MUST NOT silently emit
partial output on a schema contract violation).

Public surface
--------------

- :data:`SIPRI_ARMS_TRANSFERS_SOURCE_KEY` /
  :data:`SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION` /
  :data:`SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR` /
  :data:`SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR` -- the
  canonical slug + version stamp + 1950-2025 coverage envelope.
- :data:`SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL` /
  :data:`SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL` -- the canonical
  SIPRI citation landing page + the canonical public app URL.
- :data:`SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY` /
  :data:`SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT` -- the
  canonical citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` ``sipri_arms_transfers``
  section).
- :data:`SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER` /
  :data:`SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE` /
  :data:`SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES` -- the two
  observation families the descriptor advertises.
- :data:`SIPRI_ARMS_TRANSFERS_INDICATOR_CODES` / the 5
  indicator constants -- the canonical catalog.
- :data:`SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS` /
  :data:`SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS` -- the schema
  contract for the cached CSV header.
- :func:`build_sipri_arms_transfers_descriptor` -- factory for
  the canonical :class:`SourceDescriptor`.
- :class:`SipriArmsTransfersAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_sipri_arms_transfers_adapter` -- explicit
  factory.
- :func:`register_sipri_arms_transfers` -- explicit registration
  helper for tests and future composition.
- :class:`SipriArmsTransfersSchemaError` -- structured failure
  raised when the cached CSV / JSON header is missing required
  columns.
"""

from __future__ import annotations

from ._constants import (
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY,
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT,
    SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH,
    SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
    SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID,
    SIPRI_ARMS_TRANSFERS_CSV_NAME,
    SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
    SIPRI_ARMS_TRANSFERS_INDICATOR_CODES,
    SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED,
    SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID,
    SIPRI_ARMS_TRANSFERS_JSON_NAME,
    SIPRI_ARMS_TRANSFERS_LOCAL_FILE_NAMES,
    SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
    SIPRI_ARMS_TRANSFERS_METADATA_NAME,
    SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
    SIPRI_ARMS_TRANSFERS_NUMBER_SCALE,
    SIPRI_ARMS_TRANSFERS_NUMBER_UNIT,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER,
    SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS,
    SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND,
    SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL,
    SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
    SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR,
    SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES,
    SIPRI_ARMS_TRANSFERS_TIV_SCALE,
    SIPRI_ARMS_TRANSFERS_TIV_UNIT,
    SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION,
)
from ._descriptor import build_sipri_arms_transfers_descriptor
from ._raw_read import (
    SIPRI_ARMS_TRANSFERS_HEADER_MIN_MATCH,
    SipriArmsTransfersSchemaError,
    read_sipri_arms_transfers_csv,
)
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    emit_sipri_arms_transfers_observations,
    optional_columns,
    required_columns,
)
from .adapter import (
    SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY,
    SipriArmsTransfersAdapter,
    create_sipri_arms_transfers_adapter,
    register_sipri_arms_transfers,
)

__all__ = [
    "SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY",
    "SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY",
    "SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT",
    "SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH",
    "SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR",
    "SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR",
    "SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID",
    "SIPRI_ARMS_TRANSFERS_CSV_NAME",
    "SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY",
    "SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION",
    "SIPRI_ARMS_TRANSFERS_HEADER_MIN_MATCH",
    "SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_CODES",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED",
    "SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID",
    "SIPRI_ARMS_TRANSFERS_JSON_NAME",
    "SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID",
    "SIPRI_ARMS_TRANSFERS_LOCAL_FILE_NAMES",
    "SIPRI_ARMS_TRANSFERS_METADATA_NAME",
    "SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH",
    "SIPRI_ARMS_TRANSFERS_NUMBER_SCALE",
    "SIPRI_ARMS_TRANSFERS_NUMBER_UNIT",
    "SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE",
    "SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER",
    "SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS",
    "SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND",
    "SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL",
    "SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS",
    "SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR",
    "SIPRI_ARMS_TRANSFERS_SOURCE_KEY",
    "SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES",
    "SIPRI_ARMS_TRANSFERS_TIV_SCALE",
    "SIPRI_ARMS_TRANSFERS_TIV_UNIT",
    "SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME",
    "SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY",
    "SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION",
    "SipriArmsTransfersAdapter",
    "SipriArmsTransfersSchemaError",
    "build_sipri_arms_transfers_descriptor",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_sipri_arms_transfers_adapter",
    "emit_sipri_arms_transfers_observations",
    "optional_columns",
    "read_sipri_arms_transfers_csv",
    "register_sipri_arms_transfers",
    "required_columns",
]
