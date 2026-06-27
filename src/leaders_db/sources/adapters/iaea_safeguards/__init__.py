"""Unified-source IAEA Safeguards status-list adapter.

This package hosts the IAEA Safeguards status-list clean
adapter rebuilt under the clean ``leaders_db.sources``
interface. The adapter is the next feasible clean-interface-only
source after ``sipri_arms_transfers`` and follows the
documented Phase C protocol for clean migrations: no legacy
``leaders_db.ingest.STAGE2_ADAPTERS`` wiring, no live network
fetch (the unified adapter is offline / cache-only in this
slice), no manual propagation of source metadata, and a
runtime-local ``metadata.json`` next to the cached status-list
PDF.

The IAEA Safeguards Status List is the public legal / status
evidence the IAEA publishes at
``https://www.iaea.org/sites/default/files/20/01/sg-agreements-comprehensive-status.pdf``
("Conclusion of Safeguards Agreements, Additional Protocols and
Small Quantities Protocols"). The list is updated periodically;
the canonical stamp probed for this slice is the 2025-12-31
status date.

This source captures safeguards legal / status evidence --
the presence / status of a Comprehensive Safeguards Agreement
(CSA) (the composite status label carried in the
``Safeguards Agreement`` column, e.g. ``In Force: 153`` /
``Not in Force: 66`` / ``N/A``), the status of an Additional
Protocol (signed / approved / in force / not in force / not
signed), and the status of a Small Quantities Protocol
(modified / original / not applicable / not in force). The list
also carries the INFCIRC document identifier (e.g.
``INFCIRC/153`` / ``INFCIRC/540``). The source is NOT a
per-country nuclear-weapons score or proof of compliance /
non-compliance by itself.

Public surface
--------------

- :data:`IAEA_SAFEGUARDS_SOURCE_KEY` /
  :data:`IAEA_SAFEGUARDS_DEFAULT_VERSION` /
  :data:`IAEA_SAFEGUARDS_COVERAGE_START_YEAR` /
  :data:`IAEA_SAFEGUARDS_COVERAGE_END_YEAR` -- the
  canonical slug + version stamp + 2025 single-year coverage
  envelope.
- :data:`IAEA_SAFEGUARDS_HOMEPAGE_URL` /
  :data:`IAEA_SAFEGUARDS_PDF_URL` -- the canonical IAEA
  homepage + the canonical public status-list PDF URL (the
  clean adapter never invokes the URL at runtime).
- :data:`IAEA_SAFEGUARDS_ATTRIBUTION_KEY` /
  :data:`IAEA_SAFEGUARDS_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` ``iaea_safeguards``
  section).
- :data:`IAEA_SAFEGUARDS_OBSERVATION_FAMILY` /
  :data:`IAEA_SAFEGUARDS_SUPPORTED_FAMILIES` -- the single
  observation family the descriptor advertises.
- :data:`IAEA_SAFEGUARDS_INDICATOR_CODES` / the 4 indicator
  constants -- the canonical source-native catalog (one per
  non-State column in the cached PDF table).
- :data:`IAEA_SAFEGUARDS_REQUIRED_COLUMNS` -- the schema
  contract for the cached PDF header.
- :func:`build_iaea_safeguards_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`IaeaSafeguardsAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_iaea_safeguards_adapter` -- explicit factory.
- :func:`register_iaea_safeguards` -- explicit registration
  helper for tests and future composition.
- :class:`IaeaSafeguardsSchemaError` -- structured failure
  raised when the cached PDF header is missing required
  columns.
"""

from __future__ import annotations

