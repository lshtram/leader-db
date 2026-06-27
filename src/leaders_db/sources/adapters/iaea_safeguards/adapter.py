"""Clean IAEA Safeguards status-list source adapter.

This module owns the :class:`IaeaSafeguardsAdapter` -- the
unified-source implementation of the IAEA Safeguards
status-list adapter under the clean ``leaders_db.sources``
interface.

The unified IAEA Safeguards adapter is offline / cache-first
in this slice. It reads a single cached status-list PDF plus a
runtime-local ``metadata.json`` (gitignored per Always-On Rule
#9). Live fetch is intentionally NOT supported (the task brief:
"Do NOT implement live download/scraping. Keep scope modest").
The readiness gate blocks ``cache_policy="refresh"`` /
``"no_cache"`` with a structured
``iaea_safeguards_unsupported_cache_policy`` error BEFORE
``read_raw`` / ``transform`` are called.

The adapter implements the full ``SourceAdapter`` Protocol
(:class:`leaders_db.sources.contracts.SourceAdapter`):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  IAEA Safeguards (source_id ``iaea_safeguards``, default
  version
  ``"IAEA Safeguards Status List, status as of 2025-12-31"``,
  attribution_key ``iaea_safeguards``, ``document`` source
  type, single-year 2025 coverage hint, single observation
  family ``nuclear_safeguards_status_country``,
  ``requires_network=False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` + cached PDF BEFORE the reader opens the
  PDF; every blocker names the specific missing / invalid
  field or file. Source-version requests other than the
  canonical stamp fail readiness with a structured
  ``iaea_safeguards_metadata_version_mismatch`` /
  ``unsupported_version`` error per SRC-REQ-009.
- ``read_raw(request)`` -- opens the cached PDF via
  ``pdfplumber``, tries the table-extraction path first then
  falls back to text extraction, validates the header against
  the 5 canonical required columns, and returns a
  :class:`RawReadResult` carrying the parsed frame plus a
  :class:`RawAsset` record (path, source URL, SHA-256).
- ``transform(request, raw)`` -- emits one observation per
  cached country row + source-native indicator (4 indicators per row;
  preserves the source-native country display name and cell
  labels verbatim; does NOT invent ISO3 codes), and applies
  the documented request-scoping filters (``countries=`` /
  ``years=``).

Request-scoping
---------------

``SourceIngestRequest.years`` filters the readiness envelope
on the descriptor's 2025 single-year envelope; out-of-coverage
years (e.g. ``years=(2023,)`` -- the prototype's target year)
emit zero observations AND a structured ``YEAR_ABSENT``
warning (no stale-proxy fill per SRC-COV-002 / SRC-COV-003).
``countries=`` filters the parsed row-level frame on the
transform side by source-native case-folded substring match.
``leaders`` is unsupported for a country-level safeguards
status source and surfaces a structured
``UNSUPPORTED_FILTER`` warning (SRC-REQ-005). ``source_version``
other than the canonical stamp is unsupported and fails
readiness with a structured ``unsupported_version`` error
(SRC-REQ-009). ``cache_policy`` other than ``"offline_only"``
/ ``"prefer_cache"`` fails readiness with a structured
``iaea_safeguards_unsupported_cache_policy`` error.

Year semantics
--------------

The IAEA Safeguards Status List covers a single-point legal
/status snapshot (the canonical probed stamp is "as of 31
December 2025"). A request for an out-of-coverage year (e.g.
``years=(2023,)`` -- the prototype's target year -- falls
outside the envelope) emits zero observations AND a structured
``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003).

Important caveat
----------------

The IAEA Safeguards Status List captures safeguards legal /
status evidence -- the source-native safeguards agreement
status, INFCIRC reference, Additional Protocol status, and
Small Quantities Protocol status -- and is NOT a direct
nuclear-weapons score or proof of safeguards compliance /
non-compliance by itself. Downstream scorers MUST NOT
silently treat a ``"not in force"`` AP cell as proof of
non-cooperation; the descriptor's ``coverage_hint.notes``
carries the explicit caveat and the Stage 11 confidence
formula penalises the temporal-fit gap between the cached
status date and the prototype's target year.
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
    IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY,
    IAEA_SAFEGUARDS_PDF_NAME,
)
from ._descriptor import build_iaea_safeguards_descriptor
from ._raw_read import read_iaea_safeguards_pdf
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_iaea_safeguards_observations


class IaeaSafeguardsAdapter:
    """Unified-source IAEA Safeguards status-list adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is
    a class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_iaea_safeguards_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cached PDF.
        Four failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so the
        runner raises ``RuntimeError`` before calling
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates the
           bundle's ``metadata.json`` + cached PDF (file
           presence, required fields, canonical metadata
           ``source_version``, ``local_files`` annotation,
           ``ingestion_status='downloaded'``, checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical
           ``"IAEA Safeguards Status List, status as of 2025-12-31"``
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
                            or "IAEA Safeguards bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "pdf_name": IAEA_SAFEGUARDS_PDF_NAME,
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
        """Open the staged IAEA Safeguards cached PDF and return
        the parsed raw payload.

        Delegates to :func:`read_iaea_safeguards_pdf` in
        :mod:`._raw_read`. The reader tries the table-extraction
        path first then falls back to text extraction, validates
        the parsed header against the 5 canonical required
        columns and propagates the parsed frame on
        ``payload["rows"]`` plus the original ``header`` list
        plus the parsed ``page_number`` / ``parse_path`` for
        the transform layer. A missing-required-column fires a
        :class:`IaeaSafeguardsSchemaError` BEFORE the transform
        layer consumes the frame so the runner propagates a
        structured schema-violation error.
        """
        return read_iaea_safeguards_pdf(request)

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
        substring match against the source-native state display
        name). ``request.leaders`` is unsupported for a
        country-level safeguards status source and surfaces a
        structured ``UNSUPPORTED_FILTER`` warning
        (SRC-REQ-005).

        Emits up to 5 observations per cached country row --
        one per catalog indicator -- under the
        ``nuclear_safeguards_status_country`` family. The
        source-native state display name is preserved verbatim
        on every emitted observation's
        ``extension["iaea_safeguards_state"]`` field; the
        adapter does NOT invent ISO3 codes
        (``country_code`` / ``leader_id`` / ``leader_name``
        remain ``None`` until later matching / resolution
        stages introduce a canonical ISO3 mapping).
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "IaeaSafeguardsAdapter.transform: raw.payload "
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
                else "iaea_safeguards:sg-agreements-comprehensive-status.pdf"
            )

        return emit_iaea_safeguards_observations(
            request,
            rows,
            cache_path=cache_path,
            asset_id=asset_id,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_iaea_safeguards_adapter() -> IaeaSafeguardsAdapter:
    """Return a fresh :class:`IaeaSafeguardsAdapter` instance.

    The factory is the explicit seam callers use to wire IAEA
    Safeguards into a :class:`SourceRegistry`. The package does
    NOT auto-register on import (the registry is passive by
    design -- see ``docs/architecture/sources.md`` §10.1).
    """
    return IaeaSafeguardsAdapter()


def register_iaea_safeguards(
    registry: Any,
) -> IaeaSafeguardsAdapter:
    """Register the IAEA Safeguards adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``iaea_safeguards`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_iaea_safeguards_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_iaea_safeguards_adapter()`` (preferred) or this
# module-level callable.
IAEA_SAFEGUARDS_ADAPTER_FACTORY = create_iaea_safeguards_adapter


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
    if not isinstance(IaeaSafeguardsAdapter(), SourceAdapter):
        raise TypeError(
            "IaeaSafeguardsAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor "
            "attribute and the check_ready / read_raw / "
            "transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "IAEA_SAFEGUARDS_ADAPTER_FACTORY",
    "IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY",
    "IaeaSafeguardsAdapter",
    "create_iaea_safeguards_adapter",
    "register_iaea_safeguards",
]
