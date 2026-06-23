"""Runner seams for unified source ingestion."""

from __future__ import annotations

from .contracts import (
    SourceIngestRequest,
    SourceIngestResult,
    SourceWarning,
    ValidationResult,
)
from .registry import SourceRegistry


class SourceIngestRunner:
    """Lifecycle orchestrator for the unified source subsystem.

    The runner drives the documented Phase B / Phase C lifecycle
    (``check_ready -> read_raw -> transform``) on adapters it
    retrieves from the registered :class:`SourceRegistry` seam. It
    does NOT consult the legacy ``leaders_db.ingest.STAGE2_ADAPTERS``
    table; the new registry is the single dispatch surface for
    ``leaders_db.sources`` (SRC-REG-003).

    Validation, persistence, and manifest generation remain
    out of scope for the minimal Phase B runner. The result envelope
    surfaces the adapter-produced :class:`ReadinessResult`,
    materialised :class:`NormalizedObservation` tuple, and a
    convenience :class:`ValidationResult` so callers can inspect
    the run without depending on filesystem or DB side effects.
    """

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

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

        If ``check_ready`` returns ``ready=False``, the runner
        surfaces a :class:`RuntimeError` that names the source slug
        so callers can act on the blocker. ``read_raw`` /
        ``transform`` are NOT called in that branch.

        The result envelope is a real :class:`SourceIngestResult`
        shaped by the existing contracts; ``manifest`` is left as
        ``None`` because the minimal Phase B runner does not own
        persistence.
        """
        adapter = self._registry.get_adapter(request.source_id)

        readiness = adapter.check_ready(request)
        if not readiness.ready:
            raise RuntimeError(
                f"Source {request.source_id.slug!r} is not ready: "
                f"check_ready returned ready=False"
            )

        raw = adapter.read_raw(request)
        observations = tuple(adapter.transform(request, raw))

        # Minimal Phase B validation: the lifecycle produced zero or
        # more observations, so the result is valid by construction.
        # Real validation (duplicate ids, missing provenance, etc.)
        # lives in a later shared-validator phase and is intentionally
        # not implemented here.
        validation = ValidationResult(valid=True)

        warnings: tuple[SourceWarning, ...] = (
            tuple(readiness.warnings)
            + tuple(readiness.errors)
            + tuple(raw.warnings)
        )

        return SourceIngestResult(
            source_id=request.source_id,
            request=request,
            readiness=readiness,
            validation=validation,
            manifest=None,
            observations=observations,
            warnings=warnings,
        )


__all__ = ["SourceIngestRunner"]
