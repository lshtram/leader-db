"""Unified-source World Bank WDI adapter implementation.

Provides the :class:`WDIAdapter` -- the third source rebuilt
under the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 3,
docs/requirements/sources.md §12 SRC-MIG-005), after the PWT
10.01 and Maddison Project Database 2023 adapters.

The adapter reads staged cache files through the local
cache-only path and does not invoke the legacy reader or
HTTP path for supported policies. It reuses the legacy
catalog loader (:func:`leaders_db.ingest.wdi_io.load_indicator_catalog`)
for catalog-schema compatibility only (SRC-MIG-002: do not
delete existing prototype capabilities). The prototype package is
imported lazily only where required so the
``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved; the package
import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for World Bank WDI (source_id ``world_bank_wdi``, default
  version ``"World Bank API v2; cached indicator responses"``,
  homepage URL ``https://api.worldbank.org/v2/``,
  attribution_key ``world_bank_wdi``, coverage hint
  1960-present, observation families
  ``("economic_country_year", "social_country_year")``,
  source_type ``"api"``, requires_network ``True``).
- ``check_ready(request)`` -- delegates to
  :func:`check_world_bank_wdi_readiness`; validates the
  bundle's ``metadata.json`` AND the per-(year, indicator)
  JSON cache BEFORE the reader opens the cache files; every
  blocker names the specific missing / invalid field or file.
- ``read_raw(request)`` -- delegates to
  :func:`read_world_bank_wdi_cache`; opens the staged
  per-(year, indicator) JSON cache via the local cache-only
  read path and returns a :class:`RawReadResult` carrying
  the wide-format DataFrame + a :class:`RawAsset` record.
- ``transform(request, raw)`` -- delegates to
  :func:`transform_world_bank_wdi_observations`; applies
  the request year + country filters on the wide frame,
  pre-computes the cache index map, and emits
  :class:`NormalizedObservation` records via
  :func:`emit_world_bank_wdi_observations`.

Module split
------------

The lifecycle bodies live in dedicated sibling modules so
this module stays focused on the lifecycle class + the
protocol conformance guard + the registration helpers. All
sibling modules honor the package-isolation contract
(SRC-MIG-007) and the per-module 400-line convention:

- :mod:`._descriptor` -- canonical constants + the
  :func:`build_world_bank_wdi_descriptor` factory.
- :mod:`._metadata_readiness` -- per-field ``metadata.json``
  validators + the SHA-256 checksum contract.
- :mod:`._cache_readiness` -- per-(year, indicator) cache
  enumeration + JSON-shape validation + cache-policy gate.
- :mod:`._readiness` -- readiness-gate orchestrator:
  composes the metadata + cache gates + version + warnings.
- :mod:`._paths` -- bundle / cache / metadata path helpers
   + catalog resolution (lazy compatibility imports).
- :mod:`._lifecycle` -- :func:`check_world_bank_wdi_readiness`
  body (Phase A/B/C/D readiness orchestration).
- :mod:`._raw_read` -- :func:`read_world_bank_wdi_cache`
  body (cache-only read path orchestration).
- :mod:`._pipeline` -- :func:`transform_world_bank_wdi_observations`
  body (year/country filtering + cache index pre-compute).
- :mod:`._cache_reader` -- local cache-only parser +
  long-to-wide pivot + cache index loader.
- :mod:`._transform` -- :func:`emit_world_bank_wdi_observations`
  per-row emission loop + observation family / unit-label
  resolution.

Cache-policy semantics
----------------------

``SourceIngestRequest.cache_policy`` honors
``docs/requirements/sources.md`` §11 SRC-TYPE-002 (API
sources use cache policy):

- ``offline_only`` / ``prefer_cache`` (default for WDI):
  the readiness gate refuses to dispatch ``read_raw`` /
  ``transform`` when the cache directory is missing or any
  requested year lacks a complete indicator cache. The
  legacy HTTP layer is never invoked. This is the
  documented safe default -- the new runner is offline /
  cache-first.
- ``refresh`` / ``no_cache``: NOT supported by the unified
  WDI adapter in this slice.
  :func:`check_cache_availability` fails readiness with
  the structured ``unsupported_cache_policy`` code because
  :meth:`WDIAdapter.read_raw` never invokes the network --
  the legacy HTTP path is intentionally not wired through
  the unified runner. Callers that need fresh data must
  stage the per-(year, indicator) JSON cache under
  ``<raw_root>/world_bank_wdi/cache/<year>/<CODE>.json``
  and re-run with ``cache_policy='offline_only'`` or
  ``'prefer_cache'``.

Year semantics
--------------

WDI covers 1960+ (per the canonical attribution block in
``docs/sources/attributions.md`` and the staged
``data/raw/world_bank_wdi/metadata.json``). A request for
a year before 1960 emits zero observations AND a structured
``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003).
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
)

from ._descriptor import build_world_bank_wdi_descriptor
from ._lifecycle import check_world_bank_wdi_readiness
from ._pipeline import transform_world_bank_wdi_observations
from ._raw_read import read_world_bank_wdi_cache


class WDIAdapter:
    """Unified-source World Bank WDI adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead. Each lifecycle
    method delegates to the canonical sibling module:
    :meth:`check_ready` -> :func:`check_world_bank_wdi_readiness`,
    :meth:`read_raw` -> :func:`read_world_bank_wdi_cache`,
    :meth:`transform` -> :func:`transform_world_bank_wdi_observations`.
    The delegation is intentional: the adapter class owns the
    protocol conformance guard; the lifecycle bodies own the
    orchestration logic and stay focused / under the 400-line
    convention in their own modules.
    """

    descriptor: SourceDescriptor = build_world_bank_wdi_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        Delegates to
        :func:`check_world_bank_wdi_readiness` in
        :mod:`._lifecycle`. See that module's docstring for
        the full failure class + warning catalogue.
        """
        return check_world_bank_wdi_readiness(request)

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged per-(year, indicator) JSON cache and
        return the wide-format DataFrame + :class:`RawAsset`.

        Delegates to :func:`read_world_bank_wdi_cache` in
        :mod:`._raw_read`. The function NEVER invokes the
        network; see :mod:`._raw_read`'s docstring for the
        offline / cache-only contract.
        """
        return read_world_bank_wdi_cache(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to
        :func:`transform_world_bank_wdi_observations` in
        :mod:`._pipeline`. See that module's docstring for
        the year / country filter + cache-index pre-compute
        contract.
        """
        return transform_world_bank_wdi_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_world_bank_wdi_adapter() -> WDIAdapter:
    """Return a fresh :class:`WDIAdapter` instance.

    The factory is the explicit seam callers use to wire WDI
    into a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive by
    design -- see docs/architecture/sources.md §10.1).
    """
    return WDIAdapter()


def register_world_bank_wdi(registry: Any) -> WDIAdapter:
    """Register the WDI adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``world_bank_wdi`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_world_bank_wdi_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for registry compatibility.
# The legacy ``STAGE2_ADAPTERS`` mapping is intentionally not
# consulted here. Callers may use either
# ``create_world_bank_wdi_adapter()`` (preferred) or this
# module-level callable.
WDI_ADAPTER_FACTORY = create_world_bank_wdi_adapter


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
    if not isinstance(WDIAdapter(), SourceAdapter):
        raise TypeError(
            "WDIAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "WDI_ADAPTER_FACTORY",
    "WDIAdapter",
    "create_world_bank_wdi_adapter",
    "register_world_bank_wdi",
]
