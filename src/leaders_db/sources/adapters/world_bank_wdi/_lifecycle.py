"""World Bank WDI readiness gate orchestration.

Owns the body of :meth:`WDIAdapter.check_ready` extracted
into a free function :func:`check_world_bank_wdi_readiness`
so the adapter class module stays focused on lifecycle
wiring + registration. The function composes the metadata
gate (:mod:`._readiness`), the cache gate
(:mod:`._readiness` via :func:`check_cache_availability`),
and the source-version gate into a single
:class:`ReadinessResult` for the runner.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter`
so the adapter class file stays under the 400-line
convention while preserving the same end-to-end behaviour
the reviewer gate requires (every blocker surfaces a
structured :class:`SourceWarning`).

Behavior contract
-----------------

The gate enforces three failure classes (each surfaces a
structured :class:`SourceWarning` with ``severity='error'``
in the :class:`ReadinessResult.errors` tuple so the runner
raises ``RuntimeError` before calling ``read_raw`` /
``transform``):

1. **Bundle metadata readiness** --
   :func:`check_metadata_well_formed` validates
   ``metadata.json`` (file presence, required fields,
   canonical ``source_version``, ingestion status,
   ``local_files`` includes ``cache/``).
2. **Source-version match** --
   :func:`check_source_version` blocks when
   ``request.source_version`` is set and differs from the
   canonical ``"World Bank API v2; cached indicator
    responses"`` (SRC-REQ-009). The staged bundle does not
    encode a per-version stamp beyond
    ``metadata.json['source_version']``; silently propagating
    an unsupported version into ``RawAsset.version`` /
   ``NormalizedObservation.source_version`` would lie to
   downstream scorers.
3. **Cache availability** --
   :func:`check_cache_availability` blocks when
   ``request.years`` is explicit AND the cache policy is
   ``"offline_only"`` / ``"prefer_cache"`` AND the cache
   directory is missing or any requested year lacks a
   complete indicator cache. For ``"refresh"`` /
   ``"no_cache"`` the gate fails readiness with the
   structured ``unsupported_cache_policy`` error because the
   unified WDI adapter is offline / cache-only in this
   slice -- there is no production path that wires
   ``force_refresh=True`` or HTTP re-fetch into
   ``WDIAdapter.read_raw``.

Two request-scoping warning classes (NOT blockers) surface
on :class:`ReadinessResult.warnings`:

- ``unsupported_filter`` -- ``leaders=`` filter is
  unsupported for a country-year source.
- ``year_absent`` -- ``years=`` outside the 1960+ coverage
  envelope emits zero rows (no stale-proxy fill).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    ReadinessResult,
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
)

from ._descriptor import (
    WORLD_BANK_WDI_DEFAULT_VERSION,
)
from ._paths import (
    _bundle_dir,
    _resolve_indicator_codes_from_catalog,
)
from ._readiness import (
    check_cache_availability,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)


def check_world_bank_wdi_readiness(
    request: SourceIngestRequest,
) -> ReadinessResult:
    """Return a :class:`ReadinessResult` for the request-scoped bundle.

    The gate fires BEFORE the reader opens the cache. Every
    blocker names the specific missing / invalid field or file
    so a developer can fix the upstream issue without reading
    source code. See the module docstring for the full failure
    class + warning catalogue.
    """
    bundle_dir = _bundle_dir(request)

    # Phase A: bundle metadata readiness (file presence +
    # metadata fields + source_version match).
    ready, blocker, code = check_metadata_well_formed(
        bundle_dir, WORLD_BANK_WDI_DEFAULT_VERSION,
    )
    if not ready:
        return ReadinessResult(
            ready=False,
            errors=(
                SourceWarning(
                    code=code or MISSING_RAW,
                    message=blocker or (
                        "World Bank WDI bundle is not ready"
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
        canonical_version=WORLD_BANK_WDI_DEFAULT_VERSION,
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
                        "canonical_version": (
                            WORLD_BANK_WDI_DEFAULT_VERSION
                        ),
                    },
                ),
            ),
        )

    # Phase C: cache availability. Resolves the catalog's raw
# indicator codes via the catalog loader so the
# gate knows which files constitute "complete cache" for a
# given year. The loader is invoked here (NOT inside
# check_cache_availability) so the lazy import is symmetric
    # with read_raw.
    try:
        indicator_codes = _resolve_indicator_codes_from_catalog(
            catalog_path=None,
        )
    except FileNotFoundError as exc:
        # Catalog missing -> readiness fails. Distinct from
        # the cache-availability gate because the catalog
        # lives at the package root, not in the bundle.
        return ReadinessResult(
            ready=False,
            errors=(
                SourceWarning(
                    code=MISSING_RAW,
                    message=(
                        "World Bank WDI readiness gate: "
                        "indicator catalog not found; "
                        f"{exc}. The catalog must live at "
                        "src/leaders_db/ingest/catalogs/wdi.csv."
                    ),
                    severity="error",
                    source_id=request.source_id,
                    context={
                        "bundle_dir": str(bundle_dir),
                    },
                ),
            ),
        )

    cache_ready, cache_blocker, cache_code = check_cache_availability(
        request,
        bundle_dir=bundle_dir,
        indicator_codes=indicator_codes,
    )
    if not cache_ready:
        return ReadinessResult(
            ready=False,
            errors=(
                SourceWarning(
                    code=cache_code or NETWORK_CACHE_UNAVAILABLE,
                    message=cache_blocker or (
                        "World Bank WDI cache is not available"
                    ),
                    severity="error",
                    source_id=request.source_id,
                    context={
                        "bundle_dir": str(bundle_dir),
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


__all__ = ["check_world_bank_wdi_readiness"]
