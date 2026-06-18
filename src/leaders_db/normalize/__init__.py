"""Normalization helpers used by multiple stages.

Three submodules:

- :mod:`countries`   — ISO3 primary key, alias table, name normalization.
- :mod:`leader_names` — leader-name normalization for matching.
- :mod:`years`       — year normalization (smallint, ±1 fuzzy match).

The package-level exports here are stable; submodules may grow as the
pipeline fills in.
"""

from __future__ import annotations

from .countries import (
    COUNTRY_NAME_NORMALIZATION,
    normalize_country_name,
    normalize_iso3,
)

__all__ = [
    "COUNTRY_NAME_NORMALIZATION",
    "normalize_country_name",
    "normalize_iso3",
]
