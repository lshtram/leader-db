"""Unified-source World Bank WDI adapter implementation.

This module provides the :class:`WDIAdapter` -- the third source
rebuilt under the clean ``leaders_db.sources`` interface
(docs/architecture/sources.md §7.1 priority 3,
docs/requirements/sources.md §12 SRC-MIG-005), after the PWT
10.01 and Maddison Project Database 2023 adapters.

The adapter wraps the existing legacy reader
(:func:`leaders_db.ingest.wdi_io.read_wdi`) and catalog loader
(:func:`leaders_db.ingest.wdi_io.load_indicator_catalog`) so the
canonical WDI parsing logic is reused without duplication
(SRC-MIG-002: do not delete existing prototype capabilities).
The legacy package is imported lazily inside adapter methods
only so the ``leaders_db.sources`` package boundary documented
in docs/architecture/sources.md §10.1 is preserved; the package
import does NOT pull in ``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  World Bank WDI (source_id ``world_bank_wdi``, default version
  ``"World Bank API v2; cached indicator responses"``,
  homepage URL ``https://api.worldbank.org/v2/``,
  attribution_key ``world_bank_wdi``, coverage hint
  1960-present, observation families
  ``("economic_country_year", "social_country_year")``,
  source_type ``"api"``, requires_network ``True``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` AND the per-(year, indicator) JSON cache
  BEFORE the reader opens the cache files; every blocker names
  the specific missing / invalid field or file. Source-version
  requests other than the canonical ``"World Bank API v2;
  cached indicator responses"`` fail readiness with a structured
  ``SourceWarning(severity="error", code="unsupported_version")``
  per SRC-REQ-009, so the runner never reaches
  ``read_raw`` / ``transform`` for a mismatched version stamp.
- ``read_raw(request)`` -- opens the staged per-(year,
  indicator) JSON cache via the legacy reader and returns a
  :class:`RawReadResult` carrying the wide-format DataFrame
  plus a :class:`RawAsset` record (cache root path, API
  endpoint URL template).
- ``transform(request, raw)`` -- pivots the wide frame to the
  canonical long format via the legacy reader (already done by
  ``read_wdi``) and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), the raw WDI indicator code preserved as an
  extension field, and structured warnings (out-of-coverage
  years, unsupported leader filter, missing cache files).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
reader's year filter + post-read DataFrame filtering
(SRC-REQ-004). ``request.years=None`` means all available years
in the source's cache (the canonical 1960+ envelope; the
reader enumerates the cache root for year subdirectories). The
adapter applies explicit-year request filters AFTER the legacy
read returns the wide frame so the request-scoping semantics
stay in one place. ``leaders`` is unsupported for a country-
year source and surfaces a structured ``UNSUPPORTED_FILTER``
warning per SRC-REQ-005.

Cache-policy semantics
----------------------

``SourceIngestRequest.cache_policy`` honors
``docs/requirements/sources.md`` §11 SRC-TYPE-002 (API sources
use cache policy):

- ``offline_only`` / ``prefer_cache`` (default for WDI): the
  readiness gate refuses to dispatch ``read_raw`` /
  ``transform`` when the cache directory is missing or any
  requested year lacks a complete indicator cache. The legacy
  HTTP layer is never invoked. This is the documented safe
  default -- the new runner is offline / cache-first.
- ``refresh`` / ``no_cache``: NOT supported by the unified WDI
  adapter in this slice. ``check_cache_availability`` fails
  readiness with the structured ``unsupported_cache_policy``
  code because ``WDIAdapter.read_raw`` never invokes the
  network -- the legacy HTTP path is intentionally not
  wired through the unified runner. Callers that need
  fresh data must stage the per-(year, indicator) JSON cache
  under ``<raw_root>/world_bank_wdi/cache/<year>/<CODE>.json``
  and re-run with ``cache_policy='offline_only'`` or
  ``'prefer_cache'``.

Year semantics
--------------

WDI covers 1960+ (per the canonical attribution block in
``docs/sources/attributions.md`` and the staged
``data/raw/world_bank_wdi/metadata.json``). A request for a
year before 1960 emits zero observations AND a structured
``YEAR_ABSENT`` warning -- no stale-proxy fill (SRC-COV-002 /
SRC-COV-003).

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.world_bank_wdi._readiness`,
the canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.world_bank_wdi._descriptor`,
and the per-row observation emission lives in
:mod:`leaders_db.sources.adapters.world_bank_wdi._transform` so
this module stays focused on the lifecycle class + registration
helpers. All four modules honor the package-isolation contract
(SRC-MIG-007) and the per-module 400-line convention.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
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
    NETWORK_CACHE_UNAVAILABLE,
)

from ._descriptor import (
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_COVERAGE_START_YEAR,
    WORLD_BANK_WDI_DEFAULT_VERSION,
    WORLD_BANK_WDI_HOMEPAGE_URL,
    WORLD_BANK_WDI_SOURCE_KEY,
    build_world_bank_wdi_descriptor,
)
from ._readiness import (
    _enumerate_cache_files,
    check_cache_availability,
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import (
    _read_cached_wdi_responses,
    emit_world_bank_wdi_observations,
    load_wdi_cache_index,
)

# ---------------------------------------------------------------------------
# Path + metadata helpers
# ---------------------------------------------------------------------------


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/world_bank_wdi/`` bundle directory."""
    return Path(request.raw_root) / WORLD_BANK_WDI_SOURCE_KEY


