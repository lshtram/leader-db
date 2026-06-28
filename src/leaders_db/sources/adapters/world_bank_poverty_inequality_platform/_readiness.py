"""Readiness checks for the clean World Bank Poverty and Inequality
Platform (PIP) adapter.

The orchestrator :func:`check_metadata_well_formed` composes
the per-field validators: file presence (metadata + cached CSV
or JSON file), metadata fields (required, ``local_files``,
``ingestion_status``, ``source_version``), checksum match, the
**selected-file contract** (the actually-present cache file
that the reader will load must be listed in
``metadata.local_files`` AND covered by
``metadata.checksum_sha256``), and the source-version stamp.
The readiness envelope also builds the request-scoping
warnings (``leaders=``, out-of-coverage years,
``world_bank_poverty_inequality_platform_unsupported_cache_policy``).

Year semantics
--------------

The World Bank PIP dataset covers a broad 1960-2024 envelope
per the canonical descriptor (PIP records begin in the early
1960s when survey-based poverty estimates become available for
low / lower-middle income countries; the canonical probe stamp
is 2021 for the ``20260324_2021`` PIP version with a few
extrapolation cells into 2024 for a handful of countries). A
request for an out-of-coverage year (e.g. ``years=(2050,)`` --
well beyond the canonical envelope) emits zero observations AND
a structured ``YEAR_ABSENT`` warning -- no stale-proxy fill
(SRC-COV-002 / SRC-COV-003). The prototype's target year 2023
falls WITHIN the canonical envelope (1960-2024) so 2023 is
in-coverage.

Leader-filter semantics
-----------------------

A request with a ``leaders=`` filter is unsupported for a
country-year poverty / inequality source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
The transform ignores the filter (World Bank PIP is country-
year poverty / inequality evidence, not leader-identity
evidence; Stage 4 is the resolver for leader-identity
evidence).

Cache-policy semantics
----------------------

The unified World Bank PIP adapter is offline / cache-only in
this slice (the task brief: "Build an offline/cache-first
adapter. Do NOT implement live HTTP fetching"). The gate
blocks ``cache_policy="refresh"`` / ``"no_cache"`` so the
runner refuses to dispatch ``read_raw`` / ``transform`` rather
than silently surfacing an HTTP-fetched payload. Supported
policies (``"offline_only"`` / ``"prefer_cache"``) pass through
unmodified.

Country-filter semantics
------------------------

A request with ``countries=`` filters the cached PIP table
by case-folded substring match on the source-native
``country_name`` column (the PIP dataset uses the World Bank's
own country display names, which are NOT ISO3; the unified
adapter never invents ISO3 codes -- ``country_code`` is left
as ``None`` and the source-native identifier is preserved on
``extension["world_bank_poverty_inequality_platform_country_code_raw"]``).
The filter matches against the cached ``country_name`` cell so
callers can filter for "PIP observations for Country A" by
passing ``countries=("Country A",)``.

ISO3 caveat
-----------

The cached PIP CSV / JSON row carries a 3-character
``country_code`` column that LOOKS LIKE ISO3 but is the World
Bank's own reporting identifier (not a canonical ISO3 mapping
introduced by the project). The unified adapter preserves the
source-native ``country_code`` verbatim on the audit-trail
extension payload
(``extension["world_bank_poverty_inequality_platform_country_code_raw"]``)
and does NOT assume the source identifier is a canonical ISO3
even when it resembles one. The ``country_code`` field on
emitted observations remains ``None`` until later matching /
resolution stages introduce a canonical ISO3 mapping.
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
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical World Bank PIP bundle directory.

    The canonical World Bank PIP bundle folder is
    ``world_bank_poverty_inequality_platform/`` (the slug is
    the folder name; no source-key / folder-alias
    reconciliation is needed).
    """
    return (
        Path(request.raw_root)
        / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY
    )


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical World Bank PIP ``metadata.json`` path."""
    return (
        bundle_dir(request)
        / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME
    )


def csv_path(request: SourceIngestRequest) -> Path:
    """Return the canonical World Bank PIP cached CSV path."""
    return (
        bundle_dir(request)
        / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME
    )


def json_path(request: SourceIngestRequest) -> Path:
    """Return the canonical World Bank PIP cached JSON path."""
    return (
        bundle_dir(request)
        / WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME
    )


def resolve_selected_cache_path(
    request: SourceIngestRequest,
) -> Path | None:
    """Return the cache file path the reader would actually load.

    Mirrors the selection logic in
    :func:`._raw_read.read_world_bank_poverty_inequality_platform_cache`:
    the canonical CSV shape is preferred when it is on disk,
    and the canonical JSON shape is used only when the CSV is
    absent. Returns ``None`` when NEITHER file is on disk --
    the presence blocker fires first in that case.

    The helper exists so the readiness gate can validate that
    the **selected** cache file is the one declared in
    ``metadata.local_files`` AND covered by
    ``metadata.checksum_sha256``. Without this helper the gate
    could pass a bundle where, e.g., the cached JSON export is
    the file actually read but ``local_files`` only lists the
    canonical CSV file.
    """
    csv_p = csv_path(request)
    if csv_p.is_file():
        return csv_p
    json_p = json_path(request)
    if json_p.is_file():
        return json_p
    return None


def read_metadata(path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on
    any error.

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
    NEITHER the canonical CSV NOR the canonical JSON export
    is on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still
    reported as ``missing_metadata`` rather than ``missing_raw``.
    """
    metadata_p = metadata_path(request)
    if not metadata_p.is_file():
        return (
            f"World Bank PIP readiness gate: metadata.json "
            f"missing at {metadata_p}; place the canonical "
            f"data/raw/world_bank_poverty_inequality_platform/metadata.json "
            f"before running ingestion.",
            MISSING_METADATA,
        )

    csv_p = csv_path(request)
    json_p = json_path(request)
    if not csv_p.is_file() and not json_p.is_file():
        return (
            "World Bank PIP readiness gate: cached export "
            "missing; place either "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME!r} or "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME!r} at "
            f"{bundle_dir(request)} before running ingestion.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent.

    The canonical World Bank PIP bundle metadata shape is
    ``source_name`` / ``source_version`` / ``source_url`` /
    ``license_note`` / ``coverage`` / ``local_files`` /
    ``ingestion_status`` / ``checksum_sha256`` /
    ``download_date`` / ``notes``. Missing fields fire a
    structured ``missing_metadata`` error so the runner raises
    ``RuntimeError`` BEFORE the reader opens the cached CSV /
    JSON file.
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
        "version_id",
        "ppp_version",
        "notes",
    )
    for field in required:
        if field not in payload:
            return (
                f"World Bank PIP readiness gate: metadata.json "
                f"is missing required field {field!r}.",
                MISSING_METADATA,
            )
    return None


