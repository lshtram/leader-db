"""Unified-source UCDP (Uppsala Conflict Data Program) adapter implementation.

This module provides the :class:`UCDPAdapter` -- the sixth
source rebuilt under the clean ``leaders_db.sources``
interface (docs/architecture/sources.md §7.1 priority 11,
docs/requirements/sources.md §12 SRC-MIG-005), after
PWT 10.01, Maddison Project Database 2023, World Bank WDI,
World Bank WGI, and V-Dem.

The adapter wraps the existing legacy reader
(:func:`leaders_db.ingest.ucdp_io.read_ucdp`) and the legacy
event-level aggregator
(:func:`leaders_db.ingest.ucdp_aggregate.aggregate_events_to_country_year`)
so the canonical UCDP parsing / aggregation logic is reused
without duplication (SRC-MIG-002: do not delete existing
prototype capabilities). The legacy package is imported
lazily inside adapter methods only so the
``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved; the package
import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for UCDP GED 23.1 (source_id ``ucdp``, default version
  ``"GED 23.1"``, UCDP homepage URL
  ``https://ucdp.uu.se/downloads/``, ``attribution_key="ucdp"``,
  coverage hint 1989-2022, two observation families:
  ``international_peace_country_year`` +
  ``domestic_violence_country_year``, ``source_type="dataset"``,
  ``requires_network=False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND ``ged231-csv.zip`` BEFORE the
  reader opens the zip; every blocker names the specific
  missing / invalid field or file. The gate accepts the
  canonical primary metadata shape
  (``source_name`` / ``source_version`` / ``source_url`` /
  ``license_note`` / ``local_files`` / ``ingestion_status`` /
  ``coverage`` / optional ``checksum_sha256``). The
  canonical UCDP bundle metadata carries
  ``local_files=[]`` and ``checksum_sha256: null`` -- a
  deliberately minimal shape so the operator can update
  the metadata once the zip is staged. The mandatory
  readiness requirement is on raw-file presence: the gate
  returns ``ready=False`` with a structured ``MISSING_RAW``
  error if ``ged231-csv.zip`` is not staged on disk,
  regardless of the metadata's ``local_files`` /
  ``checksum_sha256`` shape. A metadata-only bundle is
  intentionally NOT runner-ready so the
  ``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
  ``read_raw`` / ``transform`` -- the runner never
  dispatches ``read_raw`` against a missing zip.
  When the staged zip's SHA-256 disagrees with a non-null
  ``checksum_sha256``, the gate fires the module-local
  ``ucdp_checksum_mismatch`` error code.
- ``read_raw(request)`` -- opens the staged
  ``ged231-csv.zip`` via the legacy reader and returns a
  :class:`RawReadResult` carrying the wide-format
  country-year DataFrame (one row per ``(country_id,
  year)`` with one column per catalog ``variable_name``,
  plus the two identity columns) plus a :class:`RawAsset`
  record (zip path, source URL, no checksum).
- ``transform(request, raw)`` -- applies the requested
  year / country filters and emits
  :class:`NormalizedObservation` records with raw +
  transform locators, attribution text (Rule #15), and
  structured warnings (out-of-coverage years, unsupported
  leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the
wide-frame ``year`` / post-read DataFrame filtering
(SRC-REQ-004). The UCDP ``country_id`` is UCDP's own
integer id (NOT ISO3); the unified transform layer uses the
UCDP integer id verbatim in the observation ``country_code``
field. Callers who want to filter by ISO3 must use the
legacy path or Stage 3 country match to resolve first.

``request.leaders`` is unsupported for a country-year
conflict source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
``request.source_version`` other than the canonical
``"GED 23.1"`` is unsupported and fails readiness with a
structured ``unsupported_version`` error per SRC-REQ-009.

Year semantics
--------------

UCDP GED 23.1 covers 1989-2022 per the canonical UCDP
codebook. A request for an out-of-coverage year (e.g.
``years=(2023,)`` or ``years=(1988,)``) emits zero
observations AND a structured ``YEAR_ABSENT`` warning --
no stale-proxy fill (SRC-COV-002, SRC-COV-003).

Event-level aggregation shape
-----------------------------

UCDP is the first event-level source in the unified
adapter family (PWT / Maddison / WDI / WGI / V-Dem are
country-year tables). The wide-format DataFrame is the
output of the event-level aggregation -- per-row
event-level provenance is NOT preserved through the
aggregation, so the unified ``RawLocator.row_number`` is
intentionally ``None`` and the
``transform_locator.rule_id`` carries the
``ucdp:<country_id>:<year>:<variable_name>`` pattern.
Per the documented contract: "If row-level provenance is
not available after aggregation, document and test the
aggregate locator convention rather than fabricating row
numbers."

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.ucdp._readiness` and
:mod:`leaders_db.sources.adapters.ucdp._metadata_validators`,
the canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.ucdp._descriptor`, the
catalog helpers live in
:mod:`leaders_db.sources.adapters.ucdp._catalog`, the
per-row observation emission lives in
:mod:`leaders_db.sources.adapters.ucdp._transform`, the
raw-read orchestration lives in
:mod:`leaders_db.sources.adapters.ucdp._raw_read`, and the
transform-pipeline orchestration lives in
:mod:`leaders_db.sources.adapters.ucdp._pipeline`. This
module owns the lifecycle class + registration helpers +
protocol conformance guard. All sibling modules honor the
package-isolation contract (SRC-MIG-007) and the per-module
400-line convention.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    ReadinessResult,
    SourceAdapter,
    SourceDescriptor,
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import MISSING_RAW

from ._descriptor import (
    UCDP_DEFAULT_VERSION,
    UCDP_METADATA_NAME,
    UCDP_SOURCE_KEY,
    UCDP_ZIP_NAME,
    build_ucdp_descriptor,
)
from ._pipeline import transform_ucdp_observations
from ._raw_read import _bundle_dir, read_ucdp_zip
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class UCDPAdapter:
    """Unified-source UCDP adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_ucdp_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the zip.
        Every blocker names the specific missing / invalid
        field or file so a developer can fix the upstream
        issue without reading source code.

        The gate enforces two failure classes (each surfaces
        a structured ``SourceWarning`` with
        ``severity='error'`` in the
        ``ReadinessResult.errors`` tuple so the runner
        raises ``RuntimeError`` before calling ``read_raw``
        / ``transform``):

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` + ``ged231-csv.zip``. The
           mandatory readiness requirement is on raw-file
           presence: the gate returns ``ready=False`` with a
           structured ``MISSING_RAW`` error if
           ``ged231-csv.zip`` is not staged on disk,
           regardless of the metadata's ``local_files`` /
           ``checksum_sha256`` shape. A metadata-only
           bundle is intentionally NOT runner-ready. The
           canonical UCDP bundle metadata carries
           ``local_files=[]`` and ``checksum_sha256: null``
           -- a deliberately minimal shape so the operator
           can update the metadata once the zip is staged.
           A staged zip whose SHA-256 disagrees with a
           non-null ``checksum_sha256`` fires the
           module-local ``ucdp_checksum_mismatch`` error
           code.
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs
           from the canonical ``"GED 23.1"`` (SRC-REQ-009).

        Two request-scoping warning classes (NOT blockers)
        are surfaced on ``ReadinessResult.warnings``:

        - ``unsupported_filter`` -- ``leaders=`` filter is
          unsupported for a country-year conflict source.
        - ``year_absent`` -- ``years=`` outside the
          1989-2022 coverage envelope emits zero rows (no
          stale-proxy fill per SRC-COV-002 /
          SRC-COV-003).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence +
        # metadata fields + checksum shape and optional
        # zip-checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            UCDP_ZIP_NAME,
            UCDP_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "UCDP bundle is not ready",
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009).
        version_blocker = check_source_version(
            request,
            canonical_version=UCDP_DEFAULT_VERSION,
        )
        if version_blocker is not None:
            message, code_str = version_blocker
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code_str,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "requested_version": request.source_version,
                            "canonical_version": UCDP_DEFAULT_VERSION,
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings (advisory only).
        warnings = list(collect_request_scoping_warnings(request))

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged ``ged231-csv.zip`` and return the raw bundle.

        Delegates to :func:`read_ucdp_zip` in
        :mod:`._raw_read`. See that module's docstring for
        the full local-file-only contract.
        """
        return read_ucdp_zip(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to :func:`transform_ucdp_observations`
        in :mod:`._pipeline`. See that module's docstring
        for the year / country filter contract.
        """
        return transform_ucdp_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_ucdp_adapter() -> UCDPAdapter:
    """Return a fresh :class:`UCDPAdapter` instance.

    The factory is the explicit seam callers use to wire
    UCDP into a :class:`SourceRegistry`. The package does
    NOT auto-register on import (the registry is passive by
    design -- see docs/architecture/sources.md §10.1).
    """
    return UCDPAdapter()


def register_ucdp(registry: Any) -> UCDPAdapter:
    """Register the UCDP adapter against ``registry``.

    Convenience wrapper for tests and future composition
    code. Returns the registered adapter so callers can
    introspect it. Raises :class:`ValueError` if the
    registry already has a ``ucdp`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_ucdp_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use
# either ``create_ucdp_adapter()`` (preferred) or this
# module-level callable.
UCDP_ADAPTER_FACTORY = create_ucdp_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy
    the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches
    missing ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is
    invoked at module bottom so a missing method surfaces
    during CI even when no test instantiates the adapter
    directly.
    """
    if not isinstance(UCDPAdapter(), SourceAdapter):
        raise TypeError(
            "UCDPAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and "
            "the check_ready / read_raw / transform method "
            "shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "UCDP_ADAPTER_FACTORY",
    "UCDP_DEFAULT_VERSION",
    "UCDP_METADATA_NAME",
    "UCDP_SOURCE_KEY",
    "UCDP_ZIP_NAME",
    "UCDPAdapter",
    "build_ucdp_descriptor",
    "create_ucdp_adapter",
    "register_ucdp",
]
