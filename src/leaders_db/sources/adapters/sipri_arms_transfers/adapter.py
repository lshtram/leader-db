"""Clean SIPRI Arms Transfers Database source adapter.

This module owns the :class:`SipriArmsTransfersAdapter` -- the
unified-source implementation of the SIPRI Arms Transfers
adapter under the clean ``leaders_db.sources`` interface.

The unified SIPRI Arms Transfers adapter is offline /
cache-only in this slice. It reads the staged cached export
(the canonical ``trade_register.csv`` file or the canonical
``trade_register.json`` base64-JSON wrapper) from
``data/raw/sipri_arms_transfers/`` plus a runtime-local
``metadata.json`` (gitignored per Always-On Rule #9). Live
fetch is intentionally NOT supported (the task brief: "If
implementing live fetch would be ambiguous, leave live fetch
unsupported with structured readiness error and implement
cached JSON/CSV ingestion only"). The readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``sipri_arms_transfers_unsupported_cache_policy`` error BEFORE
``read_raw`` / ``transform`` are called.

The adapter implements the full ``SourceAdapter`` Protocol
(:class:`leaders_db.sources.contracts.SourceAdapter`):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  SIPRI Arms Transfers (source_id ``sipri_arms_transfers``,
  default version
  ``"SIPRI Arms Transfers Trade Register 2026-03-09 (data 1950-2025)"``,
  attribution_key ``sipri_arms_transfers``, API source type,
  1950-2025 coverage hint, BOTH observation families
  ``arms_transfer_register_row`` +
  ``arms_transfer_country_year_aggregate``, requires_network
  ``False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` + cached CSV / JSON file BEFORE the
  reader opens the cache; every blocker names the specific
  missing / invalid field or file. Source-version requests
  other than the canonical stamp fail readiness with a
  structured
  ``sipri_arms_transfers_metadata_version_mismatch`` /
  ``unsupported_version`` error per SRC-REQ-009.
- ``read_raw(request)`` -- loads the cached CSV (CSV shape
  preferred; falls back to base64-JSON wrapper), splits the
  preamble / data lines, parses the data lines via the Python
  ``csv`` module, validates the header against the 8 canonical
  required columns, and returns a :class:`RawReadResult`
  carrying the parsed frame plus a :class:`RawAsset` record
  (path, source URL).
- ``transform(request, raw)`` -- pivots the parsed
  row-level frame to the canonical per-row register
  observations (one observation per ``(row, indicator)`` pair
  under the ``arms_transfer_register_row`` family) plus the
  deterministic per-``(role, country, year)`` aggregate
  observations under the
  ``arms_transfer_country_year_aggregate`` family; applies
  the documented coercion matrix (numeric / non-numeric /
  missing) and emits :class:`NormalizedObservation` records
  with raw + transform locators, attribution text (Rule #15),
  and structured warnings (out-of-coverage years, unsupported
  leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` filter the
parsed row-level frame on the transform side (the readiness
gate surfaces a structured ``YEAR_ABSENT`` warning on
out-of-coverage year requests). ``leaders`` is unsupported
for a country-country (supplier-recipient) flow source and
surfaces a structured ``UNSUPPORTED_FILTER`` warning
(SRC-REQ-005). ``source_version`` other than the canonical
stamp is unsupported and fails readiness with a structured
``unsupported_version`` error (SRC-REQ-009).
``cache_policy`` other than ``"offline_only"`` /
``"prefer_cache"`` fails readiness with a structured
``sipri_arms_transfers_unsupported_cache_policy`` error.

Year semantics
--------------

SIPRI Arms Transfers covers 1950-2025 per the canonical
attribution block in ``docs/sources/attributions.md``
``sipri_arms_transfers`` section. A request for an
out-of-coverage year (e.g. ``years=(2026,)`` -- one year past
the latest SIPRI update) emits zero observations AND a
structured ``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003). The prototype's target year 2023
falls WITHIN the canonical envelope (1950-2025) so 2023 is
in-coverage.

Important caveat
----------------

SIPRI Arms Transfers data is evidence of recorded arms flows
between supplier / recipient countries and is NOT direct
proof of aggression, proxy sponsorship, or illegality.
Downstream scorers MUST NOT silently treat arms-transfer TIV
totals as a proxy for aggression / responsibility without an
explicit secondary-source corroboration step (UCDP external
support, sanctions records, expert-panel reports, manual
evidence). The descriptor's ``coverage_hint.notes`` carries
the explicit caveat.
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

from ._descriptor import build_sipri_arms_transfers_descriptor
from ._raw_read import read_sipri_arms_transfers_csv
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_sipri_arms_transfers_observations


class SipriArmsTransfersAdapter:
    """Unified-source SIPRI Arms Transfers Database adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is
    a class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_sipri_arms_transfers_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cached CSV /
        JSON. Four failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so the
        runner raises ``RuntimeError`` before calling
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates the
           bundle's ``metadata.json`` + cached CSV / JSON
           (file presence, required fields, canonical metadata
           ``source_version``, ``local_files`` annotation,
           ``ingestion_status='downloaded'``, checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical
           ``"SIPRI Arms Transfers Trade Register 2026-03-09 (data 1950-2025)"``
           stamp (SRC-REQ-009).
        3. Cache-policy gate --
           :func:`check_cache_policy` blocks when
           ``request.cache_policy`` is ``"refresh"`` /
           ``"no_cache"`` (the unified adapter is offline /
           cache-only in this slice; live fetch is intentionally
           NOT supported).
        4. (Request-scoping warnings, NOT blockers) --
           out-of-coverage years and unsupported leader filters
           are surfaced on ``ReadinessResult.warnings``
           (advisory; the runner still proceeds).
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
                            or "SIPRI Arms Transfers bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={},
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
        # runner refuses to dispatch ``read_raw`` / ``transform``
        # rather than silently surfacing an HTTP-fetched
        # payload.
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
        """Open the staged cached CSV / JSON bundle and return
        the parsed raw payload.

        Delegates to :func:`read_sipri_arms_transfers_csv` in
        :mod:`._raw_read`. The reader splits the cached text
        into preamble / data lines, parses the data lines via
        the Python ``csv`` module, validates the header against
        the 8 canonical required columns, and propagates the
        parsed frame on ``payload["rows"]`` plus the original
        ``header`` list plus the ``preamble_lines`` for the
        transform layer. A missing-required-column fires a
        :class:`SipriArmsTransfersSchemaError` BEFORE the
        transform layer consumes the frame so the runner
        propagates a structured schema-violation error.
        """
        return read_sipri_arms_transfers_csv(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the parsed raw frame into
        :class:`NormalizedObservation` records.

        Honors ``request.years`` and ``request.countries`` by
        filtering the parsed row-level frame on the transform
        side (the readiness envelope surfaces a structured
        ``YEAR_ABSENT`` warning on out-of-coverage year
        requests). ``request.leaders`` is unsupported for a
        country-country flow source and surfaces a structured
        ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
        Out-of-coverage years emit zero rows plus a structured
        ``YEAR_ABSENT`` warning per offending year
        (SRC-COV-002 / SRC-COV-003: no stale-proxy fill).

        Emits BOTH ``arms_transfer_register_row`` observations
        (one per cached transfer row, per indicator) AND
        ``arms_transfer_country_year_aggregate`` observations
        (deterministic per-``(role, country, year)`` sum of TIV
        delivered).
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "SipriArmsTransfersAdapter.transform: raw.payload "
                "must be a dict carrying the parsed frame under "
                "'rows'."
            )
        rows = raw.payload.get("rows")
        if not isinstance(rows, list):
            rows = []
        preamble_lines = raw.payload.get("preamble_lines")
        if not isinstance(preamble_lines, list):
            preamble_lines = []
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
                else "sipri_arms_transfers:trade_register.csv"
            )

        return emit_sipri_arms_transfers_observations(
            request,
            rows,
            cache_path=cache_path,
            asset_id=asset_id,
            preamble_lines=preamble_lines,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_sipri_arms_transfers_adapter() -> SipriArmsTransfersAdapter:
    """Return a fresh :class:`SipriArmsTransfersAdapter` instance.

    The factory is the explicit seam callers use to wire SIPRI
    Arms Transfers into a :class:`SourceRegistry`. The package
    does NOT auto-register on import (the registry is passive
    by design -- see ``docs/architecture/sources.md`` §10.1).
    """
    return SipriArmsTransfersAdapter()


def register_sipri_arms_transfers(
    registry: Any,
) -> SipriArmsTransfersAdapter:
    """Register the SIPRI Arms Transfers adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``sipri_arms_transfers`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_sipri_arms_transfers_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_sipri_arms_transfers_adapter()`` (preferred) or this
# module-level callable.
SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY = create_sipri_arms_transfers_adapter


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
    if not isinstance(SipriArmsTransfersAdapter(), SourceAdapter):
        raise TypeError(
            "SipriArmsTransfersAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor "
            "attribute and the check_ready / read_raw / "
            "transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "SIPRI_ARMS_TRANSFERS_ADAPTER_FACTORY",
    "SipriArmsTransfersAdapter",
    "create_sipri_arms_transfers_adapter",
    "register_sipri_arms_transfers",
]
