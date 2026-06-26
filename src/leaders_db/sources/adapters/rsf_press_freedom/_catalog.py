"""Unified-source RSF catalog helpers.

This module owns the small helpers that map the legacy
RSF indicator catalog
(``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``)
onto the unified-source observation-emission contract.
The catalog is reused verbatim from the legacy Stage 2
path so the unified adapter does not duplicate the
indicator metadata; the lazy import keeps the
``leaders_db.sources`` package boundary intact
(SRC-MIG-007 + ``docs/architecture/sources.md`` §10.1).

Catalog semantics
-----------------

The canonical RSF catalog carries SEVEN indicator rows
(``rsf_press_freedom_score`` /
``rsf_press_freedom_rank`` +
``rsf_press_freedom_political_context`` /
``rsf_press_freedom_economic_context`` /
``rsf_press_freedom_legal_context`` /
``rsf_press_freedom_social_context`` /
``rsf_press_freedom_safety`` per
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``)
in the ``political_freedom`` category. The unified
adapter maps that single category to a single
observation family:

- ``political_freedom`` -> ``political_freedom_country_year``

The mapping lives in
:func:`rating_category_to_observation_family` so the
transform layer can apply it per row. Unknown rating
categories fall back to
``political_freedom_country_year`` (the default RSF
family) so a future catalog addition does not silently
drop observations.

IndicatorSpec fields used by the unified transform:

- ``variable_name`` (catalog row -> ``indicator_code``
  on the emitted observation; the unified adapter
  narrows to the 7 RSF indicators).
- ``category`` (catalog row -> observation family via
  :func:`rating_category_to_observation_family`; the
  RSF catalog uses ``category`` -- not
  ``rating_category`` -- to match the canonical
  catalog header).
- ``unit`` (catalog row -> ``unit`` on the emitted
  observation; ``index`` for the score + 5 components,
  ``rank`` for the rank per the canonical catalog).
- ``raw_scale`` (catalog row -> ``scale`` on the
  emitted observation; ``0-100`` for the score + 5
  components post-2022, ``ordinal`` for the rank per
  the canonical catalog; the pre-2022 0-100 score uses
  a different ordinal scale per the documented
  pre/post-2022 methodology change).
- ``raw_column`` (the catalog's logical
  ``raw_column``: ``score`` / ``rank`` /
  ``political_context`` / ``economic_context`` /
  ``legal_context`` / ``social_context`` / ``safety``;
  -> carried onto ``extension["rsf_raw_column"]`` so
  audit code can re-derive the value from the legacy
  xlsx).
- ``higher_is_better`` (carried onto the observation
  ``extension`` for direction hints; the RSF score +
  5 components are ``higher_is_better=True`` because
  higher RSF score = better press-freedom situation;
  the rank is ``higher_is_better=False`` because
  rank 1 = best country).
- ``normalized_scale_target`` (carried onto the
  observation ``extension``; ``"0-10"`` per the
  canonical catalog; the Stage 5 score module
  normalizes to the 0-10 target).
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import RSF_PRESS_FREEDOM_OBSERVATION_FAMILY

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime
# via the ``catalog_path`` kwarg without invalidating
# the descriptor's hash. The default path is the
# canonical checked-in catalog at
# ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "rsf_press_freedom.csv"
)


# Map legacy RSF ``category`` values to the
# unified-source observation families. The RSF catalog
# declares a single ``political_freedom`` category;
# the mapping stays in a dict so future catalog
# additions can map new categories to new families
# without changing the transform layer. Unknown
# categories fall back to
# ``political_freedom_country_year`` (the default RSF
# family) so the transform never silently drops
# observations.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "political_freedom": RSF_PRESS_FREEDOM_OBSERVATION_FAMILY,
}


def rating_category_to_observation_family(
    rating_category: str,
) -> str:
    """Map a legacy catalog ``category`` (RSF uses
    ``category`` not ``rating_category``) to a unified
    observation family.

    Unknown categories fall back to
    ``political_freedom_country_year`` (the default RSF
    family) so a future catalog addition does not
    silently drop observations. The function is a pure
    string lookup so the transform layer can apply it
    per row without consulting the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        RSF_PRESS_FREEDOM_OBSERVATION_FAMILY,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the RSF indicator catalog.

    Returns the legacy :class:`IndicatorSpec` list. The
    legacy reader / catalog module is imported lazily
    so the ``leaders_db.sources`` package boundary is
    preserved (SRC-MIG-007 +
    ``docs/architecture/sources.md`` §10.1).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest``. The legacy catalog
    # loader returns the canonical ``IndicatorSpec``
    # list (the same dataclass the Stage 2 legacy
    # adapter consumes).
    from leaders_db.ingest.rsf_press_freedom_io import (
        load_rsf_press_freedom_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
