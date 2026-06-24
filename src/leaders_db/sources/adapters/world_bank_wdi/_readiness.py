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
bundle checksum. The readiness gate accepts three ``checksum_sha256``
shapes and refuses any bundle whose checksum is missing,
incomplete, or unbacked by an actionable rationale:

- ``checksum_sha256: null`` + non-empty ``checksum_note`` that
  mentions the API / cache / per-response / checksum contract
  (canonical WDI shape; ``checksum_note`` is MANDATORY when
  the checksum is null, otherwise a developer cannot tell that
  the omission is deliberate).
- ``checksum_sha256: "<hex>"`` (flat 64-char SHA-256 hex).
- ``checksum_sha256: {"<file>": "<hex>"}`` (per-file dict, the
  same shape the Maddison bundle accepts).

Missing ``checksum_sha256`` field, ``null`` without
``checksum_note``, ``null`` with a non-actionable note, or a
non-null shape that does not validate (bad hex, dict with
non-string value, etc.) all fail readiness with the structured
``MISSING_METADATA`` warning code so the runner refuses to
dispatch ``read_raw`` / ``transform``.

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

import json
import re
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
    UNSUPPORTED_CACHE_POLICY,
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
# is in this tuple so the gate refuses a bundle whose checksum
# field is missing entirely; when it is present as ``null`` the
# gate then demands an actionable ``checksum_note`` (see
# :func:`_checksum_blocker`).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
    "checksum_sha256",
)

# Module-local structured warning code used to reject an
# unsupported request source-version per SRC-REQ-009. Mirrors
# the PWT / Maddison UNSUPPORTED_VERSION code so the WDI
# readiness envelope stays consistent with the rest of the
# unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"

# SHA-256 hex shape: exactly 64 lowercase-or-uppercase
# hexadecimal characters. Used to validate the
# ``checksum_sha256`` flat-string and per-file dict shapes.
_SHA256_HEX_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{64}$")

# Keywords the ``checksum_note`` must mention when
# ``checksum_sha256`` is ``null``. The canonical WDI bundle
# notes that checksums are managed per cached response / per
# API request; the gate requires at least one of the
# documented tokens (case-insensitive) so a developer can
# tell that the null is deliberate, not an oversight.
_CHECKSUM_NOTE_RATIONALE_KEYWORDS: tuple[str, ...] = (
    "api",
    "cache",
    "per-response",
    "per response",
    "checksum",
)


def _is_actionable_checksum_note(value: Any) -> bool:
    """Return True iff ``value`` is a non-empty string mentioning
    at least one documented API/cache/per-response/checksum
    rationale token.

    The keyword check is intentionally permissive (any of
    ``api``, ``cache``, ``per-response`` / ``per response``,
    or ``checksum``) so a developer has multiple natural ways
    to document the per-response checksum omission; the gate
    refuses a vague or empty note because a null checksum with
    no rationale is indistinguishable from a missing checksum.
    """
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    return any(
        keyword in lowered
        for keyword in _CHECKSUM_NOTE_RATIONALE_KEYWORDS
    )


def _validate_checksum_dict(
    checksum: dict[Any, Any],
) -> tuple[str, str] | None:
    """Validate the per-file ``checksum_sha256`` dict shape.

    Returns a ``(blocker_message, MISSING_METADATA)`` tuple
    when the dict is empty, carries a non-string key, or
    carries a non-hex value. Returns ``None`` when every
    key / value pair validates. Extracted from
    :func:`_checksum_blocker` to keep the latter under the
    documented 6-return-statement ceiling (PLR0911).
    """
    if not checksum:
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' is a dict but is empty; "
            "either set the dict to a non-empty per-file "
            "mapping or remove 'checksum_sha256' and "
            "document the per-response checksum contract in "
            "'checksum_note'.",
            MISSING_METADATA,
        )
    for file_name, value in checksum.items():
        if not isinstance(file_name, str) or not file_name.strip():
            return (
                "World Bank WDI readiness gate: metadata.json "
                "'checksum_sha256' dict keys must be non-empty "
                "file-name strings; got "
                f"{type(file_name).__name__}.",
                MISSING_METADATA,
            )
        if (
            not isinstance(value, str)
            or not _SHA256_HEX_PATTERN.match(value.strip())
        ):
            return (
                "World Bank WDI readiness gate: metadata.json "
                f"'checksum_sha256' value for {file_name!r} "
                "must be a 64-character hexadecimal SHA-256; "
                f"got {type(value).__name__}.",
                MISSING_METADATA,
            )
    return None


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


