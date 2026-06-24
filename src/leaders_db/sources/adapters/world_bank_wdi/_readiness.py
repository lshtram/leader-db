"""Readiness gate orchestrator for the unified-source WDI adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes the
metadata-field validators in
:mod:`leaders_db.sources.adapters.world_bank_wdi._metadata_readiness`,
the cache-availability gate lives in
:mod:`leaders_db.sources.adapters.world_bank_wdi._cache_readiness`,
and the request-scoping warning builder lives here alongside
the source-version block.

Module split
------------

The readiness gate is decomposed into three sibling modules
so each one stays focused and under the 400-line convention:

- :mod:`_metadata_readiness` -- per-field ``metadata.json``
  validators (file presence, required-field shape, value
  format, checksum contract). Three canonical
  ``checksum_sha256`` shapes are accepted: ``null`` with an
  actionable ``checksum_note``, flat 64-char hex, per-file
  dict.
- :mod:`_cache_readiness` -- per-(year, indicator) cache
  enumeration, JSON-shape validation, and cache-policy
  gating (offline / cache-only).
- :mod:`_readiness` (this module) -- orchestration:
  :func:`check_metadata_well_formed` composes the metadata
  validators; :func:`check_source_version` enforces
  SRC-REQ-009; :func:`collect_request_scoping_warnings`
  surfaces the structured warning envelope.

For backward compatibility the symbols moved to
:mod:`_metadata_readiness` and :mod:`_cache_readiness` are
re-exported here so existing
``from ._readiness import _enumerate_cache_files`` /
``from ._readiness import check_metadata_well_formed`` calls
keep working without churn.

API / cache-source specific behavior
------------------------------------

WDI is an API-backed source with a per-(year, indicator) JSON
cache. The staged ``data/raw/world_bank_wdi/metadata.json``
records ``checksum_sha256: null`` together with a
``checksum_note`` documenting that checksums are managed per
cached response by the adapter/test fixtures, NOT as a single
bundle checksum. The readiness gate accepts three
``checksum_sha256`` shapes (full contract in
:mod:`_metadata_readiness`).

The cache-availability gate is offline / cache-only. Missing
or incomplete cache for an explicit-year request fails
readiness with the structured ``NETWORK_CACHE_UNAVAILABLE`` /
``MISSING_RAW`` code. ``cache_policy="refresh"`` /
``"no_cache"`` is NOT supported by the unified WDI adapter in
this slice: it fails readiness with the structured
``UNSUPPORTED_CACHE_POLICY`` code so the runner cannot silently
hit the network. The canonical request path is the cache-backed
``"offline_only"`` / ``"prefer_cache"`` policy documented in
``docs/requirements/sources.md`` §11 SRC-TYPE-002.

Request-scoping warnings
------------------------

The same three warning classes as the PWT / Maddison adapters:

- ``UNSUPPORTED_FILTER`` -- ``request.leaders`` is set; WDI
  has no leader dimension (SRC-REQ-005).
- ``YEAR_ABSENT`` -- each year in ``request.years`` outside
  the documented 1960+ coverage envelope emits zero rows plus
  a structured warning (SRC-COV-002 / SRC-COV-003: no silent
  stale-proxy fill).
- Source-version mismatch is NOT a warning -- it is a hard
  readiness blocker (SRC-REQ-009).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

# Re-export the cache-readiness public surface so existing
# callers (``from ._readiness import _enumerate_cache_files``
# / ``from ._readiness import check_cache_availability``) keep
# working without churn. The canonical definitions live in
# :mod:`_cache_readiness`.
from ._cache_readiness import (  # noqa: F401  (re-export)
    _check_explicit_year_cache_files,
    _check_year_cache_completeness,
    _discovered_corrupt_blocker,
    _enumerate_cache_files,
    _unsupported_cache_policy_blocker,
    _validate_cached_json_shape,
    check_cache_availability,
)
from ._descriptor import WORLD_BANK_WDI_COVERAGE_START_YEAR
from ._metadata_readiness import (
    REQUIRED_METADATA_FIELDS,
    UNSUPPORTED_VERSION,
    _checksum_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)


def check_metadata_well_formed(
    bundle_dir: Path, canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the WDI bundle's ``metadata.json`` (without inspecting the cache).

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle's metadata is fully
      well-formed (does NOT inspect the cache directory; see
      :func:`check_cache_availability` for that gate).
    - ``(False, blocker, MISSING_METADATA|<field>)`` when the
      bundle is missing ``metadata.json``, missing a required
      metadata field, has ``local_files`` that does not include
      ``cache/``, has ``ingestion_status != 'downloaded'``, or
      has an unsupported / mismatched ``source_version``.

    The third tuple element is the canonical warning code the
    adapter surfaces when ``ready=False``; the runner emits the
    full blocker text in the ``SourceWarning.message``.

    Note: the per-(year, indicator) cache file gate is owned by
    :func:`check_cache_availability` and only fires when
    ``request.years`` is explicit AND the cache policy allows
    cache-only reads.
    """
    metadata_path = bundle_dir / "metadata.json"

    # Phase A: presence check.
    presence_blocker = _presence_blocker(metadata_path)
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            f"World Bank WDI readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload)),
        ("ingestion_status", _ingestion_status_blocker(payload)),
        (
            "source_version",
            _metadata_source_version_blocker(
                payload, canonical_version,
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical WDI API v2 base URL",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the WDI license (CC BY 4.0 International)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the temporal + spatial coverage",
            ),
        ),
        ("checksum_sha256", _checksum_blocker(payload)),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="World Bank API v1"`` against a canonical
    WDI bundle whose metadata records
    ``"World Bank API v2; cached indicator responses"`` must
    surface a structured readiness error so the runner refuses
    to dispatch ``read_raw`` / ``transform``.

    Returns ``(message, code)`` when ``request.source_version``
    is set and differs from ``canonical_version``; returns
    ``None`` when ``request.source_version`` is ``None`` (the
    request will use the canonical version) or when it equals
    ``canonical_version`` (explicit match).
    """
    if request.source_version is None:
        return None
    if request.source_version == canonical_version:
        return None
    return (
        f"World Bank WDI readiness gate: requested source_version="
        f"{request.source_version!r} does not match the canonical "
        f"version {canonical_version!r}; per docs/requirements/"
        f"sources.md SRC-REQ-009, unsupported source-version "
        f"requests must fail readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use the "
        f"canonical default).",
        UNSUPPORTED_VERSION,
    )


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner carries
    them through to the final result even when the transform
    layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (WDI is a country-year source and has no leader
      dimension; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented WDI coverage envelope
      (1960+). Years outside the envelope emit zero rows plus a
      structured warning (SRC-COV-002 / SRC-COV-003: no
      silent stale-proxy fill).

    Note: an unsupported ``request.source_version`` is NOT a
    warning -- it is a hard readiness blocker (see
    :func:`check_source_version` and SRC-REQ-009).
    """
    warnings: list[SourceWarning] = []

    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "World Bank WDI is a country-year indicator "
                    "source; leader filters are not supported "
                    "and have been ignored."
                ),
                severity="warning",
                source_id=request.source_id,
                context={
                    "requested_leaders": list(request.leaders),
                },
            ),
        )

    if request.years:
        coverage_start = WORLD_BANK_WDI_COVERAGE_START_YEAR
        for year in request.years:
            year_int = int(year)
            if year_int < coverage_start:
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside the "
                            f"World Bank WDI coverage envelope "
                            f"({coverage_start}+); no "
                            f"observations will be emitted for "
                            f"this year (no stale-proxy fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": coverage_start,
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "MISSING_METADATA",
    "MISSING_RAW",
    "NETWORK_CACHE_UNAVAILABLE",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_CACHE_POLICY",
    "UNSUPPORTED_FILTER",
    "UNSUPPORTED_VERSION",
    "YEAR_ABSENT",
    "_enumerate_cache_files",
    "_validate_cached_json_shape",
    "check_cache_availability",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
