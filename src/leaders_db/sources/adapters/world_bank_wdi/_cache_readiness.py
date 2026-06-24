"""World Bank WDI cache-availability readiness gate.

Owns the per-(year, indicator) cache enumeration, JSON-shape
validation, and cache-policy gating that run before the unified
cache-only reader opens the cache files. The orchestrator
:func:`check_cache_availability` composes these helpers in
the documented phase order (policy check → explicit-year
completeness / discovered-file shape).

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi._readiness`
so the metadata gate can live in :mod:`_metadata_readiness`
and the umbrella orchestrator stays focused on lifecycle
wiring. The split keeps each module under the 400-line
convention.
"""

from __future__ import annotations

import json
from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest
from leaders_db.sources.warnings import (
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
    UNSUPPORTED_CACHE_POLICY,
)

from ._descriptor import (
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_COVERAGE_START_YEAR,
)


def _validate_cached_json_shape(
    cache_file: Path,
) -> tuple[str, str] | None:
    """Validate a staged WDI v2 JSON cache file's shape.

    Returns ``(blocker_message, MISSING_RAW)`` when the file is
    missing / unreadable / non-JSON / not a 2-element list with
    a list ``data`` slot. Returns ``None`` for a valid WDI v2
    2-element ``[metadata, data]`` response. The check is
    intentionally minimal: anything stricter belongs inside
    the cache-only parser, not the readiness gate.
    """
    if not cache_file.is_file():
        return (
            f"World Bank WDI readiness gate: cache file "
            f"missing at {cache_file}; the API cache is "
            f"incomplete. Re-stage the cache before running "
            f"ingestion."
        ), MISSING_RAW
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            "World Bank WDI readiness gate: cache file "
            f"{cache_file} is malformed ({type(exc).__name__}: "
            f"{exc}); the cache-only read path refuses to "
            f"silently fall through to HTTP. Repair or "
            f"re-stage the cache file before running ingestion."
        ), MISSING_RAW
    if not isinstance(payload, list) or len(payload) < 2:
        return (
            "World Bank WDI readiness gate: cache file "
            f"{cache_file} is not a WDI v2 2-element array "
            f"(got {type(payload).__name__}); the cache-only "
            f"read path refuses to silently fall through to "
            f"HTTP. Re-stage a verbatim WDI v2 response."
        ), MISSING_RAW
    if not isinstance(payload[1], list):
        return (
            "World Bank WDI readiness gate: cache file "
            f"{cache_file} has a non-list 'data' slot "
            f"(got {type(payload[1]).__name__}); the cache-only "
            f"read path refuses to silently fall through to "
            f"HTTP. Re-stage a verbatim WDI v2 response."
        ), MISSING_RAW
    return None


def _enumerate_cache_files(
    cache_root: Path,
) -> tuple[list[tuple[int, str, Path]], list[tuple[Path, str, str]]]:
    """Enumerate every valid JSON cache file under ``cache_root``.

    Walks ``<cache_root>/<year>/<CODE>.json`` for every integer
    year subdirectory, parses each file's JSON, and partitions
    the discovered files into:

    - ``valid``: a sorted list of ``(year, code, path)`` tuples
      whose JSON is a WDI v2 2-element ``[metadata, data]``
      response. Used by :func:`WDIAdapter.read_raw` to read
      exactly these ``(year, indicator)`` pairs through the
      cache-only path; the adapter never falls through to HTTP
      for any pair not present in ``valid``.
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
    years/indicator codes through production paths" requirement
    from the comprehensive cache-policy remediation.
    """
    valid: list[tuple[int, str, Path]] = []
    malformed: list[tuple[Path, str, str]] = []
    if not cache_root.is_dir():
        return valid, malformed
    for year_dir in sorted(
        cache_root.iterdir(), key=lambda p: p.name,
    ):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year_int = int(year_dir.name)
        for cache_file in sorted(
            year_dir.iterdir(), key=lambda p: p.name,
        ):
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
                # Reduce the error_kind to the failure class so
                # the readiness envelope can surface it in the
                # structured ``context`` field without leaking
                # the full blocker text.
                if "malformed" in message:
                    kind = "json_decode_error"
                elif "not a WDI v2" in message:
                    kind = "shape_error"
                elif "non-list 'data'" in message:
                    kind = "data_slot_error"
                else:
                    kind = "unknown"
                malformed.append((cache_file, kind, message))
    return valid, malformed


