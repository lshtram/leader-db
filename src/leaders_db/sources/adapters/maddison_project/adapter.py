"""Unified-source Maddison Project Database 2023 adapter implementation.

This module provides the :class:`MaddisonProjectAdapter` -- the
second source rebuilt under the clean ``leaders_db.sources``
interface (docs/architecture/sources.md §7.1 priority 2,
docs/requirements/sources.md §12 SRC-MIG-005), after the
PWT 10.01 adapter.

The adapter wraps the existing legacy reader
(:func:`leaders_db.ingest.maddison_project_xlsx.read_maddison_project`)
so the canonical Maddison parsing logic is reused without
duplication (SRC-MIG-002: do not delete existing prototype
capabilities). The legacy package is imported lazily inside
adapter methods only so the ``leaders_db.sources`` package
boundary documented in docs/architecture/sources.md §10.1 is
preserved; the package import does NOT pull in
``leaders_db.ingest``.

Adapter contract
----------------

The adapter implements the full ``SourceAdapter`` Protocol
(docs/architecture/sources.md §5.6):

- ``descriptor`` -- the canonical :class:`SourceDescriptor` for
  Maddison Project Database 2023 (source_id ``maddison_project``,
  default version ``2023``, homepage URL,
  attribution_key ``maddison_project``, coverage hint 1-2022,
  observation family ``economic_country_year``).
- ``check_ready(request)`` -- validates the bundle's
  ``metadata.json`` and ``mpd2023.xlsx`` BEFORE the reader
  opens the workbook; every blocker names the specific
  missing / invalid field or file. Source-version requests
  other than ``2023`` fail readiness with a structured
  ``SourceWarning(severity="error", code="unsupported_version")``
  per SRC-REQ-009, so the runner never reaches ``read_raw`` /
  ``transform`` for a mismatched version stamp.
- ``read_raw(request)`` -- opens the staged ``mpd2023.xlsx``
  via the legacy reader and returns a :class:`RawReadResult`
  carrying the long-format DataFrame (one row per
  ``(countrycode, year, variable_name)`` triple) plus a
  :class:`RawAsset` record (path, SHA-256, source URL).
- ``transform(request, raw)`` -- applies the requested year /
  country filters and emits :class:`NormalizedObservation`
  records with raw + transform locators, attribution text
  (Rule #15), and structured warnings (proxy 2023 -> 2022,
  out-of-coverage years, unsupported leader filter).

Request-scoping
---------------

``SourceIngestRequest.years`` / ``countries`` map to the legacy
transform's ``year`` / post-read DataFrame filtering
(SRC-REQ-004). ``request.years=(2023,)`` is the documented
1-year-gap proxy mapping (CIRIGHTS / UNDP HDI / Leader Survival
pattern); the transform emits 2022 data with the
``proxy_year`` quality flag plus the ``requested_year`` /
``proxy_source_year`` extension fields so the mapping is never
silent. ``request.years=(2024,)`` (or any year beyond 2022)
emits zero observations plus a structured ``YEAR_ABSENT``
warning per SRC-COV-002 / SRC-COV-003 (no multi-year
stale-proxy fill). ``request.leaders`` is unsupported for a
country-year economic source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
``request.source_version`` other than ``2023`` is unsupported
and fails readiness with a structured ``unsupported_version``
error per SRC-REQ-009.

Module split
------------

The readiness gate logic lives in
:mod:`leaders_db.sources.adapters.maddison_project._readiness`,
the canonical constants + descriptor live in
:mod:`leaders_db.sources.adapters.maddison_project._descriptor`,
and the per-row observation emission lives in
:mod:`leaders_db.sources.adapters.maddison_project._transform`
so this module stays focused on the lifecycle class +
registration helpers. All four modules honor the
package-isolation contract (SRC-MIG-007) and the per-module
400-line convention.
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
    MADDISON_PROJECT_COVERAGE_END_YEAR,
    MADDISON_PROJECT_COVERAGE_START_YEAR,
    MADDISON_PROJECT_DEFAULT_VERSION,
    MADDISON_PROJECT_METADATA_NAME,
    MADDISON_PROJECT_OBSERVATION_FAMILY,
    MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
    MADDISON_PROJECT_PROXY_YEAR,
    MADDISON_PROJECT_SOURCE_KEY,
    MADDISON_PROJECT_SUPPORTED_FAMILIES,
    MADDISON_PROJECT_XLSX_ASSET_ID,
    MADDISON_PROJECT_XLSX_NAME,
    build_maddison_project_descriptor,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_maddison_project_observations

# ---------------------------------------------------------------------------
# Path + numeric helpers
# ---------------------------------------------------------------------------


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/maddison_project/`` bundle directory."""
    return Path(request.raw_root) / MADDISON_PROJECT_SOURCE_KEY