def _metadata_version_id_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block when metadata version_id / ppp_version drift from
    the canonical supported PIP basis.

    PIP values are version- and PPP-basis-specific; the bundle
    metadata must state both fields explicitly so rows cannot be
    mislabeled as the descriptor's canonical version.
    """
    version_id = payload.get("version_id")
    if not isinstance(version_id, str) or not version_id.strip():
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'version_id' must be a non-empty string naming "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
        )
    if version_id.strip() != WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID:
        return (
            "World Bank PIP readiness gate: metadata.json "
            f"'version_id' is {version_id.strip()!r}; expected "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
        )

    ppp_version = payload.get("ppp_version")
    if not isinstance(ppp_version, str) or not ppp_version.strip():
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'ppp_version' must be a non-empty string naming "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
        )
    if ppp_version.strip() != WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION:
        return (
            "World Bank PIP readiness gate: metadata.json "
            f"'ppp_version' is {ppp_version.strip()!r}; expected "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
        )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include a canonical
    cached file.

    The canonical World Bank PIP bundle metadata must list
    the cached PIP export in the ``local_files`` list. The
    bundle may legitimately list EITHER the canonical CSV
    (``pip_stats.csv``) OR the canonical JSON
    (``pip_stats.json``) OR BOTH -- the cache is
    content-addressable by file name and the adapter prefers
    the CSV shape when both are staged. A bundle that lists
    neither file is a schema contract violation (the readiness
    gate cannot validate which file to read).
    """
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files:
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'local_files' must be a non-empty string list.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        )
    if not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'local_files' must be a list of non-empty strings.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        )
    if not (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME in local_files
        or WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME in local_files
    ):
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'local_files' must include at least one of the "
            "canonical cached files ("
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME!r} or "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME!r}); "
            f"got {local_files!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'ingestion_status' must be 'downloaded'; got "
            f"{payload.get('ingestion_status')!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not
    canonical."""
    metadata_version = payload.get("source_version")
    if (
        not isinstance(metadata_version, str)
        or not metadata_version.strip()
    ):
        return (
            "World Bank PIP readiness gate: metadata.json "
            "'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"World Bank PIP readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified World Bank PIP adapter supports "
            f"only canonical version {canonical_version!r}. "
            f"Re-stage a World Bank PIP bundle or correct "
            f"metadata.json before running ingestion.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH,
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
            f"World Bank PIP readiness gate: metadata.json "
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
    shape (``checksum_sha256 = {"pip_stats.csv": "<64-hex>"}``).
    Empty / malformed fields surface a structured
    ``missing_metadata`` error.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str):
        if not value.strip():
            return (
                "World Bank PIP readiness gate: "
                "metadata.json 'checksum_sha256' must be a "
                "non-empty hex SHA-256 string OR a per-file "
                "dict mapping file names to hex SHA-256 strings.",
                MISSING_METADATA,
            )
        return None
    if isinstance(value, dict):
        if not value:
            return (
                "World Bank PIP readiness gate: "
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
                    "World Bank PIP readiness gate: "
                    "metadata.json 'checksum_sha256' per-file "
                    "dict entries must be non-empty strings "
                    "mapping file names to hex SHA-256 strings.",
                    MISSING_METADATA,
                )
        return None
    return (
        "World Bank PIP readiness gate: metadata.json "
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
    ignored -- there is exactly one cached file in the canonical
    CSV / JSON shape) AND the per-file dict shape
    (``{file_name: "<64-hex>"}``). Returns ``None`` when the
    field is absent, malformed, or has no non-empty entry for
    the requested file name.
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
    """Block if the staged CSV / JSON SHA-256 disagrees with
    the metadata field.

    Accepts BOTH the canonical flat-string shape
    (``checksum_sha256 = "<64-hex>"``) AND the per-file dict
    shape (``checksum_sha256 = {"pip_stats.csv": "<64-hex>"}``
    or ``{"pip_stats.json": "<64-hex>"}``). When the checksum
    shape is present, the gate verifies the cached file SHA-256
    against the metadata field for the canonical CSV (when
    present on disk) AND for the canonical JSON fallback (when
    present on disk).
    """
    checksum = payload.get("checksum_sha256")
    csv_p = csv_path(request)
    if csv_p.is_file():
        expected_sha = _extract_checksum(
            checksum,
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
        )
        if expected_sha is not None:
            actual_sha = hashlib.sha256(csv_p.read_bytes()).hexdigest()
            if actual_sha.lower() != expected_sha.strip().lower():
                return (
                    f"World Bank PIP readiness gate: cached "
                    f"CSV checksum mismatch for "
                    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME!r}. "
                    f"metadata.json says checksum_sha256="
                    f"{expected_sha.strip().lower()!r} but the "
                    f"staged file has sha256={actual_sha.lower()!r}.",
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
                )
    json_p = json_path(request)
    if json_p.is_file():
        expected_sha = _extract_checksum(
            checksum,
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
        )
        if expected_sha is not None:
            actual_sha = hashlib.sha256(json_p.read_bytes()).hexdigest()
            if actual_sha.lower() != expected_sha.strip().lower():
                return (
                    f"World Bank PIP readiness gate: cached "
                    f"JSON checksum mismatch for "
                    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME!r}. "
                    f"metadata.json says checksum_sha256="
                    f"{expected_sha.strip().lower()!r} but the "
                    f"staged file has sha256={actual_sha.lower()!r}.",
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
                )
    return None


def _selected_local_files_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the actually-present SELECTED cache file is not
    declared in ``metadata.local_files``.

    The existing :func:`_local_files_blocker` accepts any
    bundle whose ``local_files`` includes the canonical CSV OR
    the canonical JSON -- but that check is too lenient when
    only ONE of those files is actually on disk. The unified
    reader selects the canonical CSV when it is on disk and
    falls back to the JSON file only when the CSV is absent,
    so the SELECTED cache file (the one the reader will load)
    MUST be listed in ``local_files`` -- otherwise the
    bundle's ``local_files`` declaration silently disagrees
    with the file the reader will actually consume.

    For example, a bundle with the JSON fallback staged on disk
    and ``local_files=[pip_stats.csv]`` would pass the existing
    check (CSV is listed) but the reader would load the
    undeclared JSON file. This helper closes that gap and
    surfaces a structured
    ``world_bank_poverty_inequality_platform_local_files_invalid``
    blocker.
    """
    selected = resolve_selected_cache_path(request)
    if selected is None:
        # The presence blocker fires first when NEITHER the
        # canonical CSV NOR the canonical JSON is on disk;
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
            f"World Bank PIP readiness gate: metadata.json "
            f"'local_files' must declare the actually-present "
            f"selected cache file {selected.name!r} that the "
            f"reader will load (the canonical CSV is preferred "
            f"when present; the JSON fallback is used only "
            f"when the CSV is absent). The bundle's "
            f"'local_files' entry is {local_files!r} but the "
            f"selected file {selected.name!r} is not declared; "
            f"update metadata.local_files to include "
            f"{selected.name!r} before running ingestion.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID,
        )
    return None


