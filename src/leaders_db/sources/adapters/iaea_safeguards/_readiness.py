"""Readiness checks for the clean IAEA Safeguards status-list adapter.

The orchestrator :func:`check_metadata_well_formed` composes the
per-field validators: file presence (metadata + cached PDF),
metadata fields (required, ``local_files``, ``ingestion_status``,
``source_version``), checksum match, and the source-version
stamp. The readiness envelope also builds the request-scoping
warnings (``leaders=``, out-of-coverage years,
``unsupported_cache_policy``).

Year semantics
--------------

The IAEA Safeguards Status List is a single-point legal/status
snapshot (the canonical probed stamp is "status as of 31
December 2025"). The descriptor advertises a single-year
envelope (``start_year == end_year == 2025``). A request for
an out-of-coverage year (e.g. ``years=(2023,)`` -- the
prototype's target year -- falls outside the canonical
envelope) emits zero observations AND a structured
``YEAR_ABSENT`` warning -- no stale-proxy fill (SRC-COV-002 /
SRC-COV-003).

The request-scoping warning also handles ``years=2025`` (the
in-coverage snapshot year): the gate emits no warning and the
transform emits one observation per cached row. The gate does
NOT silently proxy any other year to 2025 -- the snapshot is a
single legal observation, not a multi-year time series.

Leader-filter semantics
-----------------------

A request with a ``leaders=`` filter is unsupported for a
country-level safeguards status source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005. The transform
ignores the filter (the IAEA Safeguards Status List is a
country-level legal/status snapshot; Stage 4 is the resolver for
leader-identity evidence; IAEA Safeguards is not leader-identity
evidence).

Cache-policy semantics
----------------------

The unified IAEA Safeguards adapter is offline / cache-only in
this slice (the task brief: "Do NOT implement live
download/scraping. Keep scope modest"). The readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``iaea_safeguards_unsupported_cache_policy`` error so the runner
refuses to dispatch ``read_raw`` / ``transform`` rather than
silently surfacing an HTTP-fetched payload. Supported policies
(``"offline_only"`` / ``"prefer_cache"``) pass through unmodified.

Country-filter semantics
------------------------

A request with ``countries=`` filters the cached status list by
case-folded substring match on the source-native country display
name (the IAEA Safeguards Status List uses IAEA's own country
display names, which are NOT ISO3; the unified adapter never
invents ISO3 codes).
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
    IAEA_SAFEGUARDS_CHECKSUM_MISMATCH,
    IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
    IAEA_SAFEGUARDS_METADATA_NAME,
    IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
    IAEA_SAFEGUARDS_PDF_NAME,
    IAEA_SAFEGUARDS_SOURCE_KEY,
    IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY,
    IAEA_SAFEGUARDS_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical IAEA Safeguards bundle directory.

    The canonical IAEA Safeguards bundle folder is
    ``iaea_safeguards/`` (the slug is the folder name; no
    source-key / folder-alias reconciliation is needed).
    """
    return Path(request.raw_root) / IAEA_SAFEGUARDS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical IAEA Safeguards ``metadata.json`` path."""
    return bundle_dir(request) / IAEA_SAFEGUARDS_METADATA_NAME


def pdf_path(request: SourceIngestRequest) -> Path:
    """Return the canonical IAEA Safeguards cached PDF path."""
    return bundle_dir(request) / IAEA_SAFEGUARDS_PDF_NAME


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
    PDF is missing.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready. The gate fires ``MISSING_RAW`` whenever the
    canonical PDF is NOT on disk, regardless of the metadata's
    ``local_files`` shape. The check fires AFTER the
    ``metadata.json`` presence check so a metadata-only bundle
    is still reported as ``missing_metadata`` rather than
    ``missing_raw``.
    """
    metadata_p = metadata_path(request)
    if not metadata_p.is_file():
        return (
            f"IAEA Safeguards readiness gate: metadata.json "
            f"missing at {metadata_p}; place the canonical "
            f"data/raw/iaea_safeguards/metadata.json before "
            f"running ingestion.",
            MISSING_METADATA,
        )

    pdf_p = pdf_path(request)
    if not pdf_p.is_file():
        return (
            f"IAEA Safeguards readiness gate: cached status "
            f"list PDF missing at {pdf_p}; place the canonical "
            f"{IAEA_SAFEGUARDS_PDF_NAME!r} at "
            f"{bundle_dir(request)} before running ingestion.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent.

    The canonical IAEA Safeguards bundle metadata shape is
    ``source_name`` / ``source_version`` / ``source_url`` /
    ``license_note`` / ``coverage`` / ``local_files`` /
    ``ingestion_status`` / ``checksum_sha256`` /
    ``download_date`` / ``notes``. Missing fields fire a
    structured ``missing_metadata`` error so the runner raises
    ``RuntimeError`` BEFORE the reader opens the cached PDF.
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
                f"IAEA Safeguards readiness gate: metadata.json "
                f"is missing required field {field!r}.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the cached PDF.

    The canonical IAEA Safeguards bundle metadata must list the
    cached status-list PDF (``sg-agreements-comprehensive-status.pdf``)
    in the ``local_files`` list. A bundle that lists neither
    file is a schema contract violation (the readiness gate
    cannot validate which file to read).
    """
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files:
        return (
            "IAEA Safeguards readiness gate: metadata.json "
            "'local_files' must be a non-empty string list.",
            IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
        )
    if not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "IAEA Safeguards readiness gate: metadata.json "
            "'local_files' must be a list of non-empty strings.",
            IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
        )
    if IAEA_SAFEGUARDS_PDF_NAME not in local_files:
        return (
            "IAEA Safeguards readiness gate: metadata.json "
            "'local_files' must include the canonical cached "
            f"PDF {IAEA_SAFEGUARDS_PDF_NAME!r}; got "
            f"{local_files!r}.",
            IAEA_SAFEGUARDS_LOCAL_FILES_INVALID,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "IAEA Safeguards readiness gate: metadata.json "
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
            "IAEA Safeguards readiness gate: metadata.json "
            "'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"IAEA Safeguards readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified IAEA Safeguards adapter supports "
            f"only canonical version {canonical_version!r}. "
            f"Re-stage an IAEA Safeguards Status List bundle or "
            f"correct metadata.json before running ingestion.",
            IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH,
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
            f"IAEA Safeguards readiness gate: metadata.json "
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
    shape (``checksum_sha256 = {"sg-agreements-comprehensive-status.pdf":
    "<64-hex>"}``). Empty / malformed fields surface a
    structured ``missing_metadata`` error.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str):
        if not value.strip():
            return (
                "IAEA Safeguards readiness gate: metadata.json "
                "'checksum_sha256' must be a non-empty hex "
                "SHA-256 string OR a per-file dict mapping file "
                "names to hex SHA-256 strings.",
                MISSING_METADATA,
            )
        return None
    if isinstance(value, dict):
        if not value:
            return (
                "IAEA Safeguards readiness gate: metadata.json "
                "'checksum_sha256' per-file dict must be "
                "non-empty.",
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
                    "IAEA Safeguards readiness gate: metadata.json "
                    "'checksum_sha256' per-file dict entries must "
                    "be non-empty strings mapping file names to "
                    "hex SHA-256 strings.",
                    MISSING_METADATA,
                )
        return None
    return (
        "IAEA Safeguards readiness gate: metadata.json "
        "'checksum_sha256' must be a non-empty hex SHA-256 "
        "string OR a per-file dict mapping file names to hex "
        "SHA-256 strings.",
        MISSING_METADATA,
    )


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


def _checksum_match_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the staged PDF SHA-256 disagrees with the metadata field.

    Accepts BOTH the canonical flat-string shape
    (``checksum_sha256 = "<64-hex>"``) AND the per-file dict
    shape (``checksum_sha256 =
    {"sg-agreements-comprehensive-status.pdf": "<64-hex>"}``).
    When the checksum shape is present, the gate verifies the
    cached file SHA-256 against the metadata field.
    """
    checksum = payload.get("checksum_sha256")
    cache_path = pdf_path(request)
    if not cache_path.is_file():
        return None
    expected_sha = _extract_checksum(checksum, IAEA_SAFEGUARDS_PDF_NAME)
    if expected_sha is None:
        return None
    actual_sha = hashlib.sha256(
        cache_path.read_bytes(),
    ).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return (
            f"IAEA Safeguards readiness gate: cached status "
            f"list PDF checksum mismatch for "
            f"{IAEA_SAFEGUARDS_PDF_NAME!r}. metadata.json says "
            f"checksum_sha256={expected_sha.strip().lower()!r} "
            f"but the staged file has sha256="
            f"{actual_sha.lower()!r}.",
            IAEA_SAFEGUARDS_CHECKSUM_MISMATCH,
        )
    return None


def check_metadata_well_formed(
    request: SourceIngestRequest,
    *,
    canonical_version: str = IAEA_SAFEGUARDS_DEFAULT_VERSION,
) -> tuple[bool, str | None, str | None]:
    """Validate the IAEA Safeguards bundle's ``metadata.json`` +
    cached status-list PDF.

    Returns ``(ready, blocker, code)``:

    - ``(True, None, None)`` when the bundle is fully well-formed
      (file presence + metadata fields + canonical metadata
      ``source_version`` + ``local_files`` annotation +
      ``ingestion_status='downloaded'`` + checksum match).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|IAEA_SAFEGUARDS_*)``
      when the bundle is missing ``metadata.json``, missing the
      cached PDF, missing a required metadata field, has
      ``local_files`` that does not include the canonical cached
      file, has ``ingestion_status != 'downloaded'``, has
      unsupported ``source_version``, or has a checksum that
      disagrees with the actual cached file SHA-256.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready; the gate fires ``MISSING_RAW`` whenever the
    cached PDF is NOT on disk, regardless of the metadata's
    ``local_files`` shape. The check fires AFTER the
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
            "IAEA Safeguards readiness gate: failed to parse "
            f"metadata.json at {metadata_path(request)}"
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
                "the canonical IAEA Safeguards source name "
                "('IAEA Safeguards Status List, Conclusion of "
                "Safeguards Agreements, Additional Protocols and "
                "Small Quantities Protocols')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical IAEA Safeguards status-list PDF "
                "URL (https://www.iaea.org/sites/default/files/"
                "20/01/sg-agreements-comprehensive-status.pdf)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the IAEA terms-of-use caveat (download / copy / "
                "use with acknowledgement; no redistribution of "
                "the full PDF / table in outputs; attribution "
                "required)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the IAEA Safeguards Status List coverage "
                "(single-point legal snapshot; status as of "
                "31 December 2025)",
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
    canonical_version: str = IAEA_SAFEGUARDS_DEFAULT_VERSION,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="IAEA Safeguards Status List, status as of 2024-12-31"``
    against a canonical 2025-12-31 bundle must surface a
    structured readiness error so the runner refuses to dispatch
    ``read_raw`` / ``transform`` (silently propagating an
    unsupported version into ``RawAsset.version`` /
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
        f"IAEA Safeguards readiness gate: requested "
        f"source_version={request.source_version!r} does not "
        f"match the canonical version {canonical_version!r}; "
        f"per docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        IAEA_SAFEGUARDS_UNSUPPORTED_VERSION,
    )


def check_cache_policy(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values.

    The unified IAEA Safeguards adapter is offline /
    cache-only in this slice (the task brief explicitly
    cautions against adding live download / scraping). The gate
    blocks ``"refresh"`` / ``"no_cache"`` so the runner
    refuses to dispatch ``read_raw`` / ``transform`` rather than
    silently surfacing an HTTP-fetched payload. Supported
    policies (``"offline_only"`` / ``"prefer_cache"``) pass
    through unmodified.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return (
            f"IAEA Safeguards readiness gate: cache_policy="
            f"{request.cache_policy!r} is not supported by the "
            f"unified IAEA Safeguards adapter in this slice "
            f"(offline / cache-only). Stage a cached "
            f"{IAEA_SAFEGUARDS_PDF_NAME!r} under "
            f"data/raw/iaea_safeguards/ and re-run with "
            f"cache_policy='offline_only' or 'prefer_cache'.",
            IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY,
        )
    return None


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    coverage_start_year: int = IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
    coverage_end_year: int = IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when the
    transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (IAEA Safeguards is a country-level legal/status snapshot
      and has no leader dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented IAEA Safeguards
      single-point 2025 coverage envelope (no stale-proxy fill
      per SRC-COV-002 / SRC-COV-003). The prototype's target
      year 2023 falls outside the envelope; the readiness
      envelope surfaces the warning so the operator can see the
      gap (the transform emits zero observations for that
      year).

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
                    "IAEA Safeguards is a country-level "
                    "safeguards-status source; leader filters "
                    "are not supported and have been ignored."
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
                            f"year={year_int} is outside IAEA "
                            f"Safeguards Status List coverage "
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
    "IAEA_SAFEGUARDS_UNSUPPORTED_VERSION",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "metadata_path",
    "pdf_path",
    "read_metadata",
]
