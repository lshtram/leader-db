"""Unified-source V-Dem (Varieties of Democracy) adapter implementation.

This module provides the :class:`VDemAdapter` -- the fifth
source rebuilt under the clean ``leaders_db.sources``
interface (docs/architecture/sources.md §7.1 priority 5,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT
10.01, Maddison Project Database 2023, World Bank WDI, and
World Bank WGI.

The adapter wraps the existing legacy reader
(:func:`leaders_db.ingest.vdem_io.read_vdem_csv`) so the
canonical V-Dem parsing logic is reused without duplication
(SRC-MIG-002: do not delete existing prototype capabilities).
The legacy package is imported lazily inside adapter methods
only so the ``leaders_db.sources`` package boundary
documented in docs/architecture/sources.md §10.1 is
preserved; the package import does NOT pull in
``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for V-Dem v16 (source_id ``vdem``, default version
  ``"v16"``, DOI homepage URL
  ``https://doi.org/10.23696/vdemds26``,
  ``attribution_key="vdem"``, coverage hint 1789-2025, five
  observation families: ``political_country_year``,
  ``governance_country_year``, ``corruption_country_year``,
  ``repression_country_year``, ``social_country_year``,
  ``source_type="dataset"``, ``requires_network=False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND ``V-Dem-CY-Full+Others-v16.csv``
  BEFORE the reader opens the CSV; every blocker names the
  specific missing / invalid field or file. The gate accepts
  the canonical primary metadata shape (``source_name`` /
  ``source_version`` / ``source_url`` / ``license_note`` /
  ``local_files`` / ``ingestion_status`` / ``coverage`` /
  ``checksum_sha256``). The CSV (388MB) is NEVER hashed
  against the metadata checksum (the metadata checksum
  covers the staged zip, NOT the CSV); the gate validates
  the metadata shape AND, if the zip is staged, recomputes
  the zip's SHA-256.
- ``read_raw(request)`` -- opens the staged
  ``V-Dem-CY-Full+Others-v16.csv`` via the legacy reader and
  returns a :class:`RawReadResult` carrying the narrow
  DataFrame (one row per ``(country_text_id, year)`` with
  one column per catalog ``raw_column``, plus four identity
  columns) plus a :class:`RawAsset` record (path, source
  URL, no checksum).
- ``transform(request, raw)`` -- applies the requested
  year / country filters and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (out-of-coverage
  years, unsupported leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the
narrow-frame ``year`` / post-read DataFrame filtering
(SRC-REQ-004). ``request.leaders`` is unsupported for a
country-year political / governance source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
``request.source_version`` other than the canonical ``"v16"``
is unsupported and fails readiness with a structured
``unsupported_version`` error per SRC-REQ-009.

Year semantics
--------------

V-Dem v16 covers 1789-2025 per the canonical codebook. A
request for an out-of-coverage year (e.g. ``years=(2026,)``
or ``years=(1788,)``) emits zero observations AND a
structured ``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002, SRC-COV-003).

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.vdem._readiness` and
:mod:`leaders_db.sources.adapters.vdem._metadata_validators`,
the canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.vdem._descriptor`, the
catalog helpers live in
:mod:`leaders_db.sources.adapters.vdem._catalog`, the
per-row observation emission lives in
:mod:`leaders_db.sources.adapters.vdem._transform`, the
raw-read orchestration lives in
:mod:`leaders_db.sources.adapters.vdem._raw_read`, and the
transform-pipeline orchestration lives in
:mod:`leaders_db.sources.adapters.vdem._pipeline`. This
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
    VDEM_CSV_NAME,
    VDEM_DEFAULT_VERSION,
    VDEM_METADATA_NAME,
    VDEM_SOURCE_KEY,
    VDEM_ZIP_NAME,
    build_vdem_descriptor,
)
from ._pipeline import transform_vdem_observations
from ._raw_read import _bundle_dir, read_vdem_csv
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class VDemAdapter:
    """Unified-source V-Dem adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_vdem_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the CSV.
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
           ``metadata.json`` + ``V-Dem-CY-Full+Others-v16.csv``
           (file presence, required fields, canonical
           metadata ``source_version``, checksum shape and
           optional zip-checksum match). The CSV (388MB) is
           NEVER hashed -- the metadata checksum covers the
           staged zip, not the CSV.
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs
           from the canonical ``"v16"`` (SRC-REQ-009; the
           legacy bundle has no per-version stamp beyond
           ``metadata.json['source_version']`` so silently
           propagating an unsupported version into
           ``RawAsset.version`` /
           ``NormalizedObservation.source_version`` would
           lie to downstream scorers).

        Two request-scoping warning classes (NOT blockers)
        are surfaced on ``ReadinessResult.warnings`` so the
        runner carries them through to the final result:

        - ``unsupported_filter`` -- ``leaders=`` filter is
          unsupported for a country-year political /
          governance source.
        - ``year_absent`` -- ``years=`` outside the
          1789-2025 coverage envelope emits zero rows (no
          stale-proxy fill per SRC-COV-002 /
          SRC-COV-003).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence +
        # metadata fields + checksum shape and optional
        # zip-checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            VDEM_CSV_NAME,
            VDEM_ZIP_NAME,
            VDEM_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "V-Dem bundle is not ready",
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
            canonical_version=VDEM_DEFAULT_VERSION,
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
                            "canonical_version": VDEM_DEFAULT_VERSION,
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
        """Open the staged ``V-Dem-CY-Full+Others-v16.csv`` and
        return the raw bundle.

        Delegates to :func:`read_vdem_csv` in
        :mod:`._raw_read`. See that module's docstring for
        the full local-file-only contract.
        """
        return read_vdem_csv(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the narrow raw frame into
        :class:`NormalizedObservation` records.

        Delegates to :func:`transform_vdem_observations`
        in :mod:`._pipeline`. See that module's docstring
        for the year / country filter contract.
        """
        return transform_vdem_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_vdem_adapter() -> VDemAdapter:
    """Return a fresh :class:`VDemAdapter` instance.

    The factory is the explicit seam callers use to wire
    V-Dem into a :class:`SourceRegistry`. The package does
    NOT auto-register on import (the registry is passive by
    design -- see docs/architecture/sources.md §10.1).
    """
    return VDemAdapter()


def register_vdem(registry: Any) -> VDemAdapter:
    """Register the V-Dem adapter against ``registry``.

    Convenience wrapper for tests and future composition
    code. Returns the registered adapter so callers can
    introspect it. Raises :class:`ValueError` if the
    registry already has a ``vdem`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_vdem_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use
# either ``create_vdem_adapter()`` (preferred) or this
# module-level callable.
VDEM_ADAPTER_FACTORY = create_vdem_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy
    the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches
    missing ``descriptor`` / ``check_ready`` / ``read_raw``
    / ``transform`` at module import time. The check is
    invoked at module bottom so a missing method surfaces
    during CI even when no test instantiates the adapter
    directly.
    """
    if not isinstance(VDemAdapter(), SourceAdapter):
        raise TypeError(
            "VDemAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and "
            "the check_ready / read_raw / transform method "
            "shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "VDEM_ADAPTER_FACTORY",
    "VDEM_CSV_NAME",
    "VDEM_DEFAULT_VERSION",
    "VDEM_METADATA_NAME",
    "VDEM_SOURCE_KEY",
    "VDEM_ZIP_NAME",
    "VDemAdapter",
    "build_vdem_descriptor",
    "create_vdem_adapter",
    "register_vdem",
]
