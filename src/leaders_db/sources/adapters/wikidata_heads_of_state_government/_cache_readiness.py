"""Per-(year, country_qids) cache enumeration + JSON-shape validation.

Owns the per-``(year, country_qids)`` JSON cache file
enumeration and shape validation for the clean Wikidata
WikiProject heads-of-state-and-government adapter. Split out
of :mod:`._readiness` so the readiness-gate orchestrator can
stay focused on the metadata + cache-policy + request-scoping
concerns. The cache enumeration helpers are pure disk-and-JSON
walkers that NEVER invoke the network -- they satisfy the
"enumerate valid cache files and pass only those exact
parameter sets through production paths" requirement.

The enumerator partitions the cache files into:

- ``valid``: a sorted list of ``(year_or_current, path)``
  tuples whose JSON is a Wikidata SPARQL response (object with
  a list ``results.bindings`` slot). Used by
  :func:`WikidataHeadsOfStateGovernmentAdapter.read_raw` to
  read exactly the cache file matching the request's first
  year + country_qids parameter set; the adapter never falls
  through to HTTP for any cache file not present in ``valid``.
- ``malformed``: a list of ``(path, error_kind, message)``
  tuples for files that exist on disk but fail JSON shape
  validation. Surfaced as a structured readiness blocker so
  a developer can repair or re-stage the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from leaders_db.sources.warnings import MISSING_RAW


def _validate_cached_sparql_json_shape(
    cache_file_path: Path,
) -> tuple[str, str] | None:
    """Validate a staged Wikidata SPARQL JSON cache file's shape.

    Returns ``(blocker_message, MISSING_RAW)`` when the file is
    missing / unreadable / non-JSON / not a JSON object with a
    list ``results.bindings`` slot. Returns ``None`` for a valid
    Wikidata SPARQL response
    (``{"head": ..., "results": {"bindings": [...]}}``).

    The check is intentionally minimal: anything stricter
    belongs inside the cache-only parser, not the readiness
    gate. The gate just needs to prove the file is JSON +
    structurally looks like a SPARQL response so the cache-only
    read path does not silently fall through to HTTP.
    """
    if not cache_file_path.is_file():
        return (
            f"Wikidata heads-of-state readiness gate: cache file "
            f"missing at {cache_file_path}; the SPARQL cache is "
            f"incomplete. Re-stage the cache before running "
            f"ingestion."
        ), MISSING_RAW
    try:
        payload = json.loads(cache_file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            "Wikidata heads-of-state readiness gate: cache file "
            f"{cache_file_path} is malformed "
            f"({type(exc).__name__}: {exc}); the cache-only read "
            f"path refuses to silently fall through to HTTP. "
            f"Repair or re-stage the cache file before running "
            f"ingestion."
        ), MISSING_RAW
    if not isinstance(payload, dict):
        return (
            "Wikidata heads-of-state readiness gate: cache file "
            f"{cache_file_path} is not a JSON object (got "
            f"{type(payload).__name__}); the cache-only read path "
            f"refuses to silently fall through to HTTP. Re-stage "
            f"a verbatim Wikidata SPARQL JSON response."
        ), MISSING_RAW
    results = payload.get("results")
    if not isinstance(results, dict):
        return (
            "Wikidata heads-of-state readiness gate: cache file "
            f"{cache_file_path} does not carry a 'results' object "
            f"(got {type(results).__name__}); the cache-only read "
            f"path refuses to silently fall through to HTTP. "
            f"Re-stage a verbatim Wikidata SPARQL JSON response."
        ), MISSING_RAW
    bindings = results.get("bindings")
    if not isinstance(bindings, list):
        return (
            "Wikidata heads-of-state readiness gate: cache file "
            f"{cache_file_path} does not carry a list "
            f"'results.bindings' slot (got "
            f"{type(bindings).__name__}); the cache-only read path "
            f"refuses to silently fall through to HTTP. Re-stage a "
            f"verbatim Wikidata SPARQL JSON response."
        ), MISSING_RAW
    return None


__all__ = [
    "_validate_cached_sparql_json_shape",
]
