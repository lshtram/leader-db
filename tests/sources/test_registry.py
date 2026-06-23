"""Phase B — Registry contract tests.

The new ``leaders_db.sources`` registry is the replacement for the
legacy ``STAGE2_ADAPTERS`` table (SRC-REG-001, SRC-REG-002,
SRC-REG-003). Phase A ships a passive ``InMemorySourceRegistry`` that
must satisfy the contract below:

- ``register(adapter)`` stores an adapter under
  ``adapter.descriptor.source_id.slug``.
- ``list_descriptors()`` returns descriptors in deterministic order
  (sorted by slug).
- ``get_descriptor(source_id)`` returns the matching descriptor or
  raises ``KeyError``.
- ``get_adapter(source_id)`` returns the matching adapter or raises
  ``KeyError``.
- Duplicate ``register`` calls raise ``ValueError`` (the contract
  Phase A chose and documented in this file; downstream test-builder
  may revisit if the architecture is later changed to "last write
  wins").

The runtime registry/runner composition seam is exercised by
``test_runner.py``; this file is the dataclass / Protocol surface.

PASS-ELIGIBLE rationale
-----------------------
All tests in this file are PASS-ELIGIBLE: the in-memory registry
implements the full ``SRC-REG-004`` contract, including duplicate-slug
rejection via ``ValueError``. The duplicate-rejection test
(``test_register_rejects_duplicate_slug_with_value_error``) is the
registry-side completion-defining test and now passes — the registry
rejects duplicate ``SourceId.slug`` registrations rather than silently
overwriting the previous adapter.
"""
from __future__ import annotations

from collections.abc import Iterable

import pytest

# ---------------------------------------------------------------------------
# Test fixtures: a minimal fake adapter + descriptor
# ---------------------------------------------------------------------------


def _fake_descriptor(slug: str = "fake") -> SourceDescriptor:  # type: ignore[no-untyped-def]  # noqa: F821
    """Build a minimal valid ``SourceDescriptor`` for contract tests."""
    from leaders_db.sources import (
        CoverageHint,
        SourceDescriptor,
        SourceId,
    )

    return SourceDescriptor(
        source_id=SourceId(slug=slug),
        display_name=f"Fake {slug}",
        source_type="dataset",
        supported_observation_families=("test_family",),
        default_version="v1",
        homepage_url=None,
        attribution_key=slug,
        coverage_hint=CoverageHint(),
        requires_manual_approval=False,
        requires_network=False,
    )


class _FakeAdapter:
    """Minimal ``SourceAdapter`` implementation with no real behavior.

    The class exposes the three required methods so ``isinstance``
    against the ``SourceAdapter`` Protocol succeeds, and it records the
    order in which the runner invoked them so dispatch tests can
    assert lifecycle ordering.
    """

    def __init__(self, slug: str = "fake") -> None:
        self.descriptor = _fake_descriptor(slug)
        self.calls: list[str] = []

    def check_ready(self, request) -> ReadinessResult:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import ReadinessResult

        self.calls.append("check_ready")
        return ReadinessResult(ready=True)

    def read_raw(self, request) -> RawReadResult:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import RawReadResult

        self.calls.append("read_raw")
        return RawReadResult(source_id=request.source_id)

    def transform(self, request, raw) -> Iterable[NormalizedObservation]:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import NormalizedObservation

        self.calls.append("transform")
        return iter(
            (
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=f"{request.source_id.slug}:1",
                    observation_family="test_family",
                    indicator_code="test_ind",
                    value=1,
                    value_type="numeric",
                    year=2023,
                    country_code="USA",
                    country_name=None,
                    leader_id=None,
                    leader_name=None,
                    unit=None,
                    scale=None,
                    source_version=None,
                    raw_locator=__import__(
                        "leaders_db.sources", fromlist=["RawLocator"],
                    ).RawLocator(asset_id="asset-1"),
                    transform_locator=__import__(
                        "leaders_db.sources", fromlist=["TransformLocator"],
                    ).TransformLocator(),
                ),
            )
        )


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


