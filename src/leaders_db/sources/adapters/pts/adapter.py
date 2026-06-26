"""Unified-source Political Terror Scale (PTS) adapter
implementation.

Eighth source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 14 and
``docs/requirements/sources.md`` §12 SRC-MIG-006), after
PWT 10.01, Maddison Project Database 2023, World Bank
WDI, World Bank WGI, V-Dem, UCDP, and Transparency
International CPI. The adapter implements the
canonical ``SourceAdapter`` Protocol (``descriptor`` +
``check_ready`` + ``read_raw`` + ``transform``) and
reuses the legacy reader
(:func:`leaders_db.ingest.pts_xlsx.read_pts`) via lazy
imports so the package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved.

The Political Terror Scale unified path is local-file
only (no network). The canonical bundle is
``data/raw/political_terror_scale/PTS-2025.xlsx`` +
``metadata.json`` (the xlsx is 572 KB, 1 sheet
``PTS-2025``, 10,531 data rows x 14 columns; verified
live 2026-06-18 per ``docs/architecture/pts.md`` §2)
and the adapter never invokes the network.

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``pts`` (CLI dispatch key +
adapter key + attribution key). The data-lake folder is
``political_terror_scale/`` (the human-readable bundle
name; preserved from the live download + the staged
metadata shape). The folder alias is preserved on disk;
the unified adapter's ``descriptor.source_id.slug`` is
``"pts"``. This reconciliation is documented in
``docs/architecture/sources.md`` §7.5 and the
``pts`` section of ``docs/sources/attributions.md``.

PTS-specific readiness
----------------------

The PTS staged bundle metadata carries
``version="2025"`` + ``sha256="6f4d1ccd...88832"`` +
``local_files=["PTS-2025.xlsx"]`` -- a deliberately
minimal shape so the operator can update the metadata
once the xlsx is staged. The mandatory readiness
requirement is on raw-file presence: the ``check_ready``
gate returns ``ready=False`` with a structured
``MISSING_RAW`` error if the staged xlsx is not on
disk, regardless of the metadata's ``local_files`` /
``sha256`` shape. The ``SourceIngestRunner`` raises
``RuntimeError`` BEFORE ``read_raw`` so the runner
never dispatches ``read_raw`` against a missing xlsx.
A metadata-only bundle is intentionally NOT runner-ready;
it has value for readiness-only inspection (validating
metadata shape, schema migrations, sanity-checking
``expected_local_files`` annotations) but
``adapter.check_ready(request).ready`` is ``False``
until the per-year xlsx is staged.

The §6 sentinel-matrix contract (4-case NA_Status
precedence rule + the §6.5 defensive check) is a
per-row data-coercion contract that lives in the
legacy reader; the unified adapter does NOT surface
sentinel-matrix warnings at the readiness gate (the
readiness gate is a bundle-level contract, not a
per-row data contract).

The PTS canonical version is ``"PTS-2025"`` (matches
the canonical xlsx filename + the legacy
``register_pts_source`` upsert key in
``src/leaders_db/ingest/pts_db.py``). The staged
bundle metadata carries ``version: "2025"`` (the
bare-year stamp); the unified adapter's canonical
``source_version`` field on emitted observations is
``"PTS-2025"`` so the audit trail records the canonical
stamp regardless of the metadata's bare-year stamp.

The end-to-end contract is proven by
``tests/sources/test_pts_adapter.py`` (descriptor /
factory / registry / runner / request-scoping /
out-of-coverage / readiness-failure / unsupported-
version / metadata-only-bundle / runner-short-circuit /
canonical-version-propagation / checksum-shape /
checksum-mismatch / correct-checksum / per-row audit-
trail / attribution-drift-guard / indicator-code /
raw-locator-row-index / direction-hints / no-network /
import-boundary / STAGE2_ADAPTERS-no-touch).

Module split: readiness in :mod:`._readiness`,
per-field validators in :mod:`._metadata_validators`,
canonical constants + descriptor in :mod:`._descriptor`,
catalog helpers in :mod:`._catalog`, sentinel-matrix
helpers in :mod:`._missing_values`, per-row emission
in :mod:`._transform`, raw-read orchestration in
:mod:`._raw_read`, transform-pipeline orchestration in
:mod:`._pipeline`, per-row observation construction
in :mod:`._observation_builder`. This module owns the
lifecycle class + registration helpers + protocol
conformance guard.
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
    PTS_DEFAULT_VERSION,
    build_pts_descriptor,
)
from ._pipeline import transform_pts_observations
from ._raw_read import read_pts_xlsx
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class PTSAdapter:
    """Unified-source Political Terror Scale (PTS)
    adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The
    descriptor is a class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_pts_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the
        request-scoped bundle.

        The gate fires BEFORE the reader opens the
        xlsx. Two failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records
        so the runner raises ``RuntimeError`` before
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` + the staged xlsx
           (mandatory raw-file presence fires
           ``missing_raw``; the optional xlsx-checksum
           match fires ``pts_checksum_mismatch``;
           malformed / mismatched ``version`` /
           ``source_version`` fires
           ``pts_metadata_version_mismatch``).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` differs from the
           canonical ``"PTS-2025"`` (SRC-REQ-009).

        Two request-scoping warning classes (NOT
        blockers) are surfaced on
        ``ReadinessResult.warnings``: ``unsupported_filter``
        for ``leaders=``; ``year_absent`` for ``years=``
        outside 1976-2024 (no stale-proxy fill per
        SRC-COV-002 / SRC-COV-003).
        """
        from ._raw_read import _bundle_dir

        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence +
        # metadata fields + checksum shape and optional
        # xlsx-checksum match).
        from ._descriptor import PTS_XLSX_NAME

        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            PTS_XLSX_NAME,
            canonical_version=PTS_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "PTS bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                            "xlsx_name": PTS_XLSX_NAME,
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009).
        version_blocker = check_source_version(
            request,
            canonical_version=PTS_DEFAULT_VERSION,
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
                                PTS_DEFAULT_VERSION
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
        """Open the staged ``PTS-2025.xlsx`` and return
        the raw bundle.

        Delegates to :func:`read_pts_xlsx` in
        :mod:`._raw_read` (local-file only).
        """
        return read_pts_xlsx(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to
        :func:`transform_pts_observations` in
        :mod:`._pipeline` (year / country filter
        contract lives there).
        """
        return transform_pts_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_pts_adapter() -> PTSAdapter:
    """Return a fresh :class:`PTSAdapter`.

    The explicit seam callers use to wire PTS into a
    :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive
    -- ``docs/architecture/sources.md`` §10.1).
    """
    return PTSAdapter()


def register_pts(registry: Any) -> PTSAdapter:
    """Register the PTS adapter against ``registry``.

    Returns the registered adapter. Raises
    :class:`ValueError` on duplicate-slug registration
    per ``docs/requirements/sources.md`` §9 SRC-REG-004.
    """
    adapter = create_pts_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the
# legacy ``STAGE2_ADAPTERS`` keying convention.
# ``create_pts_adapter()`` is the preferred form.
PTS_ADAPTER_FACTORY = create_pts_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not
    satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol
    catches missing ``descriptor`` / ``check_ready`` /
    ``read_raw`` / ``transform`` at module import
    time.
    """
    if not isinstance(PTSAdapter(), SourceAdapter):
        raise TypeError(
            "PTSAdapter does not satisfy the "
            "SourceAdapter Protocol; check the "
            "descriptor attribute and the "
            "check_ready / read_raw / transform method "
            "shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "PTS_ADAPTER_FACTORY",
    "PTSAdapter",
    "create_pts_adapter",
    "register_pts",
]
