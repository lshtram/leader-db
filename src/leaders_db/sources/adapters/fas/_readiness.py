"""Readiness checks for the clean FAS Nuclear Notebook adapter.

The orchestrator :func:`check_fas_readiness` composes the metadata
gate, the file-presence gate, the cache-policy gate, the checksum
gate, the request-version gate, and the request-scoping warning
builders. The actual HTML validation lives in :func:`_validate_fas_html`
(kept under the 400-line convention).

The gate accepts BOTH the canonical primary metadata shape
(``source_version`` / ``source_url`` / ``local_files`` /
``checksum_sha256``) AND the legacy raw-local bundle shape used by
the staged ``data/raw/fas/metadata.json``
(``source_version`` / ``source_url`` / ``local_files`` /
``checksum_sha256`` -- same keys; the staged file carries the
flat-string ``checksum_sha256`` plus ``caveats`` / ``coverage`` /
``years_available`` / ``license_note``). The gate validates the
metadata ``source_version`` against the canonical
``"consolidated status table"`` value.

Cache-policy semantics
----------------------

The FAS unified adapter is local-file only. The legacy HTTP layer
is intentionally NEVER invoked by the unified read path. For
supported cache policies (``"offline_only"`` / ``"prefer_cache"``),
the gate blocks when:

1. The cache policy is ``"refresh"`` / ``"no_cache"`` (the
   unified FAS adapter never invokes the network; the
   ``unsupported_cache_policy`` error fires).
2. The staged ``<raw_root>/fas/fas_status.html`` is missing.
3. The bundle metadata's ``checksum_sha256`` (flat-string shape)
   does NOT match the staged HTML's SHA-256 when ``checksum_sha256``
   is present.
4. ``request.source_version`` is set to a value other than the
   canonical ``"consolidated status table"``.
5. ``request.years`` is explicit AND none of the requested years
   match the snapshot year parsed from the page (the readiness gate
   still passes because FAS always emits the snapshot year rows;
   the request-scoping layer surfaces a ``YEAR_ABSENT`` warning on
   the runner envelope so the caller can see the temporal-fit gap).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import SourceIngestRequest, SourceWarning
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._constants import (
    FAS_CHECKSUM_MISMATCH,
    FAS_DEFAULT_VERSION,
    FAS_HTML_NAME,
    FAS_LOCAL_FILES_INVALID,
    FAS_METADATA_NAME,
    FAS_METADATA_VERSION_MISMATCH,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_UNSUPPORTED_CACHE_POLICY,
    FAS_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical FAS bundle directory."""
    return Path(request.raw_root) / FAS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical FAS ``metadata.json`` path."""
    return bundle_dir(request) / FAS_METADATA_NAME


def html_path(request: SourceIngestRequest) -> Path:
    """Return the canonical FAS staged HTML cache path."""
    return bundle_dir(request) / FAS_HTML_NAME


def read_metadata(path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def metadata_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    """Validate the bundle's ``metadata.json`` shape.

    Returns ``(blocker_message, code)`` when the metadata is
    missing, unparseable, carries an unsupported ``source_version``,
    or has an invalid ``local_files`` shape. Returns ``None`` for a
    well-formed metadata file.
    """
    path = metadata_path(request)
    if not path.is_file():
        return (
            f"FAS metadata.json is missing at {path}",
            MISSING_METADATA,
        )
    payload = read_metadata(path)
    if not payload:
        return (
            f"FAS metadata.json is not parseable at {path}",
            MISSING_METADATA,
        )
    version = payload.get("source_version")
    if not isinstance(version, str) or not version.strip():
        return (
            "FAS metadata source_version must be the canonical "
            f"{FAS_DEFAULT_VERSION!r}; missing or empty.",
        ), FAS_METADATA_VERSION_MISMATCH
    if version.strip() != FAS_DEFAULT_VERSION:
        return (
            "FAS metadata source_version must be "
            f"{FAS_DEFAULT_VERSION!r}; got {version.strip()!r}",
        ), FAS_METADATA_VERSION_MISMATCH
    return _local_files_blocker(payload)


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Validate the bundle metadata's optional ``local_files`` list.

    Returns ``(blocker_message, code)`` when ``local_files`` is
    present but is not a non-empty string list OR does NOT
    include the canonical ``fas_status.html`` filename. Returns
    ``None`` when the field is absent (the staged metadata carries
    the canonical list but the gate accepts the absent shape for
    backward compatibility).
    """
    local_files = payload.get("local_files")
    if local_files is None:
        return None
    if not isinstance(local_files, list) or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "FAS metadata local_files must be a non-empty string "
            "list when present",
        ), FAS_LOCAL_FILES_INVALID
    if FAS_HTML_NAME not in local_files:
        return (
            "FAS metadata local_files must include the canonical "
            f"HTML cache file {FAS_HTML_NAME!r}",
        ), FAS_LOCAL_FILES_INVALID
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    """Validate the staged HTML cache file presence + checksum.

    Returns ``(blocker_message, code)`` when the HTML cache is
    missing, OR when the bundle metadata's ``checksum_sha256``
    string does NOT match the staged HTML's SHA-256.

    The bundle metadata's ``checksum_sha256`` accepts BOTH the
    canonical flat-string shape (a single 64-character hex SHA-256
    string covering the entire HTML file -- the staged
    ``data/raw/fas/metadata.json`` shape) AND the per-file dict
    shape (``{"fas_status.html": "<sha256>"}`` -- the legacy SIPRI
    Yearbook / CIRIGHTS / SIPRI Milex convention).
    """
    path = html_path(request)
    if not path.is_file():
        return (
            f"FAS HTML cache is missing at {path}",
            MISSING_RAW,
        )
    metadata = read_metadata(metadata_path(request))
    expected = _expected_checksum(metadata)
    if expected is None:
        return None
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest().lower()
    except OSError as exc:
        return (
            f"FAS HTML cache at {path} is unreadable ({type(exc).__name__}: "
            f"{exc}); cannot validate checksum.",
            MISSING_RAW,
        )
    if actual != expected:
        return (
            f"FAS HTML cache checksum mismatch for {FAS_HTML_NAME}; "
            f"expected {expected!r}, got {actual!r}.",
        ), FAS_CHECKSUM_MISMATCH
    return None


