"""Readiness gate orchestrator for the unified-source Polity V
adapter.

This module owns the readiness-gate orchestration: the top-level
:func:`check_metadata_well_formed` composes the per-field
validators in :mod:`._metadata_validators`. The request-scoping
warning builder lives here alongside the source-version block.

Split out of :mod:`._metadata_validators` so the per-field
validators stay focused and the readiness orchestrator stays
focused on lifecycle ordering.

Year semantics
--------------

Polity V covers 1800-2018 per the canonical staged bundle
metadata + the canonical citation block in
``docs/sources/attributions.md`` § ``polity_v`` (Marshall,
Jaggers, Gleditsch 2018). A request for an out-of-coverage year
(e.g. ``years=(2023,)`` -- the prototype's target year --
falls outside the documented Polity V coverage envelope
(SRC-COV-002). The transform emits zero observations plus a
structured ``YEAR_ABSENT`` warning; no stale-proxy fill
(SRC-COV-003).

The staged ``p5v2018.sav`` carries a small number of rows
outside the canonical envelope (1776-1799 historical backfill
+ a few 2019-2020 strays). The unified transform filters the
raw frame to the canonical 1800-2018 envelope so the descriptor
advertises the canonical envelope; the readiness envelope
surfaces a ``YEAR_ABSENT`` warning on the relevant years so the
operator can see the gap.

Leader-filter semantics
-----------------------

A request with a ``leaders=`` filter is unsupported for a
country-year political-freedom source and surfaces a structured
``UNSUPPORTED_FILTER`` warning per SRC-REQ-005. The transform
ignores the filter (Polity V is country-year only; Stage 4 is
the resolver for leader-identity evidence; Stage 2 does not
filter by leader).
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
    POLITY_V_COVERAGE_END_YEAR,
    POLITY_V_COVERAGE_START_YEAR,
    POLITY_V_DEFAULT_VERSION,
    POLITY_V_SAV_NAME,
)
from ._metadata_validators import (
    MISSING_METADATA,
    UNSUPPORTED_VERSION,
    _checksum_match_blocker,
    _ingestion_status_blocker,
    _local_files_blocker,
    _metadata_source_version_blocker,
    _non_empty_string_blocker,
    _presence_blocker,
    _read_metadata_payload,
    _required_fields_blocker,
)


def check_metadata_well_formed(
    bundle_dir: Path,
    *,
    canonical_version: str = POLITY_V_DEFAULT_VERSION,
) -> tuple[bool, str | None, str | None]:
    """Validate the Polity V bundle's ``metadata.json`` +
    ``p5v2018.sav``.

    Returns ``(ready, blocker, missing_field_or_file)``:

    - ``(True, None, None)`` when the bundle is fully well-formed
      (file presence + metadata fields + canonical metadata
      ``source_version`` + ``local_files`` + ``ingestion_status``
      + ``checksum_sha256`` match).
    - ``(False, blocker, MISSING_RAW|MISSING_METADATA|UNSUPPORTED_VERSION)``
      when the bundle is missing ``metadata.json``, missing
      ``p5v2018.sav``, missing a required metadata field, has
      ``local_files`` that does not include ``p5v2018.sav``, has
      ``ingestion_status != 'downloaded'``, has unsupported
      ``source_version``, or has a checksum that disagrees with
      the actual ``.sav`` SHA-256.

    The mandatory readiness requirement is on raw-file presence:
    a metadata-only bundle is intentionally NOT runner-ready; the
    gate fires ``MISSING_RAW`` whenever the staged ``.sav`` is
    NOT on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still reported
    as ``missing_metadata`` rather than ``missing_raw``.
    """
    metadata_path = bundle_dir / "metadata.json"
    sav_path = bundle_dir / POLITY_V_SAV_NAME

    # Phase A: presence check.
    presence_blocker = _presence_blocker(
        metadata_path, sav_path, POLITY_V_SAV_NAME,
    )
    if presence_blocker is not None:
        return False, presence_blocker[0], presence_blocker[1]

    payload = _read_metadata_payload(metadata_path)
    if not payload:
        return False, (
            "Polity V readiness gate: failed to parse "
            f"metadata.json at {metadata_path}"
        ), MISSING_METADATA

    # Phase B: per-field validation. Each validator returns a
    # blocker tuple ``(message, code)`` or ``None`` when the
    # field is well-formed.
    field_checks: Iterable[tuple[str, tuple[str, str] | None]] = (
        ("required_fields", _required_fields_blocker(payload)),
        ("local_files", _local_files_blocker(payload, POLITY_V_SAV_NAME)),
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
                "the canonical Polity V source name "
                "('Polity5: Political Regime Characteristics "
                "and Transitions, 1800-2018')",
            ),
        ),
        (
            "source_url",
            _non_empty_string_blocker(
                payload,
                "source_url",
                "the canonical Polity V download URL "
                "(https://www.systemicpeace.org/inscr/p5v2018.sav)",
            ),
        ),
        (
            "license_note",
            _non_empty_string_blocker(
                payload,
                "license_note",
                "the Polity V license (free academic; cite "
                "Marshall, Jaggers, Gleditsch 2018)",
            ),
        ),
        (
            "coverage",
            _non_empty_string_blocker(
                payload,
                "coverage",
                "the Polity V temporal + spatial coverage "
                "(1800-2018, ~167 countries)",
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
        ("checksum_match", _checksum_match_blocker(payload, sav_path)),
    )
    for _, blocker in field_checks:
        if blocker is not None:
            return False, blocker[0], blocker[1]

    return True, None, None


def check_source_version(
    request: SourceIngestRequest,
    *,
    canonical_version: str = POLITY_V_DEFAULT_VERSION,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version.

    Per ``docs/requirements/sources.md`` §3 SRC-REQ-009:
    "Unsupported source-version requests shall fail readiness
    with actionable error." A request like
    ``source_version="p5v2017"`` against a Polity5 v2018 bundle
    must surface a structured readiness error so the runner
    refuses to dispatch ``read_raw`` / ``transform`` (Rule #6
    / Rule #15 -- the legacy bundle does not encode a
    per-version stamp beyond ``metadata.json['source_version']``,
    and silently propagating an unsupported version into
    ``RawAsset.version`` /
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
        f"Polity V readiness gate: requested source_version="
        f"{request.source_version!r} does not match the "
        f"canonical version {canonical_version!r}; per "
        f"docs/requirements/sources.md SRC-REQ-009, "
        f"unsupported source-version requests must fail "
        f"readiness. Re-run with source_version="
        f"{canonical_version!r} (or omit the field to use "
        f"the canonical default).",
        UNSUPPORTED_VERSION,
    )


def collect_request_scoping_warnings(
    request: SourceIngestRequest,
    *,
    coverage_start_year: int = POLITY_V_COVERAGE_START_YEAR,
    coverage_end_year: int = POLITY_V_COVERAGE_END_YEAR,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces two categories of warnings on the
    :class:`ReadinessResult.warnings` tuple so the runner carries
    them through to the final result even when the transform
    layer emits zero observations:

    - ``UNSUPPORTED_FILTER`` -- when ``request.leaders`` is set
      (Polity V is a country-year political-freedom source and
      has no leader dimension).
    - ``YEAR_ABSENT`` -- for each year in ``request.years``
      that falls outside the documented Polity V 1800-2018
      coverage envelope (no stale-proxy fill per SRC-COV-002 /
      SRC-COV-003). The prototype's target year 2023 falls
      outside the envelope; the readiness envelope surfaces
      the warning so the operator can see the gap.

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
                    "Polity V is a country-year political-"
                    "freedom source; leader filters are not "
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
                year_int < coverage_start_year
                or year_int > coverage_end_year
            ):
                warnings.append(
                    SourceWarning(
                        code=YEAR_ABSENT,
                        message=(
                            f"year={year_int} is outside "
                            f"Polity V coverage "
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
    "UNSUPPORTED_VERSION",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
]