def _unsupported_cache_policy_blocker(
    cache_policy: str, cache_root: Path,
) -> tuple[str, str]:
    """Return the structured blocker for unsupported cache policies.

    Shared helper so the policy gate stays in one place (per
    :func:`check_cache_availability` requirements: refresh /
    no_cache are NOT supported by the unified WDI adapter in
    this slice, regardless of ``years=``).
    """
    return (
        "World Bank WDI readiness gate: cache_policy="
        f"{cache_policy!r} is not supported by the "
        "unified World Bank WDI adapter in this slice; the "
        "adapter is offline / cache-only and "
        "WDIAdapter.read_raw never invokes the network. "
        "Stage the per-(year, indicator) JSON cache under "
        f"{cache_root}/<year>/<CODE>.json and re-run with "
        "cache_policy='offline_only' or 'prefer_cache' "
        "(the documented safe default)."
    ), UNSUPPORTED_CACHE_POLICY


def _discovered_corrupt_blocker(
    malformed: list[tuple[Path, str, str]],
    cache_policy: str,
) -> tuple[str, str]:
    """Build the structured blocker for ``years=None`` + a
    discovered corrupt cache file.

    Surfaces the first malformed file's message as the
    developer-visible text and includes a count suffix when
    more than one malformed file exists so the developer can
    plan to repair them all in one pass without re-running
    readiness.
    """
    _bad_path, _kind, full_message = malformed[0]
    extra = (
        f" ({len(malformed)} malformed cache file(s) "
        f"discovered total; see readiness context)"
        if len(malformed) > 1 else ""
    )
    return (
        f"{full_message} The cache-only read path "
        f"refuses to silently fall through to HTTP "
        f"for cache_policy="
        f"{cache_policy!r}; repair or "
        f"re-stage the malformed cache file(s) before "
        f"re-running{extra}."
    ), MISSING_RAW


def _check_explicit_year_cache_files(
    cache_root: Path,
    *,
    request: SourceIngestRequest,
    indicator_codes: tuple[str, ...],
) -> tuple[bool, str | None, str | None]:
    """Validate the per-year, per-indicator cache gate for an
    explicit-year request.

    Returns ``(ready, blocker, code)``. The helper splits the
    explicit-year path out of :func:`check_cache_availability`
    so the top-level gate stays under the documented return
    ceiling (PLR0911). Year directories outside the documented
    1960+ coverage envelope are skipped (the readiness envelope
    already surfaces a ``YEAR_ABSENT`` warning per offending
    year; the cache gate must not double-block).
    """
    if not cache_root.is_dir():
        return False, (
            f"World Bank WDI readiness gate: cache directory "
            f"missing at {cache_root} for cache_policy="
            f"{request.cache_policy!r}; place the per-(year, "
            f"indicator) JSON cache under "
            f"{cache_root}/<year>/<CODE>.json before running "
            f"ingestion."
        ), NETWORK_CACHE_UNAVAILABLE

    missing_year_dirs: list[int] = []
    for year in request.years:
        year_int = int(year)
        if year_int < WORLD_BANK_WDI_COVERAGE_START_YEAR:
            continue
        year_dir = cache_root / str(year_int)
        if not year_dir.is_dir():
            missing_year_dirs.append(year_int)
            continue
        blocker = _check_year_cache_completeness(
            year_int, year_dir, indicator_codes,
            cache_policy=request.cache_policy,
        )
        if blocker is not None:
            return blocker

    if missing_year_dirs:
        return False, (
            f"World Bank WDI readiness gate: cache year "
            f"directory(ies) missing for requested years "
            f"{missing_year_dirs!r} under {cache_root}; the "
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
) -> tuple[bool, str, str] | None:
    """Check one year's cache completeness for every catalog
    indicator. Returns ``None`` if every required indicator's
    cache file exists and validates as WDI v2 JSON; otherwise
    returns a structured ``(False, blocker_message, MISSING_RAW)``
    blocker.
    """
    for code in indicator_codes:
        cache_file = year_dir / f"{code}.json"
        if not cache_file.is_file():
            return False, (
                f"World Bank WDI readiness gate: cache file "
                f"missing for year={year_int} indicator="
                f"{code!r} at {cache_file} for cache_policy="
                f"{cache_policy!r}; the API cache is "
                f"incomplete. Re-stage the cache for "
                f"year {year_int} before running ingestion."
            ), MISSING_RAW
        shape_blocker = _validate_cached_json_shape(cache_file)
        if shape_blocker is not None:
            message, _ = shape_blocker
            return False, (
                f"{message} Required by the explicit "
                f"year={year_int} indicator={code!r} "
                f"request under cache_policy="
                f"{cache_policy!r}; re-stage the "
                f"cache before running ingestion."
            ), MISSING_RAW
    return None


