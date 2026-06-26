"""Unified-source PTS catalog helpers.

This module owns the small helpers that map the legacy
PTS indicator catalog
(``src/leaders_db/ingest/catalogs/pts.csv``) onto the
unified-source observation-emission contract. The
catalog is reused verbatim from the legacy Stage 2 path
so the unified adapter does not duplicate the indicator
metadata; the lazy import keeps the
``leaders_db.sources`` package boundary intact
(SRC-MIG-007 + ``docs/architecture/sources.md`` §10.1).

Catalog semantics
-----------------

The canonical PTS catalog carries THREE indicator rows
(``pts_amnesty_score`` / ``pts_human_rights_watch_score``
/ ``pts_state_dept_score`` per
``src/leaders_db/ingest/catalogs/pts.csv``) in the
``domestic_violence`` rating category. The unified
adapter maps that single category to the single unified
observation family:

- ``domestic_violence`` -> ``domestic_violence_country_year``

The mapping lives in
:func:`rating_category_to_observation_family` so the
transform layer can apply it per row. Unknown rating
categories fall back to
``domestic_violence_country_year`` (the default PTS
family) so a future catalog addition does not silently
drop observations.

IndicatorSpec fields used by the unified transform:

- ``variable_name`` (catalog row -> ``indicator_code``
  on the emitted observation; the unified adapter
  narrows to the 3 PTS indicators).
- ``rating_category`` (catalog row -> observation
  family via
  :func:`rating_category_to_observation_family`).
- ``unit`` (catalog row -> ``unit`` on the emitted
  observation; ``pts_score`` per the canonical catalog).
- ``raw_scale`` (catalog row -> ``scale`` on the emitted
  observation; ``ordinal`` per the canonical catalog).
- ``raw_column`` (the xlsx column ``PTS_A`` /
  ``PTS_H`` / ``PTS_S`` -> carried onto
  ``extension["pts_raw_column"]`` so audit code can
  re-derive the value from the legacy xlsx).
- ``higher_is_better`` (carried onto the observation
  ``extension`` for direction hints; the PTS score is
  ``higher_is_better=False`` because higher PTS = more
  terror = worse).
- ``normalized_scale_target`` (carried onto the
  observation ``extension``; ``"0-10"`` per the canonical
  catalog; the Stage 5 score module inverts the
  direction).
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import PTS_OBSERVATION_FAMILY

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime
# via the ``catalog_path`` kwarg without invalidating
# the descriptor's hash. The default path is the
# canonical checked-in catalog at
# ``src/leaders_db/ingest/catalogs/pts.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "pts.csv"
)


# Map legacy PTS ``rating_category`` values to the
# unified-source observation families. The catalog
# declares a single ``domestic_violence`` rating
# category; the mapping stays in a dict so future
# catalog additions can map new categories to new
# families without changing the transform layer.
# Unknown categories fall back to
# ``domestic_violence_country_year`` (the default PTS
# family) so the transform never silently drops
# observations.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "domestic_violence": PTS_OBSERVATION_FAMILY,
}


def rating_category_to_observation_family(
    rating_category: str,
) -> str:
    """Map a legacy catalog ``rating_category`` to a
    unified observation family.

    Unknown categories fall back to
    ``domestic_violence_country_year`` (the default PTS
    family) so a future catalog addition does not
    silently drop observations. The function is a pure
    string lookup so the transform layer can apply it
    per row without consulting the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        PTS_OBSERVATION_FAMILY,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the PTS indicator catalog.

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
    from leaders_db.ingest.pts_io import (
        load_indicator_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
