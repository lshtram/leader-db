"""Shared validation for normalized source observations."""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import (
    NormalizedObservation,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceWarning,
    ValidationResult,
)


def validate_observations(
    request: SourceIngestRequest,
    observations: Sequence[NormalizedObservation],
    *,
    descriptor: SourceDescriptor | None = None,
) -> ValidationResult:
    """Validate shared invariants for normalized source rows.

    Adapters remain responsible for source-specific parsing semantics. This
    function enforces the generic contract every persisted observation needs:
    stable identity, request/source consistency, required indicator fields, raw
    provenance, and basic declared coverage diagnostics.
    """

    errors: list[SourceWarning] = []
    warnings: list[SourceWarning] = []
    seen_ids: set[tuple[str, str]] = set()

    for index, observation in enumerate(observations):
        context = {"index": index, "observation_id": observation.observation_id}
        source_id = observation.source_id

        if source_id != request.source_id:
            errors.append(
                _warning(
                    request.source_id,
                    "source_mismatch",
                    "Observation source_id does not match the ingest request.",
                    severity="error",
                    context={
                        **context,
                        "observation_source": source_id.slug,
                        "request_source": request.source_id.slug,
                    },
                )
            )

        key = (source_id.slug, observation.observation_id)
        if not observation.observation_id:
            errors.append(
                _warning(
                    request.source_id,
                    "missing_observation_id",
                    "Observation is missing a stable observation_id.",
                    severity="error",
                    context=context,
                )
            )
        elif key in seen_ids:
            errors.append(
                _warning(
                    request.source_id,
                    "duplicate_observation_id",
                    "Duplicate observation_id within a single source run.",
                    severity="error",
                    context=context,
                )
            )
        else:
            seen_ids.add(key)

        if not observation.observation_family:
            errors.append(
                _warning(
                    request.source_id,
                    "missing_observation_family",
                    "Observation is missing observation_family.",
                    severity="error",
                    context=context,
                )
            )
        if not observation.indicator_code:
            errors.append(
                _warning(
                    request.source_id,
                    "missing_indicator_code",
                    "Observation is missing indicator_code.",
                    severity="error",
                    context=context,
                )
            )
        if not observation.raw_locator.asset_id:
            errors.append(
                _warning(
                    request.source_id,
                    "missing_raw_provenance",
                    "Observation is missing raw provenance asset_id.",
                    severity="error",
                    context=context,
                )
            )

        if descriptor is not None and observation.year is not None:
            start_year = descriptor.coverage_hint.start_year
            end_year = descriptor.coverage_hint.end_year
            if start_year is not None and observation.year < start_year:
                warnings.append(
                    _coverage_warning(
                        request.source_id,
                        context,
                        observation.year,
                        "before",
                        start_year,
                    )
                )
            if end_year is not None and observation.year > end_year:
                warnings.append(
                    _coverage_warning(
                        request.source_id,
                        context,
                        observation.year,
                        "after",
                        end_year,
                    )
                )

    return ValidationResult(valid=not errors, warnings=tuple(warnings), errors=tuple(errors))


def _coverage_warning(
    source_id: SourceId,
    context: dict[str, object],
    year: int,
    direction: str,
    boundary: int,
) -> SourceWarning:
    return _warning(
        source_id,
        "out_of_coverage_year",
        "Observation year falls outside the source descriptor coverage hint.",
        severity="warning",
        context={**context, "year": year, "direction": direction, "boundary": boundary},
    )


def _warning(
    source_id: SourceId,
    code: str,
    message: str,
    *,
    severity: str,
    context: dict[str, object],
) -> SourceWarning:
    return SourceWarning(
        code=code,
        message=message,
        severity=severity,  # type: ignore[arg-type]
        source_id=source_id,
        context=context,  # type: ignore[arg-type]
    )


__all__ = ["validate_observations"]
