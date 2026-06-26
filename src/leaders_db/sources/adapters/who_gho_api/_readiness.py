"""Readiness checks for the clean WHO GHO API adapter.

Owns the metadata + cache-file enumeration, JSON-shape
validation, and cache-policy gating that run before the unified
cache-only reader opens the per-``(year, indicator)`` JSON
files. The orchestrator :func:`check_readiness` composes these
helpers in the documented phase order (metadata -> cache policy
-> explicit-year completeness / all-available-years shape).

The gate accepts BOTH the canonical primary metadata shape
(``source_version`` / ``source_url``) AND the legacy WHO GHO API
bundle shape (``version`` / ``source_url`` / ``sha256: null``)
so the existing staged bundle metadata does not need to be
rewritten as part of the migration. The per-field validators
probe the primary key first via the :func:`_coalesce` helper,
then fall back to the legacy alias.

Cache-policy semantics
----------------------

WHO GHO API is API-backed with a per-``(year, indicator)`` JSON
cache. The new runner is offline / cache-first by default and the
unified WHO GHO API adapter is offline / cache-only in this
slice. For supported cache policies (``"offline_only"`` /
``"prefer_cache"``), the gate blocks when:

1. The cache policy is ``"refresh"`` / ``"no_cache"``
   (unified WHO GHO API adapter never invokes the network;
   stage cache and re-run with a supported policy).
2. ``request.years`` is explicit AND the cache directory
   is missing.
3. ``request.years`` is explicit AND a requested year
   directory is missing.
4. ``request.years`` is explicit AND any catalog indicator's
   cache file is missing for a requested year.
5. ``request.years`` is explicit AND any required indicator's
   cache file is malformed (not a JSON object with a list
   ``value`` slot).
6. ``request.years=None`` (all-available-years semantics)
   AND no cache directory exists at all (zero cached years
   -> zero observations is a valid all-years outcome, but the
   cache directory must exist for the readiness gate to
   detect any staged years).
"""

from __future__ import annotations

import json
from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest, SourceWarning
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_FILTER,
)

from ._constants import (
    WHO_GHO_API_CACHE_DIR_NAME,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_INDICATOR_CODES,
    WHO_GHO_API_METADATA_NAME,
    WHO_GHO_API_METADATA_VERSION_MISMATCH,
    WHO_GHO_API_NETWORK_CACHE_UNAVAILABLE,
    WHO_GHO_API_SOURCE_KEY,
    WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
    WHO_GHO_API_UNSUPPORTED_VERSION,
)

UNSUPPORTED_VERSION = WHO_GHO_API_UNSUPPORTED_VERSION


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical WHO GHO API bundle directory."""
    return Path(request.raw_root) / WHO_GHO_API_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical WHO GHO API ``metadata.json`` path."""
    return bundle_dir(request) / WHO_GHO_API_METADATA_NAME


def cache_root(request: SourceIngestRequest) -> Path:
    """Return the canonical WHO GHO API cache root directory."""
    return bundle_dir(request) / WHO_GHO_API_CACHE_DIR_NAME


def cache_file(request: SourceIngestRequest, year: int, raw_column: str) -> Path:
    """Return the canonical WHO GHO API cache file path for one ``(year, raw_column)``."""
    return cache_root(request) / str(year) / f"{raw_column}.json"


def read_metadata(path: Path) -> dict[str, object]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coalesce(payload: dict[str, object], primary: str, legacy: str | None = None) -> object:
    """Return the first non-None value among ``primary`` and ``legacy`` keys."""
    value = payload.get(primary)
    if value is not None:
        return value
    if legacy is not None:
        return payload.get(legacy)
    return None