def _expected_checksum(metadata: dict[str, Any]) -> str | None:
    """Return the expected SHA-256 hex digest for the HTML cache, if any.

    Accepts BOTH the flat-string shape (canonical FAS staged
    ``metadata.json``: ``checksum_sha256 = "<64-hex>"``) AND the
    per-file dict shape (``checksum_sha256 = {"fas_status.html":
    "<64-hex>"}``). Returns ``None`` when no checksum is recorded.
    """
    checksum = metadata.get("checksum_sha256")
    if isinstance(checksum, str):
        cleaned = checksum.strip().lower()
        if cleaned and _is_hex_sha256(cleaned):
            return cleaned
        return None
    if isinstance(checksum, dict):
        value = checksum.get(FAS_HTML_NAME)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned and _is_hex_sha256(cleaned):
                return cleaned
    return None


def _is_hex_sha256(value: str) -> bool:
    """Return ``True`` if ``value`` is a 64-character hex SHA-256 string."""
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def cache_policy_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values.

    The unified FAS adapter is local-file only -- the readiness gate
    refuses both ``"refresh"`` and ``"no_cache"`` so a caller cannot
    accidentally ask the unified adapter to fetch the page over the
    network. Use ``"offline_only"`` (the documented safe default) or
    ``"prefer_cache"`` and stage the HTML locally.
    """
    if request.cache_policy not in {"refresh", "no_cache"}:
        return None
    return (
        "FAS readiness gate: cache_policy="
        f"{request.cache_policy!r} is not supported by the unified "
        "FAS adapter in this slice; the adapter is local-file only "
        "and the legacy HTTP layer is intentionally NEVER invoked "
        "by the unified read path. Stage the canonical HTML cache at "
        f"<raw_root>/{FAS_SOURCE_KEY}/{FAS_HTML_NAME} and re-run with "
        "cache_policy='offline_only' or 'prefer_cache' (the documented "
        "safe default)."
    ), FAS_UNSUPPORTED_CACHE_POLICY


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version."""
    if request.source_version in (None, FAS_DEFAULT_VERSION):
        return None
    return (
        "FAS request source_version must be "
        f"{FAS_DEFAULT_VERSION!r}; got {request.source_version!r}",
    ), FAS_UNSUPPORTED_VERSION


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces:

    - ``UNSUPPORTED_FILTER`` when ``leaders=`` is set (FAS is
      country-year nuclear evidence; leader filters are ignored).
    - ``YEAR_ABSENT`` for each requested year that does NOT match
      the snapshot year. Per SRC-COV-002 / SRC-COV-003 the runner
      still emits the snapshot year rows (no silent stale-proxy
      fill), but the warning names the temporal-fit gap so the
      caller can branch on it. A requested snapshot year emits
      zero warnings (clean hit).
    """
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "FAS is country-year nuclear evidence; leader "
                    "filters are ignored."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            )
        )
    snapshot_year_int = snapshot_year_for_request(request)
    for year in request.years or ():
        year_int = int(year)
        if year_int == snapshot_year_int:
            continue
        warnings.append(
            SourceWarning(
                code=YEAR_ABSENT,
                message=(
                    f"year={year_int} is outside the FAS consolidated "
                    f"snapshot year ({snapshot_year_int}); the adapter "
                    f"will still emit {snapshot_year_int} rows labeled "
                    f"with the snapshot year (no silent stale-proxy "
                    f"fill per SRC-COV-002 / SRC-COV-003). The temporal-"
                    f"fit gap to the requested year is recorded on every "
                    f"observation's extension.requested_year / "
                    f"snapshot_year audit metadata."
                ),
                severity="warning",
                source_id=request.source_id,
                context={
                    "requested_year": year_int,
                    "snapshot_year": snapshot_year_int,
                },
            )
        )
    return tuple(warnings)


def snapshot_year_for_request(request: SourceIngestRequest) -> int:
    """Return the staged HTML's parsed snapshot year for readiness warnings.

    Readiness warnings must compare requested years against the same
    source of truth used by ``read_raw`` / ``transform``. The helper
    therefore reads the staged HTML cache and delegates to the legacy
    snapshot-year parser via a lazy import. If the file is absent or
    unreadable, readiness has already failed via :func:`file_blocker`;
    this warning helper falls back to the conservative default so it
    remains safe when called directly by tests.
    """
    path = html_path(request)
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return int(FAS_SNAPSHOT_YEAR)
    from leaders_db.ingest.fas_html import resolve_snapshot_year

    return int(resolve_snapshot_year(html))


__all__ = [
    "bundle_dir",
    "cache_policy_blocker",
    "file_blocker",
    "html_path",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "snapshot_year_for_request",
    "version_blocker",
]
