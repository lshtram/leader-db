"""Compatibility facade — World Bank WGI Stage 2 (legacy module name).

This module is a thin compatibility facade. The real WGI Stage 2
implementation lives in :mod:`leaders_db.ingest.wgi` (and its
companion modules ``wgi_io``, ``wgi_xlsx``, ``wgi_db``,
``wgi_db_helpers``). The implementation was renamed ``wgi`` after
the 5-module split; the historical ``world_bank_wgi.py`` file used
to be the umbrella module name and is preserved here as a facade
so external callers (``from leaders_db.ingest.world_bank_wgi import
…``) keep working without a code change.

Re-exports the public surface of the real ``wgi`` orchestrator and
the constants / helpers used by external callers. The dispatch
table in :mod:`leaders_db.ingest` resolves ``"world_bank_wgi"`` to
``wgi.ingest_wgi`` directly; this facade does not participate in
the dispatch table.

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/sources/attributions.md``; if the attributions doc is updated,
the same change must be made here in the same commit.
"""

from __future__ import annotations

# Re-export the canonical orchestrator + public surface from
# ``wgi``. This is the compatibility shim: legacy callers importing
# from ``leaders_db.ingest.world_bank_wgi`` continue to resolve to
# the real implementation without a code change. The dispatch
# table in ``leaders_db.ingest.__init__`` does NOT consume this
# facade; it imports ``wgi`` directly to keep the registry
# unambiguous.
from .wgi import (
    WGI_ATTRIBUTION,
    WGIIngestResult,
    attribution,
    ingest_wgi,
)
from .wgi_db import (
    register_wgi_source,
    write_wgi_observations,
    write_wgi_run_manifest,
)
from .wgi_io import (
    WGI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)

# Historical public aliases preserved for callers that imported
# the umbrella functions by their original name.
download_world_bank_wgi = ingest_wgi


def ingest_world_bank_wgi(*args, **kwargs):
    """Historical alias for :func:`leaders_db.ingest.wgi.ingest_wgi`."""
    return ingest_wgi(*args, **kwargs)


__all__ = [
    "WGI_ATTRIBUTION",
    "WGI_SOURCE_KEY",
    "IndicatorSpec",
    "WGIIngestResult",
    "attribution",
    "download_world_bank_wgi",
    "ingest_wgi",
    "ingest_world_bank_wgi",
    "load_indicator_catalog",
    "register_wgi_source",
    "write_wgi_observations",
    "write_wgi_run_manifest",
]
