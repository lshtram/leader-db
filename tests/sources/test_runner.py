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


def test_runner_with_engine_persists_observations_writes_manifest_and_reruns_idempotently(
    database_url: str,
    isolated_data_lake,
) -> None:
    """Engine-backed runs validate, persist, and write a manifest.

    This is the Increment 6 runtime proof: the same registry-dispatched source
    run executes through ``check_ready -> read_raw -> transform -> validate ->
    persist -> manifest`` and a rerun updates the existing SQL row instead of
    duplicating it.
    """
    from dataclasses import replace
    from pathlib import Path

    import pytest
    from sqlalchemy import text

    from leaders_db.db.engine import build_engine, init_database
    from leaders_db.research.sql_repository import SqlEvidenceRepository
    from leaders_db.sources import (
        EvidenceQuery,
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.manifests import read_manifest, write_manifest

    init_database(database_url)
    engine = build_engine(database_url)
    registry = InMemorySourceRegistry()
    adapter = _RecordingFakeAdapter(slug="persisted")
    registry.register(adapter)
    runner = SourceIngestRunner(registry=registry, engine=engine)
    request = SourceIngestRequest(
        source_id=SourceId(slug="persisted"),
        metadata_root=Path(isolated_data_lake) / "data" / "metadata",
        processed_root=Path(isolated_data_lake) / "data" / "processed",
        run_id="fixture-run",
        output_formats=("csv",),
    )

    first = runner.run(request)
    second = runner.run(request)

    assert adapter.calls == [
        "check_ready",
        "read_raw",
        "transform",
        "check_ready",
        "read_raw",
        "transform",
    ]
    assert first.validation.valid is True
    assert first.manifest is not None
    assert first.manifest.run_id == "fixture-run"
    assert first.manifest.observation_count == 1
    assert first.manifest.attribution is not None
    assert first.manifest.attribution.attribution_key == "persisted"
    assert first.manifest.adapter_version == "v1"
    assert [asset.asset_id for asset in first.manifest.output_assets] == [
        "observations-fixture-run.csv"
    ]
    assert second.manifest is not None
    assert second.manifest.content_hash == first.manifest.content_hash

    rows = SqlEvidenceRepository(engine).query_observations(
        EvidenceQuery(source_ids=(SourceId(slug="persisted"),))
    )
    assert len(rows) == 1
    assert rows[0].observation_id == "obs-1"

    with engine.connect() as conn:
        row_count = conn.execute(text("SELECT COUNT(*) FROM normalized_observations")).scalar_one()
    assert row_count == 1

    manifest_path = (
        Path(isolated_data_lake)
        / "data"
        / "processed"
        / "persisted"
        / "manifest-fixture-run.json"
    )
    payload = read_manifest(manifest_path)
    assert payload["source_id"]["slug"] == "persisted"
    assert payload["observation_count"] == 1
    assert payload["output_assets"][0]["asset_id"] == "observations-fixture-run.csv"
    assert payload["attribution"]["attribution_key"] == "persisted"
    assert payload["adapter_version"] == "v1"
    assert payload["idempotency_key"] == first.manifest.idempotency_key
    with pytest.raises(FileExistsError, match="immutable source manifest"):
        write_manifest(request.processed_root, replace(first.manifest, observation_count=2))


def test_runner_with_engine_rejects_duplicate_observation_ids(database_url: str) -> None:
    """Shared validation blocks persistence for duplicate observation IDs."""
    from dataclasses import replace

    import pytest

    from leaders_db.db.engine import build_engine, init_database
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )

    class _DuplicateAdapter(_RecordingFakeAdapter):
        def transform(self, request, raw):  # type: ignore[no-untyped-def]
            rows = tuple(super().transform(request, raw))
            return iter((rows[0], replace(rows[0], value=43)))

    init_database(database_url)
    registry = InMemorySourceRegistry()
    registry.register(_DuplicateAdapter(slug="duplicates"))
    request = SourceIngestRequest(source_id=SourceId(slug="duplicates"))

    no_engine_result = SourceIngestRunner(registry=registry).run(request)
    assert no_engine_result.validation.valid is False
    assert no_engine_result.manifest is None

    runner = SourceIngestRunner(registry=registry, engine=build_engine(database_url))

    with pytest.raises(RuntimeError, match="duplicate_observation_id"):
        runner.run(request)


