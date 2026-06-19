"""Compatibility facade — World Bank WDI Stage 2 (legacy module name).

This module is a thin compatibility facade. The real WDI Stage 2
implementation lives in :mod:`leaders_db.ingest.wdi` (and its
companion modules ``wdi_io``, ``wdi_db``, ``wdi_http``). The
implementation was renamed ``wdi`` after the 5-module split
(``wdi.py`` + ``wdi_io.py`` + ``wdi_db.py`` + ``wdi_http.py``); the
historical ``world_bank_wdi.py`` file used to be the umbrella
module name and is preserved here as a facade so external callers
(``from leaders_db.ingest.world_bank_wdi import …``) keep working
without a code change.

Re-exports the public surface of the real ``wdi`` orchestrator and
the constants / helpers used by external callers. The dispatch
table in :mod:`leaders_db.ingest` resolves ``"world_bank_wdi"`` to
``wdi.ingest_wdi`` directly; this facade does not participate in
the dispatch table.

Per AGENTS.md Always-On Rule #15, the attribution text returned by
:func:`attribution` is the exact wording from
``docs/source-attributions.md``; if the attributions doc is updated,
the same change must be made here in the same commit.
"""

from __future__ import annotations

# Re-export the canonical orchestrator + public surface from
# ``wdi``. This is the compatibility shim: legacy callers importing
# from ``leaders_db.ingest.world_bank_wdi`` continue to resolve to
# the real implementation without a code change. The dispatch table
# in ``leaders_db.ingest.__init__`` does NOT consume this facade; it
# imports ``wdi`` directly to keep the registry unambiguous.
from .wdi import (
    WDI_ATTRIBUTION,
    WDIIngestResult,
    attribution,
    ingest_wdi,
)
from .wdi_db import (
    register_wdi_source,
    write_wdi_observations,
    write_wdi_run_manifest,
)
from .wdi_io import (
    WDI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)

# Historical public aliases preserved for callers that imported
# the umbrella functions by their original name.
download_world_bank_wdi = ingest_wdi


def ingest_world_bank_wdi(*args, **kwargs):
    """Historical alias for :func:`leaders_db.ingest.wdi.ingest_wdi`."""
    return ingest_wdi(*args, **kwargs)


__all__ = [
    "WDI_ATTRIBUTION",
    "WDI_SOURCE_KEY",
    "IndicatorSpec",
    "WDIIngestResult",
    "attribution",
    "download_world_bank_wdi",
    "ingest_wdi",
    "ingest_world_bank_wdi",
    "load_indicator_catalog",
    "register_wdi_source",
    "write_wdi_observations",
    "write_wdi_run_manifest",
]
