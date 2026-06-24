"""World Bank WDI bundle-path + catalog-resolution helpers.

Owns the small set of path / metadata / catalog-resolution
helpers shared across the unified WDI adapter's lifecycle
methods (:meth:`WDIAdapter.check_ready`,
:meth:`WDIAdapter.read_raw`, :meth:`WDIAdapter.transform`).

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter` so
the adapter class module stays focused on lifecycle wiring +
registration. The helpers are intentionally lightweight (no
business logic); they resolve filesystem paths under
``<raw_root>/world_bank_wdi/...`` and use the catalog
loader from ``leaders_db.ingest.wdi_io`` via the documented
lazy-import seam so the unified ``leaders_db.sources`` package
boundary is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import SourceIngestRequest

from ._descriptor import (
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_SOURCE_KEY,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/world_bank_wdi/`` bundle directory."""
    return Path(request.raw_root) / WORLD_BANK_WDI_SOURCE_KEY


def _cache_dir(request: SourceIngestRequest) -> Path:
    """Return the request-scoped cache root directory."""
    return _bundle_dir(request) / WORLD_BANK_WDI_CACHE_DIR_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / "metadata.json"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_indicator_codes_from_catalog(
    catalog_path: Path | None,
) -> tuple[str, ...]:
    """Return the catalog's ``raw_column`` codes via the catalog loader.

    The catalog is the single source of truth for which WDI
    indicators the unified adapter reads. Loading is delegated
    to :func:`leaders_db.ingest.wdi_io.load_indicator_catalog`
    so the catalog contract (14 indicators, the documented
    CSV format) is reused without duplication.
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest`` (docs/architecture/sources.md
    # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.wdi_io import (
        load_indicator_catalog as _compat_load_catalog,
    )

    specs = _compat_load_catalog(catalog_path=catalog_path)
    return tuple(spec.raw_column for spec in specs)


def _resolve_spec_by_variable_name(
    catalog_path: Path | None,
) -> dict[str, Any]:
    """Return ``{variable_name: IndicatorSpec}`` for the catalog.

    Used by the transform layer to map wide-format column
    names (catalog ``variable_name``) back to the spec
    carrying ``raw_column`` / ``rating_category`` / ``unit``.
    """
    # Lazy import: same package-boundary reason as
    # ``_resolve_indicator_codes_from_catalog``.
    from leaders_db.ingest.wdi_io import (
        load_indicator_catalog as _compat_load_catalog,
    )

    specs = _compat_load_catalog(catalog_path=catalog_path)
    return {spec.variable_name: spec for spec in specs}


__all__ = [
    "_bundle_dir",
    "_cache_dir",
    "_metadata_path",
    "_read_metadata_payload",
    "_resolve_indicator_codes_from_catalog",
    "_resolve_spec_by_variable_name",
]
