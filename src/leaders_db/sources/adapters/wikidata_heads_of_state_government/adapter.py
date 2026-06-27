"""Clean Wikidata WikiProject heads-of-state-and-government source adapter.

This module provides the :class:`WikidataHeadsOfStateGovernmentAdapter`
-- the twentieth source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 19,
``docs/requirements/sources.md`` §12 SRC-MIG-005), after PWT,
Maddison Project, World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency CPI, PTS, RSF, BTI, Freedom House, Archigos,
REIGN, SIPRI Milex, SIPRI Yearbook Ch.7, CIRIGHTS, UNDP HDI,
WHO GHO API, and FAS.

The adapter wraps the existing legacy parser
(:func:`leaders_db.ingest.wikidata_heads_of_state_government_parse.parse_sparql_bindings`)
via lazy imports so the canonical Stage 2 parsing logic is
reused without duplication (SRC-MIG-002). The legacy package
is imported lazily inside adapter methods only so the
``leaders_db.sources`` package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved; the
package import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(``docs/architecture/sources.md`` §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for Wikidata HoS/HoG (source_id
  ``wikidata_heads_of_state_government``, default version
  ``"SPARQL"``, ``source_type="knowledge_base"``,
  ``requires_network=False``, coverage hint ``None``, single
  observation family ``leader_identity_country_year``, SPARQL
  endpoint homepage URL, attribution_key
  ``wikidata_heads_of_state_government``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND the per-``(year, country_qids)`` JSON
  cache BEFORE the reader opens the cache; the gate accepts
  BOTH the canonical primary metadata shape
  (``source_version="SPARQL"``) AND the legacy alias
  (``version="SPARQL endpoint (no version)"``). The gate also
  blocks ``cache_policy="refresh"`` / ``"no_cache"`` because
  the unified adapter never invokes the network in this slice.
- ``read_raw(request)`` -- opens the per-``(year, country_qids)``
  JSON cache via the lazy long-format parser.
- ``transform(request, raw)`` -- applies the request country /
  year filters and emits :class:`NormalizedObservation`
  records with attribution text (Rule #15) + structured
  warnings.

Request-scoping: ``SourceIngestRequest.years`` /
``countries`` map to the legacy parser's per-``(year,
country_qids)`` cache lookup. The country filter is a Wikidata
QID match against the ``country_qid`` column; non-QID inputs
surface a structured ``wikidata_non_qid_country_filter``
warning. ``leaders`` is unsupported for a per-binding
leader-identity source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005 (Stage 4 is
the resolver).

Cache-policy semantics: Wikidata HoS/HoG is API-backed (public
Wikidata SPARQL endpoint, CC0 1.0) but the new runner is
offline / cache-first by default and the unified adapter is
offline / cache-only in this slice.
``cache_policy="refresh"`` / ``"no_cache"`` is NOT supported;
the readiness gate refuses both with a structured
``unsupported_cache_policy`` error.

Year semantics:

- ``years=(YYYY,)`` reads the cache file matching the first
  requested year; the transform stamps ``year=YYYY`` on every
  emitted observation with the original ``start_date`` /
  ``end_date`` qualifiers preserved on the audit-trail
  extension payload.
- ``years=None`` reads the legacy current-holders cache and
  emits one observation per binding with ``year`` taken from
  the parsed row's ``start_date`` year (or ``None`` only when
  the start date is absent).
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

from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION,
)
from ._descriptor import build_wikidata_heads_of_state_government_descriptor
from ._raw_read import read_wikidata_heads_of_state_government_cache
from ._readiness import (
    cache_policy_blocker,
    check_cache_availability,
    metadata_blocker,
    request_warnings,
    version_blocker,
)
from ._transform import emit_wikidata_heads_of_state_government_observations


class WikidataHeadsOfStateGovernmentAdapter:
    """Unified-source Wikidata heads-of-state-and-government adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is a
    class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_wikidata_heads_of_state_government_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cache. Every
        blocker names the specific missing / invalid file,
        metadata field, or cache policy so a developer can fix
        the upstream issue without reading source code.

        Four failure classes (each surfaces a structured
        :class:`SourceWarning` with ``severity='error'`` in the
        :class:`ReadinessResult.errors` tuple so the runner
        raises ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. **Metadata readiness** -- :func:`metadata_blocker`
           validates ``metadata.json`` (file presence, parseable
           JSON, canonical ``source_version`` / legacy alias
           ``version``).
        2. **Cache policy** -- :func:`cache_policy_blocker`
           blocks ``"refresh"`` / ``"no_cache"`` because the
           unified Wikidata HoS/HoG adapter never invokes the
           network in this slice.
        3. **Cache-file availability** --
           :func:`check_cache_availability` validates the per-
           ``(year, country_qids)`` JSON cache (file presence,
           JSON shape with ``results.bindings`` list) for the
           requested years.
        4. **Version** -- :func:`version_blocker` blocks
           ``request.source_version`` other than the canonical
           ``"SPARQL"`` per SRC-REQ-009.

        Two request-scoping warning classes (NOT blockers) are
        surfaced on ``ReadinessResult.warnings``: the
        ``unsupported_filter`` warning when ``leaders=`` is set
        (Wikidata is a per-binding leader-identity source with
        no leader filter at Stage 2; Stage 4 is the resolver;
        SRC-REQ-005), and the
        ``wikidata_non_qid_country_filter`` warning when
        ``countries=`` contains values that are NOT Wikidata
        QIDs (the unified adapter never invents ISO3 codes; the
        caller can switch to QIDs to opt in to evidence).
        """
        metadata_block = metadata_blocker(request)
        if metadata_block is not None:
            message, code = metadata_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code,
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
                        code=code,
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
                        code=code or "missing_raw",
                        message=blocker or (
                            "Wikidata HoS/HoG cache is not ready"
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
                            "canonical_version": (
                                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION
                            ),
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
        """Open the per-``(year, country_qids)`` JSON cache and
        return the raw bundle.

        Delegates to :func:`read_wikidata_heads_of_state_government_cache`
        in :mod:`._raw_read`. The cache is the ONLY source of
        data the unified adapter reads in this slice: the
        readiness gate has already proved the cache policy is
        supported + the metadata version is canonical + the
        explicit-year requests have complete cache. The legacy
        HTTP layer is intentionally NEVER invoked.
        """
        return read_wikidata_heads_of_state_government_cache(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the raw long-format frame into normalized observations.

        Delegates to
        :func:`emit_wikidata_heads_of_state_government_observations`
        in :mod:`._transform`. See that module's docstring for
        the year / country filter contract and the per-binding
        audit-trail extension payload contract.
        """
        return emit_wikidata_heads_of_state_government_observations(
            request, raw,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_wikidata_heads_of_state_government_adapter() -> (
    WikidataHeadsOfStateGovernmentAdapter
):
    """Return a fresh :class:`WikidataHeadsOfStateGovernmentAdapter` instance.

    The factory is the explicit seam callers use to wire
    Wikidata HoS/HoG into a :class:`SourceRegistry`. The
    package does NOT auto-register on import (the registry is
    passive by design -- see ``docs/architecture/sources.md``
    §10.1).
    """
    return WikidataHeadsOfStateGovernmentAdapter()


def register_wikidata_heads_of_state_government(
    registry: Any,
) -> WikidataHeadsOfStateGovernmentAdapter:
    """Register the Wikidata HoS/HoG adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``wikidata_heads_of_state_government`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_wikidata_heads_of_state_government_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_wikidata_heads_of_state_government_adapter()`` (preferred) or
# this module-level callable.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY = (
    create_wikidata_heads_of_state_government_adapter
)


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches missing
    ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is invoked
    at module bottom so a missing method surfaces during CI even
    when no test instantiates the adapter directly.
    """
    if not isinstance(
        WikidataHeadsOfStateGovernmentAdapter(),
        SourceAdapter,
    ):
        raise TypeError(
            "WikidataHeadsOfStateGovernmentAdapter does not "
            "satisfy the SourceAdapter Protocol; check the "
            "descriptor attribute and the check_ready / read_raw "
            "/ transform method shapes."
        )


_ensure_protocol_conformance()


# Reference the warning-code constants so the static analyzer
# keeps them live for any future import-side warning-builder
# hooks. The codes themselves are re-exported from
# :mod:`._readiness`.
_ = (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH,
)


__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY",
    "WikidataHeadsOfStateGovernmentAdapter",
    "create_wikidata_heads_of_state_government_adapter",
    "register_wikidata_heads_of_state_government",
]
