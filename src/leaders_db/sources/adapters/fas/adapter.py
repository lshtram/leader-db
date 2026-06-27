"""Clean FAS Nuclear Notebook source adapter.

This module provides the :class:`FasAdapter` -- the next source
rebuilt under the clean ``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 18,
``docs/requirements/sources.md`` §12 SRC-MIG-005), after PWT,
Maddison, WDI, WGI, V-Dem, UCDP, Transparency CPI, PTS, RSF, BTI,
Freedom House, Archigos, REIGN, SIPRI Milex, SIPRI Yearbook Ch.7,
CIRIGHTS, UNDP HDI, and WHO GHO API.

The adapter wraps the existing legacy parser
(:func:`leaders_db.ingest.fas_html.read_fas_status_html`) via lazy
imports so the canonical Stage 2 parsing logic is reused without
duplication (SRC-MIG-002: do not delete existing prototype
capabilities). The legacy package is imported lazily inside adapter
methods only so the ``leaders_db.sources`` package boundary
documented in ``docs/architecture/sources.md`` §10.1 is preserved;
the package import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(``docs/architecture/sources.md`` §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for FAS (source_id ``fas``, default version
  ``"consolidated status table"``, attribution_key ``fas``,
  ``source_type="document"``, ``requires_network=False``, 2014
  snapshot coverage hint, single observation family
  ``nuclear_country_year``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND the staged HTML cache BEFORE the reader
  opens the cache; every blocker names the specific missing /
  invalid file or policy. The gate accepts BOTH the canonical
  primary metadata shape (``source_version`` / ``local_files`` /
  ``checksum_sha256``) AND the staged FAS legacy shape
  (``source_version`` / ``local_files`` / ``checksum_sha256`` /
  ``caveats`` / ``coverage`` / ``years_available``) so the
  existing staged bundle does not need to be rewritten as part
  of the migration. The gate also blocks
  ``cache_policy="refresh"`` / ``"no_cache"`` because the
  unified FAS adapter never invokes the network in this slice.
- ``read_raw(request)`` -- opens the staged local HTML cache via
  the legacy wide-format parser and returns a
  :class:`RawReadResult` carrying the wide DataFrame + per-spec
  raw-value lookup + parsed snapshot year + per-file
  :class:`RawAsset` record.
- ``transform(request, raw)`` -- applies the request
  countries filter and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (unsupported leader
  filter + year filter / temporal-fit gap).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
parser's per-snapshot-year output. The country filter is an exact
case-insensitive match against the FAS source-native country
display name (FAS does NOT carry ISO3 codes; the clean adapter
never invents ISO3). ``request.leaders`` is unsupported for a
country-year nuclear source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
``request.source_version`` other than the canonical
``"consolidated status table"`` is unsupported and fails readiness
with a structured ``unsupported_version`` error per SRC-REQ-009.

Snapshot-year / temporal-fit semantics
--------------------------------------

FAS is a single-snapshot source. The clean adapter parses the
snapshot year from the page's ``<meta name="date">`` element
(falling back to the footer "Current update" text and finally the
default ``2014``). The snapshot year is recorded on every
observation's ``year`` field AND ``extension.snapshot_year``
field. A requested 2023 with a 2014 snapshot emits the 2014 rows
labeled with the snapshot year (no silent relabeling) and tags
every observation with ``extension.requested_year=2023`` +
``proxy_snapshot_semantics`` audit metadata so downstream audit
code can detect the temporal-fit gap without relying on
silently-overwritten values. The readiness envelope surfaces a
structured ``YEAR_ABSENT`` warning on the request so the caller
can branch on the gap. A requested ``years=(2014,)`` (the
canonical snapshot year) emits no year warning.

Cache-policy semantics
----------------------

The FAS unified adapter is local-file only
(``requires_network=False``, no HTTP layer in the new package).
The runner NEVER invokes the network. ``cache_policy="refresh"``
/ ``"no_cache"`` is NOT supported by the unified FAS adapter in
this slice: it fails readiness with a structured
``unsupported_cache_policy`` error. Use
``cache_policy="offline_only"`` (the documented safe default) /
``"prefer_cache"`` and stage the canonical HTML cache at
``<raw_root>/fas/fas_status.html``.
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

from ._descriptor import build_fas_descriptor
from ._raw_read import read_fas_html
from ._readiness import (
    cache_policy_blocker,
    file_blocker,
    metadata_blocker,
    request_warnings,
    version_blocker,
)
from ._transform import emit_fas_observations


class FasAdapter:
    """Unified-source FAS Nuclear Notebook adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is a
    class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = build_fas_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cache. Every
        blocker names the specific missing / invalid file, metadata
        field, or cache policy so a developer can fix the upstream
        issue without reading source code.

        Five failure classes (each surfaces a structured
        :class:`SourceWarning` with ``severity='error'`` in the
        :class:`ReadinessResult.errors` tuple so the runner raises
        ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. **Metadata readiness** -- :func:`metadata_blocker`
           validates ``metadata.json`` (file presence, parseable
           JSON, canonical ``source_version``, optional
           ``local_files`` list).
        2. **File readiness** -- :func:`file_blocker` validates
           the staged ``fas_status.html`` (file presence,
           SHA-256 checksum against the metadata field when
           present).
        3. **Cache policy** -- :func:`cache_policy_blocker`
           blocks ``"refresh"`` / ``"no_cache"`` because the
           unified FAS adapter never invokes the network in
           this slice.
        4. **Version** -- :func:`version_blocker` blocks
           ``request.source_version`` other than the canonical
           ``"consolidated status table"`` per SRC-REQ-009.

        Two request-scoping warning classes (NOT blockers) are
        surfaced on ``ReadinessResult.warnings``: the
        ``unsupported_filter`` warning when ``leaders=`` is set
        (FAS is country-year nuclear evidence with no leader
        dimension; SRC-REQ-005), and the ``year_absent`` warning
        per requested year that does NOT match the snapshot
        year (FAS is a single-snapshot source so out-of-snapshot
        requests trigger the temporal-fit gap audit metadata per
        SRC-COV-002 / SRC-COV-003).
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

        file_block = file_blocker(request)
        if file_block is not None:
            message, code = file_block
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

        version_block = version_blocker(request)
        if version_block is not None:
            message, code = version_block
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "requested_version": request.source_version,
                            "canonical_version": "consolidated status table",
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
        """Open the staged HTML cache and return the raw bundle.

        Delegates to :func:`read_fas_html` in :mod:`._raw_read`. The
        staged HTML is the ONLY source of data the unified adapter
        reads in this slice: the readiness gate has already proved
        the cache policy is supported + the HTML cache is staged +
        the optional SHA-256 checksum matches + the metadata
        ``source_version`` is canonical. The legacy HTTP layer is
        intentionally never invoked.
        """
        return read_fas_html(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the raw wide-format frame into normalized observations.

        Delegates to :func:`emit_fas_observations` in
        :mod:`._transform`. See that module's docstring for the
        year / country filter contract and the snapshot-year /
        proxy audit metadata contract.
        """
        return emit_fas_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_fas_adapter() -> FasAdapter:
    """Return a fresh :class:`FasAdapter` instance.

    The factory is the explicit seam callers use to wire FAS into a
    :class:`SourceRegistry`. The package does NOT auto-register on
    import (the registry is passive by design -- see
    ``docs/architecture/sources.md`` §10.1).
    """
    return FasAdapter()


def register_fas(registry: Any) -> FasAdapter:
    """Register the FAS adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``fas`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_fas_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_fas_adapter()`` (preferred) or this module-level
# callable.
FAS_ADAPTER_FACTORY = create_fas_adapter


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
    if not isinstance(FasAdapter(), SourceAdapter):
        raise TypeError(
            "FasAdapter does not satisfy the SourceAdapter Protocol; "
            "check the descriptor attribute and the check_ready / "
            "read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "FAS_ADAPTER_FACTORY",
    "FasAdapter",
    "create_fas_adapter",
    "register_fas",
]
