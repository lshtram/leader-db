"""Clean WHO Global Health Observatory (GHO) API source adapter.

This module provides the :class:`WhoGhoApiAdapter` -- the
seventeenth source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 17,
``docs/requirements/sources.md`` §12 SRC-MIG-005), after PWT,
Maddison, WDI, WGI, V-Dem, UCDP, Transparency CPI, PTS, RSF,
BTI, Freedom House, Archigos, REIGN, SIPRI Milex, SIPRI
Yearbook Ch.7, CIRIGHTS, and UNDP HDI.

The adapter wraps the existing legacy parser
(:func:`leaders_db.ingest.who_gho_api_io.parse_who_gho_api_payload`)
via lazy imports so the canonical Stage 2 parsing logic is
reused without duplication (SRC-MIG-002: do not delete existing
prototype capabilities). The legacy package is imported lazily
inside adapter methods only so the ``leaders_db.sources`` package
boundary documented in ``docs/architecture/sources.md`` §10.1 is
preserved; the package import does NOT pull in
``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(``docs/architecture/sources.md`` §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for WHO GHO API (source_id ``who_gho_api``, default version
  ``"GHO OData v1"``, homepage URL
  ``https://ghoapi.azureedge.net/api/``, attribution_key
  ``who_gho_api``, coverage hint 1990-present, observation
  family ``social_wellbeing_country_year``, source_type
  ``"api"``, ``requires_network=True``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND the per-``(year, indicator)`` JSON cache
  BEFORE the reader opens the cache; every blocker names the
  specific missing / invalid file or policy. The gate accepts
  BOTH the canonical primary metadata shape (``source_version``
  / ``source_url``) AND the legacy WHO GHO API bundle shape
  (``version`` / ``source_url`` / ``sha256: null``) so the
  existing staged bundle does not need to be rewritten as part
  of the migration. The gate also blocks
  ``cache_policy="refresh"`` / ``"no_cache"`` because the
  unified adapter never invokes the network in this slice.
- ``read_raw(request)`` -- opens the per-``(year, indicator)``
  JSON cache via the legacy long-format parser and returns a
  :class:`RawReadResult` carrying the long-format DataFrames +
  per-file :class:`RawAsset` records + a raw-value lookup.
- ``transform(request, raw)`` -- applies the request year /
  country filters and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (unsupported leader
  filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
parser's per-year cache lookup. The country filter is an exact
ISO3 match (upper-cased). ``request.leaders`` is unsupported for
a country-year health source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
``request.source_version`` other than the canonical
``"GHO OData v1"`` is unsupported and fails readiness with a
structured ``unsupported_version`` error per SRC-REQ-009.

Cache-policy semantics
----------------------

WHO GHO API is API-backed with a per-``(year, indicator)`` JSON
cache. The new runner is offline / cache-first by default and
the unified WHO GHO API adapter is offline / cache-only in this
slice. ``cache_policy="refresh"`` / ``"no_cache"`` is NOT
supported by the unified WHO GHO API adapter: the readiness gate
refuses both with a structured ``unsupported_cache_policy``
error. Use ``cache_policy="offline_only"`` / ``"prefer_cache"``
and stage the per-``(year, indicator)`` JSON cache to refresh
data.
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
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
)

from ._constants import (
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
)
from ._descriptor import build_who_gho_api_descriptor
from ._raw_read import read_who_gho_api_cache
from ._readiness import (
    cache_policy_blocker,
    check_cache_availability,
    metadata_blocker,
    request_warnings,
    version_blocker,
)
from ._transform import emit_who_gho_api_observations

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WhoGhoApiAdapter:
    """Unified-source WHO GHO API adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is a
    class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = build_who_gho_api_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cache.
        Every blocker names the specific missing / invalid file,
        metadata field, or cache policy so a developer can fix the
        upstream issue without reading source code.

        Three failure classes (each surfaces a structured
        :class:`SourceWarning` with ``severity='error'`` in the
        :class:`ReadinessResult.errors` tuple so the runner
        raises ``RuntimeError` before calling ``read_raw`` /
        ``transform``):

        1. **Metadata readiness** --
           :func:`metadata_blocker` validates ``metadata.json``
           (file presence, parseable JSON, canonical
           ``source_version`` / ``version``).
        2. **Cache policy** --
           :func:`cache_policy_blocker` blocks
           ``"refresh"`` / ``"no_cache"`` because the unified
           WHO GHO API adapter never invokes the network in
           this slice.
        3. **Cache-file availability** --
           :func:`check_cache_availability` validates the
           per-``(year, indicator)`` JSON cache (file presence,
           JSON shape) for the requested years.

        One request-scoping warning class (NOT a blocker) is
        surfaced on ``ReadinessResult.warnings``: the
        ``unsupported_filter`` warning when ``leaders=`` is set
        (WHO GHO API is a country-year health source with no
        leader dimension; SRC-REQ-005).
        """
        metadata_block = metadata_blocker(request)
        if metadata_block is not None:
            message, code = metadata_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_METADATA,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={"raw_root": str(request.raw_root)},
                    ),
                ),
            )

        policy_block = cache_policy_blocker(request)
        if policy_block is not None:
            message, code = policy_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "cache_policy": request.cache_policy,
                            "raw_root": str(request.raw_root),
                        },
                    ),
                ),
            )

        ready, blocker, code = check_cache_availability(request)
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or (
                            "WHO GHO API cache is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "cache_policy": request.cache_policy,
                            "raw_root": str(request.raw_root),
                            "years": (
                                list(request.years)
                                if request.years else None
                            ),
                        },
                    ),
                ),
            )

        version_block = version_blocker(request)
        if version_block is not None:
            message, code = version_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or "unsupported_version",
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "requested_version": request.source_version,
                            "canonical_version": WHO_GHO_API_DEFAULT_VERSION,
                        },
                    ),
                ),
            )

        return ReadinessResult(
            ready=True,
            warnings=request_warnings(request),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the per-``(year, indicator)`` JSON cache and return the raw bundle.

        Delegates to :func:`read_who_gho_api_cache` in
        :mod:`._raw_read`. The cache is the ONLY source of data
        the unified adapter reads in this slice: the readiness
        gate has already proved the cache policy is supported
        + the explicit-year requests have complete cache, and
        the legacy HTTP layer is intentionally never invoked.
        """
        return read_who_gho_api_cache(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the raw long-format frames into
        :class:`NormalizedObservation` records.

        Delegates to :func:`emit_who_gho_api_observations` in
        :mod:`._transform`. See that module's docstring for the
        year / country filter contract.
        """
        return emit_who_gho_api_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_who_gho_api_adapter() -> WhoGhoApiAdapter:
    """Return a fresh :class:`WhoGhoApiAdapter` instance.

    The factory is the explicit seam callers use to wire WHO GHO
    API into a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive by design
    -- see ``docs/architecture/sources.md`` §10.1).
    """
    return WhoGhoApiAdapter()


def register_who_gho_api(registry: Any) -> WhoGhoApiAdapter:
    """Register the WHO GHO API adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``who_gho_api`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_who_gho_api_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_who_gho_api_adapter()`` (preferred) or this module-level
# callable.
WHO_GHO_API_ADAPTER_FACTORY = create_who_gho_api_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches missing
    ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is invoked
    at module bottom so a missing method surfaces during CI
    even when no test instantiates the adapter directly.
    """
    if not isinstance(WhoGhoApiAdapter(), SourceAdapter):
        raise TypeError(
            "WhoGhoApiAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


# Reference the warning-code constants so the static analyzer
# keeps them live for any future import-side warning-builder
# hooks. The codes themselves are re-exported from
# :mod:`._readiness`.
_ = (
    WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
)


__all__ = [
    "WHO_GHO_API_ADAPTER_FACTORY",
    "WhoGhoApiAdapter",
    "create_who_gho_api_adapter",
    "register_who_gho_api",
]