from ._constants import (
    IAEA_SAFEGUARDS_ATTRIBUTION_KEY,
    IAEA_SAFEGUARDS_ATTRIBUTION_TEXT,
    IAEA_SAFEGUARDS_CHECKSUM_MISMATCH,
    IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_YEAR,
    IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY,
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_HOMEPAGE_URL,
    IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_CODES,
    IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
    IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INFCIRC_SCALE,
    IAEA_SAFEGUARDS_INFCIRC_UNIT,
    IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
    IAEA_SAFEGUARDS_METADATA_NAME,
    IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
    IAEA_SAFEGUARDS_OBSERVATION_FAMILY,
    IAEA_SAFEGUARDS_PDF_ASSET_ID,
    IAEA_SAFEGUARDS_PDF_NAME,
    IAEA_SAFEGUARDS_PDF_URL,
    IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
    IAEA_SAFEGUARDS_SCHEMA_ERROR,
    IAEA_SAFEGUARDS_SOURCE_KEY,
    IAEA_SAFEGUARDS_STATUS_DATE,
    IAEA_SAFEGUARDS_SUPPORTED_FAMILIES,
    IAEA_SAFEGUARDS_TEXT_SCALE,
    IAEA_SAFEGUARDS_TEXT_UNIT,
    IAEA_SAFEGUARDS_TRANSFORM_NAME,
    IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY,
    IAEA_SAFEGUARDS_UNSUPPORTED_VERSION,
)
from ._descriptor import build_iaea_safeguards_descriptor
from ._raw_read import (
    IaeaSafeguardsSchemaError,
    read_iaea_safeguards_pdf,
)
from ._readiness import (
    bundle_dir,
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
    metadata_path,
    pdf_path,
    read_metadata,
)
from ._transform import (
    emit_iaea_safeguards_observations,
    indicator_codes,
    required_columns,
)
from .adapter import (
    IAEA_SAFEGUARDS_ADAPTER_FACTORY,
    IaeaSafeguardsAdapter,
    create_iaea_safeguards_adapter,
    register_iaea_safeguards,
)

__all__ = [
    "IAEA_SAFEGUARDS_ADAPTER_FACTORY",
    "IAEA_SAFEGUARDS_ATTRIBUTION_KEY",
    "IAEA_SAFEGUARDS_ATTRIBUTION_TEXT",
    "IAEA_SAFEGUARDS_CHECKSUM_MISMATCH",
    "IAEA_SAFEGUARDS_COVERAGE_END_YEAR",
    "IAEA_SAFEGUARDS_COVERAGE_START_YEAR",
    "IAEA_SAFEGUARDS_COVERAGE_YEAR",
    "IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY",
    "IAEA_SAFEGUARDS_DEFAULT_VERSION",
    "IAEA_SAFEGUARDS_HOMEPAGE_URL",
    "IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS",
    "IAEA_SAFEGUARDS_INDICATOR_CODES",
    "IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER",
    "IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS",
    "IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS",
    "IAEA_SAFEGUARDS_INFCIRC_SCALE",
    "IAEA_SAFEGUARDS_INFCIRC_UNIT",
    "IAEA_SAFEGUARDS_LOCAL_FILES_INVALID",
    "IAEA_SAFEGUARDS_METADATA_NAME",
    "IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH",
    "IAEA_SAFEGUARDS_OBSERVATION_FAMILY",
    "IAEA_SAFEGUARDS_PDF_ASSET_ID",
    "IAEA_SAFEGUARDS_PDF_NAME",
    "IAEA_SAFEGUARDS_PDF_URL",
    "IAEA_SAFEGUARDS_REQUIRED_COLUMNS",
    "IAEA_SAFEGUARDS_SCHEMA_ERROR",
    "IAEA_SAFEGUARDS_SOURCE_KEY",
    "IAEA_SAFEGUARDS_STATUS_DATE",
    "IAEA_SAFEGUARDS_SUPPORTED_FAMILIES",
    "IAEA_SAFEGUARDS_TEXT_SCALE",
    "IAEA_SAFEGUARDS_TEXT_UNIT",
    "IAEA_SAFEGUARDS_TRANSFORM_NAME",
    "IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY",
    "IAEA_SAFEGUARDS_UNSUPPORTED_VERSION",
    "IaeaSafeguardsAdapter",
    "IaeaSafeguardsSchemaError",
    "build_iaea_safeguards_descriptor",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_iaea_safeguards_adapter",
    "emit_iaea_safeguards_observations",
    "indicator_codes",
    "metadata_path",
    "pdf_path",
    "read_iaea_safeguards_pdf",
    "read_metadata",
    "register_iaea_safeguards",
    "required_columns",
]