def _checksum_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``checksum_sha256`` is missing or invalid.

    Three canonical shapes are accepted for the unified
    source-bundle contract:

    - ``checksum_sha256: null`` together with a non-empty
      ``checksum_note`` that mentions the API / cache /
      per-response / checksum contract. The canonical WDI
      bundle carries this shape because each cached response
      is independently checksummed; an empty or vague
      ``checksum_note`` would leave the omission
      indistinguishable from a forgotten checksum, so the
      gate refuses it.
    - ``checksum_sha256: "<64-char hex>"`` -- a flat
      bundle-level SHA-256. Matches the legacy PWT / Maddison
      hex-string shape.
    - ``checksum_sha256: {"<file>": "<64-char hex>"}`` -- a
      per-file dict. Matches the Maddison multi-file shape.
      Every value must be a 64-char hex string; non-string
      values fail the gate.
    """
    checksum = payload.get("checksum_sha256")
    # None / hex string / dict each have their own
    # validation path. The branches stay under the
    # 6-return-statement ceiling (PLR0911) by sharing
    # helper validations for the dict path.
    if checksum is None:
        note = payload.get("checksum_note")
        if _is_actionable_checksum_note(note):
            return None
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' is null and 'checksum_note' "
            "is missing or does not document the per-response "
            "API/cache checksum contract; for API/cache-backed "
            "bundles a null checksum MUST be paired with a "
            "non-empty checksum_note mentioning API, cache, "
            "per-response, or checksum. Either provide a "
            "valid 64-char hex SHA-256 in 'checksum_sha256' "
            "or document the per-response checksum contract "
            "in 'checksum_note'.",
            MISSING_METADATA,
        )
    if isinstance(checksum, str):
        if _SHA256_HEX_PATTERN.match(checksum.strip()):
            return None
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' must be a 64-character "
            "hexadecimal SHA-256 when set to a string; "
            f"got {len(checksum)} chars.",
            MISSING_METADATA,
        )
    if isinstance(checksum, dict):
        return _validate_checksum_dict(checksum)
    return (
        "World Bank WDI readiness gate: metadata.json "
        "'checksum_sha256' must be null, a 64-character "
        "hexadecimal SHA-256 string, or a non-empty dict "
        "mapping file names to 64-char hex SHA-256 strings; "
        f"got {type(checksum).__name__}.",
        MISSING_METADATA,
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


def _validate_cached_json_shape(
    cache_file: Path,
) -> tuple[str, str] | None:
    """Validate a staged WDI v2 JSON cache file's shape.

    Returns ``(blocker_message, MISSING_RAW)`` when the file is
    missing/unreadable/non-JSON / not a 2-element list with a
    list ``data`` slot. Returns ``None`` when the file is a
    valid WDI v2 2-element ``[metadata, data]`` response shape.

    The check is intentionally minimal: it only verifies that
    :func:`leaders_db.ingest.wdi_http.parse_wdi_payload` /
    the local cache-only parser will accept the file. Anything
    more strict belongs inside :func:`parse_wdi_payload` /
    :func:`read_raw` (where the per-row parsing actually runs).

    Used by :func:`check_cache_availability` to refuse
    readiness when a corrupt / malformed cache file would
    otherwise force :func:`WDIAdapter.read_raw` to fall
    through to HTTP under supported cache policies.
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
    # would force the legacy read_wdi fallback into HTTP, so
    # we block with an actionable error instead (per the
    # comprehensive cache-policy remediation).
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
