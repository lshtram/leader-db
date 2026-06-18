"""Vertical slice 2023 — named experimental Stage 3-15 mini-orchestrator.

This package implements the deliberately thin 2023 vertical slice defined in
``docs/architecture/vertical-slice-2023.md``. It is **not** the real
Stage 3-15 pipeline. It proves that the current Stage 2 source adapters can
feed the database, a tiny ruler-year layer, provisional score rows,
validation rows, and auditable output files for the 2023 client matrix on
a handful of countries and two scoring categories.

The single production seam is :mod:`leaders_db.vertical_slice.slice_2023`,
which exposes:

- :class:`slice_2023.ClientSliceRow`
- :class:`slice_2023.VerticalSliceResult`
- :func:`slice_2023.load_vertical_slice_client_rows`
- :func:`slice_2023.run_vertical_slice_2023`
"""

from __future__ import annotations

from .slice_2023 import (
    ClientSliceRow,
    VerticalSliceResult,
    load_vertical_slice_client_rows,
    run_vertical_slice_2023,
)

__all__ = [
    "ClientSliceRow",
    "VerticalSliceResult",
    "load_vertical_slice_client_rows",
    "run_vertical_slice_2023",
]