def check_cache_availability(
    request: SourceIngestRequest,
    *,
    bundle_dir: Path,
    indicator_codes: tuple[str, ...],
) -> tuple[bool, str | None, str | None]:
    """Validate the per-(year, indicator) cache gate for the request.

    WDI is API-backed with a per-(year, indicator) JSON cache.
    The new runner is offline / cache-first by default and the
    unified WDI adapter is offline / cache-only in this slice.
    For supported cache policies (``"offline_only"`` /
    ``"prefer_cache"``), this gate blocks when:

    1. The cache policy is ``"refresh"`` / ``"no_cache"``
       (unified WDI adapter never invokes the network;
       stage cache and re-run with a supported policy).
    2. ``request.years`` is explicit AND the cache directory
       is missing.
    3. ``request.years`` is explicit AND a requested year
       directory is missing.
    4. ``request.years`` is explicit AND any catalog
       indicator's cache file is missing for a requested year.
    5. ``request.years`` is explicit AND any required
       indicator's cache file is malformed (not a WDI v2
       2-element JSON array).
    6. ``request.years=None`` (all-available-years semantics)
       AND any discovered cache file on disk is malformed
       (the cache-only read path refuses to silently fall
       through to HTTP).

    The gate returns ``(ready, blocker, code)``; ``code`` is
    the warning code string (``MISSING_RAW``,
    ``NETWORK_CACHE_UNAVAILABLE``, or
    ``UNSUPPORTED_CACHE_POLICY``) so the adapter can surface
    a structured :class:`SourceWarning` with the canonical
    code.

    For ``years=None`` with no cache directory at all (or a
    cache directory with no files) the gate accepts the
    "all-available-years" semantics per SRC-REQ-003: the
    runner emits zero observations and the request is
    successful. For ``years=None`` with a partial / discovered
    cache (some files valid, some missing) the gate also
    accepts: ``WDIAdapter.read_raw`` uses the local cache-only
    parser and reads only the ``(year, indicator)`` pairs that
    are present on disk. The unsupported-policy branch still
    fires for ``years=None`` so callers cannot bypass it with
    the all-years semantics.
    """
    cache_root = bundle_dir / WORLD_BANK_WDI_CACHE_DIR_NAME

    # Cache-policy gate. Fires regardless of ``years=`` so
    # callers cannot bypass the unsupported-policy gate with
    # all-years semantics.
    if request.cache_policy in {"refresh", "no_cache"}:
        return False, *_unsupported_cache_policy_blocker(
            request.cache_policy, cache_root,
        )

    # No explicit year filter -- the readiness envelope accepts
    # all-available-years semantics (SRC-REQ-003) for the
    # supported policies. We still enumerate the cache files
    # to validate their JSON shapes: a corrupt discovered file
    # malformed discovered cache entries are rejected up front
    # to preserve the all-years cache-only contract.
    if not request.years:
        if not cache_root.is_dir():
            return True, None, None
        _valid, malformed = _enumerate_cache_files(cache_root)
        if malformed:
            return False, *_discovered_corrupt_blocker(
                malformed, request.cache_policy,
            )
        return True, None, None

    return _check_explicit_year_cache_files(
        cache_root,
        request=request,
        indicator_codes=indicator_codes,
    )


__all__ = [
    "MISSING_RAW",
    "NETWORK_CACHE_UNAVAILABLE",
    "UNSUPPORTED_CACHE_POLICY",
    "_check_explicit_year_cache_files",
    "_check_year_cache_completeness",
    "_discovered_corrupt_blocker",
    "_enumerate_cache_files",
    "_unsupported_cache_policy_blocker",
    "_validate_cached_json_shape",
    "check_cache_availability",
]
