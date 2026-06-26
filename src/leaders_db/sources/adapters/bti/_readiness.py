"""Readiness gate orchestrator for the unified-source
BTI adapter.

This module owns the readiness-gate orchestration: the
top-level :func:`check_metadata_well_formed` composes
the per-field validators in :mod:`._metadata_validators`,
and the request-scoping warning builder lives here
alongside the source-version block.

Split out of :mod:`._metadata_validators` so the
per-field validators stay focused and the readiness
orchestrator stays focused on lifecycle ordering.

Year semantics
--------------

BTI covers 2002-2025 per the canonical staged bundle
metadata (12 BTI editions 2006-2026, each covering
the ~2-year period preceding publication; the
``BTI 2006_old`` pre-methodology sheet covers
2002-2003) + the descriptor's
``coverage_hint.start_year=2002`` /
``end_year=2025`` (the union of per-edition covered
intervals). A request for an out-of-coverage year
(e.g. ``years=(2026,)`` or ``years=(2001,)``) emits
zero observations plus a structured ``YEAR_ABSENT``
warning per SRC-COV-002 / SRC-COV-003 (no stale-proxy
fill).

A request with a ``leaders=`` filter is unsupported
for a country-year governance source and surfaces a
structured ``UNSUPPORTED_FILTER`` warning per
SRC-REQ-005.

Country-filter semantics
------------------------

The BTI xlsx carries the BTI display name in column
0 (no ISO3 column). The request ``countries=`` filter
applies as a case-insensitive substring match
against the BTI display name -- this is the
canonical contract documented for BTI. Passing a
non-BTI display name (e.g. an ISO3 code like
``"USA"``) yields zero rows; the readiness gate does
NOT warn on non-BTI codes because the contract is
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

from ._descriptor import (
    BTI_COVERAGE_END_YEAR,
    BTI_COVERAGE_START_YEAR,
)
from ._metadata_validators import (
    BTI_CHECKSUM_MISMATCH,
    BTI_METADATA_VERSION_MISMATCH,
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
    """Validate the BTI bundle's ``metadata.json`` +
    ``xlsx``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully
      well-formed (file presence + metadata fields +
      checksum shape and optional xlsx-checksum
      match).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|...)``
      when the bundle is missing ``metadata.json``,
      missing the mandatory xlsx, missing a required
      metadata field, has malformed ``local_files`` /
      ``ingestion_status`` / ``source_version`` /
      ``checksum_sha256``, or has an xlsx SHA-256
      that disagrees with the metadata
      ``checksum_sha256``.

    A metadata-only bundle (metadata present, xlsx
    absent) is intentionally NOT runner-ready; the
    gate fires ``MISSING_RAW`` so the runner raises
    ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform``. The mandatory readiness
    requirement is on raw-file presence: the bundle
    is not-ready whenever the staged xlsx is NOT on
    disk, regardless of the metadata's
    ``local_files`` / ``checksum_sha256`` shape.
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
            "BTI readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), "missing_metadata"

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
                "the canonical BTI source name "
                "('Bertelsmann Transformation Index "
                "(BTI)')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical BTI downloads URL "
                "(https://bti-project.org/en/downloads)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the BTI license "
                "(free; cite Bertelsmann Stiftung. "
                "Reprinted with permission per BTI "
                "terms of use.)",
            ),
        ),
        (
            "edition_count",
            _positive_int_blocker(
                payload,
                "edition_count",
                "the BTI biennial edition count (12)",
            ),
        ),
        (
            "column_count",
            _positive_int_blocker(
                payload,
                "column_count",
                "the BTI xlsx column count (123)",
            ),
        ),
        ("checksum_shape", _checksum_shape_blocker(payload)),
        (
            "checksum_match",
            _checksum_match_blocker(
                payload, xlsx_path, xlsx_name,
            ),
        ),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            # The per-field validator returns the
            # right code so the runner surfaces the
            # actionable diagnostic.
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs
    from the canonical version (SRC-REQ-009).

    Returns ``(message, code)`` when
    ``request.source_version`` is set and differs
    from ``canonical_version``; returns ``None`` when
    ``request.source_version`` is ``None`` or matches
    the canonical version.
    """
    if request.source_version is None:
        return None
    if request.source_version == canonical_version:
        return None
    return (
        "BTI readiness gate: requested "
        f"source_version={request.source_version!r} "
        f"does not match the canonical version "
        f"{canonical_version!r}; per "
        "docs/requirements/sources.md SRC-REQ-009, "
        "unsupported source-version requests must "
        "fail readiness. Re-run with "
        f"source_version={canonical_version!r} (or "
        "omit the field to use the canonical "
        "default).",
        UNSUPPORTED_VERSION,
    )


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for
    the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple:

    - ``UNSUPPORTED_FILTER`` -- when
      ``request.leaders`` is set (BTI is
      country-edition only; SRC-REQ-005).
    - ``YEAR_ABSENT`` -- for each year in
      ``request.years`` that falls outside the
      documented BTI 2002-2025 coverage envelope
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
                    "BTI is a country-edition "
                    "governance source; leader filters "
                    "are not supported and have been "
                    "ignored."
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
                year_int < BTI_COVERAGE_START_YEAR
                or year_int > BTI_COVERAGE_END_YEAR
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            "BTI coverage "
                            f"({BTI_COVERAGE_START_YEAR}-"
                            f"{BTI_COVERAGE_END_YEAR}); "
                            "no observations will be "
                            "emitted for this year (no "
                            "stale-proxy fill)."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "year": year_int,
                            "coverage_start_year": (
                                BTI_COVERAGE_START_YEAR
                            ),
                            "coverage_end_year": (
                                BTI_COVERAGE_END_YEAR
                            ),
                        },
                    ),
                )

    return tuple(warnings)


__all__ = [
    "BTI_CHECKSUM_MISMATCH",
    "BTI_METADATA_VERSION_MISMATCH",
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
