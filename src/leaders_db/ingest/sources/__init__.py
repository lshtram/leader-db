"""Stage 2 -- per-source adapter packages.

Per the shared-interface plan in ``docs/sources/ingestion-plan.md``
each Stage 2 source lives in its own subpackage:

    leaders_db.ingest.sources.<source_key>/__init__.py
    leaders_db.ingest.sources.<source_key>.adapter
    leaders_db.ingest.sources.<source_key>.reader
    leaders_db.ingest.sources.<source_key>.transform

The first concrete proof of the new layout is ``pwt``
(Phase B Increment B). Subsequent slices backfill ``polity_v``,
``leader_survival``, ``freedom_house``, etc.

The legacy flat adapters (``leaders_db.ingest.vdem``,
``leaders_db.ingest.wdi``, ...) are not migrated in this slice;
their ``STAGE2_ADAPTERS`` entries keep pointing at the legacy
orchestrator functions.

The :data:`STAGE2_SOURCE_PACKAGES` tuple enumerates the per-
source package keys that have been implemented under the new
layout (currently just ``pwt``). The
:data:`leaders_db.ingest.STAGE2_ADAPTERS` dispatch entry for each
key delegates to the package's public orchestrator.
"""

from __future__ import annotations

# Import the per-source subpackages so ``leaders_db.ingest.sources.pwt``
# resolves through the namespace. ``pwt`` is the first concrete proof of
# the new layout (Phase B Increment B); subsequent slices backfill the
# other per-source packages.
from . import pwt  # noqa: F401  (re-exported through the namespace)

#: Tuple of per-source package keys that have been implemented
#: under the new shared-interface layout. Used by the package
#: discovery helpers (not yet used by the registry runner, which
#: dispatches through ``STAGE2_ADAPTERS`` directly).
STAGE2_SOURCE_PACKAGES: tuple[str, ...] = ("pwt",)


__all__ = ["STAGE2_SOURCE_PACKAGES"]
