"""Unified-source World Bank Worldwide Governance Indicators adapter
implementation.

This module provides the :class:`WGIAdapter` -- the fourth
source rebuilt under the clean ``leaders_db.sources` interface
(docs/architecture/sources.md §7.1 priority 4,
docs/requirements/sources.md §12 SRC-MIG-005), after PWT 10.01,
Maddison Project Database 2023, and World Bank WDI.

The adapter wraps the existing legacy reader
(:func:`leaders_db.ingest.wgi_xlsx.read_wgi`) so the canonical
WGI parsing logic is reused without duplication (SRC-MIG-002:
do not delete existing prototype capabilities). The legacy
package is imported lazily inside adapter methods only so the
``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved; the package
import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for World Bank WGI (source_id ``world_bank_wgi``, default
  version ``"Worldwide Governance Indicators 2023 Update
  (data through 2022)"``, homepage URL
  ``https://info.worldbank.org/governance/wgi/``,
  attribution_key ``world_bank_wgi``, coverage hint
  1996-2022, observation family ``governance_country_year``,
  source_type ``"dataset"``, requires_network ``False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND ``wgidataset.xlsx`` BEFORE the reader
  opens the workbook; every blocker names the specific missing
  / invalid field or file. The gate accepts BOTH the canonical
  primary metadata shape (``source_version`` /
  ``checksum_sha256`` / ``local_files`` / ``license_note``)
  AND the legacy WGI shape (``version`` / ``sha256`` /
  ``local_file`` / ``license``) so the existing staged bundle
  does not need to be rewritten as part of the migration.
- ``read_raw(request)`` -- opens the staged ``wgidataset.xlsx``
  via the legacy reader and returns a :class:`RawReadResult`
  carrying the wide-format DataFrame (one row per
  ``(iso3, year)``, one column per catalog ``variable_name``)
  plus a :class:`RawAsset` record (path, SHA-256, source URL).
- ``transform(request, raw)`` -- applies the requested year /
  country filters and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (out-of-coverage years,
  unsupported leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
reader's ``year`` / post-read DataFrame filtering (SRC-REQ-004).
``request.leaders`` is unsupported for a country-year governance
source and surfaces a structured ``UNSUPPORTED_FILTER`` warning
per SRC-REQ-005. ``request.source_version`` other than the
canonical ``"Worldwide Governance Indicators 2023 Update (data
through 2022)"`` is unsupported and fails readiness with a
structured ``unsupported_version`` error per SRC-REQ-009.

Year semantics
--------------

WGI covers 1996-2022 (the canonical "2023 Update" release;
"2023" in the docs / attribution refers to the release year,
not the latest data year). A request for an out-of-coverage
year (e.g. ``years=(2023,)`` or ``years=(2024,)``) emits zero
observations AND a structured ``YEAR_ABSENT`` warning -- no
stale-proxy fill (SRC-COV-002 / SRC-COV-003).

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.world_bank_wgi._readiness`
and
:mod:`leaders_db.sources.adapters.world_bank_wgi._metadata_validators`,
the canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.world_bank_wgi._descriptor`,
the per-row observation emission lives in
:mod:`leaders_db.sources.adapters.world_bank_wgi._transform`,
the raw-read orchestration lives in
:mod:`leaders_db.sources.adapters.world_bank_wgi._raw_read`,
and the transform-pipeline orchestration lives in
:mod:`leaders_db.sources.adapters.world_bank_wgi._pipeline`.
This module owns the lifecycle class + registration helpers +
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
from leaders_db.sources.warnings import (
    MISSING_RAW,
)

from ._descriptor import (
    WORLD_BANK_WGI_COVERAGE_END_YEAR,
    WORLD_BANK_WGI_COVERAGE_START_YEAR,
    WORLD_BANK_WGI_DEFAULT_VERSION,
    WORLD_BANK_WGI_METADATA_NAME,
    WORLD_BANK_WGI_OBSERVATION_FAMILY,
    WORLD_BANK_WGI_SOURCE_KEY,
    WORLD_BANK_WGI_SUPPORTED_FAMILIES,
    WORLD_BANK_WGI_XLSX_NAME,
    build_world_bank_wgi_descriptor,
)
from ._pipeline import transform_world_bank_wgi_observations
from ._raw_read import _bundle_dir, read_world_bank_wgi_xlsx
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WGIAdapter:
    """Unified-source World Bank WGI adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_world_bank_wgi_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the workbook.
        Every blocker names the specific missing / invalid field
        or file so a developer can fix the upstream issue
        without reading source code.

        The gate enforces two failure classes (each surfaces a
        structured ``SourceWarning`` with ``severity='error'``
        in the ``ReadinessResult.errors`` tuple so the runner
        raises ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` + ``wgidataset.xlsx`` (file
           presence, required fields in either the canonical
           primary or legacy shape, canonical metadata
           ``source_version`` / ``version``, checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical ``"Worldwide Governance Indicators
           2023 Update (data through 2022)"`` (SRC-REQ-009;
           the legacy bundle has no per-version stamp beyond
           ``metadata.json['version']`` so silently
           propagating an unsupported version into
           ``RawAsset.version`` /
           ``NormalizedObservation.source_version`` would lie
           to downstream scorers).

        Two request-scoping warning classes (NOT blockers)
        are surfaced on ``ReadinessResult.warnings`` so the
        runner carries them through to the final result:

        - ``unsupported_filter`` -- ``leaders=`` filter is
          unsupported for a country-year governance source.
        - ``year_absent`` -- ``years=`` outside the 1996-2022
          coverage envelope emits zero rows (no stale-proxy
          fill per SRC-COV-002 / SRC-COV-003).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir, WORLD_BANK_WGI_XLSX_NAME, WORLD_BANK_WGI_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "World Bank WGI bundle is not ready",
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
            canonical_version=WORLD_BANK_WGI_DEFAULT_VERSION,
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
                            "canonical_version": (
                                WORLD_BANK_WGI_DEFAULT_VERSION
                            ),
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
        """Open the staged ``wgidataset.xlsx`` and return the raw bundle.

        Delegates to :func:`read_world_bank_wgi_xlsx` in
        :mod:`._raw_read`. See that module's docstring for
        the full local-file-only contract.
        """
        return read_world_bank_wgi_xlsx(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to :func:`transform_world_bank_wgi_observations`
        in :mod:`._pipeline`. See that module's docstring for
        the year / country filter contract.
        """
        return transform_world_bank_wgi_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_world_bank_wgi_adapter() -> WGIAdapter:
    """Return a fresh :class:`WGIAdapter` instance.

    The factory is the explicit seam callers use to wire WGI
    into a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive by
    design -- see docs/architecture/sources.md §10.1).
    """
    return WGIAdapter()


def register_world_bank_wgi(registry: Any) -> WGIAdapter:
    """Register the WGI adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``world_bank_wgi`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_world_bank_wgi_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_world_bank_wgi_adapter()`` (preferred) or this
# module-level callable.
WORLD_BANK_WGI_ADAPTER_FACTORY = create_world_bank_wgi_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches
    missing ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is invoked
    at module bottom so a missing method surfaces during CI
    even when no test instantiates the adapter directly.
    """
    if not isinstance(WGIAdapter(), SourceAdapter):
        raise TypeError(
            "WGIAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "WORLD_BANK_WGI_ADAPTER_FACTORY",
    "WORLD_BANK_WGI_COVERAGE_END_YEAR",
    "WORLD_BANK_WGI_COVERAGE_START_YEAR",
    "WORLD_BANK_WGI_DEFAULT_VERSION",
    "WORLD_BANK_WGI_METADATA_NAME",
    "WORLD_BANK_WGI_OBSERVATION_FAMILY",
    "WORLD_BANK_WGI_SOURCE_KEY",
    "WORLD_BANK_WGI_SUPPORTED_FAMILIES",
    "WORLD_BANK_WGI_XLSX_NAME",
    "WGIAdapter",
    "build_world_bank_wgi_descriptor",
    "create_world_bank_wgi_adapter",
    "register_world_bank_wgi",
]
