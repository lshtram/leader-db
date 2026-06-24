"""Readiness gate for the unified-source Maddison Project adapter.

This module owns the per-field metadata validation that runs
BEFORE the reader opens ``mpd2023.xlsx``. Every blocker names
the specific missing / invalid field or file so a developer
can fix the upstream issue without reading source code.

Split out of :mod:`leaders_db.sources.adapters.maddison_project.adapter`
to keep the adapter class focused on the lifecycle methods and
respect the documented 400-line module convention.

Maddison-specific request-scoping logic
--------------------------------------

The Maddison Project 2023 release's ``Full data`` sheet ends at
year 2022. A request for ``years=(2023,)`` is the documented
1-year-gap proxy mapping (same pattern as CIRIGHTS / UNDP HDI /
Leader Survival): the readiness gate surfaces a structured
``MADDISON_PROJECT_PROXY`` warning naming the 2023 -> 2022
mapping so the proxy is never silent. A request for
``years=(2024,)`` (or any year beyond the coverage envelope)
emits zero observations plus a structured ``YEAR_ABSENT``
warning (no multi-year stale-proxy fill, per
``docs/requirements/sources.md`` §7 SRC-COV-002 / SRC-COV-003).
A request with a ``leaders=`` filter is unsupported for a
country-year economic source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.

Checksum shape
--------------

The staged ``data/raw/maddison_project/metadata.json`` carries
the ``checksum_sha256`` field as a ``{filename: sha256}`` dict
(not the flat string the PWT adapter uses). The readiness gate
accepts BOTH shapes for backward compatibility:
``checksum_sha256="<hex>"`` (flat string, PWT-compatible) OR
``checksum_sha256={"mpd2023.xlsx": "<hex>"}`` (dict, Maddison's
canonical shape). New bundles may use either; legacy bundles
already in place use the dict shape.
"""
from __future__ import annotations

import hashlib
import json
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

from ._descriptor import (
    MADDISON_PROJECT_COVERAGE_END_YEAR,
    MADDISON_PROJECT_COVERAGE_START_YEAR,
    MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
)

# Required metadata fields. The set mirrors the canonical
# Maddison bundle contract documented in
# ``data/raw/maddison_project/metadata.json`` and matches the
# per-source fields the legacy readiness helpers expect.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "checksum_sha256",
    "local_files",
    "ingestion_status",
    "coverage",
)

# Module-local structured warning code used to surface the
# documented Maddison 2023 -> 2022 1-year-gap proxy mapping on
# the readiness envelope. Defined locally so the code stays
# specific to the Maddison adapter without widening the shared
# ``leaders_db.sources.warnings`` surface (which is reserved
# for cross-source contract codes per the warnings module
# docstring).
MADDISON_PROJECT_PROXY: str = "maddison_project_proxy_year"

