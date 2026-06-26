"""Readiness gate orchestrator for the unified-source
PTS adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes the
per-field validators in :mod:`._metadata_validators`,
and the request-scoping warning builder lives here
alongside the source-version block.

Split out of :mod:`._metadata_validators` so the
per-field validators stay focused and the readiness
orchestrator stays focused on lifecycle ordering.

Year semantics
--------------

PTS covers 1976-2024 per the canonical staged bundle
metadata (``coverage_start_year: 1976`` /
``coverage_end_year: 2024``) + the live xlsx (49
distinct years from 1976 through 2024; verified live
2026-06-18 per ``docs/architecture/pts.md`` §2). A
request for an out-of-coverage year (e.g. ``years=(2025,)``
or ``years=(1975,)``) emits zero observations plus a
structured ``YEAR_ABSENT`` warning per SRC-COV-002 /
SRC-COV-003 (no stale-proxy fill).

A request with a ``leaders=`` filter is unsupported
for a country-year political-terror source and surfaces
a structured ``UNSUPPORTED_FILTER`` warning per
SRC-REQ-005.

Country-filter semantics
------------------------

The PTS xlsx carries the COW_Code_A 3-letter
alphabetic column (``COW_Code_A``); Stage 3 country
match resolves the COW code to ISO3 via the canonical
country table. The ``request.countries`` filter applies
as an exact match against the ``COW_Code_A`` column
(the cleanest contract given the column is the
canonical primary key per design doc §7). Passing a
non-COW code (e.g. an ISO3) yields zero rows (the
contract is documented here so callers do not silently
get zero observations when they pass a non-COW
identifier).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

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
    PTS_COVERAGE_END_YEAR,
    PTS_COVERAGE_START_YEAR,
)
from ._metadata_validators import (
    PTS_CHECKSUM_MISMATCH,
    PTS_METADATA_VERSION_MISMATCH,
    UNSUPPORTED_VERSION,
    _checksum_match_blocker,
    _checksum_shape_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _positive_int_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)


def check_metadata_well_formed(
    bundle_dir: Path,
    xlsx_name: str,
    *,
    canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the PTS bundle's ``metadata.json`` +
    ``xlsx``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed (file presence + metadata fields +
      checksum shape and optional xlsx-checksum match).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|...)``
      when the bundle is missing ``metadata.json``,
      missing the mandatory xlsx, missing a required
      metadata field, has malformed ``local_files`` /
      ``ingestion_status`` / ``version`` / ``source_version``
      / ``sha256``, or has an xlsx SHA-256 that
      disagrees with the metadata ``sha256``.

    A metadata-only bundle (metadata present, xlsx
    absent) is intentionally NOT runner-ready; the gate
    fires ``MISSING_RAW`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform``. The mandatory readiness requirement
    is on raw-file presence: the bundle is
    not-ready whenever the staged xlsx is NOT on disk,
    regardless of the metadata's ``local_files`` /
    ``sha256`` shape.
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
            "PTS readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator
    # returns a blocker tuple ``(message, code)`` or
    # ``None`` when the field is well-formed.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload, xlsx_name)),
        (
            "ingestion_status",
            _ingestion_status_blocker(payload),
        ),
        (
            "version",
            _metadata_source_version_blocker(
                payload, canonical_version=canonical_version,
            ),
        ),
        (
            "source_name",
            _non_empty_string_blocker(
                payload,
                "source_name",
                "the canonical PTS source name "
                "('Political Terror Scale')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical PTS xlsx download URL",
            ),
        ),
        (
            "license",
            _non_empty_string_blocker(
                payload,
                "license",
                "the PTS license "
                "(free academic use with attribution)",
            ),
        ),
        (
            "coverage_start_year",
            _positive_int_blocker(
                payload,
                "coverage_start_year",
                "the PTS temporal coverage start year "
                "(1976)",
            ),
        ),
        (
            "coverage_end_year",
            _positive_int_blocker(
                payload,
                "coverage_end_year",
                "the PTS temporal coverage end year "
                "(2024)",
            ),
        ),
        (
            "file_format",
            _non_empty_string_blocker(
                payload,
                "file_format",
                "the PTS bundle file format "
                "('xlsx')",
            ),
        ),
        (
            "file_size_bytes",
            _positive_int_blocker(
                payload,
                "file_size_bytes",
                "the staged PTS-2025.xlsx size in bytes",
            ),
        ),
        ("sha256_shape", _checksum_shape_blocker(payload)),
        (
            "sha256_match",
            _checksum_match_blocker(payload, xlsx_path, xlsx_name),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            # The per-field validator returns the right
            # code so the runner surfaces the actionable
            # diagnostic.
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from
    the canonical version (SRC-REQ-009).

    Returns ``(message, code)`` when
    ``request.source_version`` is set and differs from
    ``canonical_version``; returns ``None`` when
    ``request.source_version`` is ``None`` or matches
    the canonical version.
    """
    if request.source_version is None:
        return None
    if request.source_version == canonical_version:
        return None
    return (
        "PTS readiness gate: requested source_version="
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
    """Build the request-scoping warning list for the
    readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders``
      is set (PTS is country-year only; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in
      ``request.years`` that falls outside the
      documented PTS 1976-2024 coverage envelope
      (SRC-COV-002 / SRC-COV-003).

    An unsupported ``request.source_version`` is NOT
    a warning -- it is a hard readiness blocker.
    """
    warnings: list[SourceWarning] = []

    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "PTS is a country-year political-terror "
                    "source; leader filters are not "
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
                year_int < PTS_COVERAGE_START_YEAR
                or year_int > PTS_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            "PTS coverage "
                            f"({PTS_COVERAGE_START_YEAR}-"
                            f"{PTS_COVERAGE_END_YEAR}); "
                            "no observations will be emitted "
                            "for this year (no stale-proxy "
                            "fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                PTS_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                PTS_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "PTS_CHECKSUM_MISMATCH",
    "PTS_METADATA_VERSION_MISMATCH",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
