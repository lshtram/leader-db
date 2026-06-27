"""Readiness checks for the clean SIPRI Arms Transfers adapter.

The orchestrator :func:`check_metadata_well_formed` composes
the per-field validators: file presence (metadata + cached CSV
or JSON), metadata fields (required, ``local_files``,
``ingestion_status``, ``source_version``), checksum match, and
the source-version stamp. The readiness envelope also builds
the request-scoping warnings (``leaders=``, out-of-coverage
years, ``unsupported_cache_policy``).

Year semantics
--------------

SIPRI Arms Transfers covers 1950-2025 per the canonical
attribution block in ``docs/sources/attributions.md``
``sipri_arms_transfers`` section. A request for an
out-of-coverage year (e.g. ``years=(2026,)`` -- one year past
the latest SIPRI update) emits zero observations AND a
structured ``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003). The prototype's target year 2023
falls WITHIN the canonical envelope (1950-2025) so 2023 is
in-coverage.

Leader-filter semantics
-----------------------

A request with a ``leaders=`` filter is unsupported for a
country-country (supplier-recipient) flow source and surfaces
a structured ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
The transform ignores the filter (Stage 4 is the resolver for
leader-identity evidence; SIPRI Arms Transfers is not
leader-identity evidence).

Cache-policy semantics
----------------------

The unified SIPRI Arms Transfers adapter is offline /
cache-only in this slice (the task brief: "If implementing
live fetch would be ambiguous, leave live fetch unsupported
with structured readiness error and implement cached JSON/CSV
ingestion only"). The readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``sipri_arms_transfers_unsupported_cache_policy`` error so the
runner refuses to dispatch ``read_raw`` / ``transform`` rather
than silently surfacing an HTTP-fetched payload. Supported
policies (``"offline_only"`` / ``"prefer_cache"``) pass through
unmodified.

Country-filter semantics
------------------------

A request with ``countries=`` filters the cached trade
register by source-native supplier / recipient display name
case-folded substring match (the SIPRI Trade Register uses
SIPRI's own country display names, which are NOT ISO3; the
unified adapter never invents ISO3 codes).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._constants import (
    SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH,
    SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
    SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    SIPRI_ARMS_TRANSFERS_CSV_NAME,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_JSON_NAME,
    SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
    SIPRI_ARMS_TRANSFERS_METADATA_NAME,
    SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
    SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY,
    SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical SIPRI Arms Transfers bundle directory.

    The canonical SIPRI Arms Transfers bundle folder is
    ``sipri_arms_transfers/`` (the slug is the folder name; no
    source-key / folder-alias reconciliation is needed).
    """
    return Path(request.raw_root) / SIPRI_ARMS_TRANSFERS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical SIPRI Arms Transfers ``metadata.json`` path."""
    return bundle_dir(request) / SIPRI_ARMS_TRANSFERS_METADATA_NAME


def csv_path(request: SourceIngestRequest) -> Path:
    """Return the canonical SIPRI Arms Transfers cached CSV path."""
    return bundle_dir(request) / SIPRI_ARMS_TRANSFERS_CSV_NAME


def json_path(request: SourceIngestRequest) -> Path:
    """Return the canonical SIPRI Arms Transfers cached base64-JSON path."""
    return bundle_dir(request) / SIPRI_ARMS_TRANSFERS_JSON_NAME


def read_metadata(path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error.

    A malformed / unreadable ``metadata.json`` is treated as
    missing-metadata so the readiness gate returns
    ``ready=False`` with a structured ``missing_metadata``
    blocker.
    """
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the cached
    CSV / JSON file is missing.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready. The gate fires ``MISSING_RAW`` whenever
    NEITHER the canonical CSV NOR the canonical base64-JSON
    wrapper is on disk, regardless of the metadata's
    ``local_files`` shape. The check fires AFTER the
    ``metadata.json`` presence check so a metadata-only bundle
    is still reported as ``missing_metadata`` rather than
    ``missing_raw``.
    """
    metadata_p = metadata_path(request)
    if not metadata_p.is_file():
        return (
            f"SIPRI Arms Transfers readiness gate: metadata.json "
            f"missing at {metadata_p}; place the canonical "
            f"data/raw/sipri_arms_transfers/metadata.json before "
            f"running ingestion.",
            MISSING_METADATA,
        )

    csv_p = csv_path(request)
    json_p = json_path(request)
    if not csv_p.is_file() and not json_p.is_file():
        return (
            f"SIPRI Arms Transfers readiness gate: cached "
            f"export missing; place either "
            f"{SIPRI_ARMS_TRANSFERS_CSV_NAME!r} or "
            f"{SIPRI_ARMS_TRANSFERS_JSON_NAME!r} at "
            f"{bundle_dir(request)} before running ingestion.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent.

    The canonical SIPRI Arms Transfers bundle metadata shape is
    ``source_name`` / ``source_version`` / ``source_url`` /
    ``license_note`` / ``coverage`` / ``local_files`` /
    ``ingestion_status`` / ``checksum_sha256`` /
    ``download_date`` / ``notes``. Missing fields fire a
    structured ``missing_metadata`` error so the runner raises
    ``RuntimeError`` BEFORE the reader opens the CSV / JSON.
    """
    required: tuple[str, ...] = (
        "source_name",
        "source_version",
        "source_url",
        "license_note",
        "coverage",
        "local_files",
        "ingestion_status",
        "checksum_sha256",
        "download_date",
        "notes",
    )
    for field in required:
        if field not in payload:
            return (
                f"SIPRI Arms Transfers readiness gate: "
                f"metadata.json is missing required field "
                f"{field!r}.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the cached CSV or JSON.

    The canonical SIPRI Arms Transfers bundle metadata must
    list either ``trade_register.csv`` (canonical CSV shape) or
    ``trade_register.json`` (canonical base64-JSON wrapper
    shape) -- OR both -- in the ``local_files`` list. A bundle
    that lists neither is a schema contract violation (the
    readiness gate cannot validate which file to read).
    """
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files:
        return (
            "SIPRI Arms Transfers readiness gate: metadata.json "
            "'local_files' must be a non-empty string list.",
            SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
        )
    if not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "SIPRI Arms Transfers readiness gate: metadata.json "
            "'local_files' must be a list of non-empty strings.",
            SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
        )
    if not (
        SIPRI_ARMS_TRANSFERS_CSV_NAME in local_files
        or SIPRI_ARMS_TRANSFERS_JSON_NAME in local_files
    ):
        return (
            "SIPRI Arms Transfers readiness gate: metadata.json "
            "'local_files' must include either "
            f"{SIPRI_ARMS_TRANSFERS_CSV_NAME!r} or "
            f"{SIPRI_ARMS_TRANSFERS_JSON_NAME!r}; got "
            f"{local_files!r}.",
            SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "SIPRI Arms Transfers readiness gate: metadata.json "
            "'ingestion_status' must be 'downloaded'; got "
            f"{payload.get('ingestion_status')!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if (
        not isinstance(metadata_version, str)
        or not metadata_version.strip()
    ):
        return (
            "SIPRI Arms Transfers readiness gate: metadata.json "
            "'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"SIPRI Arms Transfers readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified SIPRI Arms Transfers adapter "
            f"supports only canonical version "
            f"{canonical_version!r}. Re-stage a SIPRI Arms "
            f"Transfers Trade Register bundle or correct "
            f"metadata.json before running ingestion.",
            SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH,
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
            f"SIPRI Arms Transfers readiness gate: metadata.json "
            f"{field!r} must be a non-empty string naming "
            f"{expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_field_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``payload['checksum_sha256']`` is not a valid
    flat-string OR per-file dict shape.

    Accepts BOTH the canonical flat-string shape
    (``checksum_sha256 = "<64-hex>"``) AND the per-file dict
    shape (``checksum_sha256 = {"trade_register.csv":
    "<64-hex>"}`` or ``{"trade_register.json":
    "<64-hex>"}``). Empty / malformed fields surface a
    structured ``missing_metadata`` error.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str):
        if not value.strip():
            return (
                "SIPRI Arms Transfers readiness gate: "
                "metadata.json 'checksum_sha256' must be a "
                "non-empty hex SHA-256 string OR a per-file "
                "dict mapping file names to hex SHA-256 strings.",
                MISSING_METADATA,
            )
        return None
    if isinstance(value, dict):
        if not value:
            return (
                "SIPRI Arms Transfers readiness gate: "
                "metadata.json 'checksum_sha256' per-file dict "
                "must be non-empty.",
                MISSING_METADATA,
            )
        for file_name, file_sha in value.items():
            if (
                not isinstance(file_name, str)
                or not file_name.strip()
                or not isinstance(file_sha, str)
                or not file_sha.strip()
            ):
                return (
                    "SIPRI Arms Transfers readiness gate: "
                    "metadata.json 'checksum_sha256' per-file "
                    "dict entries must be non-empty strings "
                    "mapping file names to hex SHA-256 strings.",
                    MISSING_METADATA,
                )
        return None
    return (
        "SIPRI Arms Transfers readiness gate: metadata.json "
        "'checksum_sha256' must be a non-empty hex SHA-256 "
        "string OR a per-file dict mapping file names to hex "
        "SHA-256 strings.",
        MISSING_METADATA,
    )


def _checksum_match_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the staged CSV / JSON SHA-256 disagrees with the metadata field.

    Accepts BOTH the canonical flat-string shape
    (``checksum_sha256 = "<64-hex>"``) AND the per-file dict
    shape (``checksum_sha256 = {"trade_register.csv":
    "<64-hex>"}`` or ``{"trade_register.json": "<64-hex>"}``).
    When the checksum shape is present, the gate verifies the
    cached file SHA-256 against the metadata field.
    """
    checksum = payload.get("checksum_sha256")
    csv_p = csv_path(request)
    json_p = json_path(request)
    for cache_path, cache_name in (
        (csv_p, SIPRI_ARMS_TRANSFERS_CSV_NAME),
        (json_p, SIPRI_ARMS_TRANSFERS_JSON_NAME),
    ):
        if not cache_path.is_file():
            continue
        expected_sha = _extract_checksum(checksum, cache_name)
        if expected_sha is None:
            continue
        actual_sha = hashlib.sha256(
            cache_path.read_bytes(),
        ).hexdigest()
        if actual_sha.lower() != expected_sha.strip().lower():
            return (
                f"SIPRI Arms Transfers readiness gate: cached "
                f"export checksum mismatch for "
                f"{cache_name!r}. metadata.json says "
                f"checksum_sha256={expected_sha.strip().lower()!r} "
                f"but the staged file has sha256="
                f"{actual_sha.lower()!r}.",
                SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH,
            )
    return None


def _extract_checksum(
    checksum_field: Any,
    file_name: str,
) -> str | None:
    """Extract the expected SHA-256 string for ``file_name``.

    Accepts BOTH the flat-string shape (the file_name is
    ignored -- there is exactly one cached file) AND the
    per-file dict shape (``{file_name: "<64-hex>"}``). Returns
    ``None`` when the field is absent, malformed, or has no
    non-empty entry for the requested file name.
    """
    if isinstance(checksum_field, str):
        return checksum_field.strip() or None
    if isinstance(checksum_field, dict):
        entry = checksum_field.get(file_name)
        if isinstance(entry, str) and entry.strip():
            return entry
    return None


def check_metadata_well_formed(
    request: SourceIngestRequest,
    *,
    canonical_version: str = SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
) -> tuple[bool, str | None, str | None]:
    """Validate the SIPRI Arms Transfers bundle's ``metadata.json`` +
    cached CSV / JSON.

    Returns ``(ready, blocker, code)``:

    - ``(True, None, None)`` when the bundle is fully well-formed
      (file presence + metadata fields + canonical metadata
      ``source_version`` + ``local_files`` annotation +
      ``ingestion_status='downloaded'`` + checksum match).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|SIPRI_ARMS_TRANSFERS_*)``
      when the bundle is missing ``metadata.json``, missing the
      cached CSV / JSON, missing a required metadata field, has
      ``local_files`` that does not include the canonical cached
      file, has ``ingestion_status != 'downloaded'``, has
      unsupported ``source_version``, or has a checksum that
      disagrees with the actual cached file SHA-256.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready; the gate fires ``MISSING_RAW`` whenever the
    cached CSV / JSON is NOT on disk, regardless of the
    metadata's ``local_files`` shape. The check fires AFTER the
    ``metadata.json`` presence check so a metadata-only bundle
    is still reported as ``missing_metadata`` rather than
    ``missing_raw``.
    """
    # Phase A: presence check.
    presence_blocker = _presence_blocker(request)
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = read_metadata(metadata_path(request))
    if not payload:
        return False, (
            "SIPRI Arms Transfers readiness gate: failed to "
            "parse metadata.json at "
            f"{metadata_path(request)}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed.
    field_checks: tuple[tuple[str, tuple[str, str] | None], ...] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload)),
        (
            "ingestion_status",
            _ingestion_status_blocker(payload),
        ),
        (
            "source_version",
            _metadata_source_version_blocker(
                payload, canonical_version,
            ),
        ),
        (
            "source_name",
            _non_empty_string_blocker(
                payload,
                "source_name",
                "the canonical SIPRI Arms Transfers source name "
                "('SIPRI Arms Transfers Database / Trade "
                "Register')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical SIPRI Arms Transfers canonical "
                "URL (https://www.sipri.org/databases/armstransfers)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the SIPRI Arms Transfers license / fair-use "
                "caveat (SIPRI copyright; non-commercial use; "
                "attribution required)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the SIPRI Arms Transfers temporal coverage "
                "(1950-2025 per the canonical 2026-03-09 update)",
            ),
        ),
        (
            "checksum_sha256",
            _checksum_field_blocker(payload),
        ),
        (
            "checksum_match",
            _checksum_match_blocker(payload, request),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str = SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="SIPRI Arms Transfers Trade Register 2025-09-09 (data 1950-2024)"``
    against a canonical 2026-03-09 bundle must surface a
    structured readiness error so the runner refuses to dispatch
    ``read_raw`` / ``transform`` (the canonical SIPRI Arms
    Transfers Trade Register export is the latest snapshot;
    silently propagating an unsupported version into
    ``RawAsset.version`` /
    ``NormalizedObservation.source_version`` would silently lie
    to downstream scorers).

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
        f"SIPRI Arms Transfers readiness gate: requested "
        f"source_version={request.source_version!r} does not "
        f"match the canonical version {canonical_version!r}; "
        f"per docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION,
    )


