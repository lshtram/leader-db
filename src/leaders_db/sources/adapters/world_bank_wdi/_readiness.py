"""Readiness gate for the unified-source World Bank WDI adapter.

This module owns the per-field metadata validation that runs
BEFORE the legacy reader opens the per-(year, indicator) cache
files. Every blocker names the specific missing / invalid field
or file so a developer can fix the upstream issue without
reading source code.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter` to
keep the adapter class focused on the lifecycle methods and
respect the documented 400-line module convention.

API / cache-source specific behavior
------------------------------------

WDI is an API-backed source with a per-(year, indicator) JSON
cache. The staged ``data/raw/world_bank_wdi/metadata.json``
records ``checksum_sha256: null`` together with a
``checksum_note`` documenting that checksums are managed per
cached response by the adapter/test fixtures, NOT as a single
bundle checksum. The readiness gate accepts both shapes for
backward compatibility:

- ``checksum_sha256: null`` + ``checksum_note`` (canonical WDI
  shape).
- ``checksum_sha256: "<hex>"`` (flat string).
- ``checksum_sha256: {"<indicator.json>": "<hex>"}`` (per-file
  dict, the same shape the Maddison bundle accepts).

The cache-availability gate fires when ``request.years`` is
explicit AND the cache policy is not ``"refresh"`` /
``"no_cache"``: missing or incomplete cache fails readiness
with the structured ``NETWORK_CACHE_UNAVAILABLE`` /
``MISSING_RAW`` code so the runner refuses to dispatch
``read_raw`` / ``transform``. This honors
``docs/requirements/sources.md`` §11 SRC-TYPE-002 (API sources
use cache policy) and the new-runner offline-by-default
contract documented in the slice task plan.

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

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._descriptor import (
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_COVERAGE_START_YEAR,
)

# Required metadata fields. Mirrors the Maddison / PWT
# readiness contract: the union of fields the unified gate
# inspects before parsing the legacy reader. ``checksum_sha256``
# is optional for API sources (the canonical WDI bundle carries
# ``null`` + ``checksum_note``), so it is NOT in this tuple.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
)

# Module-local structured warning code used to reject an
# unsupported request source-version per SRC-REQ-009. Mirrors
# the PWT / Maddison UNSUPPORTED_VERSION code so the WDI
# readiness envelope stays consistent with the rest of the
# unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Path,
) -> tuple[str, str] | None:
    """Block if ``metadata.json`` is missing from the bundle."""
    if not metadata_path.is_file():
        return (
            f"World Bank WDI readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/world_bank_wdi/metadata.json before running "
            "Stage 2.",
            MISSING_METADATA,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                f"World Bank WDI readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the canonical cache marker.

    The WDI bundle's ``local_files`` field is documented as
    ``["cache/"]`` in the staged metadata. We accept the
    trailing-slash cache directory name; we ALSO accept the
    bare ``"cache"`` (without slash) for forward compatibility.
    """
    local_files = payload.get("local_files")
    if not isinstance(local_files, list):
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'local_files' must be a list; got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    accepted = {WORLD_BANK_WDI_CACHE_DIR_NAME, f"{WORLD_BANK_WDI_CACHE_DIR_NAME}/"}
    if not any(item in accepted for item in local_files if isinstance(item, str)):
        return (
            f"World Bank WDI readiness gate: metadata.json "
            f"'local_files' must include {WORLD_BANK_WDI_CACHE_DIR_NAME!r}; "
            f"got {local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'ingestion_status' must be 'downloaded'; got "
            f"{payload.get('ingestion_status')!r}.",
            MISSING_METADATA,
        )
    return None


