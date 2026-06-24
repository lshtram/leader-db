"""Readiness gate for the unified-source PWT adapter.

This module owns the per-field metadata validation that runs
BEFORE the reader opens ``pwt1001.xlsx``. Every blocker names
the specific missing / invalid field or file so a developer can
fix the upstream issue without reading source code.

Split out of :mod:`leaders_db.sources.adapters.pwt.adapter` to
keep the adapter class focused on the lifecycle methods and
respect the documented 400-line module convention.
"""

from __future__ import annotations

import hashlib
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
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

# Required metadata fields (mirrors the legacy readiness contract
# so the unified adapter does not weaken the documented gate).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "checksum_sha256",
    "local_files",
    "ingestion_status",
    "coverage",
)


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        import json

        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Path, xlsx_path: Path,
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the xlsx is missing."""
    if not metadata_path.is_file():
        return (
            f"PWT readiness gate: metadata.json missing at "
            f"{metadata_path}; place the canonical "
            "data/raw/pwt/metadata.json before running Stage 2.",
            MISSING_METADATA,
        )
    if not xlsx_path.is_file():
        return (
            f"PWT readiness gate: {xlsx_name} missing at "
            f"{xlsx_path}; place the canonical Penn World Table "
            "10.01 xlsx before running Stage 2.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                f"PWT readiness gate: metadata.json is missing "
                f"required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any], xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the canonical xlsx."""
    local_files = payload.get("local_files")
    if (
        not isinstance(local_files, list)
        or xlsx_name not in local_files
    ):
        return (
            f"PWT readiness gate: metadata.json 'local_files' "
            f"must include {xlsx_name!r}; got {local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            f"PWT readiness gate: metadata.json "
            f"'ingestion_status' must be 'downloaded'; got "
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
            f"PWT readiness gate: metadata.json '{field}' must "
            f"be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any], xlsx_path: Path,
) -> tuple[str, str] | None:
    """Block if the staged xlsx SHA-256 disagrees with the metadata field."""
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        # Already covered by ``_non_empty_string_blocker`` but
        # kept as defense-in-depth so this helper is callable
        # independently.
        return (
            "PWT readiness gate: metadata.json 'checksum_sha256' "
            "must be a non-empty hex SHA-256 string.",
            MISSING_METADATA,
        )
    actual_sha = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return (
            f"PWT readiness gate: xlsx checksum mismatch. "
            f"metadata.json says checksum_sha256="
            f"{expected_sha.strip().lower()!r} but the staged "
            f"xlsx has sha256="
            f"{actual_sha.lower()!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata source_version is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "PWT readiness gate: metadata.json 'source_version' must "
            f"be the canonical version {canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"PWT readiness gate: metadata.json 'source_version' "
            f"is {metadata_version.strip()!r}, but the unified PWT "
            f"adapter supports only canonical version "
            f"{canonical_version!r}. Re-stage a PWT 10.01 bundle "
            f"or correct metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


def check_metadata_well_formed(
    bundle_dir: Path, xlsx_name: str, canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the PWT bundle's ``metadata.json`` + ``pwt1001.xlsx``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully well-formed.
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|<field>)``
      when the bundle is missing ``metadata.json``, missing
      ``pwt1001.xlsx``, missing a required metadata field, has
      ``local_files`` that does not include ``pwt1001.xlsx``, has
      ``ingestion_status != 'downloaded'``, has unsupported
      ``source_version``, or has a checksum that disagrees with
      the actual xlsx SHA-256.

    The third tuple element is the canonical warning code the
    adapter surfaces when ``ready=False``; the runner emits the
    full blocker text in the ``SourceWarning.message``.
    """
    metadata_path = bundle_dir / "metadata.json"
    xlsx_path = bundle_dir / xlsx_name

    # Phase A: presence checks. A missing metadata.json OR a
    # missing xlsx is a blocker; the message names the file.
    presence_blocker = _presence_blocker(
        metadata_path, xlsx_path, xlsx_name,
    )
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            f"PWT readiness gate: failed to parse metadata.json "
            f"at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload, xlsx_name)),
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
            "source_url",
            _non_empty_string_blocker(
                payload, "source_url", "the canonical PWT download URL",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the PWT license (CC BY 4.0; cite Feenstra, "
                "Inklaar, Timmer 2015)",
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
        (
            "checksum_sha256",
            _non_empty_string_blocker(
                payload,
                "checksum_sha256",
                "a non-empty hex SHA-256 string",
            ),
        ),
        ("checksum_match", _checksum_match_blocker(payload, xlsx_path)),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    default_version: str,
    coverage_start_year: int,
    coverage_end_year: int,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner carries
    them through to the final result even when the transform
    layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (PWT is a country-year economic source and has no leader
      dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented PWT 10.01 coverage
      envelope (no stale-proxy fill per SRC-COV-002 /
      SRC-COV-003).

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
                    "PWT is a country-year economic source; "
                    "leader filters are not supported and "
                    "have been ignored."
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
                            f"year={year_int} is outside "
                            f"PWT 10.01 coverage "
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


# Code used by :func:`check_source_version` when
# ``request.source_version`` differs from the canonical version.
# Defined as a module-local constant so the strings stay
# consistent with the rest of the readiness helpers without
# widening the shared ``leaders_db.sources.warnings`` surface
# (this is a PWT-specific blocker code, not a cross-source
# contract code).
UNSUPPORTED_VERSION: str = "unsupported_version"


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="9.99"`` against a PWT 10.01 bundle must
    surface a structured readiness error so the runner refuses
    to dispatch ``read_raw`` / ``transform`` (Rule #6 / Rule
    #15 -- the legacy bundle does not encode a per-version
    stamp beyond ``metadata.json['source_version']``, and
    silently propagating an unsupported version into
    ``RawAsset.version`` / ``NormalizedObservation.source_version``
    would silently lie to downstream scorers).

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
        f"PWT readiness gate: requested source_version="
        f"{request.source_version!r} does not match the "
        f"canonical version {canonical_version!r}; per "
        f"docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        UNSUPPORTED_VERSION,
    )


__all__ = [
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
