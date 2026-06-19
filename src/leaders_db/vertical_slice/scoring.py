"""Provisional scoring helpers for the 2023 vertical slice.

Implements architecture doc §8 formulas:

- ``social_wellbeing = round(10 * undp_hdi_hdi_value)``
- ``integrity = round(10 * clamp((wgi_z + 2.5) / 5.0))``

Both formulas are clip-safe (``0..10``) and use the Stage 2
``source_observations`` table as the input. The functions here do
not write to the DB; they return the values the orchestrator
persists.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Country, CountryYear, SourceObservation
from .constants import CATEGORY_INPUT_MAP


class ScoreInputs(NamedTuple):
    """Inputs gathered from the database for one (country, category)."""

    category_key: str
    variable_name: str
    raw_value: float | None
    normalized_value: float | None
    source_year: int | None
    is_proxy: bool


class ScoreResult(NamedTuple):
    """Output of the provisional scoring layer."""

    category_key: str
    raw_value: float | None
    raw_value_str: str | None
    source_year: int | None
    is_proxy: bool
    system_proposed_score: int | None
    confidence_agreement: int
    confidence_authority: int
    confidence_specificity: int
    confidence_temporal_fit: int
    skip_reason: str | None


def gather_inputs(
    session: Session,
    *,
    country_id: int,
    category_key: str,
    target_year: int,
    exact_year: int | None = None,
) -> ScoreInputs | None:
    """Look up the source observation needed to score one category.

    Returns ``None`` when the category is not in :data:`CATEGORY_INPUT_MAP`
    (i.e. the slice does not score it). Otherwise returns the
    :class:`ScoreInputs` resolved for the country.

    Year handling matches architecture §8: prefer ``target_year``; fall
    back to the documented proxy year (typically 2022). The proxy is
    surfaced on the :class:`ScoreInputs` so the orchestrator can record
    a temporal-fit penalty and a proxy note in the output.

    When ``exact_year`` is provided, the lookup is constrained to that
    single year (no proxy fallback) and the returned
    :class:`ScoreInputs` always reports ``is_proxy=False``. This is used
    by the multi-year source-only time-series output where rows for
    ``year < target_year`` must use the exact source observation
    year (or be omitted if missing), not a proxy year.
    """
    spec = CATEGORY_INPUT_MAP.get(category_key)
    if spec is None:
        return None
    variable_name, preferred_year, fallback_year = spec

    if exact_year is not None:
        # Exact-year lookup for the multi-year time-series output. No
        # proxy fallback: pre-2023 rows must use the literal source
        # year or be omitted from the output entirely.
        obs = session.execute(
            select(SourceObservation).where(
                SourceObservation.country_id == country_id,
                SourceObservation.variable_name == variable_name,
                SourceObservation.year == exact_year,
            )
        ).scalars().first()
        if obs is not None:
            raw_value = _coerce_float(obs.raw_value)
            return ScoreInputs(
                category_key=category_key,
                variable_name=variable_name,
                raw_value=raw_value,
                normalized_value=obs.normalized_value,
                source_year=exact_year,
                is_proxy=False,
            )
        return ScoreInputs(
            category_key=category_key,
            variable_name=variable_name,
            raw_value=None,
            normalized_value=None,
            source_year=None,
            is_proxy=False,
        )

    # Prefer the target year, then fall back to the proxy year.
    for candidate_year, is_proxy in (
        (preferred_year, False),
        (fallback_year, True),
    ):
        obs = session.execute(
            select(SourceObservation).where(
                SourceObservation.country_id == country_id,
                SourceObservation.variable_name == variable_name,
                SourceObservation.year == candidate_year,
            )
        ).scalars().first()
        if obs is not None:
            raw_value = _coerce_float(obs.raw_value)
            return ScoreInputs(
                category_key=category_key,
                variable_name=variable_name,
                raw_value=raw_value,
                normalized_value=obs.normalized_value,
                source_year=candidate_year,
                is_proxy=is_proxy,
            )
    return ScoreInputs(
        category_key=category_key,
        variable_name=variable_name,
        raw_value=None,
        normalized_value=None,
        source_year=None,
        is_proxy=False,
    )


def score_one(inputs: ScoreInputs) -> ScoreResult:
    """Compute the provisional score for one category.

    Implements the formulas from architecture doc §8. Returns a
    :class:`ScoreResult` whose ``skip_reason`` is non-None when the
    formula cannot be computed (e.g. no observation is available).
    """
    if inputs.category_key == "social_wellbeing":
        authority = 80  # UNDP HDI
        return _score_social(inputs, authority)
    if inputs.category_key == "integrity":
        authority = 80  # World Bank WGI
        return _score_integrity(inputs, authority)
    return ScoreResult(
        category_key=inputs.category_key,
        raw_value=inputs.raw_value,
        raw_value_str=None,
        source_year=inputs.source_year,
        is_proxy=inputs.is_proxy,
        system_proposed_score=None,
        confidence_agreement=0,
        confidence_authority=0,
        confidence_specificity=0,
        confidence_temporal_fit=0,
        skip_reason=f"category {inputs.category_key!r} not in slice scope",
    )


def _score_social(inputs: ScoreInputs, authority: int) -> ScoreResult:
    """``social_wellbeing = round(10 * hdi)``, clipped to 0..10."""
    if inputs.raw_value is None:
        return ScoreResult(
            category_key=inputs.category_key,
            raw_value=None,
            raw_value_str=None,
            source_year=inputs.source_year,
            is_proxy=inputs.is_proxy,
            system_proposed_score=None,
            confidence_agreement=0,
            confidence_authority=0,
            confidence_specificity=0,
            confidence_temporal_fit=0,
            skip_reason="no undp_hdi_hdi observation for country",
        )
    score = _clip_0_10(round(10.0 * inputs.raw_value))
    return ScoreResult(
        category_key=inputs.category_key,
        raw_value=inputs.raw_value,
        raw_value_str=str(inputs.raw_value),
        source_year=inputs.source_year,
        is_proxy=inputs.is_proxy,
        system_proposed_score=score,
        confidence_agreement=60,  # one direct source
        confidence_authority=authority,
        confidence_specificity=80,  # country-year, not ruler-specific
        confidence_temporal_fit=80 if inputs.is_proxy else 100,
        skip_reason=None,
    )


def _score_integrity(inputs: ScoreInputs, authority: int) -> ScoreResult:
    """``integrity = round(10 * clamp((wgi_z + 2.5) / 5.0))``."""
    # Architecture §8 says we may use the adapter's pre-normalized
    # value if it already maps to 0..1; otherwise compute from raw z.
    z_score: float | None
    if inputs.normalized_value is not None:
        # Heuristic: the slice's normalized_value covers both 0..1 and
        # raw z values. We treat the value as already-normalized only
        # when it is clearly out of the z-score range (i.e. in [0, 1]).
        if 0.0 <= inputs.normalized_value <= 1.0 and inputs.raw_value is None:
            normalized = inputs.normalized_value
        else:
            z_score = inputs.raw_value if inputs.raw_value is not None else inputs.normalized_value
            if z_score is None:
                normalized = None
            else:
                normalized = max(0.0, min(1.0, (z_score + 2.5) / 5.0))
    elif inputs.raw_value is not None:
        z_score = inputs.raw_value
        normalized = max(0.0, min(1.0, (z_score + 2.5) / 5.0))
    else:
        normalized = None

    if normalized is None:
        return ScoreResult(
            category_key=inputs.category_key,
            raw_value=inputs.raw_value,
            raw_value_str=str(inputs.raw_value) if inputs.raw_value is not None else None,
            source_year=inputs.source_year,
            is_proxy=inputs.is_proxy,
            system_proposed_score=None,
            confidence_agreement=0,
            confidence_authority=0,
            confidence_specificity=0,
            confidence_temporal_fit=0,
            skip_reason="no wgi_control_of_corruption observation for country",
        )
    score = _clip_0_10(round(10.0 * normalized))
    raw_value_str = str(inputs.raw_value) if inputs.raw_value is not None else None
    return ScoreResult(
        category_key=inputs.category_key,
        raw_value=inputs.raw_value,
        raw_value_str=raw_value_str,
        source_year=inputs.source_year,
        is_proxy=inputs.is_proxy,
        system_proposed_score=score,
        confidence_agreement=60,
        confidence_authority=authority,
        confidence_specificity=80,
        confidence_temporal_fit=80 if inputs.is_proxy else 100,
        skip_reason=None,
    )


def _clip_0_10(value: int) -> int:
    if value < 0:
        return 0
    if value > 10:
        return 10
    return value


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f:  # NaN  # noqa: PLR0124
            return None
        return f
    return _coerce_float_from_string(value)


def _coerce_float_from_string(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() in {"n/a", "-", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def find_country_year_id(
    session: Session, *, country_id: int, year: int
) -> int | None:
    """Return the ``CountryYear.id`` for ``(country_id, year)`` or ``None``."""
    return session.execute(
        select(CountryYear.id).where(
            CountryYear.country_id == country_id,
            CountryYear.year == year,
        )
    ).scalar_one_or_none()


def find_country_by_iso3(session: Session, iso3: str) -> Country | None:
    """Return the :class:`Country` row for ``iso3`` or ``None``."""
    return session.execute(
        select(Country).where(Country.iso3 == iso3.upper())
    ).scalar_one_or_none()


__all__ = [
    "ScoreInputs",
    "ScoreResult",
    "find_country_by_iso3",
    "find_country_year_id",
    "gather_inputs",
    "score_one",
]
