"""Clean World Bank Poverty and Inequality Platform (PIP) source
adapter.

This module owns the
:class:`WorldBankPovertyInequalityPlatformAdapter` -- the
unified-source implementation of the World Bank PIP adapter
under the clean ``leaders_db.sources`` interface.

The unified World Bank PIP adapter is offline / cache-first in
this slice. It reads a staged cached export (the canonical
``pip_stats.csv`` file OR the canonical ``pip_stats.json``
wrapper) from
``data/raw/world_bank_poverty_inequality_platform/`` plus a
runtime-local ``metadata.json`` (gitignored per Always-On Rule
#9). Live fetch is intentionally NOT supported (the task
brief: "Build an offline/cache-first adapter. Do NOT implement
live HTTP fetching"). The readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``world_bank_poverty_inequality_platform_unsupported_cache_policy``
error BEFORE ``read_raw`` / ``transform`` are called.

The adapter implements the full ``SourceAdapter`` Protocol
(:class:`leaders_db.sources.contracts.SourceAdapter`):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  World Bank PIP (source_id
  ``world_bank_poverty_inequality_platform``, default version
  ``"World Bank PIP, version 20260324_2021"``, attribution_key
  ``world_bank_poverty_inequality_platform``, ``api`` source
  type, 1960-2024 coverage hint, single
  ``poverty_inequality_country_year`` observation family,
  ``requires_network=False``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` + cached CSV / JSON file BEFORE the reader
  opens the cache; every blocker names the specific missing /
  invalid field or file. Source-version requests other than
  the canonical stamp fail readiness with a structured
  ``world_bank_poverty_inequality_platform_metadata_version_mismatch``
  / ``unsupported_version`` error per SRC-REQ-009.
- ``read_raw(request)`` -- loads the cached CSV (CSV shape
  preferred; falls back to JSON shape), parses the cached text
  via the Python ``csv`` module (CSV shape) or the JSON parser
  (JSON shape), validates the header against the 11 canonical
  required columns, and returns a :class:`RawReadResult`
  carrying the parsed frame plus a :class:`RawAsset` record
  (path, source URL, SHA-256).
- ``transform(request, raw)`` -- emits one observation per
  cached row + source-native catalog indicator (3 per-row
  indicators by default: headcount + poverty gap + Gini),
  preserves the source-native country code + display name
  verbatim (no ISO3 invention -- the PIP ``country_code`` is
  the World Bank's own reporting identifier, NOT a canonical
  ISO3 mapping), preserves the per-row PPP version + reporting
  level + welfare type + poverty line on the audit-trail
  extension payload (no numeric coercion that could mislead
  Stage 11 confidence calculations), and applies the documented
  request-scoping filters (``countries=`` / ``years=``).

Request-scoping
---------------

``SourceIngestRequest.years`` filters the readiness envelope on
the descriptor's 1960-2024 envelope; out-of-coverage years (e.g.
``years=(2050,)`` -- well beyond the canonical envelope) emit
zero observations AND a structured ``YEAR_ABSENT`` warning (no
stale-proxy fill per SRC-COV-002 / SRC-COV-003). The prototype's
target year 2023 falls WITHIN the canonical envelope so 2023 is
in-coverage. ``countries=`` filters the parsed row-level frame on
the transform side by source-native case-folded substring match.
``leaders`` is unsupported for a country-year poverty /
inequality source and surfaces a structured
``UNSUPPORTED_FILTER`` warning (SRC-REQ-005). ``source_version``
other than the canonical stamp is unsupported and fails readiness
with a structured ``unsupported_version`` error (SRC-REQ-009).
``cache_policy`` other than ``"offline_only"`` /
``"prefer_cache"`` fails readiness with a structured
``world_bank_poverty_inequality_platform_unsupported_cache_policy``
error.

Year semantics
--------------

The World Bank PIP dataset covers a broad 1960-2024 envelope per
the canonical descriptor (PIP records typically begin in the
early 1960s when survey-based poverty estimates become
available; the canonical probe stamp is 2021 for the
``20260324_2021`` PIP version with a few extrapolation cells
into 2024 for a handful of countries). The prototype's target
year 2023 falls WITHIN the canonical envelope (1960-2024) so
2023 is in-coverage.

Important caveat
----------------

PIP poverty / inequality estimates are SURVEY- and PPP-specific
and SHOULD NOT be silently mixed across PIP version stamps
(e.g. ``20260324_2021`` vs ``20260324_2017``) or PPP bases
(2021 PPP vs 2017 PPP) without explicit metadata propagation.
The descriptor's ``coverage_hint.notes`` carries the explicit
caveat. Downstream scorers MUST NOT silently treat a PIP cell
as comparable across version stamps or PPP bases without
explicit metadata propagation; the adapter propagates the
canonical PIP version stamp + PPP version (when present) onto
every emitted observation's audit-trail extension payload so
downstream code can apply the canonical "version / PPP basis"
treatment explicitly. The PIP ``country_code`` is the World
Bank's own reporting identifier -- a 3-character code that
LOOKS LIKE ISO3 but is NOT a canonical ISO3 mapping; the
adapter does NOT assume it is ISO3 even when it resembles one.
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
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY,
)
from ._descriptor import (
    build_world_bank_poverty_inequality_platform_descriptor,
)
from ._raw_read import (
    read_world_bank_poverty_inequality_platform_cache,
)
from ._readiness import (
    check_cache_policy,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    emit_world_bank_poverty_inequality_platform_observations,
)


class WorldBankPovertyInequalityPlatformAdapter:
    """Unified-source World Bank Poverty and Inequality Platform
    (PIP) adapter.

    Implements the ``SourceAdapter`` Protocol
    (``docs/architecture/sources.md`` §5.6). The descriptor is
    a class attribute so the protocol's ``descriptor:
    SourceDescriptor`` member is satisfied without per-instance
    construction overhead.
    """

    descriptor: SourceDescriptor = (
        build_world_bank_poverty_inequality_platform_descriptor()
    )

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the
        request-scoped bundle.

        The gate fires BEFORE the reader opens the cached CSV /
        JSON file. Four failure classes are surfaced as
        ``severity='error'`` ``SourceWarning`` records so the
        runner raises ``RuntimeError`` before calling
        ``read_raw`` / ``transform``:

        1. Bundle readiness --
           :func:`check_metadata_well_formed` validates the
           bundle's ``metadata.json`` + cached CSV / JSON file
           (file presence, required fields, canonical metadata
           ``source_version``, ``local_files`` annotation,
           ``ingestion_status='downloaded'``, checksum match,
           the selected-file contract that the actually-present
           cache file the reader will load is declared in
           ``local_files`` AND covered by ``checksum_sha256``).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical
           ``"World Bank PIP, version 20260324_2021"`` stamp
           (SRC-REQ-009; PIP version stamps encode the release
           date + PPP base year and are not interchangeable).
        3. Cache-policy gate --
           :func:`check_cache_policy` blocks when
           ``request.cache_policy`` is ``"refresh"`` /
           ``"no_cache"`` (the unified adapter is offline /
           cache-only in this slice; live fetch is intentionally
           NOT supported).
        4. (Request-scoping warnings, NOT blockers) -- out-of-
           coverage years and unsupported leader filters are
           surfaced on ``ReadinessResult.warnings`` (advisory;
           the runner still proceeds).
        """
        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match + selected-file contract).
        ready, blocker, code = check_metadata_well_formed(request)
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=(
                            blocker
                            or "World Bank PIP bundle is not ready"
                        ),
                        severity="error",
                        source_id=request.source_id,
                        context={
                            "csv_name": (
                                WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
                            ),
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
        """Open the staged cached CSV / JSON bundle and return
        the parsed raw payload.

        Delegates to
        :func:`read_world_bank_poverty_inequality_platform_cache`
        in :mod:`._raw_read`. The reader loads the cached CSV
        (CSV shape preferred; falls back to the JSON shape),
        parses the cached text via the Python ``csv`` module
        (CSV shape) or the JSON parser (JSON shape), validates
        the parsed header against the 11 canonical required
        columns, and propagates the parsed frame on
        ``payload["rows"]`` plus the original ``header`` list
        for the transform layer. A missing-required-column
        fires a :class:`WorldBankPipSchemaError` BEFORE the
        transform layer consumes the frame so the runner
        propagates a structured schema-violation error.
        """
        return (
            read_world_bank_poverty_inequality_platform_cache(
                request,
            )
        )

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
        substring match against the source-native
        ``country_name`` cell). ``request.leaders`` is
        unsupported for a country-year poverty / inequality
        source and surfaces a structured
        ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).

        Emits 3 observations per cached row by default
        (headcount + poverty gap + Gini). Blank / non-numeric
        cells emit ``value=None`` / ``value_type="missing"``
        plus the verbatim raw cell text on
        ``extension.raw_value`` -- the transform does NOT
        invent a value from missing source-native data.

        The transform layer never invents ISO3 country codes,
        leader identifiers, missing values, or proxy years.
        The source-native country code + display name are
        preserved verbatim on every emitted observation's
        audit-trail extension payload; ``country_code``
        remains ``None`` until later matching / resolution
        stages introduce a canonical ISO3 mapping. Per-row
        PPP version + reporting level + welfare type + poverty
        line are preserved on the audit-trail extension payload
        so downstream code can recover the verbatim source-
        native provenance.
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "WorldBankPovertyInequalityPlatformAdapter.transform: "
                "raw.payload must be a dict carrying the parsed "
                "frame under 'rows'."
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
                else "world_bank_poverty_inequality_platform:pip_stats.csv"
            )
        version_id = raw.payload.get("version_id")
        if not isinstance(version_id, str) or not version_id.strip():
            version_id = None

        return emit_world_bank_poverty_inequality_platform_observations(
            request,
            rows,
            cache_path=cache_path,
            asset_id=asset_id,
            version_id=version_id,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_world_bank_poverty_inequality_platform_adapter() -> (
    WorldBankPovertyInequalityPlatformAdapter
):
    """Return a fresh
    :class:`WorldBankPovertyInequalityPlatformAdapter` instance.

    The factory is the explicit seam callers use to wire World
    Bank PIP into a :class:`SourceRegistry`. The package does
    NOT auto-register on import (the registry is passive by
    design -- see ``docs/architecture/sources.md`` §10.1).
    """
    return WorldBankPovertyInequalityPlatformAdapter()


def register_world_bank_poverty_inequality_platform(
    registry: Any,
) -> WorldBankPovertyInequalityPlatformAdapter:
    """Register the World Bank PIP adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``world_bank_poverty_inequality_platform`` slug
    registered (per ``docs/requirements/sources.md`` §9
    SRC-REG-004).
    """
    adapter = create_world_bank_poverty_inequality_platform_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_world_bank_poverty_inequality_platform_adapter()``
# (preferred) or this module-level callable.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY = (
    create_world_bank_poverty_inequality_platform_adapter
)


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not satisfy the
    protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol catches
    missing ``descriptor`` / ``check_ready`` / ``read_raw`` /
    ``transform`` at module import time. The check is invoked
    at module bottom so a missing method surfaces during CI
    even when no test instantiates the adapter directly.
    """
    if not isinstance(
        WorldBankPovertyInequalityPlatformAdapter(),
        SourceAdapter,
    ):
        raise TypeError(
            "WorldBankPovertyInequalityPlatformAdapter does not "
            "satisfy the SourceAdapter Protocol; check the "
            "descriptor attribute and the check_ready / read_raw "
            "/ transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ADAPTER_FACTORY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY",
    "WorldBankPovertyInequalityPlatformAdapter",
    "create_world_bank_poverty_inequality_platform_adapter",
    "register_world_bank_poverty_inequality_platform",
]