def metadata_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    """Validate the bundle's ``metadata.json`` shape.

    Returns ``(blocker_message, code)`` when the metadata is
    missing, unparseable, or carries an unsupported source version.
    Returns ``None`` for a well-formed metadata file.

    The gate accepts BOTH the canonical primary metadata shape
    (``source_version`` / ``source_url``) AND the legacy WHO GHO
    API bundle shape (``version`` / ``source_url``). The
    per-field version probe uses the :func:`_coalesce` helper.
    """
    path = metadata_path(request)
    if not path.is_file():
        return f"WHO GHO API metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"WHO GHO API metadata.json is not parseable at {path}", MISSING_METADATA
    version = _coalesce(payload, "source_version", "version")
    if not isinstance(version, str) or not version.strip():
        return (
            "WHO GHO API metadata version must be the canonical "
            f"{WHO_GHO_API_DEFAULT_VERSION!r}; missing or empty.",
        ), WHO_GHO_API_METADATA_VERSION_MISMATCH
    if version.strip() != WHO_GHO_API_DEFAULT_VERSION:
        return (
            "WHO GHO API metadata version must be "
            f"{WHO_GHO_API_DEFAULT_VERSION!r}; got {version.strip()!r}",
        ), WHO_GHO_API_METADATA_VERSION_MISMATCH
    return None


def _validate_cached_json_shape(cache_file: Path) -> tuple[str, str] | None:
    """Validate a staged WHO GHO API JSON cache file's shape.

    Returns ``(blocker_message, MISSING_RAW)`` when the file is
    missing / unreadable / non-JSON / not a JSON object with a
    list ``value`` slot. Returns ``None`` for a valid WHO GHO API
    response (``{"@odata.context": ..., "value": [...records...]}``).

    The check is intentionally minimal: anything stricter belongs
    inside the cache-only parser, not the readiness gate. The
    gate just needs to prove the file is JSON + structurally
    looks like an OData response so the cache-only read path does
    not silently fall through to HTTP.
    """
    if not cache_file.is_file():
        return (
            f"WHO GHO API readiness gate: cache file missing at "
            f"{cache_file}; the API cache is incomplete. Re-stage "
            f"the cache before running ingestion.",
        ), MISSING_RAW
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            "WHO GHO API readiness gate: cache file "
            f"{cache_file} is malformed ({type(exc).__name__}: "
            f"{exc}); the cache-only read path refuses to silently "
            f"fall through to HTTP. Repair or re-stage the cache "
            f"file before running ingestion.",
        ), MISSING_RAW
    if not isinstance(payload, dict):
        return (
            "WHO GHO API readiness gate: cache file "
            f"{cache_file} is not a JSON object (got "
            f"{type(payload).__name__}); the cache-only read path "
            f"refuses to silently fall through to HTTP. Re-stage a "
            f"verbatim WHO GHO OData response.",
        ), MISSING_RAW
    value_slot = payload.get("value")
    if not isinstance(value_slot, list):
        return (
            "WHO GHO API readiness gate: cache file "
            f"{cache_file} does not carry a list 'value' slot "
            f"(got {type(value_slot).__name__}); the cache-only "
            f"read path refuses to silently fall through to HTTP. "
            f"Re-stage a verbatim WHO GHO OData response.",
        ), MISSING_RAW
    return None


def _enumerate_cache_files(
    cache_root_path: Path,
) -> tuple[list[tuple[int, str, Path]], list[tuple[Path, str, str]]]:
    """Enumerate every valid JSON cache file under ``cache_root_path``.

    Walks ``<cache_root>/<year>/<IndicatorCode>.json`` for every
    integer year subdirectory, parses each file's JSON, and
    partitions the discovered files into:

    - ``valid``: a sorted list of ``(year, code, path)`` tuples
      whose JSON is a WHO GHO OData response. Used by
      :func:`WhoGhoApiAdapter.read_raw` to read exactly these
      ``(year, indicator)`` pairs through the cache-only path;
      the adapter never falls through to HTTP for any pair not
      present in ``valid``.
    - ``malformed``: a list of ``(path, error_kind, message)``
      tuples for files that exist on disk but fail JSON shape
      validation. Surfaced as a structured readiness blocker so
      a developer can repair or re-stage the file.

    Missing year directories and empty year directories are
    silently ignored (the readiness gate's existing per-year
    completeness check fires for explicit-year requests; for
    ``years=None`` an empty cache is a valid "no data yet"
    outcome and surfaces zero observations).

    The function NEVER invokes the network; it is a pure
    disk-and-JSON enumeration pass that satisfies the
    "enumerate valid cache files and pass only those exact
    years/indicator codes through production paths" requirement.
    """
    valid: list[tuple[int, str, Path]] = []
    malformed: list[tuple[Path, str, str]] = []
    if not cache_root_path.is_dir():
        return valid, malformed
    for year_dir in sorted(cache_root_path.iterdir(), key=lambda p: p.name):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year_int = int(year_dir.name)
        for cache_file in sorted(year_dir.iterdir(), key=lambda p: p.name):
            if not cache_file.is_file():
                continue
            if cache_file.suffix != ".json":
                continue
            code = cache_file.stem
            blocker = _validate_cached_json_shape(cache_file)
            if blocker is None:
                valid.append((year_int, code, cache_file))
            else:
                message, _ = blocker
                if "malformed" in message:
                    kind = "json_decode_error"
                elif "not a JSON object" in message:
                    kind = "shape_error"
                elif "non-list 'value'" in message:
                    kind = "value_slot_error"
                else:
                    kind = "unknown"
                malformed.append((cache_file, kind, message))
    return valid, malformed


