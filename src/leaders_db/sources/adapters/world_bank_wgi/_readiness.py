"""Readiness gate orchestrator for the unified-source WGI adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes the
per-field validators in
:mod:`._metadata_validators`, and the request-scoping warning
builder lives here alongside the source-version block.

Split out of :mod:`._metadata_validators` so the per-field
validators stay focused and the readiness orchestrator stays
focused on lifecycle ordering. Each per-field validator lives
in :mod:`._metadata_validators` and is imported here for
composition.

The gate accepts BOTH the canonical primary metadata shape
(``source_version`` / ``checksum_sha256`` / ``local_files`` /
``license_note`` / ``coverage``) AND the staged WGI legacy
shape (``version`` / ``sha256`` / ``local_file`` / ``license`` /
``coverage_start_year`` + ``coverage_end_year``) so the existing
staged bundle metadata does not need to be rewritten as part
of the migration.

Year semantics
--------------

WGI covers 1996-2022 (the canonical "2023 Update" release;
"2023" in the docs / attribution refers to the release year,
not the latest data year). A request for ``years=(2023,)`` or
``years=(1995,)`` (out of coverage) emits zero observations
plus a structured ``YEAR_ABSENT`` warning per SRC-COV-002 /
SRC-COV-003 (no stale-proxy fill).

A request with a ``leaders=`` filter is unsupported for a
country-year governance source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.
"""

from __future__ import annotations

from collections.abc import Iterable

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._descriptor import (
    WORLD_BANK_WGI_COVERAGE_END_YEAR,
    WORLD_BANK_WGI_COVERAGE_START_YEAR,
)
from ._metadata_validators import (
    UNSUPPORTED_VERSION,
    _checksum_match_blocker,
    _has_coverage_pair,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)


def check_metadata_well_formed(
    bundle_dir, xlsx_name: str, canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the WGI bundle's ``metadata.json`` + ``wgidataset.xlsx``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully well-formed.
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|<field>)``
      when the bundle is missing ``metadata.json``, missing
      ``wgidataset.xlsx``, missing a required metadata field
      (in either primary or legacy shape), has
      ``local_files`` / ``local_file`` that does not include
      ``wgidataset.xlsx``, has ``ingestion_status != 'downloaded'``,
      has an unsupported / mismatched source-version stamp, or
      has a checksum that disagrees with the actual xlsx SHA-256.

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
            "World Bank WGI readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed. We accept BOTH the canonical
    # primary shape (PWT / Maddison / WDI convention) AND the
    # legacy WGI shape (``version`` / ``sha256`` / ``local_file``
    # / ``license``).
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
                None,
                "the canonical WGI xlsx download URL or "
                "canonical_page",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "license",
                "the WGI license (CC BY 4.0 International)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                None,
                "the temporal + spatial coverage (or "
                "coverage_start_year + coverage_end_year pair)",
            )
            if not _has_coverage_pair(payload)
            else None,
        ),
        (
            "checksum_sha256",
            _non_empty_string_blocker(
                payload,
                "checksum_sha256",
                "sha256",
                "a non-empty hex SHA-256 string",
            ),
        ),
        ("checksum_match", _checksum_match_blocker(payload, xlsx_path)),
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
    against a canonical WGI bundle must surface a structured
    readiness error so the runner refuses to dispatch
    ``read_raw`` / ``transform``.

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
        "World Bank WGI readiness gate: requested source_version="
        f"{request.source_version!r} does not match the canonical "
        f"version {canonical_version!r}; per docs/requirements/"
        "sources.md SRC-REQ-009, unsupported source-version "
        "requests must fail readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use the "
        "canonical default).",
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
      (WGI is a country-year governance source and has no leader
      dimension; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented WGI 1996-2022 coverage
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
                    "World Bank WGI is a country-year governance "
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
        for year in request.years:
            year_int = int(year)
            if (
                year_int < WORLD_BANK_WGI_COVERAGE_START_YEAR
                or year_int > WORLD_BANK_WGI_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            f"World Bank WGI coverage "
                            f"({WORLD_BANK_WGI_COVERAGE_START_YEAR}-"
                            f"{WORLD_BANK_WGI_COVERAGE_END_YEAR}); no "
                            f"observations will be emitted "
                            f"for this year (no stale-proxy "
                            f"fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                WORLD_BANK_WGI_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                WORLD_BANK_WGI_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
