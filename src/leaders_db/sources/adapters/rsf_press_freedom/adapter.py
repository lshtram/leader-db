"""Unified-source Reporters Without Borders (RSF) World
Press Freedom Index adapter implementation.

Ninth source rebuilt under the clean
``leaders_db.sources`` interface
(``docs/architecture/sources.md`` §7.1 priority 7 and
``docs/requirements/sources.md`` §12 SRC-MIG-006),
after PWT 10.01, Maddison Project Database 2023,
World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency International CPI, and Political Terror
Scale. The adapter implements the canonical
``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` +
``transform``) and reuses the legacy reader /
transform / catalog under
``leaders_db.ingest.rsf_press_freedom_csv`` and
``leaders_db.ingest.rsf_press_freedom_io`` via lazy
imports so the package boundary documented in
``docs/architecture/sources.md`` §10.1 is preserved.

The RSF World Press Freedom Index unified path is
local-file only (no network). The canonical bundle
is ``data/raw/rsf_press_freedom/`` with 24 annual
CSVs (2002-2010 + 2012-2026; the direct ``2011.csv``
is absent -- RSF's combined 2011/2012 edition is
represented by the 2012 CSV; its ``Year (N)`` column
reads ``"2011-12"``). The bundle metadata carries
``source_version="annual CSV series 2002-2026,
acquired 2026-06-18"`` (the verbose acquisition-date
stamp); the unified adapter uses the brief canonical
stamp ``"RSF Press Freedom Index 2026"`` to match the
live 2026 RSF release + the canonical attribution
block in ``docs/sources/attributions.md``.

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``rsf_press_freedom`` (CLI
dispatch key + adapter key + attribution key). The
data-lake folder is also ``rsf_press_freedom/`` (the
slug is the folder name; no source-key / folder-
alias reconciliation is needed, unlike ``pts`` /
``political_terror_scale`` where the slug differs
from the folder). The descriptor's
``source_id.slug`` is ``"rsf_press_freedom"``.

RSF-specific readiness
----------------------

The RSF staged bundle metadata carries
``source_version="annual CSV series 2002-2026,
acquired 2026-06-18"`` (the verbose acquisition-date
stamp); the unified adapter's canonical stamp is
``"RSF Press Freedom Index 2026"`` (matching the live
2026 RSF release + the canonical attribution block in
``docs/sources/attributions.md``). The bundle
metadata's ``local_files`` annotation lists all 24
canonical per-year CSV filenames; the ``files``
array carries one record per year file (with
per-file ``sha256``). The ``check_ready`` gate
returns ``ready=False`` with a structured
``missing_raw`` error if the per-year CSV(s) are
not staged on disk for the request scope, regardless
of the metadata's ``local_files`` / ``files`` shape.
Year-scoped requests (``years=(Y,)``) require the
metadata + the requested year file(s); broad / no-
year requests (``years=None``) require the canonical
staged set (the full 24-year CSV set). The
``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
``read_raw`` so the runner never dispatches
``read_raw`` against a missing per-year CSV. A
metadata-only bundle is intentionally NOT runner-
ready; it has value for readiness-only inspection
(validating metadata shape, schema migrations, sanity-
checking ``local_files`` annotations) but
``adapter.check_ready(request).ready`` is ``False``
until the per-year CSV(s) are staged.

2011 missing / direct-CSV caveat
--------------------------------

The direct ``2011.csv`` is absent; RSF's combined
2011/2012 edition is represented by the 2012 CSV.
The unified ``check_ready`` gate surfaces the
documented 2011 caveat with a structured
``rsf_year_2011_absent`` warning (NOT the generic
``year_absent`` so the operator can distinguish the
documented 2011 caveat from a generic
out-of-coverage year). Year=2011 requests fail
readiness; the runner short-circuits with
``RuntimeError`` BEFORE ``read_raw`` / ``transform``
so the legacy reader never sees a missing-CSV
scenario in production.

Pre/post-2022 methodology / schema distinction
------------------------------------------------

The RSF World Press Freedom Index changed methodology
around the 2022 edition. Pre-2022 files (2002-2021)
use a 16-col wide format with score + rank only; the
5 component-context indicators
(``rsf_press_freedom_political_context`` /
``rsf_press_freedom_economic_context`` /
``rsf_press_freedom_legal_context`` /
``rsf_press_freedom_social_context`` /
``rsf_press_freedom_safety``) are NOT emitted for
these years because the actual columns are absent in
the legacy CSV. Post-2022 files (2022+) use a 22-26
col wide format with score + rank + 5
component-context columns; all 7 catalog indicators
are emitted for these years. The pre/post-2022
methodology/schema distinction is preserved on every
observation via the
``extension["rsf_schema_group"]`` field (1 =
pre-2022; 2+ = post-2022). The unified transform
does NOT silently merge pre/post-2022 methodology --
the raw cell text is preserved verbatim on
``extension["raw_value"]`` and the ``rsf_schema_group``
flag tells downstream code which methodology
applied. Per ``docs/architecture/sources.md`` §5.5 +
§7.1 + ``docs/sources/registry.md``
``rsf_press_freedom`` row, RSF is a press/media-
freedom sub-signal for the ``political_freedom``
rating category, NOT a full political-freedom
replacement.

The end-to-end contract is proven by
``tests/sources/test_rsf_press_freedom_adapter.py``
(descriptor / factory / registry / runner / request-
scoping / out-of-coverage / readiness-failure /
unsupported-version / metadata-only-bundle / runner-
short-circuit / canonical-version-propagation /
checksum-shape / checksum-mismatch / correct-
checksum / per-row audit-trail / attribution-drift-
guard / indicator-code / raw-locator /
direction-hints / no-network / import-boundary /
STAGE2_ADAPTERS-no-touch / pre-2022-no-component /
post-2022-with-component / 2011-missing-caveat /
comma-decimal-parsing).

Module split: readiness in :mod:`._readiness`,
per-field validators in :mod:`._metadata_validators`,
per-year CSV / checksum validators in
:mod:`._year_validators` and
:mod:`._files_validators`, canonical constants in
:mod:`._constants`, descriptor factory in
:mod:`._descriptor`, catalog helpers in
:mod:`._catalog`, missing-value / decimal-comma
helpers in :mod:`._missing_values`, per-row emission
in :mod:`._transform`, per-row emission-loop helpers
in :mod:`._helpers`, raw-read orchestration in
:mod:`._raw_read`, transform-pipeline orchestration
in :mod:`._pipeline`, per-row observation
construction in :mod:`._observation_builder`,
registration helpers + protocol conformance guard in
:mod:`._registration`. This module owns the
lifecycle class.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    ReadinessResult,
    SourceDescriptor,
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import MISSING_RAW

from ._constants import RSF_PRESS_FREEDOM_DEFAULT_VERSION
from ._descriptor import build_rsf_press_freedom_descriptor
from ._pipeline import transform_rsf_press_freedom_observations
from ._raw_read import _bundle_dir, read_rsf_press_freedom_csv
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


class RSFPressFreedomAdapter:
    """Unified-source Reporters Without Borders (RSF)
    World Press Freedom Index adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The
    descriptor is a class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is
    satisfied without per-instance construction
    overhead.
    """

    descriptor: SourceDescriptor = (
        build_rsf_press_freedom_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the
        request-scoped bundle.

        The gate fires BEFORE the reader opens the
        per-year CSV(s). Two failure classes are
        surfaced as ``severity='error'``
        ``SourceWarning`` records so the runner
        raises ``RuntimeError`` before ``read_raw`` /
        ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` + the per-year CSV(s)
           (mandatory raw-file presence fires
           ``missing_raw``; the optional per-file
           SHA-256 match fires
           ``rsf_press_freedom_checksum_mismatch``;
           malformed / mismatched ``source_version``
           fires
           ``rsf_press_freedom_metadata_version_mismatch``;
           the documented 2011 missing / direct-CSV
           caveat fires
           ``rsf_year_2011_absent`` when year=2011
           is requested).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` differs from
           the canonical
           ``"RSF Press Freedom Index 2026"``
           (SRC-REQ-009).

        Two request-scoping warning classes (NOT
        blockers) are surfaced on
        ``ReadinessResult.warnings``: ``unsupported_filter``
        for ``leaders=``; ``year_absent`` for ``years=``
        outside 2002-2026 (no stale-proxy fill per
        SRC-COV-002 / SRC-COV-003);
        ``rsf_year_2011_absent`` for ``years=``
        including 2011 (the documented missing /
        direct-CSV caveat).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence +
        # metadata fields + per-year CSV presence for
        # the request scope + optional per-file
        # SHA-256 match).
        years_scope = (
            tuple(int(y) for y in request.years)
            if request.years else None
        )
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir,
            canonical_version=RSF_PRESS_FREEDOM_DEFAULT_VERSION,
            years_scope=years_scope,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "RSF bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "bundle_dir": str(bundle_dir),
                        },
                    ),
                ),
            )

        # Phase B: source-version match (SRC-REQ-009).
        version_blocker = check_source_version(
            request,
            canonical_version=RSF_PRESS_FREEDOM_DEFAULT_VERSION,
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
                                RSF_PRESS_FREEDOM_DEFAULT_VERSION
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
        """Open the staged per-year RSF CSV(s) and
        return the raw bundle.

        Delegates to :func:`read_rsf_press_freedom_csv`
        in :mod:`._raw_read` (local-file only; reads
        the per-year CSV(s) for the request scope).
        """
        return read_rsf_press_freedom_csv(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert the narrow raw frame into
        :class:`NormalizedObservation` records.

        Delegates to
        :func:`transform_rsf_press_freedom_observations`
        in :mod:`._pipeline` (year / country filter
        contract lives there).
        """
        return transform_rsf_press_freedom_observations(
            request, raw,
        )


__all__ = [
    "RSFPressFreedomAdapter",
]