def _selected_checksum_blocker(
    payload: dict[str, Any],
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if the actually-present SELECTED cache file is not
    checksum-covered by ``metadata.checksum_sha256``.

    The existing :func:`_checksum_match_blocker` validates
    that the on-disk SHA-256 matches the metadata field WHEN
    the metadata field covers the file -- but the existing
    check stays silent when the metadata field is absent or
    has no entry for the file. The reader always loads the
    SELECTED cache file (CSV preferred over JSON), so the
    bundle must declare a checksum for the selected file.
    Otherwise the bundle's ``checksum_sha256`` silently
    disagrees with the file the reader will actually consume.

    For example, a bundle with the JSON fallback staged on
    disk and ``checksum_sha256={"pip_stats.csv": "<64-hex>"}``
    (no JSON entry) would pass the existing
    ``_checksum_match_blocker`` (the JSON file is on disk but
    the per-file dict has no JSON entry, so
    ``_extract_checksum`` returns None and the loop is skipped)
    but the reader would load the undeclared JSON file. This
    helper closes that gap and surfaces a structured
    ``world_bank_poverty_inequality_platform_checksum_mismatch``
    blocker.

    The flat-string ``checksum_sha256="<64-hex>"`` shape
    covers the canonical CSV by convention; when the SELECTED
    file is the canonical CSV the flat-string shape is
    sufficient. When the SELECTED file is the JSON fallback,
    the bundle MUST use the per-file dict shape with an
    explicit ``pip_stats.json`` entry.
    """
    selected = resolve_selected_cache_path(request)
    if selected is None:
        # The presence blocker fires first when NEITHER the
        # canonical CSV NOR the canonical JSON is on disk;
        # this helper only validates the selected file shape
        # so a None result means there is nothing to validate
        # yet.
        return None
    checksum = payload.get("checksum_sha256")
    expected_sha = _extract_checksum(checksum, selected.name)
    if expected_sha is None:
        return (
            f"World Bank PIP readiness gate: metadata.json "
            f"'checksum_sha256' must cover the actually-present "
            f"selected cache file {selected.name!r} that the "
            f"reader will load (the canonical CSV is preferred "
            f"when present; the JSON fallback is used only "
            f"when the CSV is absent). The bundle's "
            f"'checksum_sha256' entry is {checksum!r} but the "
            f"selected file {selected.name!r} has no checksum "
            f"entry; add a checksum entry for {selected.name!r} "
            f"(per-file dict shape) or use the flat-string "
            f"shape when the selected file is the canonical "
            f"CSV before running ingestion.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH,
        )
    return None


def check_metadata_well_formed(
    request: SourceIngestRequest,
    *,
    canonical_version: str = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
    ),
) -> tuple[bool, str | None, str | None]:
    """Validate the World Bank PIP bundle's ``metadata.json`` +
    cached CSV / JSON file.

    Returns ``(ready, blocker, code)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed (file presence + metadata fields + canonical
      metadata ``source_version`` + ``local_files`` annotation
      + ``ingestion_status='downloaded'`` + checksum match +
      the **selected-file contract** that the actually-present
      cache file the reader will load is declared in
      ``local_files`` AND covered by ``checksum_sha256``).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_*)``
      when the bundle is missing ``metadata.json``, missing the
      cached CSV / JSON, missing a required metadata field, has
      ``local_files`` that does not include the canonical
      cached file, has ``ingestion_status != 'downloaded'``,
      has unsupported ``source_version``, has a checksum that
      disagrees with the actual cached file SHA-256, has a
      ``local_files`` declaration that does NOT list the
      SELECTED cache file the reader will actually load, or
      has a ``checksum_sha256`` that does NOT cover the
      SELECTED cache file.

    The mandatory readiness requirement is on raw-file
    presence: a metadata-only bundle is intentionally NOT
    runner-ready; the gate fires ``MISSING_RAW`` whenever
    NEITHER the canonical CSV NOR the canonical JSON export is
    on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still reported
    as ``missing_metadata`` rather than ``missing_raw``.

    The selected-file contract closes the gap where the
    canonical CSV is listed in ``local_files`` but only the
    JSON fallback is on disk (the reader would silently load
    the undeclared JSON file). The contract requires the
    SELECTED cache file -- the one the reader will actually
    load -- to be declared in ``local_files`` AND covered by
    ``checksum_sha256``.
    """
    # Phase A: presence check.
    presence_blocker = _presence_blocker(request)
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = read_metadata(metadata_path(request))
    if not payload:
        return False, (
            "World Bank PIP readiness gate: failed to parse "
            f"metadata.json at {metadata_path(request)}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed.
    field_checks: tuple[
        tuple[str, tuple[str, str] | None], ...
    ] = (
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
            "version_id_ppp_version",
            _metadata_version_id_blocker(payload),
        ),
        (
            "source_name",
            _non_empty_string_blocker(
                payload,
                "source_name",
                "the canonical World Bank PIP source name "
                "('World Bank Poverty and Inequality "
                "Platform')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical World Bank PIP canonical URL "
                "(https://pip.worldbank.org/)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the World Bank Terms of Use for Datasets "
                "caveat (free use with attribution; cite "
                "World Bank Group + the canonical URL)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the World Bank PIP temporal coverage "
                "(1960-2024; canonical PIP version stamp "
                "20260324_2021 per the canonical probe)",
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
    canonical_version: str = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
    ),
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the
    canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="World Bank PIP, version 20260324_2017"``
    against a canonical ``20260324_2021`` bundle must surface a
    structured readiness error so the runner refuses to dispatch
    ``read_raw`` / ``transform`` (silently propagating an
    unsupported version into ``RawAsset.version`` /
    ``NormalizedObservation.source_version`` would silently lie
    to downstream scorers -- PIP version stamps are
    not interchangeable across PPP bases per the canonical
    caveat).

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
        f"World Bank PIP readiness gate: requested "
        f"source_version={request.source_version!r} does not "
        f"match the canonical version {canonical_version!r}; "
        f"per docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION,
    )


def check_cache_policy(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported
    values.

    The unified World Bank PIP adapter is offline /
    cache-only in this slice (the task brief: "Build an
    offline/cache-first adapter. Do NOT implement live HTTP
    fetching"). The gate blocks ``"refresh"`` / ``"no_cache"``
    so the runner refuses to dispatch ``read_raw`` /
    ``transform`` rather than silently surfacing an
    HTTP-fetched payload. Supported policies
    (``"offline_only"`` / ``"prefer_cache"``) pass through
    unmodified.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return (
            f"World Bank PIP readiness gate: cache_policy="
            f"{request.cache_policy!r} is not supported by the "
            f"unified World Bank PIP adapter in this slice "
            f"(offline / cache-only). Stage a cached "
            f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME!r} "
            f"(or {WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME!r}) "
            f"under "
            f"data/raw/world_bank_poverty_inequality_platform/ "
            f"and re-run with cache_policy='offline_only' or "
            f"'prefer_cache'.",
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY,
        )
    return None


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    coverage_start_year: int = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR
    ),
    coverage_end_year: int = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR
    ),
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness
    envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when the
    transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is
      set (World Bank PIP is a country-year poverty /
      inequality source and has no leader dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented World Bank PIP
      1960-2024 coverage envelope (no stale-proxy fill per
      SRC-COV-002 / SRC-COV-003). The prototype's target year
      2023 falls WITHIN the envelope.

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
                    "World Bank PIP is a country-year poverty "
                    "/ inequality source; leader filters are "
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
                            f"year={year_int} is outside World "
                            f"Bank PIP coverage "
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
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION",
    "bundle_dir",
    "check_cache_policy",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "csv_path",
    "json_path",
    "metadata_path",
    "read_metadata",
    "resolve_selected_cache_path",
]
