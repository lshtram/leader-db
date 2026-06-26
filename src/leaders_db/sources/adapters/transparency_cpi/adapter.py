"""Unified-source Transparency International CPI adapter
implementation.

Seventh source rebuilt under the clean
``leaders_db.sources`` interface
(docs/architecture/sources.md section 7.1 priority 6,
docs/requirements/sources.md section 12 SRC-MIG-005),
after PWT 10.01, Maddison Project Database 2023, World
Bank WDI, World Bank WGI, V-Dem, and UCDP.

The adapter wraps the legacy reader
(:func:`leaders_db.ingest.transparency_cpi_csv.read_transparency_cpi_csv`)
via lazy imports so the package boundary in
docs/architecture/sources.md section 10.1 is preserved
(SRC-MIG-007). It implements the full ``SourceAdapter``
Protocol (section 5.6) for the canonical CPI 2023 bundle
(source_id ``transparency_cpi``, default version
``"CPI 2023"``, dataset type, 1995-2023 coverage hint,
single observation family ``integrity_country_year``,
``requires_network=False``).

The CPI staged bundle metadata carries
``local_files=["transparency_cpi_2023.csv"]`` and
``checksum_sha256=null`` -- a deliberately minimal
shape; the readiness gate enforces raw-file presence
(``missing_raw``) and optional CSV-checksum match
(``transparency_cpi_checksum_mismatch``). A mismatched
request ``source_version`` fails readiness with a
structured ``unsupported_version`` error per SRC-REQ-009.
The mirror-vs-publisher attribution contract is
documented in ``docs/sources/attributions.md``
``transparency_cpi`` section and enforced by
``test_transparency_cpi_attribution_text_matches_attributions_doc``.

The end-to-end contract is proven by
``tests/sources/test_transparency_cpi_adapter.py``
(descriptor / factory / registry / runner /
request-scoping / out-of-coverage / readiness-failure /
unsupported-version / metadata-only-bundle /
runner-short-circuit / canonical-version-propagation /
checksum-shape / checksum-mismatch / correct-checksum /
per-row audit-trail / attribution-drift-guard /
indicator-code / raw-locator-row-index / direction-hints /
no-network / import-boundary /
STAGE2_ADAPTERS-no-touch).

Module split: readiness in :mod:`._readiness`,
per-field validators in :mod:`._metadata_validators`,
canonical constants + descriptor in :mod:`._descriptor`,
catalog helpers in :mod:`._catalog`, per-row emission
in :mod:`._transform`, raw-read orchestration in
:mod:`._raw_read`, transform-pipeline orchestration in
:mod:`._pipeline`, per-row observation construction in
:mod:`._observation_builder`, missing-value helpers in
:mod:`._missing_values`. This module owns the lifecycle
class + registration helpers + protocol conformance
guard.
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
    TRANSPARENCY_CPI_DEFAULT_VERSION,
    build_transparency_cpi_descriptor,
)
from ._pipeline import transform_transparency_cpi_observations
from ._raw_read import (
    _bundle_dir,
    _csv_name_for_request,
    read_transparency_cpi_csv,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class TransparencyCPIAdapter:
    """Unified-source Transparency International CPI
    adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md section 5.6). The
    descriptor is a class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_transparency_cpi_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the
        request-scoped bundle.

        The gate fires BEFORE the reader opens the CSV.
        Two failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so
        the runner raises ``RuntimeError`` before
        ``read_raw`` / ``transform``:

        1. Bundle readiness -- :func:`check_metadata_well_formed`
           validates ``metadata.json`` + the per-year
           CSV (mandatory raw-file presence fires
           ``missing_raw``; the optional CSV-checksum
           match fires
           ``transparency_cpi_checksum_mismatch``).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` differs from the
           canonical ``"CPI 2023"`` (SRC-REQ-009).

        Two request-scoping warning classes (NOT
        blockers) are surfaced on
        ``ReadinessResult.warnings``: ``unsupported_filter``
        for ``leaders=``; ``year_absent`` for ``years=``
        outside 1995-2023 (no stale-proxy fill per
        SRC-COV-002 / SRC-COV-003).
        """
        bundle_dir = _bundle_dir(request)
        csv_name, _ = _csv_name_for_request(request)

        # Phase A: bundle readiness (file presence +
        # metadata fields + checksum shape and optional
        # CSV-checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            csv_name,
            TRANSPARENCY_CPI_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "Transparency International "
                            "CPI bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                            "csv_name": csv_name,
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009).
        version_blocker = check_source_version(
            request,
            canonical_version=TRANSPARENCY_CPI_DEFAULT_VERSION,
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
                            "requested_version": (
                                request.source_version
                            ),
                            "canonical_version": (
                                TRANSPARENCY_CPI_DEFAULT_VERSION
                            ),
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings (advisory
        # only).
        warnings = list(collect_request_scoping_warnings(request))

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged per-year CSV and return the
        raw bundle.

        Delegates to :func:`read_transparency_cpi_csv` in
        :mod:`._raw_read` (local-file only).
        """
        return read_transparency_cpi_csv(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to
        :func:`transform_transparency_cpi_observations`
        in :mod:`._pipeline` (year / country filter
        contract lives there).
        """
        return transform_transparency_cpi_observations(
            request, raw,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_transparency_cpi_adapter() -> TransparencyCPIAdapter:
    """Return a fresh :class:`TransparencyCPIAdapter`.

    The explicit seam callers use to wire CPI into a
    :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive --
    docs/architecture/sources.md section 10.1).
    """
    return TransparencyCPIAdapter()


def register_transparency_cpi(registry: Any) -> TransparencyCPIAdapter:
    """Register the CPI adapter against ``registry``.

    Returns the registered adapter. Raises
    :class:`ValueError` on duplicate-slug registration
    per ``docs/requirements/sources.md`` section 9
    SRC-REG-004.
    """
    adapter = create_transparency_cpi_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. ``create_transparency_cpi_adapter()``
# is the preferred form.
TRANSPARENCY_CPI_ADAPTER_FACTORY = create_transparency_cpi_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not
    satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches
    missing ``descriptor`` / ``check_ready`` /
    ``read_raw`` / ``transform`` at module import time.
    """
    if not isinstance(TransparencyCPIAdapter(), SourceAdapter):
        raise TypeError(
            "TransparencyCPIAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor "
            "attribute and the check_ready / read_raw / "
            "transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "TRANSPARENCY_CPI_ADAPTER_FACTORY",
    "TransparencyCPIAdapter",
    "create_transparency_cpi_adapter",
    "register_transparency_cpi",
]
