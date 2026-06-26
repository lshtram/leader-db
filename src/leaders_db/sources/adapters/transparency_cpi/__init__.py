"""Unified-source Transparency International Corruption
Perceptions Index (CPI) adapter.

This package hosts the seventh source rebuilt under the
clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 6 and
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI,
World Bank WGI, V-Dem, and UCDP. The adapter implements
the canonical ``SourceAdapter`` Protocol (``descriptor``
+ ``check_ready`` + ``read_raw`` + ``transform``) and
reuses the legacy reader / transform under
:mod:`leaders_db.ingest.transparency_cpi_csv` via lazy
imports so the package boundary documented in
docs/architecture/sources.md §10.1 is preserved. The
Transparency International CPI unified path is
local-file only (no network): the canonical bundle is
``data/raw/transparency_cpi/transparency_cpi_<year>.csv``
+ ``metadata.json`` (the per-year CSV is the HDX-mirrored
verbatim Transparency International release; the canonical
TI xlsx download is CDN-gated per
docs/sources/vetting/report.md §3.6) and the adapter never
invokes the network.

The CPI canonical bundle metadata ships with
``local_files=["transparency_cpi_2023.csv"]`` and
``checksum_sha256=null`` -- a deliberately minimal shape
so the operator can update the metadata once the per-year
CSV is staged. The mandatory readiness requirement is on
raw-file presence: the ``check_ready`` gate returns
``ready=False`` with a structured ``MISSING_RAW`` error
if the per-year CSV is not staged on disk, regardless of
the metadata's ``local_files`` / ``checksum_sha256``
shape. The ``SourceIngestRunner`` raises ``RuntimeError``
BEFORE ``read_raw`` so the runner never dispatches
``read_raw`` against a missing CSV. A metadata-only
bundle is intentionally NOT runner-ready; it has value
for readiness-only inspection (validating metadata shape,
schema migrations, sanity-checking ``expected_local_files``
annotations) but ``adapter.check_ready(request).ready``
is ``False`` until the per-year CSV is staged.

Public surface
--------------

- :data:`TRANSPARENCY_CPI_SOURCE_KEY` /
  :data:`TRANSPARENCY_CPI_DEFAULT_VERSION` / canonical
  bundle file names (``TRANSPARENCY_CPI_METADATA_NAME`,
  ``TRANSPARENCY_CPI_CSV_NAME_TEMPLATE`,
  ``TRANSPARENCY_CPI_DEFAULT_CSV_NAME`).
- :data:`TRANSPARENCY_CPI_COVERAGE_START_YEAR` /
  :data:`TRANSPARENCY_CPI_COVERAGE_END_YEAR` -- the
  1995-2023 coverage envelope.
- :data:`TRANSPARENCY_CPI_ATTRIBUTION_TEXT` -- the
  canonical citation text (Rule #15; byte-identical to
  the legacy ``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/transparency_cpi_io.py` and to
  the ``transparency_cpi`` section in
  ``docs/sources/attributions.md``). The text deliberately
  distinguishes the publisher (Transparency International)
  from the HDX mirror that preserves the verbatim TI
  release -- the report-facing attribution block names
  Transparency International CPI 2023 (the canonical
  publisher name), NOT the OCHA HDX mirror (which is the
  durable CSV provenance path documented separately in
  the bundle metadata's ``hdx_mirror_url`` field).
- The single observation family:
  :data:`TRANSPARENCY_CPI_OBSERVATION_FAMILY`
  (``integrity_country_year``).
- :func:`build_transparency_cpi_descriptor` -- factory
  for the canonical :class:`SourceDescriptor`.
- :class:`TransparencyCPIAdapter` -- the unified
  :class:`SourceAdapter` implementation.
- :func:`create_transparency_cpi_adapter` -- explicit
  factory. Callers wire it into an
  :class:`InMemorySourceRegistry` via
  :func:`register_transparency_cpi` or directly. The
  package does NOT auto-register on import (the registry
  is passive by design -- see docs/architecture/sources.md
  §10.1).
- :func:`register_transparency_cpi` -- explicit
  registration helper for tests and future composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._descriptor import (
    TRANSPARENCY_CPI_ATTRIBUTION_KEY,
    TRANSPARENCY_CPI_ATTRIBUTION_TEXT,
    TRANSPARENCY_CPI_COVERAGE_END_YEAR,
    TRANSPARENCY_CPI_COVERAGE_START_YEAR,
    TRANSPARENCY_CPI_CSV_NAME_TEMPLATE,
    TRANSPARENCY_CPI_DEFAULT_CSV_NAME,
    TRANSPARENCY_CPI_DEFAULT_VERSION,
    TRANSPARENCY_CPI_HOMEPAGE_URL,
    TRANSPARENCY_CPI_METADATA_NAME,
    TRANSPARENCY_CPI_OBSERVATION_FAMILY,
    TRANSPARENCY_CPI_SOURCE_KEY,
    TRANSPARENCY_CPI_SUPPORTED_FAMILIES,
    build_transparency_cpi_descriptor,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    REQUIRED_METADATA_FIELDS,
    TRANSPARENCY_CPI_CHECKSUM_MISMATCH,
    UNSUPPORTED_VERSION,
)
from ._missing_values import (
    _CPI_MISSING_STRINGS,
    _coerce_float_or_none,
    _coerce_int_or_none,
    _coerce_score_cell,
    _is_real_number,
    _raw_value_to_string,
)
from ._observation_builder import build_observation
from ._pipeline import transform_transparency_cpi_observations
from ._raw_read import (
    _bundle_dir,
    _csv_name_for_request,
    _csv_path,
    _metadata_path,
    _read_csv_records,
    _read_metadata_payload,
    read_transparency_cpi_csv,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    TRANSPARENCY_CPI_TRANSFORM_NAME,
    emit_transparency_cpi_observations,
)
from .adapter import (
    TRANSPARENCY_CPI_ADAPTER_FACTORY,
    TransparencyCPIAdapter,
    create_transparency_cpi_adapter,
    register_transparency_cpi,
)

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "DEFAULT_CATALOG_PATH",
    "REQUIRED_METADATA_FIELDS",
    "TRANSPARENCY_CPI_ADAPTER_FACTORY",
    "TRANSPARENCY_CPI_ATTRIBUTION_KEY",
    "TRANSPARENCY_CPI_ATTRIBUTION_TEXT",
    "TRANSPARENCY_CPI_CHECKSUM_MISMATCH",
    "TRANSPARENCY_CPI_COVERAGE_END_YEAR",
    "TRANSPARENCY_CPI_COVERAGE_START_YEAR",
    "TRANSPARENCY_CPI_CSV_NAME_TEMPLATE",
    "TRANSPARENCY_CPI_DEFAULT_CSV_NAME",
    "TRANSPARENCY_CPI_DEFAULT_VERSION",
    "TRANSPARENCY_CPI_HOMEPAGE_URL",
    "TRANSPARENCY_CPI_METADATA_NAME",
    "TRANSPARENCY_CPI_OBSERVATION_FAMILY",
    "TRANSPARENCY_CPI_SOURCE_KEY",
    "TRANSPARENCY_CPI_SUPPORTED_FAMILIES",
    "TRANSPARENCY_CPI_TRANSFORM_NAME",
    "UNSUPPORTED_VERSION",
    "_CPI_MISSING_STRINGS",
    "TransparencyCPIAdapter",
    "_bundle_dir",
    "_coerce_float_or_none",
    "_coerce_int_or_none",
    "_coerce_score_cell",
    "_csv_name_for_request",
    "_csv_path",
    "_is_real_number",
    "_metadata_path",
    "_raw_value_to_string",
    "_read_csv_records",
    "_read_metadata_payload",
    "build_observation",
    "build_transparency_cpi_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_transparency_cpi_adapter",
    "emit_transparency_cpi_observations",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "read_transparency_cpi_csv",
    "register_transparency_cpi",
    "transform_transparency_cpi_observations",
]
