"""Unified-source Penn World Table 10.01 adapter implementation.

This module provides the :class:`PWTAdapter` -- the first source
rebuilt under the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 1, docs/requirements/sources.md
§12 SRC-MIG-005).

The adapter intentionally wraps the existing legacy reader
(:func:`leaders_db.ingest.sources.pwt.reader.read_pwt`) and
transform (:func:`leaders_db.ingest.sources.pwt.transform.transform_pwt_long_frame`)
so the canonical PWT parsing logic is reused without duplication
(SRC-MIG-002: do not delete existing prototype capabilities). The
legacy package is imported lazily inside adapter methods only so
the ``leaders_db.sources`` package boundary documented in
docs/architecture/sources.md §10.1 is preserved; the package
import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  PWT 10.01 (source_id ``pwt``, default version ``10.01``,
  homepage URL, attribution_key ``pwt``, coverage hint
  1950-2019, observation family
  ``economic_country_year``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` and ``pwt1001.xlsx`` BEFORE the reader opens
  the workbook; every blocker names the specific missing /
  invalid field or file. Source-version requests other than
  ``10.01`` fail readiness with a structured
  ``SourceWarning(severity="error", code="unsupported_version")``
  per SRC-REQ-009, so the runner never reaches ``read_raw`` /
  ``transform`` for a mismatched version stamp.
- ``read_raw(request)`` -- opens the staged ``pwt1001.xlsx`` via
  the legacy reader and returns a :class:`RawReadResult`
  carrying the wide Data-sheet-shaped DataFrame plus a
  :class:`RawAsset` record (path, SHA-256, source URL).
- ``transform(request, raw)`` -- pivots the wide frame to the
  canonical long format via the legacy transform and emits
  :class:`NormalizedObservation` records with raw + transform
  locators, attribution text (Rule #15), and structured
  warnings (out-of-coverage years, unsupported leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
transform's ``years`` / ``country_filter`` keyword arguments
(SRC-REQ-004). ``leaders`` is unsupported for a country-year
economic source and surfaces a structured
``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
``source_version`` other than ``10.01`` is unsupported and fails
readiness with a structured ``unsupported_version`` error
(SRC-REQ-009).

Year semantics
--------------

PWT 10.01 covers 1950-2019 per the canonical attribution block
in ``docs/sources/attributions.md``. A request for an
out-of-coverage year (e.g. ``years=(2023,)``) emits zero
observations AND a structured ``YEAR_ABSENT`` warning -- no
stale-proxy fill (SRC-COV-002, SRC-COV-003).

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.pwt._readiness` and the
canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.pwt._descriptor` so this
module stays focused on the lifecycle class + registration
helpers. All three modules honor the package-isolation contract
(SRC-MIG-007) and the per-module 400-line convention.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawAsset,
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
    PWT_COVERAGE_END_YEAR,
    PWT_COVERAGE_START_YEAR,
    PWT_DEFAULT_VERSION,
    PWT_METADATA_NAME,
    PWT_OBSERVATION_FAMILY,
    PWT_SOURCE_KEY,
    PWT_SUPPORTED_FAMILIES,
    PWT_XLSX_ASSET_ID,
    PWT_XLSX_NAME,
    build_pwt_descriptor,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_pwt_observations

# ---------------------------------------------------------------------------
# Path + numeric helpers
# ---------------------------------------------------------------------------


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/pwt/`` bundle directory."""
    return Path(request.raw_root) / PWT_SOURCE_KEY


