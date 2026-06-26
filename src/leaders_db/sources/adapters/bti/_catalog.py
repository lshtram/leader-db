"""Unified-source Bertelsmann Transformation Index (BTI) catalog helpers.

This module owns the small helpers that map the legacy BTI indicator
catalog (``src/leaders_db/ingest/catalogs/bti.csv``) onto the
unified-source observation-emission contract. The catalog is reused
verbatim from the legacy Stage 2 path so the unified adapter does not
duplicate the indicator metadata; the lazy import keeps the
``leaders_db.sources`` package boundary intact (SRC-MIG-007 +
``docs/architecture/sources.md`` §10.1).

Catalog semantics
-----------------

The canonical BTI catalog carries TWELVE indicator rows across THREE
rating categories per ``src/leaders_db/ingest/catalogs/bti.csv``:

- ``effectiveness`` (2 indicators):
  ``bti_governance_index`` +
  ``bti_governance_performance``.
- ``political_freedom`` (7 indicators):
  ``bti_status_index`` + ``bti_democracy_status`` + Q1-Q5
  political transformation questions.
- ``economic_wellbeing`` (3 indicators): Q6/Q7/Q11 economic
  transformation questions.

The unified adapter maps each rating category to a distinct
unified observation family:

- ``effectiveness`` -> ``effectiveness_country_year``
- ``political_freedom`` -> ``political_freedom_country_year``
- ``economic_wellbeing`` -> ``economic_wellbeing_country_year``

The mapping lives in :func:`rating_category_to_observation_family`
so the transform layer can apply it per row. Unknown rating
categories fall back to ``effectiveness_country_year`` (the
default BTI family) so a future catalog addition does not silently
drop observations.

``IndicatorSpec`` fields used by the unified transform:

- ``variable_name`` (catalog row -> ``indicator_code`` on the
  emitted observation; the unified adapter narrows to the 12 BTI
  indicators).
- ``category`` (catalog row -> observation family via
  :func:`rating_category_to_observation_family`; note the BTI catalog
  uses ``category`` not ``rating_category`` as the column name --
  per the catalog's own header -- but the legacy
  :class:`IndicatorSpec` exposes the field as ``category`` so the
  unified transform consumes it under that attribute name).
- ``unit`` (catalog row -> ``unit`` on the emitted observation;
  ``bti_score`` per the canonical catalog).
- ``raw_scale`` (catalog row -> ``scale`` on the emitted
  observation; ``1-10`` per the canonical catalog).
- ``raw_column`` (the xlsx column name verbatim -- the
  whitespace-padded BTI xlsx header; the legacy reader matches it
  via ``str(cell).strip()`` so trailing whitespace does not break
  the match -- carried onto
  ``extension["bti_raw_column"]`` so audit code can re-derive the
  value from the legacy xlsx).
- ``higher_is_better`` (carried onto the observation ``extension``
  for direction hints; the BTI 1-10 score is
  ``higher_is_better=True`` because 10 = best per the canonical
  catalog).
- ``normalized_scale_target`` (carried onto the observation
  ``extension``; ``"0-10"`` per the canonical catalog; the Stage 5
  score module preserves the raw 1-10 value verbatim and applies
  the linear 1->1, 10->10 mapping).
"""

from __future__ import annotations

from pathlib import Path

from ._descriptor import BTI_OBSERVATION_FAMILY_EFFECTIVENESS

# Legacy catalog path. Lives here (rather than in
# :mod:`_descriptor`) so the path can change at runtime via the
# ``catalog_path`` kwarg without invalidating the descriptor's hash.
# The default path is the canonical checked-in catalog at
# ``src/leaders_db/ingest/catalogs/bti.csv``.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "ingest"
    / "catalogs"
    / "bti.csv"
)


# Map legacy BTI ``category`` values to the unified-source
# observation families. The catalog declares three category values
# (``effectiveness`` / ``political_freedom`` / ``economic_wellbeing``);
# the mapping stays in a dict so future catalog additions can map new
# categories to new families without changing the transform layer.
# Unknown categories fall back to
# ``effectiveness_country_year`` (the default BTI family) so the
# transform never silently drops observations.
_RATING_CATEGORY_TO_FAMILY: dict[str, str] = {
    "effectiveness": BTI_OBSERVATION_FAMILY_EFFECTIVENESS,
    "political_freedom": "political_freedom_country_year",
    "economic_wellbeing": "economic_wellbeing_country_year",
}


def rating_category_to_observation_family(
    rating_category: str,
) -> str:
    """Map a legacy catalog ``category`` to a unified
    observation family.

    Unknown categories fall back to
    ``effectiveness_country_year`` (the default BTI
    family) so a future catalog addition does not
    silently drop observations. The function is a pure
    string lookup so the transform layer can apply it
    per row without consulting the descriptor.
    """
    return _RATING_CATEGORY_TO_FAMILY.get(
        rating_category,
        BTI_OBSERVATION_FAMILY_EFFECTIVENESS,
    )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[object]:
    """Lazy-load the BTI indicator catalog.

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
    from leaders_db.ingest.bti_io import (
        load_indicator_catalog as _legacy_load,
    )

    return list(_legacy_load(catalog_path=catalog_path))


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "load_indicator_catalog",
    "rating_category_to_observation_family",
]