def test_in_memory_registry_starts_empty() -> None:
    """A fresh registry exposes no descriptors.

    Phase A: no real adapters are auto-registered; the registry must
    start empty so test code controls exactly what is registered.
    """
    from leaders_db.sources import InMemorySourceRegistry

    registry = InMemorySourceRegistry()
    assert registry.list_descriptors() == ()


def test_register_then_get_returns_same_adapter_instance() -> None:
    """``register`` stores the adapter and ``get_adapter`` returns it by slug."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    adapter = _FakeAdapter(slug="alpha")
    registry.register(adapter)

    assert registry.get_adapter(SourceId(slug="alpha")) is adapter


def test_register_then_get_descriptor_returns_descriptor() -> None:
    """``get_descriptor`` returns the descriptor attached to the adapter."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    adapter = _FakeAdapter(slug="beta")
    registry.register(adapter)

    descriptor = registry.get_descriptor(SourceId(slug="beta"))
    assert descriptor is adapter.descriptor
    assert descriptor.source_id.slug == "beta"


def test_list_descriptors_returns_sorted_by_slug() -> None:
    """``list_descriptors`` returns descriptors in deterministic slug order.

    The contract is "sorted by slug ascending" so callers can iterate
    without worrying about insertion order.
    """
    from leaders_db.sources import InMemorySourceRegistry

    registry = InMemorySourceRegistry()
    for slug in ("zeta", "alpha", "mu", "beta"):
        registry.register(_FakeAdapter(slug=slug))

    slugs = tuple(d.source_id.slug for d in registry.list_descriptors())
    assert slugs == ("alpha", "beta", "mu", "zeta")


def test_list_descriptors_returns_empty_tuple_when_no_adapters() -> None:
    """An empty registry returns an empty tuple, not None."""
    from leaders_db.sources import InMemorySourceRegistry

    registry = InMemorySourceRegistry()
    assert registry.list_descriptors() == ()


def test_get_descriptor_raises_key_error_for_unknown_slug() -> None:
    """Unknown ``SourceId`` raises ``KeyError`` with the slug in the message."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    with pytest.raises(KeyError) as exc_info:
        registry.get_descriptor(SourceId(slug="missing"))

    # The error message names the slug so it is actionable in CLI logs.
    assert "missing" in str(exc_info.value)


def test_get_adapter_raises_key_error_for_unknown_slug() -> None:
    """Unknown ``SourceId`` raises ``KeyError`` from ``get_adapter``."""
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    with pytest.raises(KeyError) as exc_info:
        registry.get_adapter(SourceId(slug="ghost"))

    assert "ghost" in str(exc_info.value)


def test_register_rejects_duplicate_slug_with_value_error() -> None:
    """``register`` rejects duplicate slugs with ``ValueError``.

    Per ``SRC-REG-004`` (docs/requirements/sources.md §9 and
    docs/architecture/sources.md §10.1), registering the same
    ``SourceId.slug`` twice is a programming error and MUST raise
    ``ValueError`` at registration time rather than silently
    overwriting the previous adapter. ``ValueError`` surfaces the
    duplicate wiring loudly so the caller fixes it before the runner
    dispatches a request.

    PASS-ELIGIBLE: ``InMemorySourceRegistry.register`` now implements
    the duplicate-rejection contract, so the assertion passes against
    the current registry. The test remains the registry-side
    completion-defining test — it will fail loudly if a future
    refactor weakens ``register`` back to "last write wins".
    """
    from leaders_db.sources import InMemorySourceRegistry

    registry = InMemorySourceRegistry()
    registry.register(_FakeAdapter(slug="dup"))
    with pytest.raises(ValueError) as exc_info:
        registry.register(_FakeAdapter(slug="dup"))

    # Error names the slug so the message is actionable.
    assert "dup" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_in_memory_registry_satisfies_registry_protocol() -> None:
    """The Phase A registry class satisfies the ``SourceRegistry`` Protocol.

    ``isinstance`` against the runtime-checkable Protocol verifies the
    full surface (``list_descriptors``, ``register``, ``get_descriptor``,
    ``get_adapter``) is implemented.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceRegistry

    registry = InMemorySourceRegistry()
    assert isinstance(registry, SourceRegistry)


