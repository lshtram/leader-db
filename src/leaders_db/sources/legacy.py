"""Optional lazy seam for legacy ingest compatibility.

This module exists only to make the migration boundary explicit. Importing it
does not import :mod:`leaders_db.ingest`; callers must invoke a helper to cross
the boundary deliberately.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def get_legacy_stage2_adapters() -> Mapping[str, Callable[..., Any] | None]:
    """Return the legacy ``STAGE2_ADAPTERS`` table through a lazy import.

    This preserves access for diagnostics and migration planning without making
    ``leaders_db.sources`` depend on ``leaders_db.ingest`` at package import time.
    """
    from leaders_db.ingest import STAGE2_ADAPTERS

    return STAGE2_ADAPTERS


def run_legacy_source(_source_key: str, **_kwargs: Any) -> Any:
    """Placeholder for a future explicit compatibility wrapper."""
    raise NotImplementedError("Legacy execution bridge is not wired in Phase A")