def _xlsx_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``mpd2023.xlsx`` path."""
    return _bundle_dir(request) / MADDISON_PROJECT_XLSX_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / MADDISON_PROJECT_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_expected_checksum(
    payload: dict[str, Any], xlsx_name: str,
) -> str | None:
    """Resolve the expected SHA-256 from the metadata checksum field.

    Accepts BOTH shapes for backward compatibility with bundles
    staged before the unified readiness contract:

    - Flat string: ``checksum_sha256="<hex>"``.
    - Per-file dict: ``checksum_sha256={"mpd2023.xlsx": "<hex>"}``.

    Returns the hex SHA-256 string or ``None`` when neither
    shape matches.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        per_file = value.get(xlsx_name)
        if isinstance(per_file, str) and per_file.strip():
            return per_file
    return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MaddisonProjectAdapter:
    """Unified-source Maddison Project Database 2023 adapter.

    Implements the ``SourceAdapter`` Protocol
    (docs/architecture/sources.md §5.6). The descriptor is a
    class attribute so the protocol's
    ``descriptor: SourceDescriptor`` member is satisfied
    without per-instance construction overhead.
    """

    descriptor: SourceDescriptor = build_maddison_project_descriptor()

    def check_ready(
        self, request: SourceIngestRequest,
    ) -> ReadinessResult:
        """Return a :class:`ReadinessResult` for the request-scoped bundle.

        The gate fires BEFORE the reader opens the workbook.
        Every blocker names the specific missing / invalid field
        or file so a developer can fix the upstream issue
        without reading source code.

        The gate enforces two failure classes (each surfaces a
        structured ``SourceWarning`` with ``severity='error'``
        in the ``ReadinessResult.errors`` tuple so the runner
        raises ``RuntimeError`` before calling ``read_raw`` /
        ``transform``):

        1. Bundle readiness --
           :func:`leaders_db.sources.adapters.maddison_project._readiness.check_metadata_well_formed`
           validates ``metadata.json`` + ``mpd2023.xlsx``
           (file presence, required fields, canonical metadata
           ``source_version``, checksum match).
        2. Source-version match --
           :func:`check_source_version` blocks when
           ``request.source_version`` is set and differs from
           the canonical ``2023`` (SRC-REQ-009; the legacy
           bundle does not encode a per-version stamp beyond
           ``metadata.json['source_version']`` so silently
           propagating an unsupported version into
           ``RawAsset.version`` /
           ``NormalizedObservation.source_version`` would lie
           to downstream scorers).

        Three request-scoping warning classes (NOT blockers)
        are surfaced on ``ReadinessResult.warnings`` so the
        runner carries them through to the final result:

        - ``unsupported_filter`` -- ``leaders=`` filter is
          unsupported for a country-year economic source.
        - ``maddison_project_proxy_year`` -- ``years=(2023,)``
          triggers the documented 1-year-gap proxy to 2022
          data; the per-observation ``proxy_year`` quality
          flag plus the ``requested_year`` /
          ``proxy_source_year`` extension fields surface the
          mapping on every affected observation.
        - ``year_absent`` -- ``years=`` outside the 1..2022
          coverage envelope emits zero rows (no multi-year
          stale-proxy fill).
        """
        bundle_dir = _bundle_dir(request)

        # Phase A: bundle readiness (file presence + metadata
        # fields + checksum match).
        ready, blocker, code = check_metadata_well_formed(
            bundle_dir, MADDISON_PROJECT_XLSX_NAME, MADDISON_PROJECT_DEFAULT_VERSION,
        )
        if not ready:
            return ReadinessResult(
                ready=False,
                errors=(
                    SourceWarning(
                        code=code or MISSING_RAW,
                        message=blocker or "Maddison Project bundle is not ready",
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
            canonical_version=MADDISON_PROJECT_DEFAULT_VERSION,
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
                            "canonical_version": MADDISON_PROJECT_DEFAULT_VERSION,
                        },
                    ),
                ),
            )

        # Phase C: request-scoping warnings (advisory only).
        warnings = list(collect_request_scoping_warnings(request))

        return ReadinessResult(
            ready=True,
            warnings=tuple(warnings),
            errors=(),
        )

    def read_raw(
        self, request: SourceIngestRequest,
    ) -> RawReadResult:
        """Open the staged ``mpd2023.xlsx`` and return the raw bundle.

        Lazy-imports the legacy reader so the unified package
        boundary is preserved. The long-format DataFrame (one
        row per ``(countrycode, year, variable_name)`` triple)
        is carried in :attr:`RawReadResult.payload` under
        ``"long_df"`` for the transform layer. The ``read_raw``
        call does NOT apply request year / country filters --
        the transform layer does that on the long frame so the
        request-scoping semantics stay in one place.
        """
        # Lazy import: keeps ``leaders_db.sources`` importable
        # without ``leaders_db.ingest`` (docs/architecture/sources.md
        # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
        from leaders_db.ingest.maddison_project_xlsx import (
            read_maddison_project,
        )

        xlsx_path = _xlsx_path(request)
        # Pass ``year=None`` so the legacy reader returns the
        # full long-format frame; the transform layer applies
        # request year / country filters + the documented
        # proxy semantics. This keeps the legacy reader's
        # behaviour intact while giving the new transform
        # full control over the request-scoping decisions.
        long_df = read_maddison_project(xlsx_path=xlsx_path)
        metadata = _read_metadata_payload(_metadata_path(request))

        expected_sha = _resolve_expected_checksum(
            metadata, MADDISON_PROJECT_XLSX_NAME,
        )
        if expected_sha is not None:
            actual_sha = hashlib.sha256(
                xlsx_path.read_bytes(),
            ).hexdigest()
            asset_checksum: str | None = (
                actual_sha
                if actual_sha.lower() == expected_sha.strip().lower()
                else None
            )
        else:
            asset_checksum = None

        asset = RawAsset(
            asset_id=MADDISON_PROJECT_XLSX_ASSET_ID,
            source_id=request.source_id,
            version=MADDISON_PROJECT_DEFAULT_VERSION,
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
                "long_df": long_df,
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
        """Convert the long raw frame into :class:`NormalizedObservation` records.

        Honors ``request.years`` and ``request.countries`` by
        filtering the long-format DataFrame after the legacy
        read (the legacy reader returns the full frame when
        called with ``year=None``; the new adapter owns the
        request-scoping logic). ``request.years=(2023,)`` is
        the documented 1-year-gap proxy: the transform maps
        the request to ``year=2022`` data and emits every
        2022 observation with the ``proxy_year`` quality flag
        plus the ``requested_year`` / ``proxy_source_year``
        extension fields so the mapping is never silent.
        ``request.years=(2024,)`` (or any year beyond 2022)
        emits zero observations (no multi-year stale-proxy
        fill); the readiness envelope already surfaced the
        ``YEAR_ABSENT`` warning.
        """
        if not isinstance(raw.payload, dict):
            raise ValueError(
                "MaddisonProjectAdapter.transform: raw.payload must "
                "be a dict carrying the long DataFrame under "
                "'long_df'."
            )
        long_df = raw.payload.get("long_df")
        if long_df is None:
            raise ValueError(
                "MaddisonProjectAdapter.transform: raw.payload has "
                "no 'long_df' key; read_raw must populate it."
            )
        metadata = raw.payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        # Apply the request year + country filters. The proxy
        # mapping is applied BEFORE the filter so a request
        # for ``years=(2023,)`` picks up the 2022 rows.
        years_arg: tuple[int, ...] | None = (
            tuple(int(y) for y in request.years)
            if request.years else None
        )
        countries_arg: tuple[str, ...] | None = (
            tuple(str(c) for c in request.countries)
            if request.countries else None
        )

        # Map the requested year(s) to the effective source-year
        # set we filter on. The Maddison 2023 release ends at
        # 2022; only the documented 2023 -> 2022 proxy is
        # permitted (multi-year stale-proxy fills are
        # forbidden by SRC-COV-003). Every other out-of-
        # coverage year is dropped silently -- the readiness
        # envelope already surfaced the YEAR_ABSENT warning
        # per offending year.
        effective_years: set[int] = set()
        if years_arg is not None:
            for year in years_arg:
                if year == MADDISON_PROJECT_PROXY_REQUESTED_YEAR:
                    effective_years.add(MADDISON_PROJECT_PROXY_YEAR)
                elif (
                    MADDISON_PROJECT_COVERAGE_START_YEAR
                    <= year
                    <= MADDISON_PROJECT_COVERAGE_END_YEAR
                ):
                    effective_years.add(year)
                # else: out-of-coverage (e.g. 2024); the
                # readiness envelope already emitted the
                # YEAR_ABSENT warning; we drop silently so no
                # rows are emitted for that year.

        # Filter the long-format DataFrame by the effective
        # year set + (optional) country filter. The legacy
        # long-format DataFrame has integer ``year`` and
        # string ``countrycode`` columns.
        filtered_df = long_df
        if years_arg is not None:
            # The caller requested a year filter. If every
            # requested year is out of coverage (e.g.
            # ``years=(2024,)``) the ``effective_years`` set
            # is empty -- we must NOT skip the filter in
            # that case, otherwise the full unfiltered frame
            # would leak through. Force an empty result
            # frame so the readiness envelope's YEAR_ABSENT
            # warning matches the zero-row observation count
            # (SRC-COV-002 / SRC-COV-003: no multi-year
            # stale-proxy fill, no silent proxy).
            if not effective_years:
                filtered_df = filtered_df.iloc[0:0]
            else:
                filtered_df = filtered_df.loc[
                    filtered_df["year"].astype(int).isin(effective_years),
                ]
        if countries_arg:
            country_set = set(countries_arg)
            filtered_df = filtered_df.loc[
                filtered_df["countrycode"].astype(str).isin(country_set),
            ]

        xlsx_path = raw.payload.get("xlsx_path")
        xlsx_path_value = (
            xlsx_path if isinstance(xlsx_path, Path) else None
        )
        return emit_maddison_project_observations(
            filtered_df, request, xlsx_path_value, metadata,
        )


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------


def create_maddison_project_adapter() -> MaddisonProjectAdapter:
    """Return a fresh :class:`MaddisonProjectAdapter` instance.

    The factory is the explicit seam callers use to wire
    Maddison into a :class:`SourceRegistry`. The package does
    NOT auto-register on import (the registry is passive by
    design -- see docs/architecture/sources.md §10.1).
    """
    return MaddisonProjectAdapter()


def register_maddison_project(registry: Any) -> MaddisonProjectAdapter:
    """Register the Maddison Project adapter against ``registry``.

    Convenience wrapper for tests and future composition code.
    Returns the registered adapter so callers can introspect
    it. Raises :class:`ValueError` if the registry already has
    a ``maddison_project`` slug registered (per
    ``docs/requirements/sources.md`` §9 SRC-REG-004).
    """
    adapter = create_maddison_project_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the legacy
# ``STAGE2_ADAPTERS`` keying convention. Callers may use either
# ``create_maddison_project_adapter()`` (preferred) or this
# module-level callable.
MADDISON_PROJECT_ADAPTER_FACTORY = create_maddison_project_adapter


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
    if not isinstance(MaddisonProjectAdapter(), SourceAdapter):
        raise TypeError(
            "MaddisonProjectAdapter does not satisfy the "
            "SourceAdapter Protocol; check the descriptor "
            "attribute and the check_ready / read_raw / "
            "transform method shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "MADDISON_PROJECT_ADAPTER_FACTORY",
    "MADDISON_PROJECT_COVERAGE_END_YEAR",
    "MADDISON_PROJECT_COVERAGE_START_YEAR",
    "MADDISON_PROJECT_DEFAULT_VERSION",
    "MADDISON_PROJECT_METADATA_NAME",
    "MADDISON_PROJECT_OBSERVATION_FAMILY",
    "MADDISON_PROJECT_PROXY_REQUESTED_YEAR",
    "MADDISON_PROJECT_PROXY_YEAR",
    "MADDISON_PROJECT_SOURCE_KEY",
    "MADDISON_PROJECT_SUPPORTED_FAMILIES",
    "MADDISON_PROJECT_XLSX_ASSET_ID",
    "MADDISON_PROJECT_XLSX_NAME",
    "MaddisonProjectAdapter",
    "build_maddison_project_descriptor",
    "create_maddison_project_adapter",
    "register_maddison_project",
]
