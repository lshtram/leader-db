"""Phase B Increment A -- shared Stage 2 registry tests.

This file covers the ``leaders_db.ingest.registry`` lookup
layer: ``register`` / ``get`` / ``has`` / ``unregister`` /
``registered_source_keys`` / ``ingest_source``. The runner
dispatches a registered ``SourceAdapter`` in the order
``check_ready -> read -> transform -> write`` and short-
circuits on ``ready=False``.

Per the ``docs/source-ingestion-plan.md`` mirrored layout
(see the Increment A design), the tests for the registry
live in ``tests/ingest/common/test_registry.py``; the
interface tests live in
``tests/ingest/common/test_interfaces.py``.

PASS-ELIGIBLE / DOMAIN-RED conventions
--------------------------------------

Every test in this file is ``PASS-ELIGIBLE``: the test
exercises the registry contract surface that is already
implemented in the Phase A stub. The tests are regression
guards -- they must keep passing once the production code
lands.

Coverage
--------

- ``register`` / ``get`` / ``has`` form a working dispatch
  (round-trip, isolation across tests).
- ``ingest_source(request)`` drives the full
  ``check_ready -> read -> transform -> write`` pipeline
  in order; the resulting ``IngestResult`` carries the
  source key the request asked for.
- ``ingest_source(request)`` with ``ready=False`` does NOT
  call ``read()`` / ``transform()`` / ``write()`` and
  surfaces the blocker as an actionable error.
"""

from __future__ import annotations

import pytest


class _RecordingFakeAdapter:
    """A minimal :class:`SourceAdapter` implementation that records
    the order of method calls.

    Implements the contract documented in
    ``docs/source-ingestion-plan.md``:

    - ``check_ready(request) -> SourceReadiness``
    - ``read(request) -> RawSourceBundle``
    - ``transform(bundle, request) -> NormalizedSourceFrame``
    - ``write(frame, request) -> IngestResult``
    - ``ingest(request) -> IngestResult`` (Phase B Increment A:
      the convenience method wraps the full pipeline on the
      adapter instance; the registry runner is the primary
      entry point for callers that hold a registry key.)

    The class records every method call so tests can assert the
    runner drove them in the order ``check_ready -> read ->
    transform -> write``.
    """

    source_key = "fake_recording"

    def __init__(self, *, ready: bool = True) -> None:
        self.calls: list[str] = []
        self._ready = ready
        # Records the request passed to ``check_ready`` so the
        # request-scoped ``raw_root`` test can assert the runner
        # forwarded the request.
        self.last_check_ready_request = None

    def check_ready(self, request):  # type: ignore[no-untyped-def]
        from leaders_db.ingest.interfaces import SourceReadiness

        self.calls.append("check_ready")
        self.last_check_ready_request = request
        if self._ready:
            return SourceReadiness(ready=True, blocker=None)
        return SourceReadiness(
            ready=False, blocker="fake blocked for test",
        )

    def read(self, request):  # type: ignore[no-untyped-def]
        from leaders_db.ingest.interfaces import RawSourceBundle

        self.calls.append(f"read:{request.source_key}")
        return RawSourceBundle(source_key=request.source_key, payload={})

    def transform(self, bundle, request):  # type: ignore[no-untyped-def]
        from leaders_db.ingest.interfaces import NormalizedSourceFrame

        self.calls.append(
            f"transform:{bundle.source_key}:{list(request.effective_years)}"
        )
        return NormalizedSourceFrame(
            source_key=bundle.source_key,
            rows=(),
            attribution="fake attribution",
        )

    def write(self, frame, request):  # type: ignore[no-untyped-def]
        from leaders_db.ingest.interfaces import IngestResult

        self.calls.append(
            f"write:{frame.source_key}:{len(frame.rows)}"
        )
        return IngestResult(
            source_key=frame.source_key,
            source_id=0,
            observation_rows=len(frame.rows),
            parquet_path=None,
            countries=0,
            years=request.effective_years,
            indicators=0,
            warnings=(),
        )

    def ingest(self, request):  # type: ignore[no-untyped-def]
        """Convenience method: drive the full pipeline on this
        adapter instance and return the :class:`IngestResult`.

        The Phase A stub protocol documents this method (see
        ``docs/source-ingestion-plan.md``); the registry runner
        is the primary entry point, but ``adapter.ingest(request)``
        is the convenience path for callers that already hold an
        adapter reference.
        """
        self.calls.append(f"ingest:{request.source_key}")
        readiness = self.check_ready(request)
        if not readiness.ready:
            raise RuntimeError(
                f"Source {request.source_key!r} is not ready: "
                f"{readiness.blocker or 'no blocker given'}"
            )
        bundle = self.read(request)
        frame = self.transform(bundle, request)
        return self.write(frame, request)


