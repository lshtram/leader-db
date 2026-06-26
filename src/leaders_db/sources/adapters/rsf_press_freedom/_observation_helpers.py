"""Unified-source RSF observation construction helper
primitives.

Split out of
:mod:`._observation_builder` so the per-row
``build_observation`` constructor stays focused on
emitting one :class:`NormalizedObservation` per row
and the small helper functions live in a focused
sibling module. The helpers handle:

- :func:`_detect_schema_group` -- return the
  pre/post-2022 schema group flag for one year
  (1 = pre-2022; 2+ = post-2022).
- :func:`_resolve_value_type` -- return the canonical
  ``value_type`` for one indicator (the RSF score +
  5 components + rank all emit ``value_type="numeric"``).
- :func:`_default_asset_id_for_year` -- return the
  canonical per-year RSF raw asset id.
- :func:`_default_source_version` -- return the
  canonical RSF source version stamp.
- :func:`_raw_columns` -- return the canonical 2 base
  RSF raw column names (``score`` + ``rank``).
- :func:`_indicator_names` -- return the canonical 7
  RSF indicator names.
- :data:`RSF_PRESS_FREEDOM_TRANSFORM_NAME` -- module-
  local binding for the per-row transform name
  (mirrors the legacy ``read_rsf_press_freedom_csv``
  reader name so audit code can recover the
  transform-stage from the observation's
  ``transform_locator.transform_name``).
- :data:`RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022` /
  :data:`RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022` --
  the pre/post-2022 schema group constants
  preserved on every observation's
  ``extension["rsf_schema_group"]`` field.
- :data:`RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS` --
  the 5 component-context indicator raw_columns
  (2022+ files only).
"""

from __future__ import annotations

from ._constants import (
    RSF_PRESS_FREEDOM_DEFAULT_VERSION,
    RSF_PRESS_FREEDOM_INDICATOR_NAMES,
    RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
    RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE,
    _csv_asset_id_for_year,
)

# Module-local binding for the per-row transform name.
# The ``emit_rsf_press_freedom_observations`` helper
# resolves this constant from the transform module at
# import time; we hardcode it here for symmetry with the
# UCDP / V-Dem / WGI / CPI / PTS pattern (one module-
# local constant per source). The transform name
# mirrors the legacy ``read_rsf_press_freedom_csv``
# reader so audit code can recover the transform-stage
# from the observation's
# ``transform_locator.transform_name``.
RSF_PRESS_FREEDOM_TRANSFORM_NAME: str = (
    "read_rsf_press_freedom_csv"
)

# Pre/post-2022 schema group constants. The canonical
# RSF bundle metadata documents 6 schema groups
# (per
# ``data/raw/rsf_press_freedom/metadata.json``
# ``header_groups``): group 1 = 2002-2021 (16-col
# wide format, score + rank only); group 2 = 2022
# (22-col wide format, blank separator rows, score +
# rank + 5 component-context columns); group 3 = 2023
# (25-col wide format); group 4 = 2024 (26-col wide
# format); group 5 = 2025 (25-col wide format,
# cp1252 encoding); group 6 = 2026 (25-col wide
# format, cp1252 encoding). The unified transform
# collapses the post-2022 schema groups (2-6) into
# one ``RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022``
# constant; the pre-2022 group is
# ``RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022``.
RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022: int = 1
RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022: int = 2

# The 5 component-context indicator raw_columns (2022+
# files ONLY). Used by the per-row emission loop to
# detect the pre/post-2022 schema break and to attach
# the correct ``rsf_schema_group`` flag. Matches the
# legacy ``COMPONENT_LOGICAL_TO_HEADER`` map.
RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS: tuple[str, ...] = (
    "political_context",
    "economic_context",
    "legal_context",
    "social_context",
    "safety",
)


def _detect_schema_group(year: int) -> int:
    """Return the schema group flag for one year.

    The canonical RSF bundle metadata documents the
    per-year schema groups:

    - group 1: 2002-2021 (16-col wide format).
    - group 2: 2022 (22-col wide format; transition
      year with blank separator rows).
    - group 3: 2023 (25-col wide format).
    - group 4: 2024 (26-col wide format).
    - group 5: 2025 (25-col wide format, cp1252).
    - group 6: 2026 (25-col wide format, cp1252).

    The unified transform collapses groups 2-6 into
    one ``RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022``
    constant; group 1 is
    ``RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022``. The
    finer-grained per-year group flag is preserved on
    the per-observation ``extension["rsf_schema_group"]``
    field so audit code can recover the exact group
    per observation (the unified descriptor advertises
    the 2-group distinction for downstream
    normalization).
    """
    if year < 2022:
        return RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022
    return RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022


def _resolve_value_type(variable_name: str) -> str:
    """Return the canonical ``value_type`` for one
    indicator.

    The RSF score + 5 components are emitted as
    ``value_type="numeric"`` (``float`` normalized
    values); the rank is emitted as
    ``value_type="numeric"`` (``int`` normalized
    values). The descriptor advertises the
    7 indicator names via
    :data:`RSF_PRESS_FREEDOM_INDICATOR_NAMES`; the
    rank is identified by its ``raw_column``
    (``rank``) rather than its ``variable_name``.
    """
    return "numeric"


def _default_asset_id_for_year(year: int) -> str:
    """Return the canonical per-year RSF raw asset id.

    The unified RSF adapter reads ONE per-year CSV per
    request year, so the asset id embeds the year so
    audit code can group observations by per-year
    asset.
    """
    return _csv_asset_id_for_year(year)


def _default_source_version() -> str:
    """Return the canonical RSF source version stamp.

    The unified adapter hardcodes the canonical
    version ``"RSF Press Freedom Index 2026"``
    (matches the staged
    ``data/raw/rsf_press_freedom/metadata.json``
    ``source_version`` field's verbose acquisition-
    date stamp + the canonical attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not
    arbitrary metadata / request text.
    """
    return RSF_PRESS_FREEDOM_DEFAULT_VERSION


def _raw_columns() -> tuple[str, ...]:
    """Return the canonical 2 base RSF raw column
    names (``score`` + ``rank``). Exposed for symmetry
    with the WGI / V-Dem / CPI / UCDP / PTS pattern so
    the per-row emission loop can iterate the 2 base
    raw columns when needed.
    """
    return (
        RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE,
        RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
    )


def _indicator_names() -> tuple[str, ...]:
    """Return the canonical 7 RSF indicator names."""
    return RSF_PRESS_FREEDOM_INDICATOR_NAMES


__all__ = [
    "RSF_PRESS_FREEDOM_COMPONENT_RAW_COLUMNS",
    "RSF_PRESS_FREEDOM_SCHEMA_GROUP_POST_2022",
    "RSF_PRESS_FREEDOM_SCHEMA_GROUP_PRE_2022",
    "RSF_PRESS_FREEDOM_TRANSFORM_NAME",
    "_default_asset_id_for_year",
    "_default_source_version",
    "_detect_schema_group",
    "_indicator_names",
    "_raw_columns",
    "_resolve_value_type",
]
