"""Clean CTBTO Treaty Status source adapter.

This module owns the :class:`CtbtoTreatyStatusAdapter` -- the
unified-source implementation of the CTBTO States Signatories
adapter under the clean ``leaders_db.sources`` interface.

The unified CTBTO Treaty Status adapter is offline /
cache-first in this slice. It reads a staged cached export
(the canonical ``states-signatories.csv`` file OR the
canonical ``states-signatories.html`` fallback) from
``data/raw/ctbto_treaty_status/`` plus a runtime-local
``metadata.json`` (gitignored per Always-On Rule #9). Live
fetch is intentionally NOT supported (the task brief:
"Build an offline/cache-first adapter. Do NOT implement live
download/scraping"). The readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a
structured ``ctbto_treaty_status_unsupported_cache_policy``
error BEFORE ``read_raw`` / ``transform`` are called.

The adapter implements the full ``SourceAdapter`` Protocol
(:class:`leaders_db.sources.contracts.SourceAdapter`):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for CTBTO Treaty Status (source_id ``ctbto_treaty_status``,
  default version
  ``"CTBTO States Signatories, status as of 2024-03-13"``,
  attribution_key ``ctbto_treaty_status``, ``document``
  source type, single-year 2024 coverage hint, single
  observation family ``nuclear_treaty_status_country``,
  ``requires_network=False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` + cached CSV / HTML file BEFORE the
  reader opens the cache; every blocker names the specific
  missing / invalid field or file. Source-version requests
  other than the canonical stamp fail readiness with a
  structured
  ``ctbto_treaty_status_metadata_version_mismatch`` /
  ``unsupported_version`` error per SRC-REQ-009.
- ``read_raw(request)`` -- loads the cached CSV (CSV shape
  preferred; falls back to the HTML shape), parses the
  cached text via the Python ``csv`` module (CSV shape) or a
  built-in HTML table parser (HTML shape), validates the
  header against the 4 canonical required columns, and
  returns a :class:`RawReadResult` carrying the parsed frame
  plus a :class:`RawAsset` record (path, source URL,
  SHA-256).
- ``transform(request, raw)`` -- emits one observation per
  cached State row + source-derived status indicator (2
  per-row indicators by default + an OPTIONAL 3rd Annex 2
  indicator when the cached fixture / source-native data
  carries an explicit Annex 2 flag column), preserves the
  source-native State display name verbatim (no ISO3
  invention), preserves the raw signature / ratification
  date cells verbatim as strings on the audit-trail
  extension (no numeric-year coercion that could mislead
  Stage 11 confidence calculations), and applies the
  documented request-scoping filters (``countries=`` /
  ``years=``).

Request-scoping
---------------

``SourceIngestRequest.years`` filters the readiness
envelope on the descriptor's 2024 single-year envelope;
out-of-coverage years (e.g. ``years=(2023,)`` -- the
prototype's target year) emit zero observations AND a
structured ``YEAR_ABSENT`` warning (no stale-proxy fill per
SRC-COV-002 / SRC-COV-003). ``countries=`` filters the
parsed row-level frame on the transform side by
source-native case-folded substring match. ``leaders`` is
unsupported for a country-level treaty-status source and
surfaces a structured ``UNSUPPORTED_FILTER`` warning
(SRC-REQ-005). ``source_version`` other than the canonical
stamp is unsupported and fails readiness with a structured
``unsupported_version`` error (SRC-REQ-009).
``cache_policy`` other than ``"offline_only"`` /
``"prefer_cache"`` fails readiness with a structured
``ctbto_treaty_status_unsupported_cache_policy`` error.

Year semantics
--------------

The CTBTO States Signatories page covers a single-point
treaty-status snapshot (the canonical probed stamp is
"status as of 13 March 2024"). A request for an
out-of-coverage year (e.g. ``years=(2023,)`` -- the
prototype's target year -- falls outside the envelope)
emits zero observations AND a structured ``YEAR_ABSENT``
warning -- no stale-proxy fill (SRC-COV-002 / SRC-COV-003).

Important caveat
----------------

CTBTO signature / ratification status is a TREATY-STATUS
observation -- the source-derived signature status
(``"signed"`` iff a signature date is present in the
cached row, ``"not_signed"`` otherwise) and the source-
derived ratification status (``"ratified"`` iff a
ratification date is present in the cached row,
``"not_ratified"`` otherwise) -- and is NOT direct proof
of nuclear behaviour, compliance, or non-compliance.
Downstream scorers MUST NOT silently treat an unsigned /
unratified status cell as proof of nuclear activity or
non-cooperation; the descriptor's ``coverage_hint.notes``
carries the explicit caveat and the Stage 11 confidence
formula penalises the temporal-fit gap between the cached
snapshot date and the prototype's target year (2023).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
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

from ._constants import (
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY,
)
from ._descriptor import build_ctbto_treaty_status_descriptor
from ._raw_read import read_ctbto_treaty_status_cache
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_ctbto_treaty_status_observations


class CtbtoTreatyStatusAdapter:
    """Unified-source CTBTO Treaty Status adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is
    a class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_ctbto_treaty_status_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cached CSV /
        HTML file. Four failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so the
        runner raises ``RuntimeError`` before calling
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates the
           bundle's ``metadata.json`` + cached CSV / HTML
           file (file presence, required fields, canonical
           metadata ``source_version``, ``local_files``
           annotation, ``ingestion_status='downloaded'``,
           checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical
           ``"CTBTO States Signatories, status as of 2024-03-13"``
           stamp (SRC-REQ-009).
        3. Cache-policy gate --
           :func:`check_cache_policy` blocks when
           ``request.cache_policy`` is ``"refresh"`` /
           ``"no_cache"`` (the unified adapter is offline /
           cache-only in this slice; live fetch is intentionally
           NOT supported).
        4. (Request-scoping warnings, NOT blockers) --
           out-of-coverage years and unsupported leader
           filters are surfaced on
           ``ReadinessResult.warnings`` (advisory; the runner
           still proceeds).
        """
        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match).
        ready, blocker, code = check_metadata_well_formed(request)
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "CTBTO Treaty Status bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "csv_name": CTBTO_TREATY_STATUS_CSV_NAME,
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009). An
        # unsupported ``source_version`` is a hard readiness
        # blocker so the runner refuses to dispatch
        # ``read_raw`` / ``transform``; this prevents the
        # bundle metadata from being silently overridden by an
        # unsupported version stamp.
        version_blocker = check_source_version(request)
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
                            "requested_version": (
                                request.source_version
                            ),
                        },
                    ),
                ),
            )

        # Phase C: cache-policy gate. ``"refresh"`` /
        # ``"no_cache"`` are unsupported in this slice; the
        # runner refuses to dispatch ``read_raw`` /
        # ``transform`` rather than silently surfacing an
        # HTTP-fetched payload.
        cache_policy_blocker = check_cache_policy(request)
        if cache_policy_blocker is not None:
            message, code_str = cache_policy_blocker
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code_str,
                        message=message,
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "cache_policy": request.cache_policy,
                        },
                    ),
                ),
            )

        # Phase D: request-scoping warnings (advisory only).
        warnings = list(collect_request_scoping_warnings(request))

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged cached CSV / HTML bundle and return
        the parsed raw payload.

        Delegates to :func:`read_ctbto_treaty_status_cache` in
        :mod:`._raw_read`. The reader loads the cached CSV
        (CSV shape preferred; falls back to the HTML shape),
        parses the cached text via the Python ``csv`` module
        (CSV shape) or a built-in HTML table parser (HTML
        shape), validates the parsed header against the 4
        canonical required columns, and propagates the parsed
        frame on ``payload["rows"]`` plus the original
        ``header`` list for the transform layer. A
        missing-required-column fires a
        :class:`CtbtoTreatyStatusSchemaError` BEFORE the
        transform layer consumes the frame so the runner
        propagates a structured schema-violation error.
        """
        return read_ctbto_treaty_status_cache(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the parsed raw frame into
        :class:`NormalizedObservation` records.

        Honors ``request.years`` (no stale-proxy fill -- the
        readiness envelope surfaces a structured
        ``YEAR_ABSENT`` warning on out-of-coverage year
        requests) and ``request.countries`` (case-folded
        substring match against the source-native State
        display name). ``request.leaders`` is unsupported
        for a country-level treaty-status source and surfaces
        a structured ``UNSUPPORTED_FILTER`` warning
        (SRC-REQ-005).

        Emits 2 observations per cached State row by default
        (signature status + ratification status under the
        ``nuclear_treaty_status_country`` family). When the
        cached fixture / source-native data carries an
        explicit ``Annex 2`` flag column, the transform emits
        an OPTIONAL 3rd Annex 2 observation per row, but the
        default 2-indicator catalog does NOT include the
        Annex 2 indicator -- the adapter never invents an
        Annex 2 flag from missing source-native data.

        The source-native State display name is preserved
        verbatim on every emitted observation's
        ``extension["ctbto_treaty_status_state"]`` field; the
        adapter does NOT invent ISO3 codes
        (``country_code`` / ``leader_id`` / ``leader_name``
        remain ``None`` until later matching / resolution
        stages introduce a canonical ISO3 mapping). Raw
        signature / ratification date cells are preserved
        verbatim as strings on the audit-trail extension
        payload (no numeric-year coercion that could mislead
        Stage 11 confidence calculations).
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "CtbtoTreatyStatusAdapter.transform: raw.payload "
                "must be a dict carrying the parsed frame under "
                "'rows'."
            )
        rows = raw.payload.get("rows")
        if not isinstance(rows, list):
            rows = []
        cache_path_value = raw.payload.get("cache_path")
        cache_path = (
            cache_path_value
            if isinstance(cache_path_value, Path)
            else None
        )
        asset_id = raw.payload.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            asset_id = (
                raw.assets[0].asset_id
                if raw.assets
                else "ctbto_treaty_status:states-signatories.csv"
            )

        return emit_ctbto_treaty_status_observations(
            request,
            rows,
            cache_path=cache_path,
            asset_id=asset_id,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_ctbto_treaty_status_adapter() -> CtbtoTreatyStatusAdapter:
    """Return a fresh :class:`CtbtoTreatyStatusAdapter` instance.

    The factory is the explicit seam callers use to wire CTBTO
    Treaty Status into a :class:`SourceRegistry`. The package
    does NOT auto-register on import (the registry is passive
    by design -- see ``docs/architecture/sources.md`` §10.1).
    """
    return CtbtoTreatyStatusAdapter()


def register_ctbto_treaty_status(
    registry: Any,
) -> CtbtoTreatyStatusAdapter:
    """Register the CTBTO Treaty Status adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``ctbto_treaty_status`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_ctbto_treaty_status_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_ctbto_treaty_status_adapter()`` (preferred) or this
# module-level callable.
CTBTO_TREATY_STATUS_ADAPTER_FACTORY = (
    create_ctbto_treaty_status_adapter
)


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
    if not isinstance(CtbtoTreatyStatusAdapter(), SourceAdapter):
        raise TypeError(
            "CtbtoTreatyStatusAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor "
            "attribute and the check_ready / read_raw / "
            "transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "CTBTO_TREATY_STATUS_ADAPTER_FACTORY",
    "CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY",
    "CtbtoTreatyStatusAdapter",
    "create_ctbto_treaty_status_adapter",
    "register_ctbto_treaty_status",
]
