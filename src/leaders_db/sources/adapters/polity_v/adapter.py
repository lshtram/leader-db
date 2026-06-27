"""Unified-source Polity V (Polity5 v2018) adapter implementation.

This module provides the :class:`PolityVAdapter` -- the first
"databases not yet in legacy" source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.2, ``polity_v`` row).

Polity V is the first source in the post-interface batch with
no legacy Stage 2 implementation in
``src/leaders_db/ingest/``. The
``STAGE2_ADAPTERS["polity_v"]`` slot is ``None`` per the
workplan Done History ("blocked on source hygiene / raw file
placement"). The unified adapter uses ``pyreadstat.read_sav``
directly (no legacy module to reuse) and emits the canonical
``NormalizedObservation`` records end-to-end through the new
registry.

The Polity V unified path is local-file only (no network). The
canonical bundle is ``data/raw/polity_v/p5v2018.sav`` (~1.4 MB,
17574 rows x 37 columns, verified live 2026-06-27; SHA-256
``c0405a807777610a65fe430e4b4828fda16717afc4b5d6e34bf56f1ca100f2f6``)
plus the user's runtime-local ``metadata.json`` (gitignored per
Always-On Rule #9). The adapter never invokes the network.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(``docs/architecture/sources.md`` §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor`
  for Polity5 v2018 (source_id ``polity_v``, default version
  ``p5v2018``, attribution_key ``polity_v``, dataset type,
  1800-2018 coverage hint, ``political_freedom_country_year``
  observation family).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` + ``p5v2018.sav`` BEFORE the reader opens
  the SPSS file; every blocker names the specific missing /
  invalid field or file. Source-version requests other than
  ``p5v2018`` fail readiness with a structured
  ``SourceWarning(severity="error", code="unsupported_version")``
  per SRC-REQ-009, so the runner never reaches ``read_raw`` /
  ``transform`` for a mismatched version stamp.
- ``read_raw(request)`` -- opens the staged ``p5v2018.sav`` via
  ``pyreadstat.read_sav``, filters the raw frame to the
  canonical 1800-2018 envelope (dropping the historical
  1776-1799 backfill + the 2019-2020 stray rows), and returns
  a :class:`RawReadResult` carrying the filtered frame plus a
  :class:`RawAsset` record (path, SHA-256, source URL).
- ``transform(request, raw)`` -- pivots the wide frame to the
  canonical per-``(country, year, raw_column)`` triple format
  via the unified transform helper, applies the documented
  special-code matrix (``-66`` / ``-77`` / ``-88``) + valid
  range checks, and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (out-of-coverage years,
  unsupported leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` filter the
wide-format DataFrame on the transform side (the readiness
gate surfaces a structured ``YEAR_ABSENT`` warning on
out-of-coverage year requests). ``leaders`` is unsupported for
a country-year political-freedom source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
``source_version`` other than ``p5v2018`` is unsupported and
fails readiness with a structured ``unsupported_version``
error (SRC-REQ-009).

Year semantics
--------------

Polity V covers 1800-2018 per the canonical attribution block
in ``docs/sources/attributions.md``. A request for an
out-of-coverage year (e.g. ``years=(2023,)`` -- the
prototype's target year -- falls outside the envelope) emits
zero observations AND a structured ``YEAR_ABSENT`` warning --
no stale-proxy fill (SRC-COV-002, SRC-COV-003).

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.polity_v._readiness` and the
canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.polity_v._descriptor` so this
module stays focused on the lifecycle class + registration
helpers. The missing-value coercion matrix lives in
:mod:`._missing_values`; the raw-read orchestration lives in
:mod:`._raw_read`; the per-row emission loop lives in
:mod:`._transform`. All five modules honor the
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
from leaders_db.sources.warnings import MISSING_RAW

from ._descriptor import (
    POLITY_V_DEFAULT_VERSION,
    POLITY_V_SAV_NAME,
    build_polity_v_descriptor,
)
from ._raw_read import _bundle_dir, read_polity_v_sav
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_polity_v_observations


class PolityVAdapter:
    """Unified-source Polity V adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is a
    class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = build_polity_v_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the SPSS file.
        Three failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so the
        runner raises ``RuntimeError`` before calling
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` + ``p5v2018.sav`` (file presence,
           required fields, canonical metadata
           ``source_version``, ``local_files`` annotation,
           ``ingestion_status='downloaded'``, checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical ``"p5v2018"`` (SRC-REQ-009; the legacy
           bundle has no per-version stamp beyond
           ``metadata.json['source_version']`` so silently
           propagating an unsupported version into
           ``RawAsset.version`` /
           ``NormalizedObservation.source_version`` would lie
           to downstream scorers).
        3. (Request-scoping warnings, NOT blockers) -- out-of-
           coverage years and unsupported leader filters are
           surfaced on ``ReadinessResult.warnings`` (advisory;
           the runner still proceeds).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            canonical_version=POLITY_V_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "Polity V bundle is not ready",
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                            "sav_name": POLITY_V_SAV_NAME,
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
            canonical_version=POLITY_V_DEFAULT_VERSION,
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
                            "canonical_version": POLITY_V_DEFAULT_VERSION,
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings (advisory only).
        warnings = list(
            collect_request_scoping_warnings(request),
        )

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged ``p5v2018.sav`` and return the raw bundle.

        Delegates to :func:`read_polity_v_sav` in
        :mod:`._raw_read`. The wide-format DataFrame is
        filtered to the canonical 1800-2018 envelope by the
        raw-read layer; the transform layer applies the
        request-scoping year / country filters on top of the
        already-filtered frame.
        """
        return read_polity_v_sav(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into :class:`NormalizedObservation` records.

        Honors ``request.years`` and ``request.countries`` by
        filtering the wide-format DataFrame on the transform
        side (the readiness envelope surfaces a structured
        ``YEAR_ABSENT`` warning on out-of-coverage year
        requests). ``request.leaders`` is unsupported for a
        country-year political-freedom source and surfaces a
        structured ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
        Out-of-coverage years emit zero rows plus a structured
        ``YEAR_ABSENT`` warning per offending year
        (SRC-COV-002 / SRC-COV-003: no stale-proxy fill).
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "PolityVAdapter.transform: raw.payload must be a "
                "dict carrying the filtered wide DataFrame under "
                "'wide_df'."
            )
        wide_df = raw.payload.get("wide_df")
        if wide_df is None:
            raise ValueError(
                "PolityVAdapter.transform: raw.payload has no "
                "'wide_df' key; read_raw must populate it."
            )
        metadata = raw.payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        sav_path = raw.payload.get("sav_path")
        sav_path_value = (
            sav_path if isinstance(sav_path, Path) else None
        )

        # Request-scoping filters are applied on the already-
        # filtered wide frame. The raw-read layer has already
        # dropped rows outside the canonical 1800-2018
        # envelope; the transform layer narrows to the
        # request scope (specific years / countries).
        filtered_df = wide_df

        if request.years:
            allowed_years = {int(y) for y in request.years}
            if "year" in filtered_df.columns:
                year_int = filtered_df["year"].astype("Int64")
                filtered_df = filtered_df.loc[
                    year_int.isin(allowed_years)
                ].reset_index(drop=True)
        if request.countries:
            allowed_countries = {str(c) for c in request.countries}
            if "scode" in filtered_df.columns:
                filtered_df = filtered_df.loc[
                    filtered_df["scode"].astype(str).isin(
                        allowed_countries,
                    )
                ].reset_index(drop=True)

        # Per-row observation emission lives in the focused
        # ``_transform`` helper so this adapter class stays
        # focused on lifecycle orchestration.
        return emit_polity_v_observations(
            filtered_df,
            request,
            sav_path_value,
            metadata,
        )


# Late import for ``Path`` typing (avoid eager top-level
# import; the type annotation is only used inside the transform
# method body).
from pathlib import Path  # noqa: E402

# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_polity_v_adapter() -> PolityVAdapter:
    """Return a fresh :class:`PolityVAdapter` instance.

    The factory is the explicit seam callers use to wire Polity
    V into a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive by design
    -- see ``docs/architecture/sources.md`` §10.1).
    """
    return PolityVAdapter()


def register_polity_v(registry: Any) -> PolityVAdapter:
    """Register the Polity V adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``polity_v`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_polity_v_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_polity_v_adapter()`` (preferred) or this module-level
# callable.
POLITY_V_ADAPTER_FACTORY = create_polity_v_adapter


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
    if not isinstance(PolityVAdapter(), SourceAdapter):
        raise TypeError(
            "PolityVAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "POLITY_V_ADAPTER_FACTORY",
    "POLITY_V_DEFAULT_VERSION",
    "POLITY_V_SAV_NAME",
    "PolityVAdapter",
    "build_polity_v_descriptor",
    "create_polity_v_adapter",
    "register_polity_v",
]
