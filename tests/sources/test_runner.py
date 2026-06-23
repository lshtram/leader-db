"""Phase B/C — Runner dispatch seam tests.

The ``SourceIngestRunner`` is the lifecycle orchestrator for the unified
source subsystem. The contract covered by this file:

- The runner exposes the registry seam it dispatches through
  (``registry`` attribute, identity-equal to the constructor argument).
- ``run(request)`` calls lifecycle methods in the documented order:
  ``check_ready -> read_raw -> transform`` (validate/persist/manifest
  are runner-owned; the adapter does not implement them).
- ``run(request)`` returns a ``SourceIngestResult`` carrying the
  ``ReadinessResult``, ``ValidationResult``, observations, and warnings
  produced during the run (``manifest`` is ``None`` because shared
  persistence and manifest generation are deferred to a later phase).
- The runner routes requests through the registry, not through the
  legacy ``STAGE2_ADAPTERS`` table.

All four tests in this file are PASS-ELIGIBLE: the runner is wired
through the new registry, the lifecycle ordering is enforced, and
legacy dispatch is rejected.
"""
from __future__ import annotations

from collections.abc import Iterable

import pytest

# ---------------------------------------------------------------------------
# Fake adapter + descriptor (kept inline to make the dispatch test self
# contained; the registry tests reuse a similar pattern).
# ---------------------------------------------------------------------------


def _descriptor(slug: str) -> SourceDescriptor:  # type: ignore[no-untyped-def]  # noqa: F821
    from leaders_db.sources import CoverageHint, SourceDescriptor, SourceId

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


class _RecordingFakeAdapter:
    """Adapter that records lifecycle calls in order.

    Each method appends a tag to ``self.calls`` so the runner test can
    assert the order is ``check_ready -> read_raw -> transform``. The
    three required methods are implemented; ``validate``, ``persist``,
    and ``manifest`` are intentionally NOT on the adapter — they are
    runner-owned per the architecture contract.
    """

    def __init__(self, slug: str = "fake") -> None:
        self.descriptor = _descriptor(slug)
        self.calls: list[str] = []
        self.last_request: object = None
        self.last_raw: object = None

    def check_ready(self, request) -> ReadinessResult:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import ReadinessResult

        self.last_request = request
        self.calls.append("check_ready")
        return ReadinessResult(ready=True)

    def read_raw(self, request) -> RawReadResult:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import RawReadResult

        self.last_request = request
        self.calls.append("read_raw")
        return RawReadResult(source_id=request.source_id)

    def transform(self, request, raw) -> Iterable[NormalizedObservation]:  # type: ignore[no-untyped-def]  # noqa: F821
        from leaders_db.sources import NormalizedObservation, RawLocator, TransformLocator

        self.last_request = request
        self.last_raw = raw
        self.calls.append("transform")
        return iter(
            (
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id="obs-1",
                    observation_family="test_family",
                    indicator_code="test_ind",
                    value=42,
                    value_type="numeric",
                    year=2023,
                    country_code="USA",
                    country_name=None,
                    leader_id=None,
                    leader_name=None,
                    unit=None,
                    scale=None,
                    source_version=None,
                    raw_locator=RawLocator(asset_id="asset-1"),
                    transform_locator=TransformLocator(),
                ),
            )
        )


# ---------------------------------------------------------------------------
# Registry seam exposure
# ---------------------------------------------------------------------------


def test_runner_exposes_registry_seam() -> None:
    """``SourceIngestRunner.registry`` returns the registry passed in.

    The runner must route dispatch through the registry seam (not the
    legacy ``STAGE2_ADAPTERS`` table). The test asserts the registry
    attribute is exposed and identity-equal to the constructor argument.
    """
    from leaders_db.sources import InMemorySourceRegistry, SourceIngestRunner

    registry = InMemorySourceRegistry()
    runner = SourceIngestRunner(registry=registry)
    assert runner.registry is registry


# ---------------------------------------------------------------------------
# Runtime boundary: the runner drives the adapter lifecycle in order
# ---------------------------------------------------------------------------


