"""Unified-source Political Terror Scale (PTS) adapter.

This package hosts the eighth source rebuilt under the
clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 14 and
``docs/requirements/sources.md`` §12 SRC-MIG-006), after
PWT 10.01, Maddison Project Database 2023, World Bank
WDI, World Bank WGI, V-Dem, UCDP, and Transparency
International CPI. The adapter implements the canonical
``SourceAdapter`` Protocol (``descriptor`` +
``check_ready`` + ``read_raw`` + ``transform``) and
reuses the legacy reader
(:func:`leaders_db.ingest.pts_xlsx.read_pts`) via lazy
imports so the package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved.

The Political Terror Scale unified path is local-file
only (no network): the canonical bundle is
``data/raw/political_terror_scale/PTS-2025.xlsx`` +
``metadata.json`` (single sheet ``PTS-2025``, 14
columns, ~10,531 country-year rows; verified live
2026-06-18 per ``docs/architecture/pts.md`` §2) and the
adapter never invokes the network.

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``pts`` (CLI dispatch key +
adapter key + attribution key). The data-lake folder is
``political_terror_scale/`` (the human-readable bundle
name; preserved from the live download + the staged
metadata shape). The folder alias is preserved on disk;
the unified adapter's ``descriptor.source_id.slug`` is
``"pts"``. This reconciliation is documented in
``docs/architecture/sources.md`` §7.5 and the
``pts`` section of ``docs/sources/attributions.md``.

PTS canonical bundle metadata
-----------------------------

The staged bundle metadata carries
``version="2025"`` + ``sha256="6f4d1ccd...88832"`` +
``local_files=["PTS-2025.xlsx"]`` -- a deliberately
minimal shape so the operator can update the metadata
once the xlsx is staged. The mandatory readiness
requirement is on raw-file presence: the ``check_ready``
gate returns ``ready=False`` with a structured
``MISSING_RAW`` error if the staged xlsx is not on
disk, regardless of the metadata's ``local_files`` /
``sha256`` shape. The ``SourceIngestRunner`` raises
``RuntimeError`` BEFORE ``read_raw`` so the runner
never dispatches ``read_raw`` against a missing xlsx.
A metadata-only bundle is intentionally NOT runner-ready.

The §6 sentinel-matrix contract (4-case NA_Status
precedence rule + the §6.5 defensive check) is a
per-row data-coercion contract that lives in the
legacy reader; the unified adapter does NOT surface
sentinel-matrix warnings at the readiness gate (the
readiness gate is a bundle-level contract, not a
per-row data contract).

Public surface
--------------

- :data:`PTS_SOURCE_KEY` /
  :data:`PTS_DEFAULT_VERSION` / canonical bundle
  file names (``PTS_METADATA_NAME`, ``PTS_XLSX_NAME``).
- :data:`PTS_COVERAGE_START_YEAR` /
  :data:`PTS_COVERAGE_END_YEAR` -- the 1976-2024
  coverage envelope.
- :data:`PTS_ATTRIBUTION_KEY` /
  :data:`PTS_ATTRIBUTION_TEXT` -- the canonical
  citation text (Rule #15; byte-identical to the
  legacy ``PTS_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/pts_io.py` and to the
  ``pts`` section in
  ``docs/sources/attributions.md``).
- The single observation family:
  :data:`PTS_OBSERVATION_FAMILY`
  (``domestic_violence_country_year``).
- The 3 indicator names:
  :data:`PTS_INDICATOR_AMNESTY` /
  :data:`PTS_INDICATOR_HUMAN_RIGHTS_WATCH` /
  :data:`PTS_INDICATOR_STATE_DEPT` (and the
  3-tuple :data:`PTS_INDICATOR_NAMES`).
- :data:`PTS_NA_STATUS_CODES` -- the 5 known
  ``NA_Status_X`` provenance codes (0/66/77/88/99)
  per design doc §6.
- :func:`build_pts_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`PTSAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_pts_adapter` -- explicit factory.
  Callers wire it into an
  :class:`InMemorySourceRegistry` via
  :func:`register_pts` or directly. The package does
  NOT auto-register on import (the registry is
  passive by design -- see
  ``docs/architecture/sources.md`` §10.1).
- :func:`register_pts` -- explicit registration
  helper for tests and future composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._checksum_validators import (
    PTS_CHECKSUM_MISMATCH as _PTS_CHECKSUM_MISMATCH_CV,  # noqa: F401
)
from ._descriptor import (
    PTS_ATTRIBUTION_KEY,
    PTS_ATTRIBUTION_TEXT,
    PTS_COVERAGE_END_YEAR,
    PTS_COVERAGE_START_YEAR,
    PTS_DEFAULT_VERSION,
    PTS_HOMEPAGE_URL,
    PTS_INDICATOR_AMNESTY,
    PTS_INDICATOR_HUMAN_RIGHTS_WATCH,
    PTS_INDICATOR_NAMES,
    PTS_INDICATOR_STATE_DEPT,
    PTS_METADATA_NAME,
    PTS_OBSERVATION_FAMILY,
    PTS_RAW_COLUMN_AMNESTY,
    PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH,
    PTS_RAW_COLUMN_STATE_DEPT,
    PTS_RAW_COLUMNS,
    PTS_SHEET_NAME,
    PTS_SOURCE_KEY,
    PTS_SUPPORTED_FAMILIES,
    PTS_XLSX_ASSET_ID,
    PTS_XLSX_NAME,
    build_pts_descriptor,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    CANONICAL_LOCAL_FILES,
    PTS_BUNDLE_VERSION_STAMP,
    PTS_CHECKSUM_MISMATCH,
    PTS_METADATA_VERSION_MISMATCH,
    REQUIRED_METADATA_FIELDS,
    UNSUPPORTED_VERSION,
)
from ._missing_values import (
    PTS_INCONSISTENCY_WARNING_CODE,
    PTS_NA_SENTINEL_STRING,
    PTS_NA_STATUS_CODES,
    PTS_RAW_SCALE_MAX,
    PTS_RAW_SCALE_MIN,
    PTS_UNKNOWN_NA_STATUS_WARNING_CODE,
    _coerce_pts_value,
    _raw_cell_text,
    _raw_na_status_text,
)
from ._observation_builder import (
    PTS_TRANSFORM_NAME,
    _default_asset_id,
    _default_source_version,
    _raw_columns,
    _xlsx_name,
    build_observation,
)
from ._pipeline import transform_pts_observations
from ._raw_read import (
    _bundle_dir,
    _metadata_path,
    _read_metadata_payload,
    _xlsx_path,
    read_pts_xlsx,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_pts_observations
from .adapter import (
    PTS_ADAPTER_FACTORY,
    PTSAdapter,
    create_pts_adapter,
    register_pts,
)

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "CANONICAL_LOCAL_FILES",
    "DEFAULT_CATALOG_PATH",
    "PTS_ADAPTER_FACTORY",
    "PTS_ATTRIBUTION_KEY",
    "PTS_ATTRIBUTION_TEXT",
    "PTS_BUNDLE_VERSION_STAMP",
    "PTS_CHECKSUM_MISMATCH",
    "PTS_COVERAGE_END_YEAR",
    "PTS_COVERAGE_START_YEAR",
    "PTS_DEFAULT_VERSION",
    "PTS_HOMEPAGE_URL",
    "PTS_INCONSISTENCY_WARNING_CODE",
    "PTS_INDICATOR_AMNESTY",
    "PTS_INDICATOR_HUMAN_RIGHTS_WATCH",
    "PTS_INDICATOR_NAMES",
    "PTS_INDICATOR_STATE_DEPT",
    "PTS_METADATA_NAME",
    "PTS_METADATA_VERSION_MISMATCH",
    "PTS_NA_SENTINEL_STRING",
    "PTS_NA_STATUS_CODES",
    "PTS_OBSERVATION_FAMILY",
    "PTS_RAW_COLUMNS",
    "PTS_RAW_COLUMN_AMNESTY",
    "PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH",
    "PTS_RAW_COLUMN_STATE_DEPT",
    "PTS_RAW_SCALE_MAX",
    "PTS_RAW_SCALE_MIN",
    "PTS_SHEET_NAME",
    "PTS_SOURCE_KEY",
    "PTS_SUPPORTED_FAMILIES",
    "PTS_TRANSFORM_NAME",
    "PTS_UNKNOWN_NA_STATUS_WARNING_CODE",
    "PTS_XLSX_ASSET_ID",
    "PTS_XLSX_NAME",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "PTSAdapter",
    "_bundle_dir",
    "_coerce_pts_value",
    "_default_asset_id",
    "_default_source_version",
    "_metadata_path",
    "_raw_cell_text",
    "_raw_columns",
    "_raw_na_status_text",
    "_read_metadata_payload",
    "_xlsx_name",
    "_xlsx_path",
    "build_observation",
    "build_pts_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_pts_adapter",
    "emit_pts_observations",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "read_pts_xlsx",
    "register_pts",
    "transform_pts_observations",
]
