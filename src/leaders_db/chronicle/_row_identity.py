"""Identity column population for the Country-Year Chronicle row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_identity` — set the year / iso3 / country / status
  columns from the country metadata (pilot or scope-derived).
- :func:`derive_country_status` — compute ``country_status`` from the
  metadata + requested year (with the colonial-cutoff exception for
  identities like IND that span a colonial / independent transition).

Increment 5 changes (all-country condensed export):

- :func:`populate_identity` now accepts an optional
  :class:`CountryScopeEntry` so the row builder can populate the
  identity columns from the all-country scope (V-Dem coverage +
  pilot historical identities) instead of the small
  :data:`COUNTRY_METADATA` constant.
- When the scope entry is provided the ``country_name`` comes from
  the scope entry; otherwise the row falls back to the pilot
  metadata and ultimately the ISO3 code.
- The detailed CSV / SQLite behavior is preserved when the caller
  does NOT pass a scope entry: existing pilot tests still see
  ``country_name`` / ``country_status`` / ``region`` / ``subregion``
  from :data:`COUNTRY_METADATA`.
"""

from __future__ import annotations

from ._formatters import coerce_int, safe_int
from .constants import COUNTRY_METADATA
from .country_scope import CountryScopeEntry


def populate_identity(
    row: dict[str, str],
    iso3: str,
    year: int,
    *,
    country_scope_entry: CountryScopeEntry | None = None,
) -> None:
    """Populate year / iso3 / country metadata into the row in place.

    ``country_status`` is computed dynamically: when the country
    metadata declares a ``colonial_status_until`` year, years at or
    before that cutoff are emitted as ``colonial/dependent`` and
    later years fall back to the metadata's static
    ``country_status`` (typically ``independent``). This is how we
    keep IND's pre-1947 rows honest without duplicating the country
    record for British India — the same ISO3 spans both eras and the
    status flips at the documented cutoff.

    When ``country_scope_entry`` is provided (the Increment 5
    all-country path), the ``country_name`` comes from the scope
    entry. ``country_status`` falls back to the pilot metadata's
    static value (pilot identities with a colonial cutoff still
    get the IND-style flip); non-pilot countries with no pilot
    metadata default to ``unknown``. ``region`` / ``subregion`` are
    not populated by the all-country scope (V-Dem does not supply
    them); they are blank when no pilot metadata is available.
    """
    row["year"] = coerce_int(year)
    row["iso3"] = iso3
    metadata = COUNTRY_METADATA.get(iso3, {})
    if country_scope_entry is not None:
        row["country_name"] = country_scope_entry.country_name or iso3
    else:
        row["country_name"] = metadata.get("country_name", iso3)
    row["country_status"] = derive_country_status(metadata, year)
    if country_scope_entry is not None and iso3 not in COUNTRY_METADATA:
        # The all-country path: keep the static ``unknown`` status
        # for countries that have no pilot metadata. The pilot
        # colonial-cutoff logic above already handled the pilot
        # cases.
        row["country_status"] = (
            metadata.get("country_status", "unknown")
            if metadata
            else "unknown"
        )
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