def check_cache_policy(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values.

    The unified SIPRI Arms Transfers adapter is offline /
    cache-only in this slice (the task brief explicitly
    cautions against adding a broad network downloader; the
    existing clean-source architecture does not expose a
    dedicated safe http-client pattern for SIPRI Arms
    Transfers, so live fetch is intentionally unsupported). The
    gate blocks ``"refresh"`` / ``"no_cache"`` so the runner
    refuses to dispatch ``read_raw`` / ``transform`` rather
    than silently surfacing an HTTP-fetched payload. Supported
    policies (``"offline_only"`` / ``"prefer_cache"``) pass
    through unmodified.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return (
            f"SIPRI Arms Transfers readiness gate: cache_policy="
            f"{request.cache_policy!r} is not supported by the "
            f"unified SIPRI Arms Transfers adapter in this "
            f"slice (offline / cache-only). Stage a cached "
            f"{SIPRI_ARMS_TRANSFERS_CSV_NAME!r} or "
            f"{SIPRI_ARMS_TRANSFERS_JSON_NAME!r} export under "
            f"data/raw/sipri_arms_transfers/ and re-run with "
            f"cache_policy='offline_only' or "
            f"'prefer_cache'.",
            SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY,
        )
    return None


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    coverage_start_year: int = SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    coverage_end_year: int = SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when the
    transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (SIPRI Arms Transfers is a country-country flow source and
      has no leader dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented SIPRI Arms Transfers
      1950-2025 coverage envelope (no stale-proxy fill per
      SRC-COV-002 / SRC-COV-003).

    Note: an unsupported ``request.source_version`` is NOT a
    warning -- it is a hard readiness blocker (see
    :func:`check_source_version` and SRC-REQ-009). An
    unsupported ``request.cache_policy`` is likewise a hard
    readiness blocker (see :func:`check_cache_policy`).
    """
    warnings: list[SourceWarning] = []

    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "SIPRI Arms Transfers is a supplier-recipient "
                    "flow source; leader filters are not supported "
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
        for year in request.years:
            year_int = int(year)
            if (
                year_int < coverage_start_year
                or year_int > coverage_end_year
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside SIPRI "
                            f"Arms Transfers coverage "
                            f"({coverage_start_year}-"
                            f"{coverage_end_year}); no "
                            f"observations will be emitted "
                            f"for this year (no stale-proxy "
                            f"fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                coverage_start_year
                            ),
                            "coverage_end_year": (
                                coverage_end_year
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "csv_path",
    "json_path",
    "metadata_path",
    "read_metadata",
]
