"""Clean Archigos v4.1 source adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    ReadinessResult,
    SourceAdapter,
    SourceDescriptor,
    SourceIngestRequest,
    SourceWarning,
)

from ._descriptor import build_archigos_descriptor
from ._raw_read import read_archigos_dta
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_archigos_observations


class ArchigosAdapter:
    """Local-file-only Archigos v4.1 leader-spell adapter."""

    descriptor: SourceDescriptor = build_archigos_descriptor()

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        for blocker in (
            metadata_blocker(request),
            file_blocker(request),
            version_blocker(request),
        ):
            if blocker is not None:
                message, code = blocker
                return ReadinessResult(
                    ready=False,
                    errors=(
                        SourceWarning(
                            code=code,
                            message=message,
                            severity="error",
                            source_id=request.source_id,
                        ),
                    ),
                )
        return ReadinessResult(ready=True, warnings=request_warnings(request))

    def read_raw(self, request: SourceIngestRequest) -> RawReadResult:
        return read_archigos_dta(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_archigos_observations(request, raw)


def create_archigos_adapter() -> ArchigosAdapter:
    return ArchigosAdapter()


def register_archigos(registry: Any) -> ArchigosAdapter:
    adapter = create_archigos_adapter()
    registry.register(adapter)
    return adapter


ARCHIGOS_ADAPTER_FACTORY = create_archigos_adapter

_PROTOCOL_CHECK: SourceAdapter = ArchigosAdapter()

__all__ = [
    "ARCHIGOS_ADAPTER_FACTORY",
    "ArchigosAdapter",
    "create_archigos_adapter",
    "register_archigos",
]