def _cache_dir(request: SourceIngestRequest) -> Path:
    """Return the request-scoped cache root directory."""
    return _bundle_dir(request) / WORLD_BANK_WDI_CACHE_DIR_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / "metadata.json"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_indicator_codes_from_catalog(
    catalog_path: Path | None,
) -> tuple[str, ...]:
    """Return the catalog's ``raw_column`` codes via the legacy catalog loader.

    The catalog is the single source of truth for which WDI
    indicators the unified adapter reads. Loading is delegated
    to :func:`leaders_db.ingest.wdi_io.load_indicator_catalog`
    so the legacy contract (14 indicators, the documented
    CSV format) is reused without duplication.
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest`` (docs/architecture/sources.md
    # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.wdi_io import (
        load_indicator_catalog as _legacy_load_catalog,
    )

    specs = _legacy_load_catalog(catalog_path=catalog_path)
    return tuple(spec.raw_column for spec in specs)


def _resolve_spec_by_variable_name(
    catalog_path: Path | None,
) -> dict[str, Any]:
    """Return ``{variable_name: IndicatorSpec}`` for the legacy catalog.

    Used by the transform layer to map wide-format column
    names (catalog ``variable_name``) back to the spec
    carrying ``raw_column`` / ``rating_category`` / ``unit``.
    """
    # Lazy import: same package-boundary reason as
    # ``_resolve_indicator_codes_from_catalog``.
    from leaders_db.ingest.wdi_io import (
        load_indicator_catalog as _legacy_load_catalog,
    )

    specs = _legacy_load_catalog(catalog_path=catalog_path)
    return {spec.variable_name: spec for spec in specs}


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WDIAdapter:
    """Unified-source World Bank WDI adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_world_bank_wdi_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the cache. Every
        blocker names the specific missing / invalid field or
        file so a developer can fix the upstream issue without
        reading source code.

        The gate enforces three failure classes (each surfaces
        a structured ``SourceWarning`` with ``severity='error'``
        in the ``ReadinessResult.errors`` tuple so the runner
        raises ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. Bundle metadata readiness --
           :func:`check_metadata_well_formed` validates
           ``metadata.json`` (file presence, required fields,
           canonical ``source_version``, ingestion status,
           local_files includes ``cache/``).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical ``"World Bank API v2; cached indicator
           responses"`` (SRC-REQ-009). The legacy bundle does
           not encode a per-version stamp beyond
           ``metadata.json['source_version']``; silently
           propagating an unsupported version into
           ``RawAsset.version`` /
           ``NormalizedObservation.source_version`` would lie
           to downstream scorers.
        3. Cache availability --
           :func:`check_cache_availability` blocks when
           ``request.years`` is explicit AND the cache policy
           is ``"offline_only"`` / ``"prefer_cache"`` AND the
           cache directory is missing or any requested year
           lacks a complete indicator cache. For
           ``"refresh"`` / ``"no_cache"`` the gate fails
           readiness with the structured
           ``unsupported_cache_policy`` error because the
           unified WDI adapter is offline / cache-only in
           this slice -- there is no production path that
           wires ``force_refresh=True`` or HTTP re-fetch into
           ``WDIAdapter.read_raw``.

        Two request-scoping warning classes (NOT blockers)
        surface on ``ReadinessResult.warnings``:

        - ``unsupported_filter`` -- ``leaders=`` filter is
          unsupported for a country-year source.
        - ``year_absent`` -- ``years=`` outside the 1960+
          coverage envelope emits zero rows (no stale-proxy
          fill).
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

        # Phase C: cache availability. Resolves the catalog's
        # raw indicator codes via the legacy catalog loader so
        # the gate knows which files constitute "complete
        # cache" for a given year. The loader is invoked here
        # (NOT inside check_cache_availability) so the lazy
        # import is symmetric with read_raw.
        try:
            indicator_codes = _resolve_indicator_codes_from_catalog(
                catalog_path=None,
            )
        except FileNotFoundError as exc:
            # Catalog missing -> readiness fails. This is
            # distinct from the cache-availability gate
            # because the catalog lives at the package root,
            # not in the bundle.
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

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged per-(year, indicator) JSON cache and
        return the wide-format DataFrame.

        The unified WDI adapter is offline / cache-only in this
        slice: ``read_raw`` NEVER invokes the network. It uses
        the local :func:`_read_cached_wdi_responses` cache-only
        read path (mirrors the legacy
        :func:`leaders_db.ingest.wdi_io.read_wdi` /
        :func:`leaders_db.ingest.wdi_http.parse_wdi_payload`
        parsing just enough for the staged per-(year, indicator)
        JSON cache, but with no HTTP fallback). The legacy
        :func:`read_wdi` falls through to HTTP on missing /
        corrupt cache files; the local path deliberately does
        not.

        For ``years=None`` (all-available-years semantics per
        SRC-REQ-003), the function enumerates the cache root for
        valid ``(year, indicator)`` JSON files via the readiness
        gate's :func:`_enumerate_cache_files` helper and reads
        exactly those ``(year, indicator)`` pairs through the
        cache-only path. For explicit ``years=``, the readiness
        gate has already validated that every catalog indicator
        has a complete, valid cache file under each requested
        year dir; ``read_raw`` then reads those exact files.

        The wide-format DataFrame (one row per ``(iso3, year)``
        with one column per catalog ``variable_name``) is carried
        in :attr:`RawReadResult.payload` under ``"wide_df"`` for
        the transform layer. The ``read_raw`` call does NOT
        apply request year / country filters -- the transform
        layer does that on the wide frame so the
        request-scoping semantics stay in one place.

        The :class:`RawAsset` describes the cache root as one
        logical asset; per-observation locators carry the
        specific cache file path + json_pointer.
        """
        cache_root = _cache_dir(request)

        # Resolve the catalog spec mapping so the cache-only read
        # path can rename raw WDI codes (``SP.POP.TOTL``) to
        # canonical variable names (``wdi_population``). Lazy
        # import to preserve the package boundary
        # (docs/architecture/sources.md §10.1).
        spec_by_variable_name: Mapping[str, Any] | None = None
        try:
            spec_by_variable_name = _resolve_spec_by_variable_name(
                catalog_path=None,
            )
        except FileNotFoundError:
            # The catalog gate already fired in ``check_ready``
            # so this branch is defensive: ``read_raw`` is only
            # reachable when the readiness gate passed, which
            # requires the catalog to be present. If the catalog
            # disappeared between ``check_ready`` and
            # ``read_raw`` (race), fall back to raw-code columns
            # so the read path still works without the network.
            spec_by_variable_name = None

        # For ``years=None``, enumerate the cache files via the
        # readiness-gate helper so the read path operates on
        # exactly the validated ``(year, indicator)`` pairs
        # (no opportunistic file discovery that could miss a
        # file the gate did not inspect). The enumeration is
        # idempotent and fast (one ``iterdir`` per year dir +
        # one ``json.loads`` per file); we deliberately do not
        # cache it across calls because the cache may have
        # changed between ``check_ready`` and ``read_raw``.
        if not request.years:
            discovered_pairs, _malformed = _enumerate_cache_files(
                cache_root,
            )
        else:
            # Explicit ``years=``: the readiness gate has
            # already validated that every catalog indicator has
            # a complete, valid cache file under each requested
            # year dir. Enumerate the (year, catalog_indicator)
            # pairs directly so the read path is deterministic
            # and does not need to re-validate shape. We do NOT
            # request a re-enumeration here because the catalog
            # names ARE the file names per the canonical WDI
            # cache layout (``<year>/<CODE>.json`` where CODE is
            # the catalog's ``raw_column``).
            discovered_pairs = []
            for year in request.years:
                year_int = int(year)
                if year_int < WORLD_BANK_WDI_COVERAGE_START_YEAR:
                    continue
                year_dir = cache_root / str(year_int)
                if not year_dir.is_dir():
                    continue
                for code in _resolve_indicator_codes_from_catalog(
                    catalog_path=None,
                ):
                    cache_file = year_dir / f"{code}.json"
                    if cache_file.is_file():
                        discovered_pairs.append(
                            (year_int, code, cache_file),
                        )

        wide_df = _read_cached_wdi_responses(
            cache_root,
            years=request.years,
            discovered_pairs=discovered_pairs or None,
            spec_by_variable_name=spec_by_variable_name,
        )
        metadata = _read_metadata_payload(_metadata_path(request))

        # Surface the cached/fetched counts the local read path
        # attached to ``df.attrs`` so the result envelope
        # carries them for downstream audits. ``indicators_fetched``
        # is always 0 because the cache-only read path never
        # invokes the network.
        indicators_cached = int(
            getattr(wide_df, "attrs", {}).get("indicators_cached", 0),
        )
        indicators_fetched = int(
            getattr(wide_df, "attrs", {}).get("indicators_fetched", 0),
        )

        asset = RawAsset(
            asset_id=f"{WORLD_BANK_WDI_SOURCE_KEY}:{WORLD_BANK_WDI_CACHE_DIR_NAME}",
            source_id=request.source_id,
            version=WORLD_BANK_WDI_DEFAULT_VERSION,
            media_type="application/json",
            path=cache_root,
            url=WORLD_BANK_WDI_HOMEPAGE_URL,
            checksum_sha256=None,
            retrieved_at=None,
            immutable=True,
        )
        return RawReadResult(
            source_id=request.source_id,
            assets=(asset,),
            payload={
                "wide_df": wide_df,
                "metadata": metadata,
                "cache_root": cache_root,
                "indicators_cached": indicators_cached,
                "indicators_fetched": indicators_fetched,
                "discovered_pairs": tuple(discovered_pairs),
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
        filtering the wide-format DataFrame after the legacy
        read (the legacy reader returns the full frame when
        called with ``year=None``; the new adapter owns the
        request-scoping logic). ``request.years=`` outside the
        documented 1960+ coverage envelope emits zero
        observations (no stale-proxy fill); the readiness
        envelope already surfaced the ``YEAR_ABSENT`` warning
        per offending year.

        Pre-computes a ``(year, raw_indicator_code) ->
        {countryiso3code: numeric_index}`` map by reading each
        cache file once via :func:`load_wdi_cache_index`. The
        map lets the transform layer stamp each emitted
        observation's ``raw_locator.json_pointer`` with a
        real ``/1/<numeric_index>`` value so audit code can
        resolve the pointer to the underlying cache record
        byte-for-byte (per
        ``docs/requirements/sources.md`` §6 SRC-PROV-001).
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "WDIAdapter.transform: raw.payload must be a "
                "dict carrying the wide DataFrame under 'wide_df'."
            )
        wide_df = raw.payload.get("wide_df")
        if wide_df is None:
            raise ValueError(
                "WDIAdapter.transform: raw.payload has no "
                "'wide_df' key; read_raw must populate it."
            )
        cache_root = raw.payload.get("cache_root")
        cache_root_value = (
            cache_root if isinstance(cache_root, Path) else None
        )

        # Apply the request year + country filters on the wide
        # frame. The wide frame has integer ``year`` and string
        # ``iso3`` columns.
        years_arg: tuple[int, ...] | None = (
            tuple(int(y) for y in request.years)
            if request.years else None
        )
        countries_arg: tuple[str, ...] | None = (
            tuple(str(c) for c in request.countries)
            if request.countries else None
        )

        filtered_df = wide_df
        if years_arg is not None:
            # Honor the documented 1960+ coverage envelope:
            # years outside the envelope are dropped silently
            # (the readiness envelope already surfaced the
            # YEAR_ABSENT warning). When the caller asked for
            # only out-of-coverage years, the filtered frame
            # is empty so we emit zero observations (no
            # stale-proxy fill per SRC-COV-003).
            in_coverage = [
                y for y in years_arg
                if y >= 1960
            ]
            if not in_coverage:
                filtered_df = filtered_df.iloc[0:0]
            else:
                filtered_df = filtered_df.loc[
                    filtered_df["year"].astype(int).isin(in_coverage),
                ]
        if countries_arg:
            country_set = set(countries_arg)
            filtered_df = filtered_df.loc[
                filtered_df["iso3"].astype(str).isin(country_set),
            ]

        # Resolve the catalog spec mapping (variable_name ->
        # IndicatorSpec). The legacy catalog loader returns
        # the canonical 14-indicator set; missing specs (e.g.
        # for forward-compatible catalog additions) fall back
        # to the economic-family default + the default unit
        # hint inside ``emit_world_bank_wdi_observations``.
        spec_by_variable_name = _resolve_spec_by_variable_name(
            catalog_path=None,
        )

        # Pre-compute the (year, raw_indicator_code) cache
        # index map so the transform can stamp each
        # observation with a real ``/1/<numeric_index>``
        # JSON pointer. We enumerate the (year, indicator)
        # pairs that survive the filter; for every pair we
        # look up the catalog ``raw_column`` (the WDI v2
        # indicator code) and load the cache file once.
        # Missing / malformed cache files yield ``None`` so
        # the transform falls back to the documented
        # ``/1/{iso3}`` placeholder pointer (no silent
        # corruption of the audit envelope).
        cache_index_by_year_indicator: dict[
            tuple[int, str], dict[str, int] | None
        ] = {}
        if (
            isinstance(cache_root_value, Path)
            and not filtered_df.empty
        ):
            for column_name in filtered_df.columns:
                if column_name in {"iso3", "year"}:
                    continue
                spec = spec_by_variable_name.get(column_name)
                raw_indicator_code = (
                    getattr(spec, "raw_column", None) or column_name
                )
                for year_int in (
                    int(y) for y in filtered_df["year"].unique()
                ):
                    key = (year_int, raw_indicator_code)
                    if key in cache_index_by_year_indicator:
                        continue
                    cache_file = (
                        cache_root_value
                        / str(year_int)
                        / f"{raw_indicator_code}.json"
                    )
                    cache_index_by_year_indicator[key] = (
                        load_wdi_cache_index(cache_file)
                    )

        return emit_world_bank_wdi_observations(
            filtered_df, request, cache_root_value,
            spec_by_variable_name,
            cache_index_by_year_indicator=(
                cache_index_by_year_indicator
                if cache_index_by_year_indicator
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_world_bank_wdi_adapter() -> WDIAdapter:
    """Return a fresh :class:`WDIAdapter` instance.

    The factory is the explicit seam callers use to wire WDI
    into a :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive by design
    -- see docs/architecture/sources.md §10.1).
    """
    return WDIAdapter()


def register_world_bank_wdi(registry: Any) -> WDIAdapter:
    """Register the WDI adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``world_bank_wdi`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_world_bank_wdi_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_world_bank_wdi_adapter()`` (preferred) or this
# module-level callable.
WDI_ADAPTER_FACTORY = create_world_bank_wdi_adapter


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
    if not isinstance(WDIAdapter(), SourceAdapter):
        raise TypeError(
            "WDIAdapter does not satisfy the SourceAdapter "
            "Protocol; check the descriptor attribute and the "
            "check_ready / read_raw / transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "WDI_ADAPTER_FACTORY",
    "WDIAdapter",
    "create_world_bank_wdi_adapter",
    "register_world_bank_wdi",
]