def test_runner_detects_manifest_conflict_before_mutating_outputs(
    database_url: str,
    isolated_data_lake,
) -> None:
    """Changed content for an existing run_id is rejected before side effects."""
    from pathlib import Path

    import pytest

    from leaders_db.db.engine import build_engine, init_database
    from leaders_db.research.sql_repository import SqlEvidenceRepository
    from leaders_db.sources import (
        EvidenceQuery,
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )

    class _MutableAdapter(_RecordingFakeAdapter):
        def __init__(self, slug: str = "mutable") -> None:
            super().__init__(slug=slug)
            self.extension = {"version": "first"}

        def transform(self, request, raw):  # type: ignore[no-untyped-def]
            from dataclasses import replace

            row = next(iter(super().transform(request, raw)))
            return iter((replace(row, extension=self.extension),))

    init_database(database_url)
    engine = build_engine(database_url)
    registry = InMemorySourceRegistry()
    adapter = _MutableAdapter()
    registry.register(adapter)
    runner = SourceIngestRunner(registry=registry, engine=engine)
    request = SourceIngestRequest(
        source_id=SourceId(slug="mutable"),
        processed_root=Path(isolated_data_lake) / "data" / "processed",
        run_id="same-run",
        output_formats=("csv",),
    )

    runner.run(request)
    output_path = request.processed_root / "mutable" / "observations-same-run.csv"
    original_bytes = output_path.read_bytes()

    adapter.extension = {"version": "second"}
    with pytest.raises(FileExistsError, match="immutable source manifest"):
        runner.run(request)

    rows = SqlEvidenceRepository(engine).query_observations(
        EvidenceQuery(source_ids=(SourceId(slug="mutable"),))
    )
    assert len(rows) == 1
    assert rows[0].value == 42
    assert rows[0].extension == {"version": "first"}
    assert output_path.read_bytes() == original_bytes


def test_shared_validator_reports_all_blocking_error_codes() -> None:
    """Shared validation covers each generic blocking observation invariant."""
    from dataclasses import replace

    from leaders_db.sources import RawLocator, SourceId, SourceIngestRequest, validate_observations

    adapter = _RecordingFakeAdapter(slug="invalid")
    request = SourceIngestRequest(source_id=SourceId(slug="invalid"))
    raw = adapter.read_raw(request)
    base = next(iter(adapter.transform(request, raw)))

    result = validate_observations(
        request,
        (
            base,
            replace(base, source_id=SourceId(slug="other"), observation_id="source-mismatch"),
            replace(base, observation_id=""),
            replace(base, observation_id=base.observation_id, value=43),
            replace(base, observation_id="missing-family", observation_family=""),
            replace(base, observation_id="missing-indicator", indicator_code=""),
            replace(
                base,
                observation_id="missing-provenance",
                raw_locator=RawLocator(asset_id=""),
            ),
        ),
        descriptor=adapter.descriptor,
    )

    assert result.valid is False
    assert {error.code for error in result.errors} == {
        "source_mismatch",
        "missing_observation_id",
        "duplicate_observation_id",
        "missing_observation_family",
        "missing_indicator_code",
        "missing_raw_provenance",
    }


def test_shared_validator_reports_out_of_coverage_years_without_blocking() -> None:
    """Coverage diagnostics are structured warnings, not hard failures."""
    from dataclasses import replace

    from leaders_db.sources import SourceId, SourceIngestRequest, validate_observations

    adapter = _RecordingFakeAdapter(slug="coverage")
    request = SourceIngestRequest(source_id=SourceId(slug="coverage"))
    raw = adapter.read_raw(request)
    observation = next(iter(adapter.transform(request, raw)))
    descriptor = replace(
        adapter.descriptor,
        coverage_hint=replace(
            adapter.descriptor.coverage_hint,
            start_year=2024,
            end_year=2020,
        ),
    )

    result = validate_observations(request, (observation,), descriptor=descriptor)

    assert result.valid is True
    assert [warning.code for warning in result.warnings] == [
        "out_of_coverage_year",
        "out_of_coverage_year",
    ]
    assert {warning.context["direction"] for warning in result.warnings} == {"before", "after"}


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
