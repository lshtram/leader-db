"""Shared test fixtures and builders for the Stage 5 evidence-bundle tests.

These helpers are intentionally not :func:`pytest.fixture` s — they
take a :class:`Session` and keyword arguments and either return a
constructed ORM row or append to it, so the test body reads
naturally:

    country = seed_country(session)
    undp = upsert_source(session, source_name="UNDP HDI 2023-24 (test)")
    add_observation(session, source_id=undp.id, country_id=country.id,
                    year=2023, variable_name="undp_hdi_hdi", ...)

The :class:`Session` is passed in by the caller (via the
``session_scope`` helper or the ``database_url`` fixture) so each
test stages its own short-lived ORM rows against the isolated
SQLite fixture. Helpers keep their own ID resolution and tolerate
idempotent re-runs (the ``upsert_source`` and ``seed_country``
helpers re-use an existing row when one is already present).

The leading underscore in the module name keeps pytest from
collecting it as a test file.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public helper parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from leaders_db.db.models import Country, Source, SourceObservation

# ---------------------------------------------------------------------------
# Constants — names follow the production ``register_*_source`` calls so the
# substring match in :func:`canonical_source_key` still resolves to the right
# canonical key.
# ---------------------------------------------------------------------------

COUNTRY_ISO3: str = "MEX"
COUNTRY_NAME: str = "Mexico"
COUNTRY_REGION: str = "LAC"
COUNTRY_NAME_NORMALIZED: str = "mexico"
TARGET_YEAR: int = 2023

UNDP_SOURCE_NAME: str = "UNDP HDI 2023-24 (test)"
WGI_SOURCE_NAME: str = "World Bank WGI 2023 (test)"
WDI_SOURCE_NAME: str = "World Bank WDI 2024 (test)"
VDEM_SOURCE_NAME: str = "V-Dem v16 (test)"
WHO_SOURCE_NAME: str = "WHO Global Health Observatory (OData API) (test)"
CPI_SOURCE_NAME: str = "Transparency International CPI 2023 (test)"


# ---------------------------------------------------------------------------
# Country / source / observation builders
# ---------------------------------------------------------------------------


def seed_country(session: Session) -> Country:
    """Insert or fetch the single test :class:`Country` row (``MEX``)."""
    country = session.execute(
        select(Country).where(Country.iso3 == COUNTRY_ISO3)
    ).scalar_one_or_none()
    if country is not None:
        return country
    country = Country(
        iso3=COUNTRY_ISO3,
        country_name=COUNTRY_NAME,
        country_name_normalized=COUNTRY_NAME_NORMALIZED,
        region=COUNTRY_REGION,
    )
    session.add(country)
    session.flush()
    return country


def upsert_source(session: Session, *, source_name: str) -> Source:
    """Insert or fetch a :class:`Source` row by name; idempotent."""
    existing = session.execute(
        select(Source).where(Source.source_name == source_name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Source(
        source_name=source_name,
        source_type="official",
    )
    session.add(row)
    session.flush()
    return row


def add_observation(
    session: Session,
    *,
    source_id: int,
    country_id: int,
    year: int,
    variable_name: str,
    raw_value: str | None = None,
    normalized_value: float | None = None,
    unit: str | None = None,
    source_row_reference: str | None = None,
) -> SourceObservation:
    """Insert a :class:`SourceObservation` row and flush so ``.id`` is set.

    Returns the inserted row so callers can assert on its
    auto-generated primary key when exercising the deterministic
    tie-breaker tests.
    """
    row = SourceObservation(
        source_id=source_id,
        country_id=country_id,
        year=year,
        variable_name=variable_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        unit=unit,
        source_row_reference=source_row_reference,
    )
    session.add(row)
    session.flush()
    return row


__all__ = [
    "COUNTRY_ISO3",
    "COUNTRY_NAME",
    "CPI_SOURCE_NAME",
    "TARGET_YEAR",
    "UNDP_SOURCE_NAME",
    "VDEM_SOURCE_NAME",
    "WDI_SOURCE_NAME",
    "WGI_SOURCE_NAME",
    "WHO_SOURCE_NAME",
    "add_observation",
    "seed_country",
    "upsert_source",
]