def _non_empty_string_blocker(
    payload: dict[str, Any],
    field: str,
    expected: str,
) -> tuple[str, str] | None:
    """Block if ``payload[field]`` is not a non-empty string."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return (
            f"World Bank WDI readiness gate: metadata.json '{field}' "
            f"must be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "World Bank WDI readiness gate: metadata.json "
            f"'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"World Bank WDI readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified World Bank WDI adapter supports only "
            f"canonical version {canonical_version!r}. Re-stage a "
            f"WDI bundle with the canonical source_version or "
            f"correct metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


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
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def check_cache_availability(
    request: SourceIngestRequest,
    *,
    bundle_dir: Path,
    indicator_codes: tuple[str, ...],
) -> tuple[bool, str | None, str | None]:
    """Validate the per-(year, indicator) cache gate for explicit-year requests.

    WDI is API-backed with a per-(year, indicator) JSON cache.
    The new runner is offline / cache-first by default; for
    explicit-year requests with ``cache_policy`` of
    ``"offline_only"`` or ``"prefer_cache"``, this gate blocks
    when:

    1. The cache directory does not exist.
    2. A requested year directory does not exist.
    3. Any catalog indicator's cache file is missing for a
       requested year (the indicator catalog has 14 indicators;
       complete cache means all 14 ``<CODE>.json`` files exist
       under each requested year dir).

    For ``cache_policy="refresh"`` or ``"no_cache"``, the gate
    is intentionally a no-op so the legacy HTTP path can run
    (not exercised by tests in this slice).

    For ``years=None`` (all-years semantics per SRC-REQ-003),
    the gate is also a no-op -- the readiness envelope accepts
    "all available years in cache" without enumerating which
    years are present.

    Returns ``(ready, blocker, code)``. ``code`` is the warning
    code string (``MISSING_RAW`` or
    ``NETWORK_CACHE_UNAVAILABLE``) so the adapter can surface
    a structured ``SourceWarning`` with the canonical code.
    """
    cache_root = bundle_dir / WORLD_BANK_WDI_CACHE_DIR_NAME

    # No explicit year filter -- the readiness envelope accepts
    # all-available-years semantics (SRC-REQ-003). The transform
    # layer enumerates the cache at read time; readiness does
    # not gate that.
    if not request.years:
        return True, None, None

    # Refresh / no_cache policies allow the legacy HTTP path.
    # The slice does not exercise network I/O; production
    # callers that opt in to ``refresh`` / ``no_cache`` accept
    # that the new adapter may hit the network on read_raw.
    if request.cache_policy in {"refresh", "no_cache"}:
        return True, None, None

    # The cache root must exist. Per SRC-TYPE-002 + the
    # offline-by-default contract, an API source without a
    # cache directory is a blocker (not silently hit the
    # network).
    if not cache_root.is_dir():
        return False, (
            f"World Bank WDI readiness gate: cache directory "
            f"missing at {cache_root} for cache_policy="
            f"{request.cache_policy!r}; place the per-(year, "
            f"indicator) JSON cache under "
            f"{cache_root}/<year>/<CODE>.json before running "
            f"ingestion, or set cache_policy to 'refresh' / "
            f"'no_cache' to allow the legacy HTTP path."
        ), NETWORK_CACHE_UNAVAILABLE

    # Each requested year must have a complete cache directory.
    # Years outside the documented 1960+ coverage envelope
    # are skipped: the YEAR_ABSENT warning on the readiness
    # envelope already covers them (no stale-proxy fill per
    # SRC-COV-003), so the cache gate should not also block.
    missing_year_dirs: list[int] = []
    for year in request.years:
        year_int = int(year)
        if year_int < WORLD_BANK_WDI_COVERAGE_START_YEAR:
            # Out of coverage -- the YEAR_ABSENT warning is
            # surfaced on the readiness envelope via
            # ``collect_request_scoping_warnings``. The
            # transform layer drops these years silently so no
            # rows are emitted (no stale-proxy fill). Skip the
            # cache check here so the envelope's zero-obs
            # outcome matches the warning, not a separate
            # MISSING_RAW blocker.
            continue
        year_dir = cache_root / str(year_int)
        if not year_dir.is_dir():
            missing_year_dirs.append(year_int)
            continue
        # All catalog indicators must have a cache file under
        # the year dir. We only block when at least one file is
        # missing; the partial-cache case is also a blocker.
        for code in indicator_codes:
            cache_file = year_dir / f"{code}.json"
            if not cache_file.is_file():
                # First missing indicator for this year -- emit
                # one blocker message naming the missing file so
                # the developer can act on it. We do not surface
                # every missing file (could be long); one
                # actionable error per year is enough.
                return False, (
                    f"World Bank WDI readiness gate: cache file "
                    f"missing for year={year_int} indicator="
                    f"{code!r} at {cache_file} for cache_policy="
                    f"{request.cache_policy!r}; the API cache is "
                    f"incomplete. Either re-stage the cache for "
                    f"year {year_int} or set cache_policy to "
                    f"'refresh' / 'no_cache' to allow the legacy "
                    f"HTTP path."
                ), MISSING_RAW

    if missing_year_dirs:
        return False, (
            f"World Bank WDI readiness gate: cache year "
            f"directory(ies) missing for requested years "
            f"{missing_year_dirs!r} under {cache_root}; the "
            f"API cache is incomplete. Re-stage the cache for "
            f"those years or set cache_policy to 'refresh' / "
            f"'no_cache' to allow the legacy HTTP path."
        ), MISSING_RAW

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
    "MISSING_RAW",
    "NETWORK_CACHE_UNAVAILABLE",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_FILTER",
    "UNSUPPORTED_VERSION",
    "YEAR_ABSENT",
    "check_cache_availability",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