def test_fake_adapter_satisfies_adapter_protocol() -> None:
    """A minimal adapter implementation satisfies the ``SourceAdapter`` Protocol.

    The Protocol is ``runtime_checkable``; the test confirms the three
    required methods (``check_ready``, ``read_raw``, ``transform``) plus
    the ``descriptor`` attribute are present and callable.
    """
    from leaders_db.sources import SourceAdapter

    adapter = _FakeAdapter(slug="proto")
    assert isinstance(adapter, SourceAdapter)


def test_fake_adapter_missing_transform_fails_protocol_check() -> None:
    """An object that lacks ``transform`` does NOT satisfy ``SourceAdapter``.

    Defense in depth: the protocol check catches missing methods at
    registration time. The test builds a deliberately incomplete
    adapter and asserts ``isinstance`` rejects it.
    """
    from leaders_db.sources import SourceAdapter

    class _IncompleteAdapter:
        descriptor = _fake_descriptor("incomplete")

        def check_ready(self, request):  # type: ignore[no-untyped-def]
            return None

        def read_raw(self, request):  # type: ignore[no-untyped-def]
            return None

        # NOTE: ``transform`` is intentionally absent.

    assert not isinstance(_IncompleteAdapter(), SourceAdapter)


# ---------------------------------------------------------------------------
# Defaults / static assertions
# ---------------------------------------------------------------------------


def test_fresh_registry_does_not_register_client_existing() -> None:
    """A fresh registry does not auto-register ``client_existing`` as evidence.

    Per SRC-DEFAULT-007 / docs/architecture/sources.md §7.4, the client
    matrix is validation-only and must never be evidence. The contract
    here is that the Phase A registry does not auto-register it.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    with pytest.raises(KeyError):
        registry.get_adapter(SourceId(slug="client_existing"))


def test_fresh_registry_does_not_register_legacy_adapters() -> None:
    """A fresh registry does not auto-register legacy ``STAGE2_ADAPTERS``
    entries (PWT, V-Dem, etc.).

    Per docs/architecture/sources.md §10.1, the new registry starts
    empty and never auto-imports legacy adapters. This guards against
    a regression where Phase C accidentally wires the legacy table
    into the new registry at module import time.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceId

    registry = InMemorySourceRegistry()
    for slug in (
        "vdem",
        "world_bank_wdi",
        "world_bank_wgi",
        "ucdp",
        "pts",
        "pwt",
        "archigos",
        "reign",
    ):
        with pytest.raises(KeyError):
            registry.get_adapter(SourceId(slug=slug))


__all__ = [
    "_FakeAdapter",
    "_fake_descriptor",
    "test_fake_adapter_missing_transform_fails_protocol_check",
    "test_fake_adapter_satisfies_adapter_protocol",
    "test_fresh_registry_does_not_register_client_existing",
    "test_fresh_registry_does_not_register_legacy_adapters",
    "test_get_adapter_raises_key_error_for_unknown_slug",
    "test_get_descriptor_raises_key_error_for_unknown_slug",
    "test_in_memory_registry_satisfies_registry_protocol",
    "test_in_memory_registry_starts_empty",
    "test_list_descriptors_returns_empty_tuple_when_no_adapters",
    "test_list_descriptors_returns_sorted_by_slug",
    "test_register_rejects_duplicate_slug_with_value_error",
    "test_register_then_get_descriptor_returns_descriptor",
    "test_register_then_get_returns_same_adapter_instance",
]
