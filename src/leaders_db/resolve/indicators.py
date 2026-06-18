"""Stage 5 — indicator extraction (requirement §8, REQ-STAGE-006).

For each ruler-year, collect relevant country-year indicators from
``source_observations`` and arrange them into per-category indicator
bundles. The bundles are then handed to the per-category scoring modules
in :mod:`leaders_db.score`.

Indicator catalog lives at ``data/metadata/indicator_catalog.csv``.

Phase E implementation.
"""

from __future__ import annotations

from pathlib import Path


def extract_indicators(year: int) -> Path:
    """Extract per-ruler-year per-category indicator bundles for ``year``.

    Returns the absolute path to the indicator-bundles file (parquet or
    csv under ``data/interim/``).
    """
    raise NotImplementedError("extract_indicators is not implemented yet. Phase E.")


__all__ = ["extract_indicators"]