# Module-local structured warning code used to reject an
# unsupported request source-version per SRC-REQ-009. Mirrors
# the PWT adapter's UNSUPPORTED_VERSION code so the
# Maddison readiness envelope stays consistent with the rest
# of the unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"


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
    metadata_path: Path, xlsx_path: Path, xlsx_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the xlsx is missing."""
    if not metadata_path.is_file():
        return (
            f"Maddison Project readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical data/raw/"
            "maddison_project/metadata.json before running Stage 2.",
            MISSING_METADATA,
        )
    if not xlsx_path.is_file():
        return (
            f"Maddison Project readiness gate: {xlsx_name} missing at "
            f"{xlsx_path}; place the canonical Maddison Project "
            "Database 2023 xlsx before running Stage 2.",
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
                f"Maddison Project readiness gate: metadata.json is "
                f"missing required field '{field}'.",
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
            f"Maddison Project readiness gate: metadata.json "
            f"'local_files' must include {xlsx_name!r}; got "
            f"{local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            f"Maddison Project readiness gate: metadata.json "
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
            f"Maddison Project readiness gate: metadata.json "
            f"'{field}' must be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _resolve_expected_checksum(
    payload: dict[str, Any], xlsx_name: str,
) -> str | None:
    """Return the expected SHA-256 for the xlsx from the metadata.

    Accepts BOTH shapes for backward compatibility with bundles
    staged before the unified readiness contract was documented:

    - Flat string: ``checksum_sha256="<hex>"`` (PWT-compatible).
    - Per-file dict: ``checksum_sha256={"mpd2023.xlsx": "<hex>"}``
      (Maddison's canonical shape, written by the source
      hygiene pass that staged the 4.9 MB bundle).

    Returns the hex SHA-256 string or ``None`` when neither
    shape matches.
    """
    value = payload.get("checksum_sha256")
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        per_file = value.get(xlsx_name)
        if isinstance(per_file, str) and per_file.strip():
            return per_file
    return None


def _checksum_match_blocker(
    payload: dict[str, Any], xlsx_path: Path, xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if the staged xlsx SHA-256 disagrees with the metadata field.

    Accepts both flat-string and per-file dict checksum shapes
    (see :func:`_resolve_expected_checksum`). The actual SHA-256
    is computed from the staged bytes and compared case-
    insensitively.
    """
    expected_sha = _resolve_expected_checksum(payload, xlsx_name)
    if expected_sha is None:
        return (
            "Maddison Project readiness gate: metadata.json "
            "'checksum_sha256' must be a non-empty hex SHA-256 "
            "string or a {'<xlsx_name>': '<sha256>'} dict.",
            MISSING_METADATA,
        )
    actual_sha = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return (
            f"Maddison Project readiness gate: xlsx checksum "
            f"mismatch. metadata.json says checksum_sha256="
            f"{expected_sha.strip().lower()!r} but the staged "
            f"xlsx has sha256="
            f"{actual_sha.lower()!r}.",
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
            "Maddison Project readiness gate: metadata.json "
            f"'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"Maddison Project readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified Maddison Project adapter supports "
            f"only canonical version {canonical_version!r}. "
            f"Re-stage a Maddison Project 2023 bundle or "
            f"correct metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


def check_metadata_well_formed(
    bundle_dir: Path, xlsx_name: str, canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the Maddison bundle's ``metadata.json`` + ``mpd2023.xlsx``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully well-formed.
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|<field>)``
      when the bundle is missing ``metadata.json``, missing
      ``mpd2023.xlsx``, missing a required metadata field, has
      ``local_files`` that does not include ``mpd2023.xlsx``, has
      ``ingestion_status != 'downloaded'``, has unsupported
      ``source_version``, or has a checksum that disagrees with
      the actual xlsx SHA-256.

    The third tuple element is the canonical warning code the
    adapter surfaces when ``ready=False``; the runner emits the
    full blocker text in the ``SourceWarning.message``.
    """
    metadata_path = bundle_dir / "metadata.json"
    xlsx_path = bundle_dir / xlsx_name

    # Phase A: presence checks.
    presence_blocker = _presence_blocker(
        metadata_path, xlsx_path, xlsx_name,
    )
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            f"Maddison Project readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation.
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
                payload,
                "source_url",
                "the canonical Maddison Project download URL",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the Maddison Project license (CC BY 4.0; cite "
                "Bolt and van Zanden 2024)",
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
            "checksum_match",
            _checksum_match_blocker(
                payload, xlsx_path, xlsx_name,
            ),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like ``source_version="9999"``
    against the Maddison Project 2023 bundle must surface a
    structured readiness error so the runner refuses to dispatch
    ``read_raw`` / ``transform`` (Rule #6 / Rule #15).

    Returns ``(message, code)`` when ``request.source_version``
    is set and differs from ``canonical_version``; returns
    ``None`` when ``request.source_version`` is ``None`` or
    when it equals ``canonical_version`` (explicit match).
    """
    if request.source_version is None:
        return None
    if request.source_version == canonical_version:
        return None
    return (
        f"Maddison Project readiness gate: requested source_version="
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

    Surfaces three categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner carries
    them through to the final result even when the transform
    layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (Maddison is a country-year economic source and has no
      leader dimension; SRC-REQ-005).
    - ``MADDISON_PROJECT_PROXY`` -- when ``request.years``
      contains ``2023`` (the documented 1-year-gap proxy mapping
      to ``2022``; this is the documented Maddison contract per
      ``docs/sources/attributions.md`` and the legacy Stage 2
      orchestrator, so the proxy is never silent). Years outside
      ``1..2022`` are still individually warned about via
      ``YEAR_ABSENT`` if applicable.
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that is outside the documented Maddison 2023 coverage
      envelope (``1..2022``). The proxy mapping (above) is the
      documented exception for the single-year ``2023`` request;
      every other out-of-coverage year (including multi-year
      ``2024+`` proxies) emits zero rows plus this warning
      (SRC-COV-002 / SRC-COV-003).

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
                    "Maddison Project is a country-year economic "
                    "source; leader filters are not supported and "
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
        proxy_year_requested = False
        for year in request.years:
            year_int = int(year)
            # Per-year coverage check. ``2023`` is the single
            # documented proxy mapping -- the next branch emits
            # the structured MADDISON_PROJECT_PROXY warning
            # below. Years < 1 or > 2022 (other than the
            # documented 2023 proxy) emit zero rows plus a
            # YEAR_ABSENT warning.
            if year_int > MADDISON_PROJECT_COVERAGE_END_YEAR:
                if (
                    year_int == MADDISON_PROJECT_PROXY_REQUESTED_YEAR
                ):
                    proxy_year_requested = True
                else:
                    warnings.append(
                        SourceWarning(
                            code=YEAR_ABSENT,
                            message=(
                                f"year={year_int} is outside the "
                                f"Maddison Project Database 2023 "
                                f"coverage envelope "
                                f"(1-{MADDISON_PROJECT_COVERAGE_END_YEAR}); "
                                f"no observations will be emitted "
                                f"for this year (no multi-year "
                                f"stale-proxy fill)."
                            ),
                            severity="warning",
                            source_id=request.source_id,
                            context={
                                "year": year_int,
                                "coverage_start_year": (
                                    MADDISON_PROJECT_COVERAGE_START_YEAR
                                ),
                                "coverage_end_year": (
                                    MADDISON_PROJECT_COVERAGE_END_YEAR
                                ),
                            },
                        ),
                    )
            elif year_int < MADDISON_PROJECT_COVERAGE_START_YEAR:
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside the "
                            f"Maddison Project Database 2023 "
                            f"coverage envelope "
                            f"(1-{MADDISON_PROJECT_COVERAGE_END_YEAR}); "
                            f"no observations will be emitted "
                            f"for this year."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                MADDISON_PROJECT_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                MADDISON_PROJECT_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )
        if proxy_year_requested:
            warnings.append(
                SourceWarning(
                    code=MADDISON_PROJECT_PROXY,
                    message=(
                        f"year={MADDISON_PROJECT_PROXY_REQUESTED_YEAR} "
                        "is proxied to Maddison Project 2022 data "
                        "(1-year-gap pattern, per the CIRIGHTS / "
                        "UNDP HDI / Leader Survival mapping; the "
                        "Maddison 2023 release ends at 2022). "
                        "Proxy observations carry the proxy_year "
                        "quality flag and the proxy_source_year "
                        "extension field so the mapping is never "
                        "silent."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "requested_year": (
                            MADDISON_PROJECT_PROXY_REQUESTED_YEAR
                        ),
                        "proxy_source_year": (
                            MADDISON_PROJECT_COVERAGE_END_YEAR
                        ),
                    },
                ),
            )

    return tuple(warnings)


__all__ = [
    "MADDISON_PROJECT_PROXY",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
