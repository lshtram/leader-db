"""Readiness gate orchestrator for the unified-source
RSF adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes
the per-field validators in
:mod:`._metadata_validators` and the per-year CSV
presence / per-file SHA-256 check in
:mod:`._year_validators`. The request-scoping warning
builder lives here alongside the source-version block.

Split out of :mod:`._metadata_validators` so the
per-field validators stay focused and the readiness
orchestrator stays focused on lifecycle ordering.

Year semantics
--------------

RSF covers 2002-2026 per the canonical staged bundle
metadata (``coverage.start_year: 2002`` /
``coverage.end_year: 2026`` +
``files`` array with 24 per-year records covering
2002-2010 + 2012-2026; verified live 2026-06-18 per
``docs/sources/attributions.md`` §
``rsf_press_freedom``). A request for an
out-of-coverage year (e.g. ``years=(2027,)`` or
``years=(2001,)``) emits zero observations plus a
structured ``YEAR_ABSENT`` warning per SRC-COV-002 /
SRC-COV-003 (no stale-proxy fill).

A request for the documented missing year
(``years=(2011,)``) fails readiness with a
structured ``rsf_year_2011_absent`` warning. The
direct ``2011.csv`` is absent -- RSF's combined
2011/2012 edition is represented by the 2012 file
(its ``Year (N)`` column reads ``"2011-12"``). The
structured ``rsf_year_2011_absent`` code is distinct
from the generic ``year_absent`` so the operator
can distinguish the documented 2011 caveat from a
generic out-of-coverage year.

For broad ``years=None`` requests, the readiness gate
requires the canonical staged set documented in
metadata (the full ``local_files`` annotation + the
canonical per-year CSV presence on disk). For
year-scoped ``years=(Y,)`` requests, the gate
requires at minimum the metadata and the requested
year file(s); correctly reports 2011
absent/unsupported if requested.

A request with a ``leaders=`` filter is unsupported
for a country-year press-freedom source and surfaces
a structured ``UNSUPPORTED_FILTER`` warning per
SRC-REQ-005.

Country-filter semantics
------------------------

The RSF CSVs carry the ISO 3166-1 alpha-3 3-letter
alphabetic column (``ISO``); the ``ISO`` is the
canonical primary key (per the legacy
``rsf_press_freedom_csv`` reader and the per-row
``source_row_reference`` shape). The
``request.countries`` filter applies as an exact
match against the ``ISO`` column -- this is the
canonical contract documented in
``docs/architecture/sources.md`` §7.1 priority 7.
Passing a non-ISO3 code (e.g. ``"United States"``)
yields zero rows; the readiness gate does NOT warn
on non-ISO3 codes because the contract is
documented-and-tested rather than inferred.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import (
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._constants import (
    RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
    RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
    RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR,
    RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE,
)
from ._metadata_validators import (
    RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH,
    RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH,
    UNSUPPORTED_VERSION,
    _files_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)
from ._year_validators import _check_year_csvs


def check_metadata_well_formed(
    bundle_dir: Path,
    *,
    canonical_version: str,
    years_scope: tuple[int, ...] | None = None,
) -> tuple[bool, str | None, str | None]:
    """Validate the RSF bundle's ``metadata.json`` +
    the per-year CSV(s) for the request scope.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed (file presence + metadata fields +
      per-year CSV presence for the request scope +
      per-file SHA-256 match when present).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|...)``
      when the bundle is missing ``metadata.json``,
      missing a required metadata field, has malformed
      ``local_files`` / ``ingestion_status`` /
      ``source_version`` / ``files``, or has a per-year
      CSV SHA-256 that disagrees with the metadata
      field.

    A metadata-only bundle (metadata present, per-year
    CSVs absent) is intentionally NOT runner-ready; the
    gate fires ``MISSING_RAW`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform``. The mandatory readiness requirement
    is on per-year raw-file presence: the bundle is
    not-ready whenever ANY requested per-year CSV is
    NOT on disk, regardless of the metadata's
    ``local_files`` / ``files`` shape.

    The ``years_scope`` argument lets the orchestrator
    narrow the per-year presence check to the request
    scope. When ``years_scope`` is ``None``, the gate
    validates the full ``local_files`` annotation
    (broad / no-year request). When ``years_scope`` is
    set, the gate validates only the requested year
    files; 2011 is always reported as
    ``rsf_year_2011_absent`` if requested (the direct
    ``2011.csv`` is absent).
    """
    metadata_path = bundle_dir / "metadata.json"

    # Phase A: presence check.
    presence_blocker = _presence_blocker(metadata_path)
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            "RSF readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), "missing_metadata"

    # Phase B: per-field validation. Each validator
    # returns a blocker tuple ``(message, code)`` or
    # ``None`` when the field is well-formed.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload)),
        (
            "ingestion_status",
            _ingestion_status_blocker(payload),
        ),
        (
            "source_version",
            _metadata_source_version_blocker(
                payload, canonical_version=canonical_version,
            ),
        ),
        (
            "source_name",
            _non_empty_string_blocker(
                payload,
                "source_name",
                "the canonical RSF source name "
                "('Reporters Without Borders World "
                "Press Freedom Index')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical RSF CSV download URL "
                "(https://rsf.org/sites/default/files/"
                "import_classement/{year}.csv)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the RSF license (public dataset; "
                "cite Reporters Without Borders)",
            ),
        ),
        ("files", _files_blocker(payload)),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    # Phase C: per-year CSV presence + (optional)
    # per-file SHA-256 match. The check is scoped to
    # the request's ``years`` argument when supplied,
    # and to the full ``local_files`` annotation when
    # ``years`` is ``None`` (broad / no-year request).
    return _check_year_csvs(
        bundle_dir=bundle_dir,
        payload=payload,
        years_scope=years_scope,
    )


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
        "RSF readiness gate: requested source_version="
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

    Surfaces three categories of warnings on the
    :class:`ReadinessResult.warnings` tuple:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders``
      is set (RSF is country-year only; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in
      ``request.years`` that falls outside the
      documented RSF 2002-2026 coverage envelope
      (SRC-COV-002 / SRC-COV-003).
    - ``rsf_year_2011_absent`` -- when
      ``request.years`` includes 2011 (the documented
      missing year; the direct ``2011.csv`` is absent
      and the 2012 file represents the combined
      2011/2012 edition). Distinct from the generic
      ``YEAR_ABSENT`` so the operator can distinguish
      the documented 2011 caveat from a generic
      out-of-coverage year.

    Note: the ``rsf_year_2011_absent`` is also raised
    as a hard readiness blocker by
    :func:`check_metadata_well_formed` when 2011 is
    requested (the runner short-circuits with
    ``RuntimeError``). The advisory copy here covers
    the case where 2011 is in a multi-year request
    (e.g. ``years=(2010, 2011, 2012)``); the per-year
    CSV-presence loop surfaces the 2011 caveat as a
    blocker, but the warning surface is the operator-
    facing copy.

    An unsupported ``request.source_version`` is NOT
    a warning -- it is a hard readiness blocker.
    """
    warnings: list[SourceWarning] = []

    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "RSF is a country-year press-freedom "
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
                year_int < RSF_PRESS_FREEDOM_COVERAGE_START_YEAR
                or year_int > RSF_PRESS_FREEDOM_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            "RSF coverage "
                            f"({RSF_PRESS_FREEDOM_COVERAGE_START_YEAR}-"
                            f"{RSF_PRESS_FREEDOM_COVERAGE_END_YEAR}); "
                            "no observations will be emitted "
                            "for this year (no stale-proxy "
                            "fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                RSF_PRESS_FREEDOM_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                RSF_PRESS_FREEDOM_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )
            elif year_int == RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR:
                warnings.append(
                    SourceWarning(
                        code=RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE,
                        message=(
                            "year=2011 is the documented "
                            "missing year in the direct-CSV "
                            "pattern. RSF publishes a combined "
                            "2011/2012 edition represented by "
                            "the 2012 CSV (its `Year (N)` "
                            "column reads `2011-12`); the "
                            "direct `2011.csv` is intentionally "
                            "absent. To ingest 2011-related "
                            "data, request the 2012 file "
                            "(years=(2012,)); do NOT silently "
                            "proxy 2011 -> 2012 (no stale-proxy "
                            "fill per SRC-COV-002 / SRC-COV-003)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "missing_year": (
                                RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH",
    "RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH",
    "RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
