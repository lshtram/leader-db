"""Per-scope drop-reason construction for the derived-recipe helper.

The diagnostic helper (:func:`leaders_db.sources.concepts.extract_concept_result`)
surfaces every per-scope derivation failure as a structured
:class:`SourceWarning`. This module owns the internal
:class:`_DerivationDropReason` record + the focused helpers that
build it for each failure mode the catalog handles:

- :func:`_check_derivation_inputs` -- top-level entry; checks
  source-version provenance first (strictest), then missing
  numerator / denominator, then ambiguous pair, then defers to
  :func:`_structural_drop_reason` for non-numeric / zero /
  defensive-year checks.
- :func:`_structural_drop_reason` -- checks numeric / division
  sanity of the paired inputs once both sides are present.

The module never imports ``leaders_db.ingest``. It only depends on
the unified :class:`NormalizedObservation` /
:class:`SourceWarning` contracts and the concept-catalog warning
codes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..contracts import (
    JsonValue,
    NormalizedObservation,
    SourceId,
    SourceWarning,
)
from ._catalog import (
    CONCEPT_WARNING_AMBIGUOUS_PAIR,
    CONCEPT_WARNING_MISSING_DENOMINATOR,
    CONCEPT_WARNING_MISSING_NUMERATOR,
    CONCEPT_WARNING_MISSING_SOURCE_VERSION,
    CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR,
    CONCEPT_WARNING_NON_NUMERIC_NUMERATOR,
    CONCEPT_WARNING_PAIR_YEAR_MISMATCH,
    CONCEPT_WARNING_ZERO_DENOMINATOR,
)
from ._direct import is_finite_number


@dataclass(frozen=True)
class _DerivationDropReason:
    """Lightweight record describing why one scope emitted no row.

    The ``code`` / ``message`` / ``context`` fields map 1:1 onto the
    :class:`SourceWarning` constructor; :meth:`to_warning` packages
    them together with ``source_id`` and ``severity`` defaults.
    """

    country_code: str | None
    year: int | None
    source_id: SourceId
    concept_key: str
    code: str
    message: str
    context: Mapping[str, JsonValue]

    def to_warning(self) -> SourceWarning:
        """Materialize this drop reason as a structured :class:`SourceWarning`."""
        return SourceWarning(
            code=self.code,
            message=self.message,
            severity="info",
            source_id=self.source_id,
            context=dict(self.context),
        )


def _scope_label(
    *,
    concept_key: str,
    source_id: SourceId,
    scope_country_code: str | None,
    scope_year: int | None,
) -> str:
    """Build the shared ``"Derived concept X scope country=Y year=Z
    in source S"`` prefix used by every drop-reason message so the
    message builders below stay compact."""
    return (
        f"Derived concept {concept_key!r} scope "
        f"country={scope_country_code!r} year={scope_year!r} "
        f"in source {source_id.slug!r}"
    )


def _scope_context(
    *,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
) -> dict[str, JsonValue]:
    """Build the shared scope context for the ``context`` dict."""
    return {
        "concept_key": concept_key,
        "country_code": scope_country_code,
        "year": scope_year,
    }


def _missing_source_version_reason(
    *,
    source_id: SourceId,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
    nums: Sequence[NormalizedObservation],
    dens: Sequence[NormalizedObservation],
) -> _DerivationDropReason | None:
    """Return a drop reason if paired inputs lack matching non-empty
    ``source_version`` stamps.

    Provenance is the strictest gate, so the check fires before the
    numeric / ambiguous / structural checks. Both inputs must share
    the same non-empty string; missing or mismatched versions
    surface the same ``concept_missing_source_version`` code so
    downstream diagnostics can branch on a single actionable code.
    """
    if not nums or not dens:
        return None
    label = _scope_label(
        concept_key=concept_key,
        source_id=source_id,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
    )
    for candidate in (nums[0], dens[0]):
        if not candidate.source_version:
            return _DerivationDropReason(
                country_code=scope_country_code,
                year=scope_year,
                source_id=source_id,
                concept_key=concept_key,
                code=CONCEPT_WARNING_MISSING_SOURCE_VERSION,
                message=(
                    f"{label} has a paired observation "
                    f"{candidate.observation_id!r} with a missing "
                    f"or empty source_version; row is not emitted "
                    f"because provenance is incomplete."
                ),
                context={
                    **_scope_context(
                        concept_key=concept_key,
                        scope_country_code=scope_country_code,
                        scope_year=scope_year,
                    ),
                    "observation_id": candidate.observation_id,
                    "indicator_code": candidate.indicator_code,
                },
            )
    if nums[0].source_version != dens[0].source_version:
        return _DerivationDropReason(
            country_code=scope_country_code,
            year=scope_year,
            source_id=source_id,
            concept_key=concept_key,
            code=CONCEPT_WARNING_MISSING_SOURCE_VERSION,
            message=(
                f"{label} has paired observations with different "
                f"source_version stamps "
                f"(numerator={nums[0].source_version!r}, "
                f"denominator={dens[0].source_version!r}); row is "
                f"not emitted because the derivation would mix "
                f"incompatible provenance."
            ),
            context={
                **_scope_context(
                    concept_key=concept_key,
                    scope_country_code=scope_country_code,
                    scope_year=scope_year,
                ),
                "numerator_observation_id": nums[0].observation_id,
                "numerator_source_version": nums[0].source_version,
                "denominator_observation_id": dens[0].observation_id,
                "denominator_source_version": dens[0].source_version,
            },
        )
    return None


def _missing_side_reason(
    *,
    source_id: SourceId,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
    role: str,
    expected_indicator: str,
    other_indicator: str,
) -> _DerivationDropReason:
    """Build a drop reason for a missing numerator or denominator."""
    if role == "numerator":
        code = CONCEPT_WARNING_MISSING_NUMERATOR
    else:
        code = CONCEPT_WARNING_MISSING_DENOMINATOR
    label = _scope_label(
        concept_key=concept_key,
        source_id=source_id,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
    )
    return _DerivationDropReason(
        country_code=scope_country_code,
        year=scope_year,
        source_id=source_id,
        concept_key=concept_key,
        code=code,
        message=(
            f"{label} has no matching {expected_indicator!r} "
            f"{role} observation; row is not emitted."
        ),
        context={
            **_scope_context(
                concept_key=concept_key,
                scope_country_code=scope_country_code,
                scope_year=scope_year,
            ),
            "expected_numerator_indicator": (
                expected_indicator if role == "numerator" else other_indicator
            ),
            "expected_denominator_indicator": (
                expected_indicator if role == "denominator" else other_indicator
            ),
        },
    )


def _ambiguous_pair_reason(
    *,
    source_id: SourceId,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
    numerator_code: str,
    denominator_code: str,
    nums: Sequence[NormalizedObservation],
    dens: Sequence[NormalizedObservation],
) -> _DerivationDropReason:
    """Build a drop reason when more than one numerator or denominator
    observation matches the same scope."""
    label = _scope_label(
        concept_key=concept_key,
        source_id=source_id,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
    )
    return _DerivationDropReason(
        country_code=scope_country_code,
        year=scope_year,
        source_id=source_id,
        concept_key=concept_key,
        code=CONCEPT_WARNING_AMBIGUOUS_PAIR,
        message=(
            f"{label} has more than one numerator ({len(nums)}) "
            f"or denominator ({len(dens)}) observation; the slice "
            f"refuses to guess which pair to use."
        ),
        context={
            **_scope_context(
                concept_key=concept_key,
                scope_country_code=scope_country_code,
                scope_year=scope_year,
            ),
            "expected_numerator_indicator": numerator_code,
            "expected_denominator_indicator": denominator_code,
            "numerator_observation_count": len(nums),
            "denominator_observation_count": len(dens),
        },
    )


def _structural_drop_reason(
    *,
    source_id: SourceId,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
    numerator_code: str,
    denominator_code: str,
    nums: Sequence[NormalizedObservation],
    dens: Sequence[NormalizedObservation],
) -> _DerivationDropReason | None:
    """Return a drop reason for year-mismatch / non-numeric / zero inputs.

    Defensive net: with year-scoped grouping, the year-mismatch
    check is normally unreachable (each scope has a single year),
    but the catalog keeps it so a future refactor that loosens the
    scope key still produces a structured diagnostic rather than a
    silent row. Missing numerator / denominator / ambiguous pair
    are enforced separately by :func:`_check_derivation_inputs`.
    """
    if not nums or not dens:
        return None
    num = nums[0]
    den = dens[0]
    label = _scope_label(
        concept_key=concept_key,
        source_id=source_id,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
    )

    # Defensive year-mismatch check: unreachable with year-scoped
    # grouping, but the catalog keeps the check so future scope-key
    # refactors cannot silently emit a bad ratio.
    if num.year != den.year:
        return _DerivationDropReason(
            country_code=scope_country_code,
            year=scope_year,
            source_id=source_id,
            concept_key=concept_key,
            code=CONCEPT_WARNING_PAIR_YEAR_MISMATCH,
            message=(
                f"{label} has mismatched years between paired "
                f"numerator / denominator; row is not emitted."
            ),
            context={
                **_scope_context(
                    concept_key=concept_key,
                    scope_country_code=scope_country_code,
                    scope_year=scope_year,
                ),
                "numerator_indicator_code": numerator_code,
                "numerator_observation_id": num.observation_id,
                "numerator_year": num.year,
                "denominator_indicator_code": denominator_code,
                "denominator_observation_id": den.observation_id,
                "denominator_year": den.year,
            },
        )

    pair_context = {
        **_scope_context(
            concept_key=concept_key,
            scope_country_code=scope_country_code,
            scope_year=scope_year,
        ),
        "numerator_indicator_code": numerator_code,
        "numerator_observation_id": num.observation_id,
        "denominator_indicator_code": denominator_code,
        "denominator_observation_id": den.observation_id,
    }

    if not is_finite_number(num.value):
        return _DerivationDropReason(
            country_code=scope_country_code,
            year=scope_year,
            source_id=source_id,
            concept_key=concept_key,
            code=CONCEPT_WARNING_NON_NUMERIC_NUMERATOR,
            message=(
                f"{label} has a non-numeric or missing numerator "
                f"value (observation_id={num.observation_id!r}, "
                f"indicator={numerator_code!r}); row is not emitted."
            ),
            context=pair_context,
        )
    if not is_finite_number(den.value):
        return _DerivationDropReason(
            country_code=scope_country_code,
            year=scope_year,
            source_id=source_id,
            concept_key=concept_key,
            code=CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR,
            message=(
                f"{label} has a non-numeric or missing denominator "
                f"value (observation_id={den.observation_id!r}, "
                f"indicator={denominator_code!r}); row is not emitted."
            ),
            context=pair_context,
        )
    if float(den.value) == 0:
        # Division would be undefined. Refuse to guess.
        return _DerivationDropReason(
            country_code=scope_country_code,
            year=scope_year,
            source_id=source_id,
            concept_key=concept_key,
            code=CONCEPT_WARNING_ZERO_DENOMINATOR,
            message=(
                f"{label} has a zero denominator "
                f"(observation_id={den.observation_id!r}, "
                f"indicator={denominator_code!r}); row is not "
                f"emitted because the ratio would be undefined."
            ),
            context=pair_context,
        )

    return None


def _check_derivation_inputs(
    *,
    source_id: SourceId,
    concept_key: str,
    scope_country_code: str | None,
    scope_year: int | None,
    numerator_code: str,
    denominator_code: str,
    nums: Sequence[NormalizedObservation],
    dens: Sequence[NormalizedObservation],
) -> _DerivationDropReason | None:
    """Return a drop reason if the scope should NOT emit a derived row.

    Check order (strictest first):

    1. source_version provenance (only when both sides present)
    2. missing numerator / denominator
    3. ambiguous pair (more than one of either)
    4. structural (non-numeric numerator / denominator, zero
       denominator, defensive year mismatch)
    """
    # Provenance: both inputs must share the same non-empty
    # ``source_version`` -- enforced before missing/ambiguous
    # checks so the diagnostic surfaces the strictest gate.
    version_reason = _missing_source_version_reason(
        source_id=source_id,
        concept_key=concept_key,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
        nums=nums,
        dens=dens,
    )
    if version_reason is not None:
        return version_reason

    if len(nums) == 0:
        return _missing_side_reason(
            source_id=source_id,
            concept_key=concept_key,
            scope_country_code=scope_country_code,
            scope_year=scope_year,
            role="numerator",
            expected_indicator=numerator_code,
            other_indicator=denominator_code,
        )
    if len(dens) == 0:
        return _missing_side_reason(
            source_id=source_id,
            concept_key=concept_key,
            scope_country_code=scope_country_code,
            scope_year=scope_year,
            role="denominator",
            expected_indicator=denominator_code,
            other_indicator=numerator_code,
        )
    if len(nums) > 1 or len(dens) > 1:
        return _ambiguous_pair_reason(
            source_id=source_id,
            concept_key=concept_key,
            scope_country_code=scope_country_code,
            scope_year=scope_year,
            numerator_code=numerator_code,
            denominator_code=denominator_code,
            nums=nums,
            dens=dens,
        )
    return _structural_drop_reason(
        source_id=source_id,
        concept_key=concept_key,
        scope_country_code=scope_country_code,
        scope_year=scope_year,
        numerator_code=numerator_code,
        denominator_code=denominator_code,
        nums=nums,
        dens=dens,
    )


__all__ = [
    "_DerivationDropReason",
    "_ambiguous_pair_reason",
    "_check_derivation_inputs",
    "_missing_side_reason",
    "_missing_source_version_reason",
    "_structural_drop_reason",
]
