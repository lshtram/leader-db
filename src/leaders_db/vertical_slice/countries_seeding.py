"""Country / country-year / observation helpers for the 2023 slice.

Implements architecture doc §6: upsert MEX/NGA/USA, link ISO3-bearing
``source_observations`` rows by their ``source_row_reference`` prefix,
and create/update ``country_years`` for the target year.

The slice is deliberately not the real Stage 3 matcher. It uses the
fixed :data:`SLICE_ISO3_BY_CLIENT_NAME` map plus a small helper that
parses ``<prefix>:<ISO3>`` patterns.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db.models import Country, CountryYear, SourceObservation
from ..normalize.countries import normalize_country_name
from .constants import (
    ISO3_LINK_PREFIXES,
    SLICE_INCLUSION_REASON,
)


def seed_countries(
    session: Session,
    *,
    iso3s: Iterable[str],
    preferred_names: dict[str, str],
) -> dict[str, int]:
    """Upsert :class:`Country` rows for the given ISO3s.

    Returns a mapping ``{iso3: country.id}``. Existing rows are kept
    untouched (no overwrite of ``country_name`` etc.); new rows use the
    preferred display name plus a normalized name from the existing
    helper.
    """
    out: dict[str, int] = {}
    for iso3 in iso3s:
        iso3_upper = iso3.upper()
        existing = session.execute(
            select(Country).where(Country.iso3 == iso3_upper)
        ).scalar_one_or_none()
        if existing is not None:
            out[iso3_upper] = existing.id
            continue
        display_name = preferred_names.get(iso3_upper, iso3_upper)
        row = Country(
            iso3=iso3_upper,
            country_name=display_name,
            country_name_normalized=normalize_country_name(display_name),
            notes=None,
        )
        session.add(row)
        session.flush()
        out[iso3_upper] = row.id
    return out


def seed_country_years(
    session: Session,
    *,
    country_ids: dict[str, int],
    target_year: int,
    population_by_iso3: dict[str, int | None],
) -> dict[tuple[str, int], int]:
    """Upsert :class:`CountryYear` rows for ``(country_id, target_year)``.

    Returns a mapping ``{(iso3, year): country_year.id}``. Existing rows
    are updated only when the slice adds new evidence (population is
    backfilled from the client matrix if a parsed value is available
    and the existing row has none).
    """
    out: dict[tuple[str, int], int] = {}
    for iso3, country_id in country_ids.items():
        existing = session.execute(
            select(CountryYear).where(
                CountryYear.country_id == country_id,
                CountryYear.year == target_year,
            )
        ).scalar_one_or_none()
        if existing is None:
            cy = CountryYear(
                country_id=country_id,
                year=target_year,
                population=population_by_iso3.get(iso3),
                included_in_project=True,
                inclusion_reason=SLICE_INCLUSION_REASON,
            )
            session.add(cy)
            session.flush()
            out[(iso3, target_year)] = cy.id
        else:
            if existing.population is None and population_by_iso3.get(iso3) is not None:
                existing.population = population_by_iso3[iso3]
            existing.included_in_project = True
            existing.inclusion_reason = SLICE_INCLUSION_REASON
            session.flush()
            out[(iso3, target_year)] = existing.id
    return out


def link_iso3_observations(
    session: Session,
    *,
    country_ids: dict[str, int],
    prefixes: tuple[str, ...] = ISO3_LINK_PREFIXES,
) -> int:
    """Link :class:`SourceObservation` rows to countries by ISO3 prefix.

    For every observation whose ``source_row_reference`` matches
    ``<prefix>:<ISO3>`` for some prefix in :data:`ISO3_LINK_PREFIXES`,
    set ``country_id`` to the matching country, but only when:

    - ``country_id`` is NULL, or
    - ``country_id`` already points to the same country.

    Rows whose ``country_id`` already points to a *different* country
    are preserved (architecture §6 conflict rule).

    Returns the number of rows updated.
    """
    if not country_ids:
        return 0

    candidate_refs = [f"{prefix}:" for prefix in prefixes]
    # OR-combined prefix filter so a single query covers all known
    # ISO3-bearing reference prefixes.
    prefix_filters = [
        SourceObservation.source_row_reference.like(f"{ref}%")
        for ref in candidate_refs
    ]
    observations = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_row_reference.is_not(None),
            or_(*prefix_filters),
        )
    ).scalars().all()

    updated = 0
    for obs in observations:
        ref = obs.source_row_reference or ""
        prefix, _, iso3_suffix = ref.partition(":")
        if prefix not in prefixes:
            continue
        if not iso3_suffix:
            continue
        iso3_upper = iso3_suffix.strip().upper()
        target_id = country_ids.get(iso3_upper)
        if target_id is None:
            continue  # ISO3 is not in the slice scope (other countries)
        if obs.country_id is None:
            obs.country_id = target_id
            updated += 1
        elif obs.country_id == target_id:
            pass  # already linked to the same country; no-op
        else:
            # Conflict with a non-slice country link; preserve the row.
            continue
    return updated


def get_country_year_id(
    session: Session, *, country_id: int, year: int
) -> int | None:
    """Return the :class:`CountryYear` id for ``(country_id, year)`` if it exists."""
    return session.execute(
        select(CountryYear.id).where(
            CountryYear.country_id == country_id,
            CountryYear.year == year,
        )
    ).scalar_one_or_none()


__all__ = [
    "get_country_year_id",
    "link_iso3_observations",
    "seed_countries",
    "seed_country_years",
]
