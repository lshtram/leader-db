"""Unified-source Transparency International CPI catalog helpers.

This module owns the small helpers that map the legacy
Transparency International CPI indicator catalog
(``src/leaders_db/ingest/catalogs/transparency_cpi.csv``)
onto the unified-source observation-emission contract. The
catalog is reused verbatim from the legacy Stage 2 path so
the unified adapter does not duplicate the indicator
metadata; the lazy import keeps the
``leaders_db.sources`` package boundary intact.

Catalog semantics
-----------------

The canonical Transparency International CPI catalog carries
ONE indicator row (``cpi_score`` per
``src/leaders_db/ingest/catalogs/transparency_cpi.csv``) in
the ``integrity`` rating category. The unified adapter maps
that single catalog row to the single unified observation
family:

- ``integrity`` -> ``integrity_country_year``

The mapping lives in
:func:`rating_category_to_observation_family` so the
transform layer can apply it per row. Unknown rating
categories fall back to ``integrity_country_year`` (the
default CPI family) so a future catalog addition does not
silently drop observations.

IndicatorSpec fields used by the unified transform:

- ``variable_name`` (catalog row -> ``indicator_code`` on
  the emitted observation; the unified adapter narrows to
  ``cpi_score``)
- ``rating_category`` (catalog row -> observation family
  via :func:`rating_category_to_observation_family`)
- ``unit`` (catalog row -> ``unit`` on the emitted
  observation)
- ``raw_scale`` (catalog row -> ``scale`` on the emitted
  observation)
- ``raw_column`` (the HDX CSV column ``score`` -> carried
  onto ``extension["transparency_cpi_raw_column"]`` so
  audit code can re-derive the value from the legacy CSV)
- ``higher_is_better`` + ``normalized_scale_target``
  (carried onto the observation ``extension`` for
  direction hints)
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import (
    TRANSPARENCY_CPI_OBSERVATION_FAMILY,
)

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime via
# the ``catalog_path`` kwarg without invalidating the
# descriptor's hash. The default path is the canonical
# checked-in catalog at
# ``src/leaders_db/ingest/catalogs/transparency_cpi.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "transparency_cpi.csv"
)


# Map legacy Transparency International CPI
# ``rating_category`` values to the unified-source
# observation families. The catalog declares a single
# ``integrity`` rating category; the mapping stays in a
# dict so future catalog additions can map new categories
# to new families without changing the transform layer.
# Unknown categories fall back to
# ``integrity_country_year`` (the default CPI family) so
# the transform never silently drops observations.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "integrity": TRANSPARENCY_CPI_OBSERVATION_FAMILY,
}


def rating_category_to_observation_family(
    rating_category: str,
) -> str:
    """Map a legacy catalog ``rating_category`` to a
    unified observation family.

    Unknown categories fall back to
    ``integrity_country_year`` (the default CPI family)
    so a future catalog addition does not silently drop
    observations. The function is a pure string lookup so
    the transform layer can apply it per row without
    consulting the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        TRANSPARENCY_CPI_OBSERVATION_FAMILY,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the Transparency International CPI
    indicator catalog.

    Returns the legacy :class:`IndicatorSpec` list. The
    legacy reader / catalog module is imported lazily so
    the ``leaders_db.sources`` package boundary is
    preserved (SRC-MIG-007 +
    docs/architecture/sources.md §10.1).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest``. The legacy catalog
    # loader returns the canonical ``IndicatorSpec`` list.
    from leaders_db.ingest.transparency_cpi_io import (
        load_indicator_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
