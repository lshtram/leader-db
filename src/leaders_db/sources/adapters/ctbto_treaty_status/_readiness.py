"""Readiness checks for the clean CTBTO Treaty Status adapter.

The orchestrator :func:`check_metadata_well_formed` composes
the per-field validators: file presence (metadata + cached CSV
or HTML file), metadata fields (required, ``local_files``,
``ingestion_status``, ``source_version``), checksum match, the
**selected-file contract** (the actually-present cache file
that the reader will load must be listed in
``metadata.local_files`` AND covered by
``metadata.checksum_sha256``), and the source-version stamp.
The readiness envelope also builds the request-scoping
warnings (``leaders=``, out-of-coverage years,
``ctbto_treaty_status_unsupported_cache_policy``).

Year semantics
--------------

The CTBTO States Signatories page is a single-point
treaty-status snapshot (the canonical probed stamp is
"status as of 13 March 2024"). The descriptor advertises a
single-year envelope (``start_year == end_year == 2024``).
A request for an out-of-coverage year (e.g. ``years=(2023,)``
-- the prototype's target year -- falls outside the canonical
envelope) emits zero observations AND a structured
``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003).

The request-scoping warning also handles ``years=(2024,)`` (the
in-coverage snapshot year): the gate emits no warning and the
transform emits one observation per cached row. The gate does
NOT silently proxy any other year to 2024 -- the snapshot is
a single legal observation, not a multi-year time series.

Leader-filter semantics
-----------------------

A request with a ``leaders=`` filter is unsupported for a
country-level treaty-status source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005. The transform
ignores the filter (the CTBTO States Signatories page is a
country-level treaty-status snapshot; Stage 4 is the resolver
for leader-identity evidence; CTBTO treaty status is not
leader-identity evidence).

Cache-policy semantics
----------------------

The unified CTBTO Treaty Status adapter is offline /
cache-only in this slice (the task brief: "Do NOT implement
live download/scraping. Build an offline/cache-first
adapter"). The gate blocks ``cache_policy="refresh"`` /
``"no_cache"`` so the runner refuses to dispatch ``read_raw`` /
``transform`` rather than silently surfacing an HTTP-fetched
payload. Supported policies (``"offline_only"`` /
``"prefer_cache"``) pass through unmodified.

Country-filter semantics
------------------------

A request with ``countries=`` filters the cached CTBTO table
by case-folded substring match on the source-native State
display name (the CTBTO States Signatories page uses CTBTO's
own State display names, which are NOT ISO3; the unified
adapter never invents ISO3 codes).
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
    CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
    CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_HTML_NAME,
    CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
    CTBTO_TREATY_STATUS_METADATA_NAME,
    CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
    CTBTO_TREATY_STATUS_SOURCE_KEY,
    CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY,
    CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical CTBTO Treaty Status bundle directory.

    The canonical CTBTO Treaty Status bundle folder is
    ``ctbto_treaty_status/`` (the slug is the folder name; no
    source-key / folder-alias reconciliation is needed).
    """
    return Path(request.raw_root) / CTBTO_TREATY_STATUS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical CTBTO Treaty Status ``metadata.json`` path."""
    return bundle_dir(request) / CTBTO_TREATY_STATUS_METADATA_NAME


def csv_path(request: SourceIngestRequest) -> Path:
    """Return the canonical CTBTO Treaty Status cached CSV path."""
    return bundle_dir(request) / CTBTO_TREATY_STATUS_CSV_NAME


def html_path(request: SourceIngestRequest) -> Path:
    """Return the canonical CTBTO Treaty Status cached HTML path.

    The HTML file is the optional fallback; the unified adapter
    in this slice supports the canonical CSV shape primarily
    and the HTML file only when explicitly listed in
    ``metadata.local_files`` and present on disk.
    """
    return bundle_dir(request) / CTBTO_TREATY_STATUS_HTML_NAME


def resolve_selected_cache_path(
    request: SourceIngestRequest,
) -> Path | None:
    """Return the cache file path the reader would actually load.

    Mirrors the selection logic in
    :func:`._raw_read.read_ctbto_treaty_status_cache`: the
    canonical CSV shape is preferred when it is on disk, and
    the canonical HTML fallback is used only when the CSV is
    absent. Returns ``None`` when NEITHER file is on disk --
    the presence blocker fires first in that case.

    The helper exists so the readiness gate can validate
    that the **selected** cache file is the one declared in
    ``metadata.local_files`` AND covered by
    ``metadata.checksum_sha256``. Without this helper the
    gate could pass a bundle where, e.g., the cached HTML
    export is the file actually read but ``local_files``
    only lists the canonical CSV file.
    """
    csv_p = csv_path(request)
    if csv_p.is_file():
        return csv_p
    html_p = html_path(request)
    if html_p.is_file():
        return html_p
    return None


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
    CSV / HTML file is missing.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready. The gate fires ``MISSING_RAW`` whenever
    NEITHER the canonical CSV NOR the canonical HTML export
    is on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still
    reported as ``missing_metadata`` rather than ``missing_raw``.
    """
    metadata_p = metadata_path(request)
    if not metadata_p.is_file():
        return (
            f"CTBTO Treaty Status readiness gate: metadata.json "
            f"missing at {metadata_p}; place the canonical "
            f"data/raw/ctbto_treaty_status/metadata.json before "
            f"running ingestion.",
            MISSING_METADATA,
        )

    csv_p = csv_path(request)
    html_p = html_path(request)
    if not csv_p.is_file() and not html_p.is_file():
        return (
            f"CTBTO Treaty Status readiness gate: cached export "
            f"missing; place either "
            f"{CTBTO_TREATY_STATUS_CSV_NAME!r} or "
            f"{CTBTO_TREATY_STATUS_HTML_NAME!r} at "
            f"{bundle_dir(request)} before running ingestion.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent.

    The canonical CTBTO Treaty Status bundle metadata shape is
    ``source_name`` / ``source_version`` / ``source_url`` /
    ``license_note`` / ``coverage`` / ``local_files`` /
    ``ingestion_status`` / ``checksum_sha256`` /
    ``download_date`` / ``notes``. Missing fields fire a
    structured ``missing_metadata`` error so the runner raises
    ``RuntimeError`` BEFORE the reader opens the cached CSV /
    HTML file.
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
                f"CTBTO Treaty Status readiness gate: "
                f"metadata.json is missing required field "
                f"{field!r}.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include a canonical cached file.

    The canonical CTBTO Treaty Status bundle metadata must list
    the cached States Signatories export in the ``local_files``
    list. The bundle may legitimately list EITHER the canonical
    CSV (``states-signatories.csv``) OR the canonical HTML
    (``states-signatories.html``) OR BOTH -- the cache is
    content-addressable by file name and the adapter prefers the
    CSV shape when both are staged. A bundle that lists neither
    file is a schema contract violation (the readiness gate
    cannot validate which file to read).
    """
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files:
        return (
            "CTBTO Treaty Status readiness gate: metadata.json "
            "'local_files' must be a non-empty string list.",
            CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
        )
    if not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "CTBTO Treaty Status readiness gate: metadata.json "
            "'local_files' must be a list of non-empty strings.",
            CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
        )
    if not (
        CTBTO_TREATY_STATUS_CSV_NAME in local_files
        or CTBTO_TREATY_STATUS_HTML_NAME in local_files
    ):
        return (
            "CTBTO Treaty Status readiness gate: metadata.json "
            "'local_files' must include at least one of the "
            f"canonical cached files ({CTBTO_TREATY_STATUS_CSV_NAME!r} "
            f"or {CTBTO_TREATY_STATUS_HTML_NAME!r}); got "
            f"{local_files!r}.",
            CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "CTBTO Treaty Status readiness gate: metadata.json "
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
            "CTBTO Treaty Status readiness gate: metadata.json "
            "'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"CTBTO Treaty Status readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified CTBTO Treaty Status adapter supports "
            f"only canonical version {canonical_version!r}. "
            f"Re-stage a CTBTO States Signatories bundle or "
            f"correct metadata.json before running ingestion.",
            CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
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
            f"CTBTO Treaty Status readiness gate: metadata.json "
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
    shape (``checksum_sha256 =
    {"states-signatories.csv": "<64-hex>"}``). Empty /
    malformed fields surface a structured ``missing_metadata``
    error.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str):
        if not value.strip():
            return (
                "CTBTO Treaty Status readiness gate: metadata.json "
                "'checksum_sha256' must be a non-empty hex "
                "SHA-256 string OR a per-file dict mapping file "
                "names to hex SHA-256 strings.",
                MISSING_METADATA,
            )
        return None
    if isinstance(value, dict):
        if not value:
            return (
                "CTBTO Treaty Status readiness gate: metadata.json "
                "'checksum_sha256' per-file dict must be non-empty.",
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
                    "CTBTO Treaty Status readiness gate: metadata.json "
                    "'checksum_sha256' per-file dict entries must be "
                    "non-empty strings mapping file names to hex "
                    "SHA-256 strings.",
                    MISSING_METADATA,
                )
        return None
    return (
        "CTBTO Treaty Status readiness gate: metadata.json "
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
    ignored -- there is exactly one cached file in the
    canonical CSV shape) AND the per-file dict shape
    (``{file_name: "<64-hex>"}``). Returns ``None`` when the
    field is absent, malformed, or has no non-empty entry
    for the requested file name.
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
    """Block if the staged CSV / HTML SHA-256 disagrees with the metadata field.

    Accepts BOTH the canonical flat-string shape
    (``checksum_sha256 = "<64-hex>"``) AND the per-file dict
    shape (``checksum_sha256 =
    {"states-signatories.csv": "<64-hex>"}``). When the
    checksum shape is present, the gate verifies the cached
    file SHA-256 against the metadata field for the canonical
    CSV (when present on disk) AND for the canonical HTML
    fallback (when present on disk).
    """
    checksum = payload.get("checksum_sha256")
    csv_p = csv_path(request)
    if csv_p.is_file():
        expected_sha = _extract_checksum(
            checksum, CTBTO_TREATY_STATUS_CSV_NAME,
        )
        if expected_sha is not None:
            actual_sha = hashlib.sha256(csv_p.read_bytes()).hexdigest()
            if actual_sha.lower() != expected_sha.strip().lower():
                return (
                    f"CTBTO Treaty Status readiness gate: cached "
                    f"CSV checksum mismatch for "
                    f"{CTBTO_TREATY_STATUS_CSV_NAME!r}. "
                    f"metadata.json says checksum_sha256="
                    f"{expected_sha.strip().lower()!r} but the "
                    f"staged file has sha256={actual_sha.lower()!r}.",
                    CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
                )
    html_p = html_path(request)
    if html_p.is_file():
        expected_sha = _extract_checksum(
            checksum, CTBTO_TREATY_STATUS_HTML_NAME,
        )
        if expected_sha is not None:
            actual_sha = hashlib.sha256(html_p.read_bytes()).hexdigest()
            if actual_sha.lower() != expected_sha.strip().lower():
                return (
                    f"CTBTO Treaty Status readiness gate: cached "
                    f"HTML checksum mismatch for "
                    f"{CTBTO_TREATY_STATUS_HTML_NAME!r}. "
                    f"metadata.json says checksum_sha256="
                    f"{expected_sha.strip().lower()!r} but the "
                    f"staged file has sha256={actual_sha.lower()!r}.",
                    CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
                )
    return None


def _selected_local_files_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the actually-present SELECTED cache file is
    not declared in ``metadata.local_files``.

    The existing :func:`_local_files_blocker` accepts any
    bundle whose ``local_files`` includes the canonical CSV
    OR the canonical HTML -- but that check is too lenient
    when only ONE of those files is actually on disk. The
    unified reader selects the canonical CSV when it is on
    disk and falls back to the HTML file only when the CSV
    is absent, so the SELECTED cache file (the one the
    reader will load) MUST be listed in ``local_files`` --
    otherwise the bundle's ``local_files`` declaration
    silently disagrees with the file the reader will
    actually consume.

    For example, a bundle with the HTML fallback staged on
    disk and ``local_files=[states-signatories.csv]`` would
    pass the existing check (CSV is listed) but the reader
    would load the undeclared HTML file. This helper closes
    that gap and surfaces a structured
    ``ctbto_treaty_status_local_files_invalid`` blocker.
    """
    selected = resolve_selected_cache_path(request)
    if selected is None:
        # The presence blocker fires first when NEITHER the
        # canonical CSV NOR the canonical HTML is on disk;
        # this helper only validates the selected file shape
        # so a None result means there is nothing to validate
        # yet.
        return None
    local_files = payload.get("local_files")
    if not isinstance(local_files, list):
        # The shape-level ``_local_files_blocker`` catches
        # this case (non-list ``local_files``); the helper
        # stays silent so the structured shape error fires
        # first.
        return None
    if selected.name not in local_files:
        return (
            f"CTBTO Treaty Status readiness gate: metadata.json "
            f"'local_files' must declare the actually-present "
            f"selected cache file {selected.name!r} that the "
            f"reader will load (the canonical CSV is preferred "
            f"when present; the HTML fallback is used only "
            f"when the CSV is absent). The bundle's "
            f"'local_files' entry is {local_files!r} but the "
            f"selected file {selected.name!r} is not declared; "
            f"update metadata.local_files to include "
            f"{selected.name!r} before running ingestion.",
            CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
        )
    return None


def _selected_checksum_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the actually-present SELECTED cache file is
    not checksum-covered by ``metadata.checksum_sha256``.

    The existing :func:`_checksum_match_blocker` validates
    that the on-disk SHA-256 matches the metadata field
    WHEN the metadata field covers the file -- but the
    existing check stays silent when the metadata field is
    absent or has no entry for the file. The reader always
    loads the SELECTED cache file (CSV preferred over HTML),
    so the bundle must declare a checksum for the selected
    file. Otherwise the bundle's ``checksum_sha256``
    silently disagrees with the file the reader will
    actually consume.

    For example, a bundle with the HTML fallback staged on
    disk and ``checksum_sha256={"states-signatories.csv":
    "<64-hex>"}`` (no HTML entry) would pass the existing
    ``_checksum_match_blocker`` (the HTML file is on disk
    but the per-file dict has no HTML entry, so
    ``_extract_checksum`` returns None and the loop is
    skipped) but the reader would load the undeclared
    HTML file. This helper closes that gap and surfaces a
    structured ``ctbto_treaty_status_checksum_mismatch``
    blocker.

    The flat-string ``checksum_sha256="<64-hex>"`` shape
    covers the canonical CSV by convention; when the
    SELECTED file is the canonical CSV the flat-string
    shape is sufficient. When the SELECTED file is the
    HTML fallback, the bundle MUST use the per-file dict
    shape with an explicit ``states-signatories.html``
    entry.
    """
    selected = resolve_selected_cache_path(request)
    if selected is None:
        # The presence blocker fires first when NEITHER the
        # canonical CSV NOR the canonical HTML is on disk;
        # this helper only validates the selected file shape
        # so a None result means there is nothing to validate
        # yet.
        return None
    checksum = payload.get("checksum_sha256")
    expected_sha = _extract_checksum(checksum, selected.name)
    if expected_sha is None:
        return (
            f"CTBTO Treaty Status readiness gate: metadata.json "
            f"'checksum_sha256' must cover the actually-present "
            f"selected cache file {selected.name!r} that the "
            f"reader will load (the canonical CSV is preferred "
            f"when present; the HTML fallback is used only "
            f"when the CSV is absent). The bundle's "
            f"'checksum_sha256' entry is {checksum!r} but the "
            f"selected file {selected.name!r} has no checksum "
            f"entry; add a checksum entry for "
            f"{selected.name!r} (per-file dict shape) or use "
            f"the flat-string shape when the selected file is "
            f"the canonical CSV before running ingestion.",
            CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
        )
    return None


def check_metadata_well_formed(
    request: SourceIngestRequest,
    *,
    canonical_version: str = CTBTO_TREATY_STATUS_DEFAULT_VERSION,
) -> tuple[bool, str | None, str | None]:
    """Validate the CTBTO Treaty Status bundle's ``metadata.json`` +
    cached CSV / HTML file.

    Returns ``(ready, blocker, code)``:

    - ``(True, None, None)`` when the bundle is fully well-formed
      (file presence + metadata fields + canonical metadata
      ``source_version`` + ``local_files`` annotation +
      ``ingestion_status='downloaded'`` + checksum match + the
      **selected-file contract** that the actually-present
      cache file the reader will load is declared in
      ``local_files`` AND covered by ``checksum_sha256``).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|CTBTO_TREATY_STATUS_*)``
      when the bundle is missing ``metadata.json``, missing the
      cached CSV / HTML, missing a required metadata field, has
      ``local_files`` that does not include the canonical cached
      file, has ``ingestion_status != 'downloaded'``, has
      unsupported ``source_version``, has a checksum that
      disagrees with the actual cached file SHA-256, has a
      ``local_files`` declaration that does NOT list the
      SELECTED cache file the reader will actually load, or
      has a ``checksum_sha256`` that does NOT cover the
      SELECTED cache file.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready; the gate fires ``MISSING_RAW`` whenever
    NEITHER the canonical CSV NOR the canonical HTML export is
    on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still
    reported as ``missing_metadata`` rather than ``missing_raw``.

    The selected-file contract closes the gap where the
    canonical CSV is listed in ``local_files`` but only the
    HTML fallback is on disk (the reader would silently load
    the undeclared HTML file). The contract requires the
    SELECTED cache file -- the one the reader will actually
    load -- to be declared in ``local_files`` AND covered
    by ``checksum_sha256``.
    """
    # Phase A: presence check.
    presence_blocker = _presence_blocker(request)
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = read_metadata(metadata_path(request))
    if not payload:
        return False, (
            "CTBTO Treaty Status readiness gate: failed to parse "
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
                "the canonical CTBTO Treaty Status source name "
                "('CTBTO States Signatories, Comprehensive "
                "Nuclear-Test-Ban Treaty signature and ratification "
                "status')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical CTBTO States Signatories page URL "
                "(https://www.ctbto.org/our-mission/states-signatories)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the CTBTO terms-of-use caveat (download / copy / "
                "use with acknowledgement for personal, "
                "non-commercial, research / teaching use; no "
                "redistribution of copied full table in outputs; "
                "attribution required)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the CTBTO States Signatories coverage (single-"
                "point treaty-status snapshot; status as of "
                "13 March 2024)",
            ),
        ),
        (
            "checksum_sha256",
            _checksum_field_blocker(payload),
        ),
        (
            "selected_local_files",
            _selected_local_files_blocker(payload, request),
        ),
        (
            "selected_checksum_covered",
            _selected_checksum_blocker(payload, request),
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
    canonical_version: str = CTBTO_TREATY_STATUS_DEFAULT_VERSION,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="CTBTO States Signatories, status as of 2023-06-01"``
    against a canonical 2024-03-13 bundle must surface a
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
        f"CTBTO Treaty Status readiness gate: requested "
        f"source_version={request.source_version!r} does not "
        f"match the canonical version {canonical_version!r}; "
        f"per docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION,
    )


def check_cache_policy(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values.

    The unified CTBTO Treaty Status adapter is offline /
    cache-only in this slice (the task brief explicitly cautions
    against adding live download / scraping). The gate blocks
    ``"refresh"`` / ``"no_cache"`` so the runner refuses to
    dispatch ``read_raw`` / ``transform`` rather than silently
    surfacing an HTTP-fetched payload. Supported policies
    (``"offline_only"`` / ``"prefer_cache"``) pass through
    unmodified.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return (
            f"CTBTO Treaty Status readiness gate: cache_policy="
            f"{request.cache_policy!r} is not supported by the "
            f"unified CTBTO Treaty Status adapter in this slice "
            f"(offline / cache-only). Stage a cached "
            f"{CTBTO_TREATY_STATUS_CSV_NAME!r} (or "
            f"{CTBTO_TREATY_STATUS_HTML_NAME!r}) under "
            f"data/raw/ctbto_treaty_status/ and re-run with "
            f"cache_policy='offline_only' or 'prefer_cache'.",
            CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY,
        )
    return None


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    coverage_start_year: int = CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
    coverage_end_year: int = CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when the
    transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is
      set (CTBTO Treaty Status is a country-level
      treaty-status snapshot and has no leader dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented CTBTO Treaty Status
      single-point 2024 coverage envelope (no stale-proxy
      fill per SRC-COV-002 / SRC-COV-003). The prototype's
      target year 2023 falls outside the envelope; the
      readiness envelope surfaces the warning so the
      operator can see the gap (the transform emits zero
      observations for that year).

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
                    "CTBTO Treaty Status is a country-level "
                    "treaty-status source; leader filters are "
                    "not supported and have been ignored."
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
                            f"year={year_int} is outside CTBTO "
                            f"Treaty Status coverage "
                            f"({coverage_start_year}-"
                            f"{coverage_end_year}); no "
                            f"observations will be emitted for "
                            f"this year (no stale-proxy fill)."
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
    "CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "csv_path",
    "html_path",
    "metadata_path",
    "read_metadata",
    "resolve_selected_cache_path",
]
