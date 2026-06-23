"""Registry seams for the unified source subsystem."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import SourceAdapter, SourceDescriptor, SourceId


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
