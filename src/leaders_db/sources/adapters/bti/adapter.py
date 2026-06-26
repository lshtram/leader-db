"""Unified-source Bertelsmann Transformation Index (BTI)
adapter implementation.

Tenth source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 8 and
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, Political Terror Scale,
and Reporters Without Borders (RSF). The adapter
implements the canonical ``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` +
``transform``) and reuses the legacy reader /
transform / catalog under ``leaders_db.ingest.bti``,
``leaders_db.ingest.bti_io``, ``leaders_db.ingest.bti_xlsx``
via lazy imports so the package boundary documented
in ``docs/architecture/sources.md`` §10.1 is
preserved.

The BTI unified path is local-file only (no network).
The canonical bundle is ``data/raw/bti/`` with the
cumulative ``BTI_2006-2026_Scores.xlsx`` (12 edition
sheets: ``BTI 2026`` / ``BTI 2024`` / ``BTI 2022`` /
... / ``BTI 2006`` / ``BTI 2006_old``; 137-159
countries per edition; 123 columns) + the optional
``BTI2026_Codebook.pdf`` + ``metadata.json``. The
unified adapter never invokes the network.

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``bti`` (CLI dispatch key +
adapter key + attribution key). The data-lake folder
is also ``bti/`` (the slug is the folder name; no
source-key / folder-alias reconciliation is needed,
unlike ``pts`` / ``political_terror_scale`` where the
slug differs from the folder). The descriptor's
``source_id.slug`` is ``"bti"``.

BTI-specific readiness
----------------------

The BTI staged bundle metadata carries a verbose
``source_version="BTI 2026 (covers 2024-2025);
cumulative file covers 2006-2026 (biennial, 12
editions)"`` (the verbose acquisition-date stamp);
the unified adapter's canonical stamp is the brief
``"BTI 2026"`` (matching the canonical attribution
block in ``docs/sources/attributions.md`` + the
``Attribution text in reports`` line). The bundle
metadata carries ``checksum_sha256`` as a
``{filename: sha256}`` dict (the canonical BTI
bundle ships per-file SHA-256 values for both the
xlsx + the codebook PDF); the unified adapter
verifies the xlsx's SHA-256 against the
``checksum_sha256["BTI_2006-2026_Scores.xlsx"]``
value when present.

The mandatory readiness requirement is on raw-file
presence: the ``check_ready`` gate returns
``ready=False`` with a structured ``MISSING_RAW``
error if the staged xlsx is not on disk, regardless
of the metadata's ``local_files`` / ``checksum_sha256``
shape. The ``SourceIngestRunner`` raises
``RuntimeError`` BEFORE ``read_raw`` so the runner
never dispatches ``read_raw`` against a missing xlsx.
A metadata-only bundle is intentionally NOT
runner-ready; it has value for readiness-only
inspection (validating metadata shape, schema
migrations, sanity-checking ``local_files``
annotations) but ``adapter.check_ready(request).ready``
is ``False`` until the staged xlsx is present.

Biennial sheet/year mapping
---------------------------

BTI is biennial: each edition covers the ~2-year
period preceding publication (BTI 2024 covers
2022-2023; BTI 2026 covers 2024-2025). The per-edition
covered interval map is documented in
:data:`leaders_db.ingest.bti_io._BTI_EDITION_COVERED_INTERVAL`
and resolved at runtime via
:func:`leaders_db.ingest.bti_io.sheet_for_year` (the
legacy bridge, lazily imported). For the prototype
target year 2023, the canonical mapping resolves to
the ``"BTI 2024"`` sheet (covers 2022-2023). The
unified transform carries the resolved sheet name +
covered interval on every observation's ``extension``
(``bti_sheet_name`` / ``bti_target_year``) so the
Stage 5 score module can apply the proxy /
source-edition semantics without re-reading the
parquet metadata.

The canonical version is ``"BTI 2026"`` (matches the
canonical attribution block + the canonical xlsx
filename's last-edition stamp). The staged bundle's
verbose ``source_version`` stamp is accepted at the
readiness gate (per
:func:`_metadata_source_version_blocker`).

The end-to-end contract is proven by
``tests/sources/test_bti_adapter.py`` (descriptor /
factory / registry / runner / request-scoping /
out-of-coverage / readiness-failure /
unsupported-version / metadata-only-bundle /
runner-short-circuit / canonical-version-propagation /
checksum-shape / checksum-mismatch / correct-checksum
/ per-row audit-trail / attribution-drift-guard /
indicator-code / raw-locator / direction-hints /
no-network / import-boundary / STAGE2_ADAPTERS-no-touch
/ biennial-sheet-mapping / missing-cell behavior).

Module split: readiness in :mod:`._readiness`,
per-field validators in :mod:`._metadata_validators`,
checksum shape + match validators in
:mod:`._checksum_validators`, canonical constants +
descriptor in :mod:`._descriptor`, catalog helpers in
:mod:`._catalog`, missing-value coercion helpers in
:mod:`._missing_values`, per-row emission loop in
:mod:`._transform`, per-row observation construction
in :mod:`._observation_builder`, raw-read
orchestration in :mod:`._raw_read`, transform-pipeline
orchestration in :mod:`._pipeline`. This module owns
the lifecycle class + registration helpers + protocol
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
    BTI_DEFAULT_VERSION,
    BTI_XLSX_NAME,
    build_bti_descriptor,
)
from ._pipeline import transform_bti_observations
from ._raw_read import read_bti_xlsx
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class BTIAdapter:
    """Unified-source Bertelsmann Transformation
    Index (BTI) adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The
    descriptor is a class attribute so the
    protocol's ``descriptor: SourceDescriptor``
    member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = build_bti_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the
        request-scoped bundle.

        The gate fires BEFORE the reader opens the
        xlsx. Two failure classes are surfaced as
        ``severity='error'`` ``SourceWarning``
        records so the runner raises ``RuntimeError``
        before ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed`
           validates ``metadata.json`` + the staged
           xlsx (mandatory raw-file presence fires
           ``missing_raw``; the optional xlsx-checksum
           match fires ``bti_checksum_mismatch``;
           malformed / mismatched ``source_version``
           fires ``bti_metadata_version_mismatch``).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` differs from
           the canonical ``"BTI 2026"`` (SRC-REQ-009).

        Two request-scoping warning classes (NOT
        blockers) are surfaced on
        ``ReadinessResult.warnings``:
        ``unsupported_filter`` for ``leaders=``;
        ``year_absent`` for ``years=`` outside
        2002-2025 (no stale-proxy fill per
        SRC-COV-002 / SRC-COV-003).
        """
        from ._raw_read import _bundle_dir

        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence
        # + metadata fields + checksum shape and
        # optional xlsx-checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            BTI_XLSX_NAME,
            canonical_version=BTI_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "BTI bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                            "xlsx_name": BTI_XLSX_NAME,
                        },
                    ),
                ),
            )

        # Phase B: source-version match
        # (SRC-REQ-009).
        version_blocker = check_source_version(
            request,
            canonical_version=BTI_DEFAULT_VERSION,
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
                                BTI_DEFAULT_VERSION
                            ),
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings
        # (advisory only).
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
        """Open the staged cumulative
        ``BTI_2006-2026_Scores.xlsx`` and return the
        raw bundle.

        Delegates to :func:`read_bti_xlsx` in
        :mod:`._raw_read` (local-file only; reads
        the canonical cumulative xlsx and applies the
        biennial sheet resolution at read time).
        """
        return read_bti_xlsx(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the wide raw frame into
        :class:`NormalizedObservation` records.

        Delegates to
        :func:`transform_bti_observations` in
        :mod:`._pipeline` (year / country filter
        contract lives there).
        """
        return transform_bti_observations(request, raw)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_bti_adapter() -> BTIAdapter:
    """Return a fresh :class:`BTIAdapter`.

    The explicit seam callers use to wire BTI into
    a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive
    -- ``docs/architecture/sources.md`` §10.1).
    """
    return BTIAdapter()


def register_bti(registry: Any) -> BTIAdapter:
    """Register the BTI adapter against ``registry``.

    Returns the registered adapter. Raises
    :class:`ValueError` on duplicate-slug
    registration per
    ``docs/requirements/sources.md`` §9 SRC-REG-004.
    """
    adapter = create_bti_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the
# legacy ``STAGE2_ADAPTERS`` keying convention.
# ``create_bti_adapter()`` is the preferred form.
BTI_ADAPTER_FACTORY = create_bti_adapter


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not
    satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol
    catches missing ``descriptor`` / ``check_ready``
    / ``read_raw`` / ``transform`` at module import
    time.
    """
    if not isinstance(BTIAdapter(), SourceAdapter):
        raise TypeError(
            "BTIAdapter does not satisfy the "
            "SourceAdapter Protocol; check the "
            "descriptor attribute and the "
            "check_ready / read_raw / transform "
            "method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "BTI_ADAPTER_FACTORY",
    "BTIAdapter",
    "create_bti_adapter",
    "register_bti",
]
