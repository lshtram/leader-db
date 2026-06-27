"""Clean Wikipedia Action API (search + extract) source adapter.

This module provides the :class:`WikipediaSearchExtractAdapter` --
the next source rebuilt under the clean ``leaders_db.sources``
interface (``docs/architecture/sources.md`` §7.1 priority 20,
``docs/requirements/sources.md`` §12 SRC-MIG-006), after PWT,
Maddison Project, World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency CPI, PTS, RSF, BTI, Freedom House, Archigos, REIGN,
SIPRI Milex, SIPRI Yearbook Ch.7, CIRIGHTS, UNDP HDI, WHO GHO API,
FAS, and Wikidata WikiProject heads-of-state-and-government.

The adapter wraps the existing legacy parsers
(:func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`,
:func:`leaders_db.ingest.wikipedia_search_extract_parse.parse_extracts_response`,
:func:`leaders_db.ingest.wikipedia_search_extract_parse.parse_search_response`)
via lazy imports so the canonical Stage 2 parsing logic is reused
without duplication (SRC-MIG-002). The legacy package is imported
lazily inside adapter methods only so the ``leaders_db.sources``
package boundary documented in ``docs/architecture/sources.md`` §10.1
is preserved; the package import does NOT pull in
``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(``docs/architecture/sources.md`` §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for the
  Wikipedia Action API (source_id ``wikipedia_search_extract``,
  default version ``"Action API"``, ``source_type="api"``,
  ``requires_network=False``, coverage hint ``None``, single
  observation family ``leader_identity_context``, Action API
  homepage URL, attribution_key ``wikipedia_search_extract``).
- ``check_ready(request)`` -- validates the explicit query list
  (``request.leaders=`` carries the query / title strings per the
  clean-slice contract) AND the per-``(query, action)`` JSON cache
  BEFORE the reader opens the cache; the gate accepts BOTH the
  canonical primary metadata shape (``source_version="Action API"``)
  AND the legacy alias (``version="Action API (no version)"``). The
  gate also blocks ``cache_policy="refresh"`` / ``"no_cache"``
  because the unified Wikipedia Action API adapter never invokes
  the network in this slice.
- ``read_raw(request)`` -- opens the per-``(query, action)`` JSON
  cache via the lazy long-format parser.
- ``transform(request, raw)`` -- emits
  :class:`NormalizedObservation` records with attribution text
  (Rule #15) + structured warnings (the ``unsupported_filter``
  warning when ``years=`` / ``countries=`` is set).

Request-scoping: ``SourceIngestRequest.leaders`` is the explicit
query-string list (the clean-slice input contract -- the helper does
NOT browse / discover); missing or empty ``leaders=`` fails readiness
with a structured ``wikipedia_search_extract_missing_queries`` error
BEFORE the reader opens the cache. ``years=`` and ``countries=`` are
unsupported filters -- the Action API responses are not
temporally-scoped and not country-coded; the readiness envelope
surfaces a structured ``UNSUPPORTED_FILTER`` warning per request
filter when set (the runner ignores the filters and still emits the
cached rows; the unified adapter never invents year / country /
leader values).

Cache-policy semantics: Wikipedia Action API is API-backed (public
Action API, CC BY-SA 4.0) but the new runner is offline /
cache-first by default and the unified adapter is offline /
cache-only in this slice. ``cache_policy="refresh"`` /
``"no_cache"`` is NOT supported; the readiness gate refuses both
with a structured ``unsupported_cache_policy`` error.
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
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION,
)
from ._descriptor import build_wikipedia_search_extract_descriptor
from ._raw_read import read_wikipedia_search_extract_cache
from ._readiness import (
    cache_policy_blocker,
    check_cache_availability,
    metadata_blocker,
    queries_blocker,
    request_warnings,
    version_blocker,
)
from ._transform import emit_wikipedia_search_extract_observations


class WikipediaSearchExtractAdapter:
    """Unified-source Wikipedia Action API (search + extract) adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is a class
    attribute so the protocol's ``descriptor: SourceDescriptor`` member
    is satisfied without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_wikipedia_search_extract_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cache. Every
        blocker names the specific missing / invalid file, metadata
        field, query, or cache policy so a developer can fix the
        upstream issue without reading source code.

        Five failure classes (each surfaces a structured
        :class:`SourceWarning` with ``severity='error'`` in the
        :class:`ReadinessResult.errors` tuple so the runner raises
        ``RuntimeError` before calling ``read_raw`` / ``transform``):

        1. **Query-presence readiness** -- :func:`queries_blocker`
           validates that ``request.leaders=`` carries at least one
           non-empty query / title string (the clean-slice input
           contract -- the helper does NOT browse / discover).
        2. **Cache policy** -- :func:`cache_policy_blocker` blocks
           ``"refresh"`` / ``"no_cache"`` because the unified
           Wikipedia Action API adapter never invokes the network
           in this slice.
        3. **Metadata readiness** -- :func:`metadata_blocker`
           validates the optional ``metadata.json`` (the staged
           metadata is optional for a cache-only bundle; when
           present, the gate accepts BOTH the canonical primary
           metadata shape ``source_version="Action API"`` AND the
           legacy alias ``version="Action API (no version)"``).
        4. **Cache-file availability** --
           :func:`check_cache_availability` validates the per-
           ``(query, action)`` JSON cache (file presence, JSON
           shape with the documented ``query.pages`` dict for
           ``extracts`` or ``query.search`` list for ``search``)
           for every requested query and every catalog action.
        5. **Version** -- :func:`version_blocker` blocks
           ``request.source_version`` other than the canonical
           ``"Action API"`` per SRC-REQ-009.

        Two request-scoping warning classes (NOT blockers) are
        surfaced on ``ReadinessResult.warnings``: the
        ``unsupported_filter`` warning when ``years=`` is set
        (Wikipedia Action API responses are not temporally
        scoped) and the ``unsupported_filter`` warning when
        ``countries=`` is set (Wikipedia Action API responses are
        not country-coded). The leader filter is NOT warned
        about -- ``request.leaders=`` is the query-string list
        for this source (the documented clean-slice contract).
        """
        queries_block = queries_blocker(request)
        if queries_block is not None:
            message, code = queries_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "raw_root": str(request.raw_root),
                        },
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

        ready, blocker, code = check_cache_availability(request)
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or "missing_raw",
                        message=blocker or (
                            "Wikipedia Action API cache is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "cache_policy": request.cache_policy,
                            "raw_root": str(request.raw_root),
                            "leaders": (
                                list(request.leaders)
                                if request.leaders else None
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
                                WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION
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
        """Open the per-``(query, action)`` JSON cache and return the raw bundle.

        Delegates to
        :func:`read_wikipedia_search_extract_cache` in
        :mod:`._raw_read`. The cache is the ONLY source of data the
        unified adapter reads in this slice: the readiness gate has
        already proved the cache policy is supported + the metadata
        version is canonical + the explicit query list is non-empty
        + every requested (query, action) cache file is present and
        well-formed. The legacy HTTP layer is intentionally NEVER
        invoked.
        """
        return read_wikipedia_search_extract_cache(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the raw long-format frame into normalized observations.

        Delegates to
        :func:`emit_wikipedia_search_extract_observations` in
        :mod:`._transform`. See that module's docstring for the
        per-row observation contract and the per-observation
        extension payload contract.
        """
        return emit_wikipedia_search_extract_observations(
            request, raw,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_wikipedia_search_extract_adapter() -> (
    WikipediaSearchExtractAdapter
):
    """Return a fresh :class:`WikipediaSearchExtractAdapter` instance.

    The factory is the explicit seam callers use to wire the
    Wikipedia Action API into a :class:`SourceRegistry`. The package
    does NOT auto-register on import (the registry is passive by
    design -- see ``docs/architecture/sources.md`` §10.1).
    """
    return WikipediaSearchExtractAdapter()


def register_wikipedia_search_extract(
    registry: Any,
) -> WikipediaSearchExtractAdapter:
    """Register the Wikipedia Action API adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``wikipedia_search_extract`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_wikipedia_search_extract_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_wikipedia_search_extract_adapter()`` (preferred) or this
# module-level callable.
WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY = (
    create_wikipedia_search_extract_adapter
)


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches missing
    ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is invoked at
    module bottom so a missing method surfaces during CI even when
    no test instantiates the adapter directly.
    """
    if not isinstance(
        WikipediaSearchExtractAdapter(),
        SourceAdapter,
    ):
        raise TypeError(
            "WikipediaSearchExtractAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor attribute "
            "and the check_ready / read_raw / transform method "
            "shapes."
        )


_ensure_protocol_conformance()


# Reference the warning-code constants so the static analyzer keeps
# them live for any future import-side warning-builder hooks. The
# codes themselves are re-exported from :mod:`._readiness`.
_ = (
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION,
)


__all__ = [
    "WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY",
    "WikipediaSearchExtractAdapter",
    "create_wikipedia_search_extract_adapter",
    "register_wikipedia_search_extract",
]
