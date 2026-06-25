"""Readiness gate orchestrator for the unified-source V-Dem adapter.

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

Year semantics
--------------

V-Dem covers 1789-2025 per the canonical codebook. A request
for an out-of-coverage year (e.g. ``years=(2026,)`` or
``years=(1788,)``) emits zero observations plus a structured
``YEAR_ABSENT`` warning per SRC-COV-002 / SRC-COV-003 (no
stale-proxy fill).

A request with a ``leaders=`` filter is unsupported for a
country-year political / governance source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005.

Checksum contract
-----------------

The metadata ``checksum_sha256`` covers the staged zip, NOT
the 388MB CSV. The gate validates the metadata shape AND, if
the zip is staged, recomputes the zip's SHA-256. The CSV is
never hashed (it would be a 388MB I/O for no benefit; the
audit chain is preserved via the legacy parquet metadata and
the canonical attribution text).
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
    VDEM_COVERAGE_END_YEAR,
    VDEM_COVERAGE_START_YEAR,
)
from ._metadata_validators import (
    UNSUPPORTED_VERSION,
    VDEM_CHECKSUM_MISMATCH,
    _checksum_match_blocker,
    _checksum_shape_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
    _year_range_from_coverage,
)


def check_metadata_well_formed(
    bundle_dir, csv_name: str, zip_name: str, canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the V-Dem bundle's ``metadata.json`` + ``CSV`` + ``zip``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed.
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|...)``
      when the bundle is missing ``metadata.json``, missing
      ``V-Dem-CY-Full+Others-v16.csv``, missing a required
      metadata field, has ``local_files`` that does not
      include the canonical CSV, has
      ``ingestion_status not in ('ingested', 'downloaded')``,
      has an unsupported / mismatched source-version stamp,
      has a malformed ``checksum_sha256`` (not a 64-char hex
      SHA-256), or has a zip checksum that disagrees with the
      metadata field.

    The third tuple element is the canonical warning code the
    adapter surfaces when ``ready=False``; the runner emits the
    full blocker text in the ``SourceWarning.message``.

    The CSV (388MB) is NEVER hashed. The zip checksum is
    verified only when the zip is present in the bundle (the
    canonical V-Dem bundle carries the zip; a test fixture
    with only the CSV is acceptable -- the gate does not
    block on a missing zip alone, but the gate still requires
    the CSV to be present and the metadata to be well-formed).
    """
    metadata_path = bundle_dir / "metadata.json"
    csv_path = bundle_dir / csv_name

    # Phase A: presence checks.
    presence_blocker = _presence_blocker(
        metadata_path, csv_path, csv_name,
    )
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            "V-Dem readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload, csv_name)),
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
                "the canonical V-Dem source name",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical V-Dem data landing page or DOI",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the V-Dem license (free academic; cite "
                "Coppedge et al. 2026)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the temporal + spatial coverage (or "
                "coverage_start_year + coverage_end_year pair)",
            )
            if _year_range_from_coverage(payload) is None
            else None,
        ),
        ("checksum_shape", _checksum_shape_blocker(payload)),
        (
            "checksum_match",
            _checksum_match_blocker(payload, bundle_dir, zip_name),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            # V-Dem zip checksum mismatches surface the
            # module-local VDEM_CHECKSUM_MISMATCH code (NOT
            # MISSING_METADATA); remap to the canonical
            # MISSING_METADATA only when the blocker code is
            # not already a V-Dem-specific code.
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
    with actionable error." A request like ``source_version="v15"``
    against a canonical V-Dem v16 bundle must surface a
    structured readiness error so the runner refuses to
    dispatch ``read_raw`` / ``transform``.

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
        "V-Dem readiness gate: requested source_version="
        f"{request.source_version!r} does not match the "
        f"canonical version {canonical_version!r}; per "
        "docs/requirements/sources.md SRC-REQ-009, "
        "unsupported source-version requests must fail "
        "readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        "the canonical default).",
        UNSUPPORTED_VERSION,
    )


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when the
    transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is
      set (V-Dem is a country-year political / governance
      source and has no leader dimension; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented V-Dem 1789-2025
      coverage envelope (no stale-proxy fill per
      SRC-COV-002 / SRC-COV-003).

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
                    "V-Dem is a country-year political / "
                    "governance source; leader filters are not "
                    "supported and have been ignored."
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
                year_int < VDEM_COVERAGE_START_YEAR
                or year_int > VDEM_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside V-Dem "
                            f"coverage ({VDEM_COVERAGE_START_YEAR}-"
                            f"{VDEM_COVERAGE_END_YEAR}); no "
                            f"observations will be emitted for "
                            f"this year (no stale-proxy fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                VDEM_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                VDEM_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "UNSUPPORTED_VERSION",
    "VDEM_CHECKSUM_MISMATCH",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
