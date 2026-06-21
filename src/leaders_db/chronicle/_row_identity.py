"""Identity column population for the Country-Year Chronicle row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_identity` — set the year / iso3 / country / status
  columns from the country metadata.
- :func:`derive_country_status` — compute ``country_status`` from the
  metadata + requested year (with the colonial-cutoff exception for
  identities like IND that span a colonial / independent transition).
"""

from __future__ import annotations

from ._formatters import coerce_int, safe_int
from .constants import COUNTRY_METADATA


def populate_identity(row: dict[str, str], iso3: str, year: int) -> None:
    """Populate year / iso3 / country metadata into the row in place.

    ``country_status`` is computed dynamically: when the country
    metadata declares a ``colonial_status_until`` year, years at or
    before that cutoff are emitted as ``colonial/dependent`` and
    later years fall back to the metadata's static
    ``country_status`` (typically ``independent``). This is how we
    keep IND's pre-1947 rows honest without duplicating the country
    record for British India — the same ISO3 spans both eras and the
    status flips at the documented cutoff.
    """
    metadata = COUNTRY_METADATA.get(iso3, {})
    row["year"] = coerce_int(year)
    row["iso3"] = iso3
    row["country_name"] = metadata.get("country_name", iso3)
    row["country_status"] = derive_country_status(metadata, year)
    row["region"] = metadata.get("region", "")
    row["subregion"] = metadata.get("subregion", "")


def derive_country_status(metadata: dict[str, str], year: int) -> str:
    """Compute ``country_status`` from the metadata + requested year.

    The default is the metadata's static ``country_status`` (usually
    ``independent`` or ``successor_state``). For countries with a
    ``colonial_status_until`` cutoff (currently just IND with
    ``colonial_status_until=1946``) the row flips to
    ``colonial/dependent`` for years at or before that cutoff, and
    back to the static value for later years. This keeps a single
    IND identity spanning the colonial/independent transition without
    inventing a new country record.
    """
    static_status = metadata.get("country_status", "unknown")
    colonial_until = safe_int(metadata.get("colonial_status_until"))
    if colonial_until is not None and year <= colonial_until:
        return "colonial/dependent"
    return static_status


__all__ = [
    "derive_country_status",
    "populate_identity",
]
