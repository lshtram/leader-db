"""Ingest layer — Stage 0-2 of the pipeline.

- :mod:`source_availability` — Stage 0 (probe every priority source).
- :mod:`client_matrix`      — Stage 1 (load the client's xlsx as the reference).
- :mod:`external`           — generic helpers shared by Stage 2 adapters.
- One module per priority source for Stage 2 (Archigos, REIGN, …).

A Stage 2 adapter is implemented only after its source's
``source_vetting_report`` verdict is ``vetted_ok`` or
``vetted_with_caveats``. See Phase B in ``docs/workplan.md``.

The ``STAGE2_ADAPTERS`` dispatch table below maps each source key (as
used in the data lake folder names and the CLI ``--source`` flag) to
its Stage 2 orchestrator. Adding a new source means: write the adapter
module, then add an entry here. The CLI consumes the table directly so
there is no ``if/elif`` chain to maintain. Sources without an entry
fall through to the "not implemented yet" stub at the CLI boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import (
    pts,
    sipri_milex,
    sipri_yearbook_ch7,
    ucdp,
    undp_hdi,
    vdem,
    wdi,
    wgi,
)

#: Registry of implemented Stage 2 adapters.
#: The key is the source key (matches ``data/raw/<key>/`` and the CLI
#: ``--source`` flag). The value is the orchestrator function (signature:
#: ``(**kwargs) -> result``). ``None`` marks a source whose adapter is
#: not implemented yet; the CLI will print the standard stub message.
STAGE2_ADAPTERS: dict[str, Callable[..., Any] | None] = {
    # Implemented adapters
    "vdem": vdem.ingest_vdem,
    "world_bank_wdi": wdi.ingest_wdi,
    "world_bank_wgi": wgi.ingest_wgi,
    "ucdp": ucdp.ingest_ucdp,
    # Adapters gated on Phase B sign-off + Stage 2 build (Phase C,
    # second batch per docs/workplan.md "Phase C execution order").
    # Each entry becomes a real import as its adapter lands.
    "sipri_milex": sipri_milex.ingest_sipri_milex,
    "sipri_yearbook_ch7": sipri_yearbook_ch7.ingest_sipri_yearbook_ch7,
    "pts": pts.ingest_pts,
    "undp_hdi": undp_hdi.ingest_undp_hdi,
    "who_gho_api": None,
    "polity_v": None,
    "pwt": None,
    "archigos": None,
    "reign": None,
    "leader_survival": None,
    "transparency_cpi": None,
    "fas": None,
    "wikidata_heads_of_state_government": None,
    "wikipedia_search_extract": None,
    # User-managed (no code until files are placed)
    "freedom_house": None,
    "imf_weo": None,
    # Blocked / deferred (no code)
    "cow_mid": None,
    "cirights": None,
    "nti": None,
    "bti": None,
    "cia_world_leaders": None,
}


__all__: list[str] = ["STAGE2_ADAPTERS"]
