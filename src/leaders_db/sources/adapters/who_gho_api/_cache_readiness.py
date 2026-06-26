"""Cache enumeration + JSON-shape validation for the clean WHO GHO API adapter.

Owns the per-``(year, indicator)`` JSON cache file enumeration
and shape validation. Split out of :mod:`._readiness` so the
readiness gate orchestrator can stay focused on the metadata +
cache-policy + request-scoping concerns. The cache enumeration
helpers are pure disk-and-JSON walkers that NEVER invoke the
network -- they satisfy the "enumerate valid cache files and
pass only those exact years/indicator codes through production
paths" requirement from the WDI cache-policy remediation.

The enumerator partitions the cache files into:

- ``valid``: a sorted list of ``(year, code, path)`` tuples
  whose JSON is a WHO GHO OData response (object with list
  ``value`` slot). Used by :func:`WhoGhoApiAdapter.read_raw`
  to read exactly these ``(year, indicator)`` pairs through
  the cache-only path; the adapter never falls through to
  HTTP for any pair not present in ``valid``.
- ``malformed``: a list of ``(path, error_kind, message)``
  tuples for files that exist on disk but fail JSON shape
  validation. Surfaced as a structured readiness blocker so
  a developer can repair or re-stage the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from leaders_db.sources.warnings import MISSING_RAW


def _validate_cached_json_shape(
    cache_file: Path,
) -> tuple[str, str] | None:
    """Validate a staged WHO GHO API JSON cache file's shape.

    Returns ``(blocker_message, MISSING_RAW)`` when the file is
    missing / unreadable / non-JSON / not a JSON object with a
    list ``value`` slot. Returns ``None`` for a valid WHO GHO
    API response (``{"@odata.context": ..., "value":
    [...records...]}``).

    The check is intentionally minimal: anything stricter
    belongs inside the cache-only parser, not the readiness
    gate. The gate just needs to prove the file is JSON +
    structurally looks like an OData response so the cache-only
    read path does not silently fall through to HTTP.
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
            f"{exc}); the cache-only read path refuses to "
            f"silently fall through to HTTP. Repair or re-stage "
            f"the cache file before running ingestion.",
        ), MISSING_RAW
    if not isinstance(payload, dict):
        return (
            "WHO GHO API readiness gate: cache file "
            f"{cache_file} is not a JSON object (got "
            f"{type(payload).__name__}); the cache-only read path "
            f"refuses to silently fall through to HTTP. Re-stage "
            f"a verbatim WHO GHO OData response.",
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
    partitions the discovered files into ``valid`` (one tuple
    per valid WHO GHO API cache file) + ``malformed`` (one
    tuple per corrupt JSON file) lists.

    Missing year directories and empty year directories are
    silently ignored (the readiness gate's per-year
    completeness check fires for explicit-year requests; for
    ``years=None`` an empty cache is a valid "no data yet"
    outcome and surfaces zero observations).

    The function NEVER invokes the network; it is a pure
    disk-and-JSON enumeration pass.
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
                elif "list 'value' slot" in message:
                    kind = "value_slot_error"
                else:
                    kind = "unknown"
                malformed.append((cache_file, kind, message))
    return valid, malformed


__all__ = [
    "_enumerate_cache_files",
    "_validate_cached_json_shape",
]