def _xlsx_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``pwt1001.xlsx`` path."""
    return _bundle_dir(request) / PWT_XLSX_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / PWT_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PWTAdapter:
    """Unified-source PWT adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a class
    attribute so the protocol's ``descriptor: SourceDescriptor``
    member is satisfied without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_pwt_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the workbook. Every
        blocker names the specific missing / invalid field or file
        so a developer can fix the upstream issue without reading
        source code.

        The gate enforces three failure classes (each surfaces a
        structured ``SourceWarning`` with ``severity='error'`` in
        the ``ReadinessResult.errors`` tuple so the runner raises
        ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. Bundle readiness -- ``check_metadata_well_formed``
           validates ``metadata.json`` + ``pwt1001.xlsx`` (file
           presence, required fields, canonical metadata
           ``source_version``, checksum match).
        2. Source-version match -- ``check_source_version`` blocks
           when ``request.source_version`` is set and differs from
           the canonical ``10.01`` (SRC-REQ-009; the legacy bundle
           has no per-version stamp beyond
           ``metadata.json['source_version']`` so silently
           propagating an unsupported version into
           ``RawAsset.version`` / ``NormalizedObservation.source_version``
           would lie to downstream scorers).
        3. (Request-scoping warnings, NOT blockers) -- out-of-
           coverage years and unsupported leader filters are
           surfaced on ``ReadinessResult.warnings`` (advisory; the
           runner still proceeds).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir, PWT_XLSX_NAME, PWT_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "PWT bundle is not ready",
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009). An
        # unsupported ``source_version`` is a hard readiness
        # blocker so the runner refuses to dispatch
        # ``read_raw`` / ``transform``; this prevents the
        # legacy bundle metadata from being silently
        # overridden by an unsupported version stamp.
        version_blocker = check_source_version(
            request,
            canonical_version=PWT_DEFAULT_VERSION,
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
                            "canonical_version": PWT_DEFAULT_VERSION,
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings (advisory only).
        warnings = list(
            collect_request_scoping_warnings(
                request,
                default_version=PWT_DEFAULT_VERSION,
                coverage_start_year=PWT_COVERAGE_START_YEAR,
                coverage_end_year=PWT_COVERAGE_END_YEAR,
            ),
        )

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged ``pwt1001.xlsx`` and return the raw bundle.

        Lazy-imports the legacy reader so the unified package
        boundary is preserved. The wide Data-sheet-shaped
        DataFrame is carried in :attr:`RawReadResult.payload`
        under ``"wide_df"`` for the transform layer.
        """
        # Lazy import: keeps ``leaders_db.sources`` importable
        # without ``leaders_db.ingest`` (docs/architecture/sources.md
        # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
        from leaders_db.ingest.sources.pwt.reader import read_pwt

        xlsx_path = _xlsx_path(request)
        wide_df = read_pwt(xlsx_path=xlsx_path)
        metadata = _read_metadata_payload(_metadata_path(request))
        expected_sha = metadata.get("checksum_sha256")
        if isinstance(expected_sha, str):
            actual_sha = hashlib.sha256(
                xlsx_path.read_bytes(),
            ).hexdigest()
            asset_checksum: str | None = (
                actual_sha if actual_sha.lower()
                == expected_sha.strip().lower()
                else None
            )
        else:
            asset_checksum = None
        asset = RawAsset(
            asset_id=PWT_XLSX_ASSET_ID,
            source_id=request.source_id,
            version=PWT_DEFAULT_VERSION,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            path=xlsx_path,
            url=metadata.get("source_url") if isinstance(
                metadata.get("source_url"), str,
            ) else None,
            checksum_sha256=asset_checksum,
            retrieved_at=None,
            immutable=True,
        )
        return RawReadResult(
            source_id=request.source_id,
            assets=(asset,),
            payload={
                "wide_df": wide_df,
                "metadata": metadata,
                "xlsx_path": xlsx_path,
            },
            warnings=(),
        )

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into :class:`NormalizedObservation` records.

        Honors ``request.years`` and ``request.countries`` by
        forwarding to the legacy transform's ``years`` and
        ``country_filter`` keyword arguments. ``request.leaders``
        is unsupported for a country-year economic source and
        surfaces a structured ``UNSUPPORTED_FILTER`` warning
        (SRC-REQ-005). Out-of-coverage years emit zero rows
        plus a structured ``YEAR_ABSENT`` warning per offending
        year (SRC-COV-002 / SRC-COV-003: no stale-proxy fill).
        """
        # Lazy import: same package-boundary reason as read_raw.
        from leaders_db.ingest.sources.pwt.transform import (
            transform_pwt_long_frame,
        )

        if not isinstance(raw.payload, dict):
            raise ValueError(
                "PWTAdapter.transform: raw.payload must be a dict "
                "carrying the wide DataFrame under 'wide_df'."
            )
        wide_df = raw.payload.get("wide_df")
        if wide_df is None:
            raise ValueError(
                "PWTAdapter.transform: raw.payload has no "
                "'wide_df' key; read_raw must populate it."
            )
        metadata = raw.payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        # Request-scoping warnings are surfaced on the
        # ``ReadinessResult`` envelope (see ``check_ready``);
        # the runner collects them onto the final result. The
        # transform does NOT re-emit them per-row to avoid
        # double-counting in the warnings audit trail.

        years_arg: tuple[int, ...] | None = (
            tuple(int(y) for y in request.years)
            if request.years else None
        )
        countries_arg: tuple[str, ...] | None = (
            tuple(str(c) for c in request.countries)
            if request.countries else None
        )

        long_df = transform_pwt_long_frame(
            wide_df,
            years=years_arg,
            country_filter=countries_arg,
        )

        # Per-row observation emission lives in the focused
        # ``_transform`` helper so this adapter class stays
        # focused on lifecycle orchestration.
        xlsx_path = raw.payload.get("xlsx_path")
        xlsx_path_value = (
            xlsx_path if isinstance(xlsx_path, Path) else None
        )
        return emit_pwt_observations(
            long_df, request, xlsx_path_value, metadata,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_pwt_adapter() -> PWTAdapter:
    """Return a fresh :class:`PWTAdapter` instance.

    The factory is the explicit seam callers use to wire PWT into
    a :class:`SourceRegistry`. The package does NOT auto-register
    on import (the registry is passive by design -- see
    docs/architecture/sources.md §10.1).
    """
    return PWTAdapter()


def register_pwt(registry: Any) -> PWTAdapter:
    """Register the PWT adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect it.
    Raises :class:`ValueError` if the registry already has a
    ``pwt`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_pwt_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_pwt_adapter()`` (preferred) or this module-level
# callable.
PWT_ADAPTER_FACTORY = create_pwt_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the protocol.

    Defense in depth: ``isinstance`` against the runtime-checkable
    ``SourceAdapter`` Protocol catches missing ``descriptor`` /
    ``check_ready`` / ``read_raw`` / ``transform`` at module
    import time. The check is invoked at module bottom so a
    missing method surfaces during CI even when no test
    instantiates the adapter directly.
    """

    if not isinstance(PWTAdapter(), SourceAdapter):
        raise TypeError(
            "PWTAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "PWT_ADAPTER_FACTORY",
    "PWT_COVERAGE_END_YEAR",
    "PWT_COVERAGE_START_YEAR",
    "PWT_DEFAULT_VERSION",
    "PWT_METADATA_NAME",
    "PWT_OBSERVATION_FAMILY",
    "PWT_SOURCE_KEY",
    "PWT_SUPPORTED_FAMILIES",
    "PWT_XLSX_NAME",
    "PWTAdapter",
    "build_pwt_descriptor",
    "create_pwt_adapter",
    "register_pwt",
]
