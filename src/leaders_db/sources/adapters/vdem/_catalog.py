"""Unified-source V-Dem catalog helpers.

This module owns the small helpers that map the legacy V-Dem
indicator catalog (``src/leaders_db/ingest/catalogs/vdem.csv``)
onto the unified-source observation-emission contract. The
catalog is reused verbatim from the legacy Stage 2 path so the
unified adapter does not duplicate the indicator metadata;
the lazy import keeps the ``leaders_db.sources`` package
boundary intact.

Catalog semantics
-----------------

The catalog carries 22 V-Dem indicators across the five
rating categories V-Dem feeds (political_freedom, integrity,
effectiveness, domestic_violence, social_wellbeing). The
unified adapter maps each catalog row to one of the five
unified observation families:

- ``political_freedom`` -> ``political_country_year``
- ``integrity`` -> ``corruption_country_year``
- ``effectiveness`` -> ``governance_country_year``
- ``domestic_violence`` -> ``repression_country_year``
- ``social_wellbeing`` -> ``social_country_year``

The mapping lives in :func:`rating_category_to_observation_family`
so the transform layer can apply it per row. Unknown rating
categories fall back to ``political_country_year`` (the
default V-Dem family) so a future catalog addition does not
silently drop observations.
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import (
    VDEM_OBSERVATION_FAMILY_CORRUPTION,
    VDEM_OBSERVATION_FAMILY_GOVERNANCE,
    VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    VDEM_OBSERVATION_FAMILY_REPRESSION,
    VDEM_OBSERVATION_FAMILY_SOCIAL,
)

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime via
# the ``catalog_path`` kwarg without invalidating the
# descriptor's hash. The default path is the canonical
# checked-in catalog at
# ``src/leaders_db/ingest/catalogs/vdem.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "vdem.csv"
)


# Map legacy V-Dem ``rating_category`` values to the
# unified-source observation families. Unknown categories
# fall back to ``political_country_year`` so the transform
# never silently drops observations on a future catalog
# addition; the fallback is documented in the module
# docstring.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "political_freedom": VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    "integrity": VDEM_OBSERVATION_FAMILY_CORRUPTION,
    "effectiveness": VDEM_OBSERVATION_FAMILY_GOVERNANCE,
    "domestic_violence": VDEM_OBSERVATION_FAMILY_REPRESSION,
    "social_wellbeing": VDEM_OBSERVATION_FAMILY_SOCIAL,
}


def rating_category_to_observation_family(rating_category: str) -> str:
    """Map a legacy catalog ``rating_category`` to a unified observation family.

    Unknown categories fall back to
    ``political_country_year`` (the default V-Dem family) so
    a future catalog addition does not silently drop
    observations. The function is a pure string lookup so the
    transform layer can apply it per row without consulting
    the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the V-Dem indicator catalog.

    Returns the legacy :class:`IndicatorSpec` list. The
    legacy reader / catalog module is imported lazily so the
    ``leaders_db.sources`` package boundary is preserved
    (SRC-MIG-007 + docs/architecture/sources.md §10.1).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest``. The legacy catalog
    # loader returns the canonical ``IndicatorSpec`` list.
    from leaders_db.ingest.vdem_io import (
        load_indicator_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
