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
    archigos,
    bti,
    cirights,
    fas,
    pts,
    reign,
    rsf_press_freedom,
    sipri_milex,
    sipri_yearbook_ch7,
    transparency_cpi,
    ucdp,
    undp_hdi,
    vdem,
    wdi,
    wgi,
    who_gho_api,
    wikidata_heads_of_state_government,
    wikipedia_search_extract,
)

#: Registry of implemented Stage 2 adapters.
#: The key is the source key (matches ``data/raw/<key>/`` and the CLI
#: ``--source`` flag). The value is the orchestrator function (signature:
#: ``(**kwargs) -> result``). ``None`` marks a source whose adapter is
#: not implemented yet; the CLI will print the standard stub message.
STAGE2_ADAPTERS: dict[str, Callable[..., Any] | None] = {
    # Implemented adapters (vetted_ok or vetted_with_caveats, provenance
    # metadata present in data/raw/<source> or a documented alias folder;
    # some raw bundles remain user-managed while fixture/provenance tests
    # cover the adapter contract). Indicator catalog, orchestrator, tests,
    # and CLI dispatch are shipped for each non-None entry.
    "vdem": vdem.ingest_vdem,
    "world_bank_wdi": wdi.ingest_wdi,
    "world_bank_wgi": wgi.ingest_wgi,
    "ucdp": ucdp.ingest_ucdp,
    "sipri_milex": sipri_milex.ingest_sipri_milex,
    "sipri_yearbook_ch7": sipri_yearbook_ch7.ingest_sipri_yearbook_ch7,
    "pts": pts.ingest_pts,
    "undp_hdi": undp_hdi.ingest_undp_hdi,
    "who_gho_api": who_gho_api.ingest_who_gho_api,
    "archigos": archigos.ingest_archigos,
    "reign": reign.ingest_reign,
    "cirights": cirights.ingest_cirights,
    "transparency_cpi": transparency_cpi.ingest_transparency_cpi,
    "fas": fas.ingest_fas,
    "bti": bti.ingest_bti,
    "rsf_press_freedom": rsf_press_freedom.ingest_rsf_press_freedom,
    "wikidata_heads_of_state_government": (
        wikidata_heads_of_state_government.ingest_wikidata_heads_of_state_government
    ),
    "wikipedia_search_extract": (
        wikipedia_search_extract.ingest_wikipedia_search_extract
    ),
    # Blocked on raw bundle (raw file not staged locally; per Always-On
    # Rule #6 we never invent fixtures). Adapters will be implemented in
    # Phase C.10+ once the user stages ``p5v2018.sav`` / ``pwt100.xlsx``
    # at ``data/raw/<source>/`` with a ``metadata.json``.
    "polity_v": None,
    "pwt": None,
    # Demscore H-DATA v5 has a manual form/email/gender gate; raw file
    # is not staged in this environment (data/raw/leader_survival/ has
    # only a placeholder ``.gitkeep``). No code until the user stages
    # the data.
    "leader_survival": None,
    # User-managed (no code until files are placed)
    "freedom_house": None,
    "imf_weo": None,
    # Blocked / deferred (no code)
    "cow_mid": None,
    "nti": None,
    "cia_world_leaders": None,
}


__all__: list[str] = ["STAGE2_ADAPTERS"]
