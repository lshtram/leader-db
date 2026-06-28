"""Runner seams for unified source ingestion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from sqlalchemy.engine import Engine

from leaders_db.research.sql_repository import observation_to_row

from .attributions import source_attribution_from_descriptor
from .contracts import (
    NormalizedObservation,
    RawAsset,
    RawReadResult,
    SourceDescriptor,
    SourceIngestRequest,
    SourceIngestResult,
    SourceManifest,
    SourceWarning,
)
from .manifests import ensure_manifest_writable, write_manifest
from .persistence import SourcePersistenceService
from .registry import SourceRegistry
from .validation import validate_observations


class SourceIngestRunner:
    """Lifecycle orchestrator for the unified source subsystem.

    The runner drives the documented source lifecycle
    (``check_ready -> read_raw -> transform`` and, when configured,
    ``validate -> persist -> manifest``) on adapters it
    retrieves from the registered :class:`SourceRegistry` seam. It
    does NOT consult the legacy ``leaders_db.ingest.STAGE2_ADAPTERS``
    table; the new registry is the single dispatch surface for
    ``leaders_db.sources`` (SRC-REG-003).

    SQL persistence and manifest generation are opt-in via ``engine`` so
    existing in-memory runner callers remain side-effect free.
    """

    def __init__(self, registry: SourceRegistry, *, engine: Engine | None = None) -> None:
        self._registry = registry
        self._persistence = SourcePersistenceService(engine) if engine is not None else None

    @property
    def registry(self) -> SourceRegistry:
        """Registry used for source dispatch."""
        return self._registry

    def run(self, request: SourceIngestRequest) -> SourceIngestResult:
        """Drive the adapter lifecycle for ``request`` through the registry.

        The runner looks up the adapter under ``request.source_id``
        via :meth:`SourceRegistry.get_adapter` (which raises
        ``KeyError`` for unknown slugs), then calls the adapter
        methods in the documented fixed order:

        1. ``check_ready(request)`` -- validate request/raw/source
           readiness before parsing payloads.
        2. ``read_raw(request)`` -- read immutable raw assets or
           cache-permitted API payloads.
        3. ``transform(request, raw)`` -- convert the raw payload
           into :class:`NormalizedObservation` records.
        4. ``validate`` -- enforce shared observation invariants.
        5. ``persist`` / ``manifest`` -- only when an engine is configured and
           ``request.dry_run`` is false.

        If ``check_ready`` returns ``ready=False``, the runner
        surfaces a :class:`RuntimeError` that names the source slug
        so callers can act on the blocker. ``read_raw`` /
        ``transform`` are NOT called in that branch.

        The result envelope is a real :class:`SourceIngestResult` shaped by the
        existing contracts. Without an engine, ``manifest`` is left as ``None``.
        """
        adapter = self._registry.get_adapter(request.source_id)
        descriptor = adapter.descriptor

        readiness = adapter.check_ready(request)
        if not readiness.ready:
            raise RuntimeError(
                f"Source {request.source_id.slug!r} is not ready: "
                f"check_ready returned ready=False"
            )

        raw = adapter.read_raw(request)
        observations = tuple(adapter.transform(request, raw))
        validation = validate_observations(request, observations, descriptor=descriptor)

        warnings: tuple[SourceWarning, ...] = (
            tuple(readiness.warnings)
            + tuple(readiness.errors)
            + tuple(raw.warnings)
            + tuple(validation.warnings)
            + tuple(validation.errors)
        )

        manifest: SourceManifest | None = None
        if self._persistence is not None:
            if not validation.valid:
                codes = ", ".join(error.code for error in validation.errors)
                raise RuntimeError(
                    f"Source {request.source_id.slug!r} produced invalid observations: {codes}"
                )
            content_hash = _content_hash(observations)
            run_id = request.run_id or f"{request.source_id.slug}-{content_hash[:12]}"
            source_version = request.source_version or descriptor.default_version
            output_assets: tuple[RawAsset, ...] = self._persistence.plan_output_assets(
                request,
                run_id=run_id,
                source_version=source_version,
            )
            if not request.dry_run:
                manifest = _build_manifest(
                    request,
                    raw,
                    observations,
                    warnings,
                    descriptor,
                    run_id=run_id,
                    source_version=source_version,
                    content_hash=content_hash,
                    output_assets=output_assets,
                )
                ensure_manifest_writable(request.processed_root, manifest)
                output_assets = self._persistence.persist_observations(
                    request,
                    observations,
                    run_id=run_id,
                    source_version=source_version,
                )
            manifest = _build_manifest(
                request,
                raw,
                observations,
                warnings,
                descriptor,
                run_id=run_id,
                source_version=source_version,
                content_hash=content_hash,
                output_assets=output_assets,
            )
            if not request.dry_run:
                write_manifest(request.processed_root, manifest)

        return SourceIngestResult(
            source_id=request.source_id,
            request=request,
            readiness=readiness,
            validation=validation,
            manifest=manifest,
            observations=observations,
            warnings=warnings,
        )


def _build_manifest(
    request: SourceIngestRequest,
    raw: RawReadResult,
    observations: Sequence[NormalizedObservation],
    warnings: Sequence[SourceWarning],
    descriptor: SourceDescriptor,
    *,
    run_id: str,
    source_version: str | None,
    content_hash: str,
    output_assets: Sequence[RawAsset],
) -> SourceManifest:
    return SourceManifest(
        source_id=request.source_id,
        run_id=run_id,
        request=request,
        source_version=source_version,
        raw_assets=tuple(raw.assets),
        output_assets=tuple(output_assets),
        observation_count=len(observations),
        coverage=_coverage(observations),
        warnings=tuple(warnings),
        attribution=source_attribution_from_descriptor(descriptor),
        adapter_version=_adapter_version(observations, source_version),
        content_hash=content_hash,
        idempotency_key=f"{request.source_id.slug}:{content_hash}",
    )


def _content_hash(observations: Sequence[NormalizedObservation]) -> str:
    payload = [observation_to_row(observation) for observation in observations]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _adapter_version(
    observations: Sequence[NormalizedObservation],
    source_version: str | None,
) -> str | None:
    for observation in observations:
        if observation.transform_locator.adapter_version:
            return observation.transform_locator.adapter_version
    return source_version


def _coverage(observations: Sequence[NormalizedObservation]) -> dict[str, object]:
    years = sorted(
        {observation.year for observation in observations if observation.year is not None}
    )
    countries = sorted(
        {
            observation.country_code
            for observation in observations
            if observation.country_code is not None
        }
    )
    leaders = sorted(
        {observation.leader_id for observation in observations if observation.leader_id is not None}
    )
    return {
        "years": years,
        "countries": countries,
        "leaders": leaders,
    }


__all__ = ["SourceIngestRunner"]