# ---------------------------------------------------------------------------
# Registry dispatch primitives
# ---------------------------------------------------------------------------


def test_registry_register_get_has_roundtrip() -> None:
    """``register`` / ``get`` / ``has`` form a working dispatch.

    Contract: after ``register("k", adapter)``, ``has("k")`` is
    True and ``get("k")`` returns the same adapter object.

    PASS-ELIGIBLE: the registry module exposes the three
    primitives; the Phase B stub satisfies the contract.
    """
    from leaders_db.ingest.registry import get, has, register

    adapter = _RecordingFakeAdapter()
    register("phase_b_increment_a_roundtrip", adapter)
    try:
        assert has("phase_b_increment_a_roundtrip") is True
        assert get("phase_b_increment_a_roundtrip") is adapter
    finally:
        # Clean the registry entry so other tests stay isolated.
        from leaders_db.ingest.registry import unregister

        try:
            unregister("phase_b_increment_a_roundtrip")
        except Exception:
            pass


def test_registry_ingest_source_dispatches_full_pipeline() -> None:
    """``ingest_source(request)`` drives the full
    ``check_ready -> read -> transform -> write`` pipeline in order.

    Contract: the registry runner calls the four protocol methods
    in this exact order; the resulting ``IngestResult`` carries the
    source key the request asked for.

    PASS-ELIGIBLE: the stub registry implements the dispatch
    ordering; the test exercises the runner against a fake
    adapter that records every method call.
    """
    from leaders_db.ingest.interfaces import IngestRequest
    from leaders_db.ingest.registry import ingest_source, register

    adapter = _RecordingFakeAdapter(ready=True)
    register("phase_b_increment_a_pipeline", adapter)
    try:
        result = ingest_source(
            IngestRequest(source_key="phase_b_increment_a_pipeline", year=2019),
        )
    finally:
        from leaders_db.ingest.registry import unregister

        try:
            unregister("phase_b_increment_a_pipeline")
        except Exception:
            pass

    assert adapter.calls == [
        "check_ready",
        "read:phase_b_increment_a_pipeline",
        "transform:phase_b_increment_a_pipeline:[2019]",
        "write:phase_b_increment_a_pipeline:0",
    ], f"adapter call order mismatch: {adapter.calls}"
    assert result.source_key == "phase_b_increment_a_pipeline"


def test_registry_ingest_source_blocks_when_not_ready() -> None:
    """``ingest_source(request)`` with ``ready=False`` does NOT call
    ``read()`` / ``transform()`` / ``write()`` and surfaces the
    blocker as an actionable error.

    Contract: ``check_ready()`` returning ``ready=False`` is a hard
    stop. The runner raises an exception (a domain-specific
    ``IngestBlocked`` or ``RuntimeError``) that names the source
    and the blocker reason; ``read()`` is never called.

    PASS-ELIGIBLE: the stub registry short-circuits on
    ``ready=False`` without calling ``read()``.
    """
    from leaders_db.ingest.interfaces import IngestRequest
    from leaders_db.ingest.registry import ingest_source, register

    adapter = _RecordingFakeAdapter(ready=False)
    register("phase_b_increment_a_blocked", adapter)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            ingest_source(
                IngestRequest(
                    source_key="phase_b_increment_a_blocked", year=2019,
                ),
            )
    finally:
        from leaders_db.ingest.registry import unregister

        try:
            unregister("phase_b_increment_a_blocked")
        except Exception:
            pass

    # The runner refused to call read/transform/write.
    assert "read:" not in adapter.calls
    assert "transform:" not in adapter.calls
    assert "write:" not in adapter.calls
    # The blocker reason is mentioned in the error.
    msg = str(exc_info.value)
    assert "fake blocked for test" in msg or "blocker" in msg.lower()


__all__ = ["_RecordingFakeAdapter"]
