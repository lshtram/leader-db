"""Unified-source UCDP catalog helpers.

This module owns the small helpers that map the legacy UCDP
indicator catalog (``src/leaders_db/ingest/catalogs/ucdp.csv``)
onto the unified-source observation-emission contract. The
catalog is reused verbatim from the legacy Stage 2 path so the
unified adapter does not duplicate the indicator metadata;
the lazy import keeps the ``leaders_db.sources`` package
boundary intact.

Catalog semantics
-----------------

The catalog carries 6 UCDP indicators across the two rating
categories UCDP feeds (international_peace for 4
state-based indicators, domestic_violence for 2 one-sided
indicators). The unified adapter maps each catalog row to one
of the two unified observation families:

- ``international_peace`` -> ``international_peace_country_year``
- ``domestic_violence`` -> ``domestic_violence_country_year``

The mapping lives in :func:`rating_category_to_observation_family`
so the transform layer can apply it per row. Unknown rating
categories fall back to ``international_peace_country_year``
(the default UCDP family) so a future catalog addition does
not silently drop observations.

The UCDP catalog adds a 9th ``filter_logic`` column beyond
the standard 8-column V-Dem / WDI / WGI shape. The column
holds the pandas query string for the type + cross-border
filter (``type_of_violence == 1``, ``type_of_violence == 3``,
``type_of_violence == 1 and gwnob.notna()``). The unified
transform layer does not consult ``filter_logic`` directly;
the aggregation is performed by the legacy
:func:`aggregate_events_to_country_year` reader (lazy-imported
in :mod:`._raw_read`) which already applies the type filter
and cross-border filter during the long-to-wide pivot. The
unified transform layer only consumes the wide-format
country-year DataFrame and emits one
:class:`NormalizedObservation` per ``(country_id, year,
variable_name)`` triple.

IndicatorSpec fields used by the unified transform:

- ``variable_name`` (catalog row -> ``indicator_code`` on the
  emitted observation)
- ``rating_category`` (catalog row -> observation family via
  :func:`rating_category_to_observation_family`)
- ``unit`` (catalog row -> ``unit`` on the emitted observation)
- ``raw_scale`` (catalog row -> ``scale`` on the emitted
  observation)
- ``raw_column`` (``event_count`` or ``best`` -- the column
  the legacy aggregator picked; the unified transform carries
  this onto ``extension["ucdp_raw_column"]`` so audit code can
  re-derive the value from the legacy long frame)
- ``filter_logic`` (carried onto
  ``extension["ucdp_filter_logic"]`` for audit traceability)
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import (
    UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE,
    UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE,
)

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime via
# the ``catalog_path`` kwarg without invalidating the
# descriptor's hash. The default path is the canonical
# checked-in catalog at
# ``src/leaders_db/ingest/catalogs/ucdp.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "ucdp.csv"
)


# Map legacy UCDP ``rating_category`` values to the
# unified-source observation families. Unknown categories
# fall back to ``international_peace_country_year`` so the
# transform never silently drops observations on a future
# catalog addition; the fallback is documented in the module
# docstring.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "international_peace": UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE,
    "domestic_violence": UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE,
}


def rating_category_to_observation_family(rating_category: str) -> str:
    """Map a legacy catalog ``rating_category`` to a unified observation family.

    Unknown categories fall back to
    ``international_peace_country_year`` (the default UCDP
    family) so a future catalog addition does not silently
    drop observations. The function is a pure string lookup
    so the transform layer can apply it per row without
    consulting the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the UCDP indicator catalog.

    Returns the legacy :class:`IndicatorSpec` list. The
    legacy reader / catalog module is imported lazily so the
    ``leaders_db.sources`` package boundary is preserved
    (SRC-MIG-007 + docs/architecture/sources.md §10.1).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest``. The legacy catalog
    # loader returns the canonical ``IndicatorSpec`` list.
    from leaders_db.ingest.ucdp_io import (
        load_indicator_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
