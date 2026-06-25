"""Derived (recipe) concept extraction helpers.

The current slice ships exactly one derived recipe:

    ``PWT gdp_per_capita = pwt_real_gdp_output_side / pwt_population``

The helper pairs the two observations by ``(source_id,
country_code, country_name, leader_id, leader_name, year)`` scope
-- ``year`` is part of the scope key so multi-year valid same-country
inputs produce one derived row per country-year, never an ambiguous
multi-year aggregate. ``source_version`` is intentionally NOT in
the scope key: it is enforced inside the scope once both sides are
paired, so mismatched or missing source_versions surface the
``concept_missing_source_version`` diagnostic rather than silently
collapsing into separate (and equally broken) scopes.

Each per-scope failure mode (missing numerator / denominator,
ambiguous pair, non-numeric numerator / denominator, zero
denominator, missing / mismatched source_version, defensive year
mismatch) emits zero rows for that scope AND surfaces a structured
:class:`SourceWarning` via :func:`extract_concept_result`.

The helper never silently guesses values. Drop reasons are
collected as :class:`SourceWarning` records on the diagnostic
helper's ``warnings`` tuple (see :mod:`._api`); the convenience
:func:`extract_concept` returns only the observations tuple so the
minimal public API stays flat.

The per-failure-mode drop-reason construction lives in the focused
:mod:`._derived_reasons` helper module so this file can stay close
to the 400-line convention while keeping each module's
responsibility clear.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import (
    NormalizedObservation,
    SourceWarning,
)
from ._catalog import (
    DERIVED_CONCEPT_QUALITY_FLAG,
    PWT_GDP_PER_CAPITA_RECIPE_KEY,
    PWT_POPULATION_INDICATOR_CODE,
    PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
)
from ._dataclasses import ConceptMapping, ConceptObservation
from ._derived_reasons import _check_derivation_inputs, _DerivationDropReason

# Group-by key for scope coherence. Group by source id, country
# code, country name, leader id, leader name, and year. ``year`` is
# in the scope key (added in this slice) so the same country with
# 2018 and 2019 inputs yields two distinct scopes; multi-year valid
# same-country inputs no longer collide into one ambiguous bucket.
# ``source_version`` is intentionally excluded -- see the module
# docstring for why it lives in the per-scope check instead.
_ScopeKey = tuple[
    str, str | None, str | None, str | None, str | None, int | None,
]


def _group_key(obs: NormalizedObservation) -> _ScopeKey:
    """Return the scope key used to pair inputs for a derivation.

    ``year`` is part of the scope key so the same country with 2018
    and 2019 inputs yields two distinct scopes; multi-year valid
    same-country inputs no longer collide into one ambiguous bucket.
    ``source_version`` is checked separately (inside the scope) so
    mismatched versions still surface the missing-source-version
    diagnostic.
    """
    return (
        obs.source_id.slug,
        obs.country_code,
        obs.country_name,
        obs.leader_id,
        obs.leader_name,
        obs.year,
    )


def _scope_sort_key(scope: _ScopeKey) -> tuple:
    """Stable, orderable sort key for a :data:`_ScopeKey`.

    Tuple comparison short-circuits on the first unequal element, so
    we coerce each ``Optional[str]`` to ``str`` and ``Optional[int]``
    to ``int`` here so the ``sorted()`` call downstream does not
    raise :class:`TypeError` when some fields are ``None``.
    """
    slug, country_code, country_name, leader_id, leader_name, year = scope
    return (
        slug,
        country_code or "",
        country_name or "",
        leader_id or "",
        leader_name or "",
        year if year is not None else -1,
    )


def _build_derived_observation(
    *,
    mapping: ConceptMapping,
    numerator: NormalizedObservation,
    denominator: NormalizedObservation,
    ratio: float,
) -> ConceptObservation:
    """Assemble the :class:`ConceptObservation` for one valid scope."""
    return ConceptObservation(
        concept_key=mapping.concept_key,
        source_id=mapping.source_id,
        value=ratio,
        value_type="numeric",
        year=numerator.year,
        country_code=numerator.country_code,
        country_name=numerator.country_name,
        leader_id=numerator.leader_id,
        leader_name=numerator.leader_name,
        unit=mapping.output_unit,
        scale=mapping.output_scale,
        source_version=numerator.source_version,
        source_indicator_codes=(
            numerator.indicator_code,
            denominator.indicator_code,
        ),
        input_observation_ids=(
            numerator.observation_id,
            denominator.observation_id,
        ),
        raw_locators=(numerator.raw_locator, denominator.raw_locator),
        transform_locators=(
            numerator.transform_locator,
            denominator.transform_locator,
        ),
        quality_flags=(DERIVED_CONCEPT_QUALITY_FLAG,),
        warnings=(),
        mapping_type="derived",
        recipe_key=mapping.recipe_key,
        extension={
            "recipe_key": mapping.recipe_key,
            "numerator_indicator_code": numerator.indicator_code,
            "numerator_observation_id": numerator.observation_id,
            "numerator_unit": numerator.unit,
            "denominator_indicator_code": denominator.indicator_code,
            "denominator_observation_id": denominator.observation_id,
            "denominator_unit": denominator.unit,
        },
    )


def _drop_reason_to_warning(reason: _DerivationDropReason) -> SourceWarning:
    """Materialize a :class:`_DerivationDropReason` as a :class:`SourceWarning`."""
    return reason.to_warning()


def emit_derived_pwt_gdp_per_capita_observations(
    *,
    observations: Sequence[NormalizedObservation],
    mapping: ConceptMapping,
) -> tuple[ConceptObservation, ...]:
    """Emit one :class:`ConceptObservation` per valid (country, year) scope.

    The pairing rule (mirrors the task brief): pair the
    ``pwt_real_gdp_output_side`` observation with the matching
    ``pwt_population`` observation for the same (source_id,
    country, year, leader scope) tuple. ``year`` is part of the
    scope key, so a country with valid 2018 AND 2019 inputs yields
    two derived rows rather than collapsing into an ambiguous
    multi-year bucket.

    When the denominator is missing, non-numeric, zero, ambiguous
    for the scope, or when one / both inputs lacks a matching
    non-empty ``source_version``, the slice emits zero rows for
    that scope. Drop reasons are returned to the caller via the
    diagnostic helper (:func:`_derived_diagnostic`); the
    :func:`extract_concept` convenience wrapper discards them so
    the minimal public API stays flat.
    """
    return _derived_diagnostic(
        observations=observations,
        mapping=mapping,
    )[0]


def _derived_diagnostic(
    *,
    observations: Sequence[NormalizedObservation],
    mapping: ConceptMapping,
) -> tuple[tuple[ConceptObservation, ...], tuple[SourceWarning, ...]]:
    """Run the PWT recipe and return ``(observations, warnings)``.

    The split return shape lets the public :func:`extract_concept`
    wrapper discard the warnings while :func:`extract_concept_result`
    surfaces them directly. The recipe is defensive: any recipe
    other than the canonical PWT GDP-per-capita recipe returns
    empty tuples so a future slice can add more recipes without
    breaking the contract.
    """
    if (
        mapping.recipe_key != PWT_GDP_PER_CAPITA_RECIPE_KEY
        or set(mapping.indicator_codes)
        != {
            PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            PWT_POPULATION_INDICATOR_CODE,
        }
    ):
        # Defensive: only the canonical recipe is implemented. A
        # future slice that adds more PWT-derived recipes should
        # branch here on ``mapping.recipe_key``.
        return ((), ())

    expected_source = mapping.source_id.slug
    numerator_code = PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE
    denominator_code = PWT_POPULATION_INDICATOR_CODE

    # Index inputs by scope key (now includes ``year``).
    numerators: dict[_ScopeKey, list[NormalizedObservation]] = {}
    denominators: dict[_ScopeKey, list[NormalizedObservation]] = {}
    for obs in observations:
        if obs.source_id.slug != expected_source:
            continue
        if obs.indicator_code == numerator_code:
            numerators.setdefault(_group_key(obs), []).append(obs)
        elif obs.indicator_code == denominator_code:
            denominators.setdefault(_group_key(obs), []).append(obs)

    emitted: list[ConceptObservation] = []
    warnings: list[SourceWarning] = []
    all_scopes = sorted(
        set(numerators.keys()) | set(denominators.keys()),
        key=_scope_sort_key,
    )
    for scope in all_scopes:
        nums = numerators.get(scope, ())
        dens = denominators.get(scope, ())
        # The scope key carries leader-scope fields that are not
        # surfaced on the warning label; we only need the country
        # code and year for the diagnostic context.
        (
            _slug, country_code, _country_name, _lid, _lname, scope_year,
        ) = scope
        _ = (_slug, _country_name, _lid, _lname)

        drop_reason = _check_derivation_inputs(
            source_id=mapping.source_id,
            concept_key=mapping.concept_key,
            scope_country_code=country_code,
            scope_year=scope_year,
            numerator_code=numerator_code,
            denominator_code=denominator_code,
            nums=nums,
            dens=dens,
        )
        if drop_reason is not None:
            # Drop the scope without emitting a row. Surface the
            # reason as a structured :class:`SourceWarning` so the
            # diagnostic helper can pick it up; the convenience
            # :func:`extract_concept` discards it.
            warnings.append(_drop_reason_to_warning(drop_reason))
            continue

        num = nums[0]
        den = dens[0]
        ratio = float(num.value) / float(den.value)

        emitted.append(
            _build_derived_observation(
                mapping=mapping,
                numerator=num,
                denominator=den,
                ratio=ratio,
            ),
        )
    return (tuple(emitted), tuple(warnings))


def emit_derived_observations(
    *,
    observations: Sequence[NormalizedObservation],
    mapping: ConceptMapping,
) -> tuple[ConceptObservation, ...]:
    """Dispatch a derived mapping to the matching recipe helper.

    The current slice ships only the PWT GDP-per-capita recipe. A
    future slice that adds more derived recipes should branch on
    ``mapping.recipe_key`` here. The convenience return is just the
    observations tuple -- the diagnostic helper in :mod:`._api` uses
    :func:`emit_derived_observations_with_warnings` instead so the
    drop-reason warnings survive the wrapper boundary.
    """
    if mapping.recipe_key == PWT_GDP_PER_CAPITA_RECIPE_KEY:
        return emit_derived_pwt_gdp_per_capita_observations(
            observations=observations,
            mapping=mapping,
        )
    # Unknown recipe key: refuse to invent a derivation on the fly.
    return ()


def emit_derived_observations_with_warnings(
    *,
    observations: Sequence[NormalizedObservation],
    mapping: ConceptMapping,
) -> tuple[
    tuple[ConceptObservation, ...],
    tuple[SourceWarning, ...],
]:
    """Dispatch a derived mapping and return ``(observations, warnings)``.

    The diagnostic helper (:func:`extract_concept_result`) uses this
    entry point so per-scope drop reasons surface as structured
    :class:`SourceWarning` records. The convenience
    :func:`extract_concept` wrapper discards the warnings and returns
    only ``observations`` to keep the minimal public API flat.
    """
    if mapping.recipe_key == PWT_GDP_PER_CAPITA_RECIPE_KEY:
        return _derived_diagnostic(
            observations=observations,
            mapping=mapping,
        )
    # Unknown recipe key: refuse to invent a derivation on the fly.
    return ((), ())


__all__ = [
    "emit_derived_observations",
    "emit_derived_observations_with_warnings",
    "emit_derived_pwt_gdp_per_capita_observations",
]
