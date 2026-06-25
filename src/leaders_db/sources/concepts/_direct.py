"""Direct (alias) concept extraction helpers.

A direct concept mapping declares one or more source-specific
indicator codes that alias the concept. The extraction helper in
this module produces one :class:`ConceptObservation` per matching
input observation, preserving the source-specific indicator code,
input observation id, raw locator, transform locator, source
version, and source-supplied quality flags.

Non-numeric / missing input values are surfaced as structured
``missing_value`` :class:`SourceWarning` records on the emitted
row's ``warnings`` tuple. The row itself is NOT dropped: it is
emitted with ``value=None`` and ``value_type="missing"`` so the
analyst can see that the source cell was unusable without losing
the observation id / locator. Downstream diagnostics that aggregate
row-level warnings via :func:`extract_concept_result` pick them up
directly from each row's ``warnings`` tuple.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Literal

from ..contracts import (
    NormalizedObservation,
    SourceId,
    SourceWarning,
)
from ._dataclasses import ConceptMapping, ConceptObservation


def is_finite_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric.

    Booleans are explicitly excluded so ``True`` / ``False`` are not
    silently coerced into 1 / 0 -- the prototype's source contract
    uses ``value_type="boolean"`` for booleans, never ``numeric``.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return not math.isnan(value) and not math.isinf(value)
    return False


def _concept_value_type(value: Any) -> Literal["numeric", "missing"]:
    """Return the canonical concept value_type for ``value``."""
    return "numeric" if is_finite_number(value) else "missing"


def _missing_value_warning(
    *,
    source_id: SourceId,
    concept_key: str,
    observation_id: str,
    expected_indicator: str,
) -> SourceWarning:
    """Build a structured ``missing_value`` :class:`SourceWarning`.

    The message clarifies that the row IS still emitted (with
    ``value=None`` and ``value_type="missing"``) so callers can see
    the upstream gap without losing the observation id / locator.
    """
    return SourceWarning(
        code="missing_value",
        message=(
            f"Direct concept {concept_key!r} observation "
            f"{observation_id!r} from source {source_id.slug!r} "
            f"has a missing or non-numeric value for indicator "
            f"{expected_indicator!r}; row is emitted with "
            f"value=None and value_type='missing' so the analyst "
            f"can see the upstream gap without losing the "
            f"observation id / locator."
        ),
        severity="info",
        source_id=source_id,
        context={
            "concept_key": concept_key,
            "observation_id": observation_id,
            "indicator_code": expected_indicator,
        },
    )


def emit_direct_observations(
    *,
    observations: Sequence[NormalizedObservation],
    mapping: ConceptMapping,
) -> tuple[ConceptObservation, ...]:
    """Emit one :class:`ConceptObservation` per matching input observation.

    "Matching" means ``observation.indicator_code`` is in
    ``mapping.indicator_codes`` AND ``observation.source_id.slug``
    equals ``mapping.source_id.slug``. Non-numeric / missing values
    yield a structured ``missing_value`` warning attached to the
    emitted row's ``warnings`` tuple; the row itself carries
    ``value=None`` and ``value_type="missing"`` so the analyst can
    see that the input cell was unusable without losing the
    observation id / locator.
    """
    expected = set(mapping.indicator_codes)
    emitted: list[ConceptObservation] = []
    for obs in observations:
        if obs.source_id.slug != mapping.source_id.slug:
            continue
        if obs.indicator_code not in expected:
            continue

        if is_finite_number(obs.value):
            warnings: tuple[SourceWarning, ...] = ()
            emitted_value: float | int | None = obs.value
        else:
            warnings = (
                _missing_value_warning(
                    source_id=mapping.source_id,
                    concept_key=mapping.concept_key,
                    observation_id=obs.observation_id,
                    expected_indicator=obs.indicator_code,
                ),
            )
            emitted_value = None

        emitted.append(
            ConceptObservation(
                concept_key=mapping.concept_key,
                source_id=mapping.source_id,
                value=emitted_value,
                value_type=_concept_value_type(obs.value),
                year=obs.year,
                country_code=obs.country_code,
                country_name=obs.country_name,
                leader_id=obs.leader_id,
                leader_name=obs.leader_name,
                unit=obs.unit,
                scale=obs.scale,
                source_version=obs.source_version,
                source_indicator_codes=(obs.indicator_code,),
                input_observation_ids=(obs.observation_id,),
                raw_locators=(obs.raw_locator,),
                transform_locators=(obs.transform_locator,),
                quality_flags=obs.quality_flags,
                warnings=warnings,
                mapping_type="direct",
                recipe_key=None,
                extension=dict(obs.extension),
            ),
        )
    return tuple(emitted)


__all__ = [
    "emit_direct_observations",
    "is_finite_number",
]
