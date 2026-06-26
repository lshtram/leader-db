"""Clean CIRIGHTS source adapter."""

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

from ._descriptor import build_cirights_descriptor
from ._raw_read import read_cirights_xlsx
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_cirights_observations


class CirightsAdapter:
    """Local-file-only CIRIGHTS country-year adapter."""

    descriptor: SourceDescriptor = build_cirights_descriptor()

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
        return read_cirights_xlsx(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_cirights_observations(request, raw)


def create_cirights_adapter() -> CirightsAdapter:
    return CirightsAdapter()


def register_cirights(registry: Any) -> CirightsAdapter:
    adapter = create_cirights_adapter()
    registry.register(adapter)
    return adapter


CIRIGHTS_ADAPTER_FACTORY = create_cirights_adapter

_PROTOCOL_CHECK: SourceAdapter = CirightsAdapter()

__all__ = [
    "CIRIGHTS_ADAPTER_FACTORY",
    "CirightsAdapter",
    "create_cirights_adapter",
    "register_cirights",
]
