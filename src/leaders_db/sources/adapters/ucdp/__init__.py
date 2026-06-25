"""Unified-source UCDP (Uppsala Conflict Data Program) adapter.

This package hosts the sixth source rebuilt under the clean
``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 11 and
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI,
World Bank WGI, and V-Dem. The adapter implements the
canonical ``SourceAdapter`` Protocol (``descriptor`` +
``check_ready`` + ``read_raw`` + ``transform``) and reuses
the legacy reader / event-level aggregator under
:mod:`leaders_db.ingest.ucdp_io` and
:mod:`leaders_db.ingest.ucdp_aggregate` via lazy imports so
the package boundary documented in
docs/architecture/sources.md §10.1 is preserved. The UCDP
unified path is local-file only (no network): the canonical
bundle is ``data/raw/ucdp/ged231-csv.zip`` + ``metadata.json``
and the adapter never invokes the network.

The UCDP canonical bundle metadata ships with
``local_files=[]`` and ``checksum_sha256=null`` -- a
deliberately minimal shape so the operator can update the
metadata once the zip is staged. The mandatory readiness
requirement is on raw-file presence: the
``check_ready`` gate returns ``ready=False`` with a
structured ``MISSING_RAW`` error if ``ged231-csv.zip`` is
not staged on disk, regardless of the metadata's
``local_files`` / ``checksum_sha256`` shape. The
``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
``read_raw`` so the runner never dispatches
``read_raw`` against a missing zip. A metadata-only
bundle is intentionally NOT runner-ready; it has value
for readiness-only inspection (validating metadata shape,
schema migrations, sanity-checking
``expected_local_files`` annotations) but
``adapter.check_ready(request).ready`` is ``False`` until
the zip is staged.

UCDP is structurally distinct from the prior five
clean-source migrations: PWT / Maddison / WDI / WGI / V-Dem
are country-year tables, while UCDP GED is an **event-level**
dataset (316,818 events in v23.1). The Stage 2 adapter
aggregates events to country-year by ``type_of_violence``
(1 = state-based, 3 = one-sided) and the cross-border filter
(``type=1 AND gwnob.notna()`` for the internationalized
subset) before the long-to-wide pivot. The unified transform
layer consumes the wide-format country-year DataFrame and
emits one ``NormalizedObservation`` per ``(country_id, year,
variable_name)`` triple. Per-row event-level provenance is
NOT preserved through the aggregation -- the unified
``RawLocator.row_number`` is intentionally ``None`` and the
``transform_locator.rule_id`` carries the
``ucdp:<country_id>:<year>:<variable_name>`` pattern. The
per-observation ``quality_flags`` carries the
``ucdp_aggregated_from_events`` flag so downstream audit code
can recognize the aggregate locator convention.

Public surface
--------------

- :data:`UCDP_SOURCE_KEY` / :data:`UCDP_DEFAULT_VERSION` /
  canonical bundle file names (``UCDP_ZIP_NAME``,
  ``UCDP_METADATA_NAME``).
- :data:`UCDP_COVERAGE_START_YEAR` /
  :data:`UCDP_COVERAGE_END_YEAR` -- the 1989-2022 coverage
  envelope (the legacy ``GED 23.1`` release ends at 2022;
  "23.1" in the docs refers to the UCDP release year, not
  the latest data year).
- :data:`UCDP_ATTRIBUTION_TEXT` -- the canonical citation
  text (Rule #15; byte-identical to the legacy
  ``UCDP_ATTRIBUTION`` constant in
  ``src/leaders_db/ingest/ucdp_io.py`` and to the
  ``ucdp`` section in ``docs/sources/attributions.md``).
- The two observation families:
  :data:`UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE` /
  :data:`UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE`.
- :func:`build_ucdp_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`UCDPAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_ucdp_adapter` -- explicit factory. Callers
  wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_ucdp` or directly. The package does NOT
  auto-register on import (the registry is passive by
  design -- see docs/architecture/sources.md §10.1).
- :func:`register_ucdp` -- explicit registration helper for
  tests and future composition.
"""

from __future__ import annotations

from ._catalog import (
    DEFAULT_CATALOG_PATH,
    load_indicator_catalog,
    rating_category_to_observation_family,
)
from ._constants import (
    UCDP_AGGREGATE_QUALITY_FLAG,
    UCDP_TRANSFORM_NAME,
)
from ._descriptor import (
    UCDP_ATTRIBUTION_KEY,
    UCDP_ATTRIBUTION_TEXT,
    UCDP_COVERAGE_END_YEAR,
    UCDP_COVERAGE_START_YEAR,
    UCDP_DEFAULT_VERSION,
    UCDP_HOMEPAGE_URL,
    UCDP_METADATA_NAME,
    UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE,
    UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE,
    UCDP_SOURCE_KEY,
    UCDP_SUPPORTED_FAMILIES,
    UCDP_ZIP_ASSET_ID,
    UCDP_ZIP_NAME,
    build_ucdp_descriptor,
)
from ._metadata_validators import (
    ACCEPTABLE_INGESTION_STATUSES,
    REQUIRED_METADATA_FIELDS,
    UCDP_CHECKSUM_MISMATCH,
    UNSUPPORTED_VERSION,
)
from ._missing_values import (
    _coerce_cell,
    _is_real_number,
)
from ._pipeline import transform_ucdp_observations
from ._raw_read import read_ucdp_zip
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    emit_ucdp_observations,
)
from .adapter import (
    UCDP_ADAPTER_FACTORY,
    UCDPAdapter,
    create_ucdp_adapter,
    register_ucdp,
)

__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "DEFAULT_CATALOG_PATH",
    "REQUIRED_METADATA_FIELDS",
    "UCDP_ADAPTER_FACTORY",
    "UCDP_AGGREGATE_QUALITY_FLAG",
    "UCDP_ATTRIBUTION_KEY",
    "UCDP_ATTRIBUTION_TEXT",
    "UCDP_CHECKSUM_MISMATCH",
    "UCDP_COVERAGE_END_YEAR",
    "UCDP_COVERAGE_START_YEAR",
    "UCDP_DEFAULT_VERSION",
    "UCDP_HOMEPAGE_URL",
    "UCDP_METADATA_NAME",
    "UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE",
    "UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE",
    "UCDP_SOURCE_KEY",
    "UCDP_SUPPORTED_FAMILIES",
    "UCDP_TRANSFORM_NAME",
    "UCDP_ZIP_ASSET_ID",
    "UCDP_ZIP_NAME",
    "UNSUPPORTED_VERSION",
    "UCDPAdapter",
    "_coerce_cell",
    "_is_real_number",
    "build_ucdp_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_ucdp_adapter",
    "emit_ucdp_observations",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
    "read_ucdp_zip",
    "register_ucdp",
    "transform_ucdp_observations",
]