def test_runner_run_dispatches_lifecycle_in_order() -> None:
    """``runner.run(request)`` drives the adapter through
    ``check_ready -> read_raw -> transform`` in fixed order.

    The runner is wired through the new ``SourceRegistry`` (no legacy
    dispatch) and returns a ``SourceIngestResult`` carrying the
    adapter-produced ``ReadinessResult``, the materialised
    ``NormalizedObservation`` tuple, and a convenience
    ``ValidationResult``. The test asserts both the lifecycle order
    and the result envelope.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestResult,
        SourceIngestRunner,
    )

    registry = InMemorySourceRegistry()
    adapter = _RecordingFakeAdapter(slug="dispatch")
    registry.register(adapter)

    runner = SourceIngestRunner(registry=registry)
    request = SourceIngestRequest(source_id=SourceId(slug="dispatch"))

    result = runner.run(request)

    # Lifecycle ordering: the runner must drive the adapter through the
    # three documented methods in this exact order.
    assert adapter.calls == ["check_ready", "read_raw", "transform"], (
        f"adapter call order mismatch: {adapter.calls}"
    )

    # Result envelope: the runner returns the documented result type
    # with the readiness and observations surfaced.
    assert isinstance(result, SourceIngestResult)
    assert result.source_id == request.source_id
    assert result.request is request
    # Readiness came from the adapter; the runner must surface it on
    # the result envelope.
    assert result.readiness.ready is True


# ---------------------------------------------------------------------------
# Registry routing: the runner must use the registry, not legacy dispatch
# ---------------------------------------------------------------------------


def test_runner_does_not_dispatch_through_legacy_stage2_adapters() -> None:
    """The runner must not call into the legacy ``STAGE2_ADAPTERS`` table.

    The architecture decision (SRC-REG-003, docs/architecture/sources.md
    §8 and §10.1) is that the new runner uses only the new registry.
    The test monkeypatches the legacy ``STAGE2_ADAPTERS`` orchestrator
    for ``dispatch`` with a tracking function and asserts it is never
    invoked when the runner dispatches a registered new-style adapter.

    The test asserts both:

    1. The new adapter was driven through ``check_ready`` (i.e. the
       runner actually executed the lifecycle), AND
    2. The legacy tracker was not invoked.

    This protects against a regression where a future change
    accidentally falls back to the legacy dispatch table.
    """
    from leaders_db import ingest as legacy_ingest
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )

    # Swap the legacy dispatch slot for a tracking function so any
    # accidental fall-through to ``STAGE2_ADAPTERS`` is observable.
    legacy_calls: list[tuple[str, dict]] = []
    original = legacy_ingest.STAGE2_ADAPTERS.get("dispatch")

    def _legacy_tracker(**kwargs):  # type: ignore[no-untyped-def]
        legacy_calls.append(("dispatch", kwargs))

    legacy_ingest.STAGE2_ADAPTERS["dispatch"] = _legacy_tracker
    try:
        registry = InMemorySourceRegistry()
        adapter = _RecordingFakeAdapter(slug="dispatch")
        registry.register(adapter)

        runner = SourceIngestRunner(registry=registry)
        request = SourceIngestRequest(source_id=SourceId(slug="dispatch"))

        runner.run(request)

        # The runner must have driven the new adapter AND must not
        # have called into the legacy dispatch table. The two
        # assertions together prove the new runner routes through the
        # new registry only.
        assert adapter.calls[:1] == ["check_ready"], (
            "runner did not dispatch through the new registry adapter; "
            f"first call was {adapter.calls[:1]!r}"
        )
        assert legacy_calls == [], (
            f"runner must not route through STAGE2_ADAPTERS; saw {legacy_calls}"
        )
    finally:
        # Restore the legacy table.
        legacy_ingest.STAGE2_ADAPTERS["dispatch"] = original


# ---------------------------------------------------------------------------
# Registry lookup: unknown source -> KeyError
# ---------------------------------------------------------------------------


def test_runner_registry_lookups_unknown_source_raise_key_error() -> None:
    """A request for an unregistered source raises ``KeyError``.

    The runner's registry lookup is the gate for dispatch: if the
    ``SourceId`` is unknown the registry must refuse to return an
    adapter. The contract is exercised through the registry surface
    so the assertion is independent of any specific runner behaviour.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRunner,
    )

    registry = InMemorySourceRegistry()
    SourceIngestRunner(registry=registry)

    with pytest.raises(KeyError):
        registry.get_adapter(SourceId(slug="not_registered"))


__all__ = [
    "_RecordingFakeAdapter",
    "_descriptor",
    "test_runner_does_not_dispatch_through_legacy_stage2_adapters",
    "test_runner_exposes_registry_seam",
    "test_runner_registry_lookups_unknown_source_raise_key_error",
    "test_runner_run_dispatches_lifecycle_in_order",
]
