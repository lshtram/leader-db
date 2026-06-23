"""Shared-protocol adapter registry for protocol-based Stage 2 sources.

This module holds an in-memory registry keyed by source key (for example,
``pwt``) and executes the shared ``SourceAdapter`` contract in order:
``check_ready -> read -> transform -> write``.

The registry is intentionally **opt-in**:

- Per-source protocol packages call :func:`register` at import/module setup to
  register their adapter.
- Callers must dispatch through :func:`ingest_source` with a registered
  adapter key.
- The broader CLI dispatch remains in ``STAGE2_ADAPTERS`` and stays the
  default execution seam.

This distinction is intentional; it keeps Stage 2 CLI behavior stable
while allowing protocol-based slices to test the shared seam independently.
"""

from __future__ import annotations

from .interfaces import (
    IngestRequest,
    IngestResult,
    SourceAdapter,
)

# Module-level adapter registry. ``register`` / ``unregister`` /
# ``get`` / ``has`` mutate this dict; ``ingest_source`` reads it
# to dispatch a request.
_REGISTRY: dict[str, SourceAdapter] = {}


def register(source_key: str, adapter: SourceAdapter) -> None:
    """Register ``adapter`` under ``source_key``.

    The registry is a plain in-memory dict. Tests call this
    directly. In protocol-based production paths, source packages are
    expected to call :func:`register` during module import (typically in
    ``__init__.py``).
    """
    _REGISTRY[source_key] = adapter


def unregister(source_key: str) -> None:
    """Remove the adapter registered under ``source_key``.

    Silent no-op if the key is not registered (matches the
    ``MutableMapping.pop`` default so tests can clean up after
    themselves without try/except).
    """
    _REGISTRY.pop(source_key, None)


def has(source_key: str) -> bool:
    """Return True iff ``source_key`` is currently registered."""
    return source_key in _REGISTRY


def get(source_key: str) -> SourceAdapter | None:
    """Return the adapter registered under ``source_key`` (or
    ``None`` if no adapter is registered).
    """
    return _REGISTRY.get(source_key)


def registered_source_keys() -> tuple[str, ...]:
    """Return the currently-registered source keys (sorted).

    Tests use this to assert that the registry surface is what
    they expect after wiring / unwiring adapters in fixtures.
    """
    return tuple(sorted(_REGISTRY.keys()))


def ingest_source(request: IngestRequest) -> IngestResult:
    """Drive ``check_ready -> read -> transform -> write`` on the
    adapter registered under ``request.source_key``.

    Contract:

    - If no adapter is registered under ``request.source_key``,
      raise :class:`KeyError` naming the missing key.
    - If :meth:`SourceAdapter.check_ready` returns ``ready=False``,
      raise :class:`RuntimeError` that names the source and the
      blocker reason. ``read()`` is NEVER called in this branch.
    - Otherwise call ``read -> transform -> write`` in order and
      return the :class:`IngestResult` from ``write``.
    """
    adapter = _REGISTRY.get(request.source_key)
    if adapter is None:
        raise KeyError(
            f"No adapter registered for source_key="
            f"{request.source_key!r}; known: "
            f"{sorted(_REGISTRY.keys())}"
        )
    readiness = adapter.check_ready(request)
    if not readiness.ready:
        raise RuntimeError(
            f"Source {request.source_key!r} is not ready: "
            f"{readiness.blocker or 'no blocker given'}"
        )
    bundle = adapter.read(request)
    frame = adapter.transform(bundle, request)
    return adapter.write(frame, request)


__all__ = [
    "get",
    "has",
    "ingest_source",
    "register",
    "registered_source_keys",
    "unregister",
]
