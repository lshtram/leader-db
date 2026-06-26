"""Readiness gate orchestrator for the unified-source
Transparency International CPI adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes the
per-field validators in :mod:`._metadata_validators`, and
the request-scoping warning builder lives here alongside
the source-version block.

Split out of :mod:`._metadata_validators` so the
per-field validators stay focused and the readiness
orchestrator stays focused on lifecycle ordering. Each
per-field validator lives in :mod:`._metadata_validators`
and is imported here for composition.

Year semantics
--------------

Transparency International CPI covers 1995-2023 per the
canonical staged bundle metadata (``years_available:
"1995-2023+"``). A request for an out-of-coverage year
(e.g. ``years=(2024,)`` or ``years=(1994,)``) emits zero
observations plus a structured ``YEAR_ABSENT`` warning per
SRC-COV-002 / SRC-COV-003 (no stale-proxy fill).

A request with a ``leaders=`` filter is unsupported for a
country-year corruption-perception source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning per
SRC-REQ-005.

Country-filter semantics
------------------------

The CPI ``iso3`` column is the canonical ISO3 alpha-3
country code (e.g. ``MEX`` / ``USA`` / ``SWE``). The
``request.countries`` filter applies as an exact match
against the CPI ``iso3`` column. Passing a non-ISO3 code
yields zero rows (the contract is documented here so
callers do not silently get zero observations when they
pass a non-ISO3 identifier).
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
    TRANSPARENCY_CPI_COVERAGE_END_YEAR,
    TRANSPARENCY_CPI_COVERAGE_START_YEAR,
)
from ._metadata_validators import (
    TRANSPARENCY_CPI_CHECKSUM_MISMATCH,
    UNSUPPORTED_VERSION,
    _checksum_match_blocker,
    _checksum_shape_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)


def check_metadata_well_formed(
    bundle_dir,
    csv_name: str,
    canonical_version: str,
) -> tuple[bool, str | None, str | None]:
    """Validate the CPI bundle's ``metadata.json`` + ``CSV``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed (file presence + metadata fields +
      checksum shape and optional CSV-checksum match).
      The mandatory requirement is that the per-year CSV
      is staged on disk; the metadata's ``local_files``
      may be empty (the canonical bundle metadata shape).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|...)``
      when the bundle is missing ``metadata.json``,
      missing the mandatory per-year CSV, missing a
      required metadata field, has ``local_files`` that
      is a non-list or non-empty-without-canonical-csv,
      has an ``ingestion_status`` not in the acceptable
      set, has an unsupported / mismatched source-version
      stamp, has a malformed ``checksum_sha256``, or has
      a CSV SHA-256 that disagrees with the metadata
      field.

    The third tuple element is the canonical warning code
    the adapter surfaces when ``ready=False``; the runner
    emits the full blocker text in the
    ``SourceWarning.message``.

    The CPI canonical bundle metadata carries
    ``local_files=["transparency_cpi_2023.csv"]`` +
    ``checksum_sha256=null`` -- a deliberately minimal
    shape so the operator can update the metadata once
    the per-year CSV is staged. The mandatory readiness
    requirement is on raw-file presence: the gate
    returns ``ready=False`` with a structured
    ``MISSING_RAW`` error if the per-year CSV is not
    staged on disk, regardless of the metadata's
    ``local_files`` / ``checksum_sha256`` shape. This
    guarantees that the ``SourceIngestRunner`` never
    dispatches ``read_raw`` and surfaces an unhandled
    ``FileNotFoundError``.

    A metadata-only bundle (metadata present, CSV absent)
    is intentionally NOT runner-ready. The runner raises
    ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform`` whenever ``ready=False``. The
    metadata-only bundle still has value for
    readiness-only inspection -- callers can still
    ``adapter.check_ready(request)`` to validate
    metadata shape -- but
    ``adapter.check_ready(request).ready`` is ``False``
    until the CSV is staged.
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
            "Transparency International CPI readiness "
            "gate: failed to parse metadata.json at "
            f"{metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator
    # returns a blocker tuple ``(message, code)`` or
    # ``None`` when the field is well-formed.
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
                "the canonical Transparency International "
                "CPI source name",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical Transparency International "
                "CPI publisher URL",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the Transparency International license "
                "(free for non-commercial use; cite "
                "Transparency International 2023)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the temporal + spatial coverage envelope "
                "(annual country-year corruption "
                "perceptions)",
            ),
        ),
        ("checksum_shape", _checksum_shape_blocker(payload)),
        (
            "checksum_match",
            _checksum_match_blocker(payload, csv_path, csv_name),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            # CPI CSV checksum mismatches surface the
            # module-local
            # ``TRANSPARENCY_CPI_CHECKSUM_MISMATCH`` code
            # (NOT ``MISSING_METADATA``); the per-field
            # validator returns the right code so the
            # runner surfaces the actionable diagnostic.
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the
    canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail
    readiness with actionable error." A request like
    ``source_version="CPI 2024"`` against a canonical CPI
    2023 bundle must surface a structured readiness error
    so the runner refuses to dispatch ``read_raw`` /
    ``transform``.

    Returns ``(message, code)`` when
    ``request.source_version`` is set and differs from
    ``canonical_version``; returns ``None`` when
    ``request.source_version`` is ``None`` or when it
    equals ``canonical_version`` (explicit match).
    """
    if request.source_version is None:
        return None
    if request.source_version == canonical_version:
        return None
    return (
        "Transparency International CPI readiness gate: "
        "requested source_version="
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
    :class:`ReadinessResult.warnings` tuple so the runner
    carries them through to the final result even when
    the transform layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders``
      is set (CPI is a country-year corruption-perception
      source and has no leader dimension; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented CPI 1995-2023
      coverage envelope (no stale-proxy fill per
      SRC-COV-002 / SRC-COV-003).

    Note: an unsupported ``request.source_version`` is NOT
    a warning -- it is a hard readiness blocker (see
    :func:`check_source_version` and SRC-REQ-009).
    """
    warnings: list[SourceWarning] = []

    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Transparency International CPI is a "
                    "country-year corruption-perception "
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
                year_int < TRANSPARENCY_CPI_COVERAGE_START_YEAR
                or year_int > TRANSPARENCY_CPI_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            "Transparency International CPI "
                            "coverage "
                            f"({TRANSPARENCY_CPI_COVERAGE_START_YEAR}-"
                            f"{TRANSPARENCY_CPI_COVERAGE_END_YEAR}); "
                            "no observations will be emitted "
                            "for this year (no stale-proxy "
                            "fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                TRANSPARENCY_CPI_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                TRANSPARENCY_CPI_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "TRANSPARENCY_CPI_CHECKSUM_MISMATCH",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
