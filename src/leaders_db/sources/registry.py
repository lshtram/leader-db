"""Registry seams for the unified source subsystem."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, runtime_checkable

from .contracts import SourceAdapter, SourceDescriptor, SourceId

_DEFAULT_SOURCE_REGISTRARS: tuple[tuple[str, str], ...] = (
    ("leaders_db.sources.adapters.archigos", "register_archigos"),
    ("leaders_db.sources.adapters.bti", "register_bti"),
    ("leaders_db.sources.adapters.cirights", "register_cirights"),
    ("leaders_db.sources.adapters.ctbto_treaty_status", "register_ctbto_treaty_status"),
    ("leaders_db.sources.adapters.eiu_democracy_index", "register_eiu_democracy_index"),
    ("leaders_db.sources.adapters.fas", "register_fas"),
    ("leaders_db.sources.adapters.freedom_house", "register_freedom_house"),
    ("leaders_db.sources.adapters.iaea_safeguards", "register_iaea_safeguards"),
    ("leaders_db.sources.adapters.maddison_project", "register_maddison_project"),
    ("leaders_db.sources.adapters.polity_v", "register_polity_v"),
    ("leaders_db.sources.adapters.pts", "register_pts"),
    ("leaders_db.sources.adapters.pwt", "register_pwt"),
    ("leaders_db.sources.adapters.reign", "register_reign"),
    ("leaders_db.sources.adapters.rsf_press_freedom", "register_rsf_press_freedom"),
    ("leaders_db.sources.adapters.sipri_arms_transfers", "register_sipri_arms_transfers"),
    ("leaders_db.sources.adapters.sipri_milex", "register_sipri_milex"),
    ("leaders_db.sources.adapters.sipri_yearbook_ch7", "register_sipri_yearbook_ch7"),
    ("leaders_db.sources.adapters.transparency_cpi", "register_transparency_cpi"),
    ("leaders_db.sources.adapters.ucdp", "register_ucdp"),
    ("leaders_db.sources.adapters.un_snaama", "register_un_snaama"),
    ("leaders_db.sources.adapters.undp_hdi", "register_undp_hdi"),
    ("leaders_db.sources.adapters.vdem", "register_vdem"),
    ("leaders_db.sources.adapters.who_gho_api", "register_who_gho_api"),
    (
        "leaders_db.sources.adapters.wikidata_heads_of_state_government",
        "register_wikidata_heads_of_state_government",
    ),
    ("leaders_db.sources.adapters.wikipedia_search_extract", "register_wikipedia_search_extract"),
    (
        "leaders_db.sources.adapters.world_bank_poverty_inequality_platform",
        "register_world_bank_poverty_inequality_platform",
    ),
    ("leaders_db.sources.adapters.world_bank_wdi", "register_world_bank_wdi"),
    ("leaders_db.sources.adapters.world_bank_wgi", "register_world_bank_wgi"),
)


@runtime_checkable
class SourceRegistry(Protocol):
    """Registry interface used by future CLI and runner dispatch paths."""

    def list_descriptors(self) -> tuple[SourceDescriptor, ...]:
        """Return known source descriptors in deterministic order."""
        ...

    def register(self, adapter: SourceAdapter) -> None:
        """Register an adapter under ``adapter.descriptor.source_id``."""
        ...

    def get_descriptor(self, source_id: SourceId) -> SourceDescriptor:
        """Return the descriptor for ``source_id`` or raise ``KeyError``."""
        ...

    def get_adapter(self, source_id: SourceId) -> SourceAdapter:
        """Return the adapter for ``source_id`` or raise ``KeyError``."""
        ...


class InMemorySourceRegistry:
    """Passive in-memory registry for contract tests and future composition.

    The registry starts empty by design. No legacy adapters and no real new
    adapters are auto-registered at import time.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def list_descriptors(self) -> tuple[SourceDescriptor, ...]:
        """Return registered descriptors sorted by source slug."""
        return tuple(
            adapter.descriptor
            for _, adapter in sorted(
                self._adapters.items(),
                key=lambda item: item[0],
            )
        )

    def register(self, adapter: SourceAdapter) -> None:
        """Register ``adapter`` without invoking source lifecycle methods.

        Per ``SRC-REG-004`` (docs/requirements/sources.md §9 and
        docs/architecture/sources.md §10.1), registering the same
        ``SourceId.slug`` twice is a programming error and MUST raise
        ``ValueError`` rather than silently overwriting the previous
        adapter. The error message names the offending slug so the
        caller can fix the wiring before the runner dispatches a
        request.
        """
        slug = adapter.descriptor.source_id.slug
        if slug in self._adapters:
            raise ValueError(
                f"Source adapter for slug {slug!r} is already "
                f"registered; duplicate registration is a programming "
                f"error and must be fixed at the call site"
            )
        self._adapters[slug] = adapter

    def get_descriptor(self, source_id: SourceId) -> SourceDescriptor:
        """Return the descriptor for ``source_id`` or raise ``KeyError``."""
        return self.get_adapter(source_id).descriptor

    def get_adapter(self, source_id: SourceId) -> SourceAdapter:
        """Return the adapter for ``source_id`` or raise ``KeyError``."""
        try:
            return self._adapters[source_id.slug]
        except KeyError as exc:
            raise KeyError(f"No source adapter registered for {source_id.slug!r}") from exc


def build_default_source_registry() -> InMemorySourceRegistry:
    """Compose the production clean-source registry.

    The registry remains passive at import time: adapters are imported and
    registered only when this composition helper is called. This keeps the
    clean ``leaders_db.sources`` system separate from legacy Stage 2 dispatch.
    """
    registry = InMemorySourceRegistry()
    for module_name, registrar_name in _DEFAULT_SOURCE_REGISTRARS:
        registrar = getattr(import_module(module_name), registrar_name)
        registrar(registry)
    return registry