def _unsupported_cache_policy_blocker(
    cache_policy: str, cache_root_path: Path,
) -> tuple[str, str]:
    """Return the structured blocker for unsupported cache policies."""
    return (
        "WHO GHO API readiness gate: cache_policy="
        f"{cache_policy!r} is not supported by the "
        "unified WHO GHO API adapter in this slice; the adapter "
        "is offline / cache-only and "
        "WhoGhoApiAdapter.read_raw never invokes the network. "
        "Stage the per-(year, indicator) JSON cache under "
        f"{cache_root_path}/<year>/<IndicatorCode>.json and re-run "
        "with cache_policy='offline_only' or 'prefer_cache' "
        "(the documented safe default)."
    ), WHO_GHO_API_UNSUPPORTED_CACHE_POLICY


def cache_policy_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values."""
    if request.cache_policy in {"refresh", "no_cache"}:
        return _unsupported_cache_policy_blocker(
            request.cache_policy, cache_root(request),
        )
    return None


def _check_explicit_year_cache_files(
    request: SourceIngestRequest,
    *,
    cache_root_path: Path,
    indicator_codes: tuple[str, ...],
) -> tuple[bool, str | None, str | None]:
    """Validate the per-year, per-indicator cache gate for an explicit-year request."""
    if not cache_root_path.is_dir():
        return False, (
            f"WHO GHO API readiness gate: cache directory missing "
            f"at {cache_root_path} for cache_policy="
            f"{request.cache_policy!r}; place the per-(year, "
            f"indicator) JSON cache under "
            f"{cache_root_path}/<year>/<IndicatorCode>.json before "
            f"running ingestion."
        ), WHO_GHO_API_NETWORK_CACHE_UNAVAILABLE

    missing_year_dirs: list[int] = []
    for year in request.years:
        year_int = int(year)
        year_dir = cache_root_path / str(year_int)
        if not year_dir.is_dir():
            missing_year_dirs.append(year_int)
            continue
        blocker = _check_year_cache_completeness(
            year_int, year_dir, indicator_codes,
            cache_policy=request.cache_policy,
        )
        if blocker is not None:
            return False, blocker[0], blocker[1]

    if missing_year_dirs:
        return False, (
            f"WHO GHO API readiness gate: cache year "
            f"directory(ies) missing for requested years "
            f"{missing_year_dirs!r} under {cache_root_path}; the "
            f"API cache is incomplete. Re-stage the cache for "
            f"those years before running ingestion."
        ), MISSING_RAW
    return True, None, None


def _check_year_cache_completeness(
    year_int: int,
    year_dir: Path,
    indicator_codes: tuple[str, ...],
    *,
    cache_policy: str,
) -> tuple[str, str] | None:
    """Check one year's cache completeness for every catalog indicator.

    Returns ``None`` if every required indicator's cache file
    exists and validates as WHO GHO API JSON; otherwise returns
    a structured ``(blocker_message, MISSING_RAW)`` blocker.
    """
    for code in indicator_codes:
        cache_file = year_dir / f"{code}.json"
        shape_blocker = _validate_cached_json_shape(cache_file)
        if shape_blocker is not None:
            message, _ = shape_blocker
            return (
                f"{message} Required by the explicit year="
                f"{year_int} indicator={code!r} request under "
                f"cache_policy={cache_policy!r}; re-stage the "
                f"cache before running ingestion."
            ), MISSING_RAW
    return None


def check_cache_availability(
    request: SourceIngestRequest,
) -> tuple[bool, str | None, str | None]:
    """Validate the per-``(year, indicator)`` cache gate for the request.

    Returns ``(ready, blocker, code)`` so the adapter can surface
    a structured :class:`SourceWarning` with the canonical code.

    For ``years=None`` with no cache directory at all the gate
    surfaces a ``NETWORK_CACHE_UNAVAILABLE`` readiness blocker
    because the cache-only reader cannot enumerate any years
    (this is consistent with the WDI per-``(year, indicator)``
    cache policy: ``years=None`` with no cache is rejected so a
    caller cannot accidentally bypass the cache gate). For
    ``years=None`` with a partial / discovered cache (some files
    valid, some missing) the gate accepts: ``read_raw`` uses the
    local cache-only parser and reads only the ``(year,
    indicator)`` pairs that are present on disk.

    The unsupported-policy branch still fires for ``years=None``
    so callers cannot bypass it with the all-years semantics.
    """
    cache_root_path = cache_root(request)

    if request.cache_policy in {"refresh", "no_cache"}:
        return False, *_unsupported_cache_policy_blocker(
            request.cache_policy, cache_root_path,
        )

    if not request.years:
        if not cache_root_path.is_dir():
            return False, (
                f"WHO GHO API readiness gate: cache directory "
                f"missing at {cache_root_path} for cache_policy="
                f"{request.cache_policy!r}; place the per-(year, "
                f"indicator) JSON cache under "
                f"{cache_root_path}/<year>/<IndicatorCode>.json "
                f"before running ingestion."
            ), NETWORK_CACHE_UNAVAILABLE
        _valid, malformed = _enumerate_cache_files(cache_root_path)
        if malformed:
            return False, *_discovered_corrupt_blocker(
                malformed, request.cache_policy,
            )
        return True, None, None

    return _check_explicit_year_cache_files(
        request,
        cache_root_path=cache_root_path,
        indicator_codes=WHO_GHO_API_INDICATOR_CODES,
    )


def _discovered_corrupt_blocker(
    malformed: list[tuple[Path, str, str]],
    cache_policy: str,
) -> tuple[str, str]:
    """Build the structured blocker for ``years=None`` + a
    discovered corrupt cache file."""
    _bad_path, _kind, full_message = malformed[0]
    extra = (
        f" ({len(malformed)} malformed cache file(s) discovered "
        f"total; see readiness context)"
        if len(malformed) > 1 else ""
    )
    return (
        f"{full_message} The cache-only read path refuses to "
        f"silently fall through to HTTP for cache_policy="
        f"{cache_policy!r}; repair or re-stage the malformed "
        f"cache file(s) before re-running{extra}."
    ), MISSING_RAW


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version."""
    if request.source_version is None:
        return None
    if request.source_version == WHO_GHO_API_DEFAULT_VERSION:
        return None
    return (
        "WHO GHO API request source_version must be "
        f"{WHO_GHO_API_DEFAULT_VERSION!r}; got {request.source_version!r}",
    ), WHO_GHO_API_UNSUPPORTED_VERSION


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope."""
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(SourceWarning(
            code=UNSUPPORTED_FILTER,
            message=(
                "WHO GHO API is country-year data; leader filters "
                "are ignored."
            ),
            severity="warning",
            source_id=request.source_id,
            context={"requested_leaders": list(request.leaders)},
        ))
    return tuple(warnings)


__all__ = [
    "UNSUPPORTED_VERSION",
    "bundle_dir",
    "cache_file",
    "cache_policy_blocker",
    "cache_root",
    "check_cache_availability",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
