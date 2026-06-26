"""Clean REIGN 2021-8 source adapter."""

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

from ._descriptor import build_reign_descriptor
from ._raw_read import read_reign_csv
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_reign_observations


class ReignAdapter:
    """Local-file-only REIGN 2021-8 leader-month adapter."""

    descriptor: SourceDescriptor = build_reign_descriptor()

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
        return read_reign_csv(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_reign_observations(request, raw)


def create_reign_adapter() -> ReignAdapter:
    return ReignAdapter()


def register_reign(registry: Any) -> ReignAdapter:
    adapter = create_reign_adapter()
    registry.register(adapter)
    return adapter


REIGN_ADAPTER_FACTORY = create_reign_adapter

_PROTOCOL_CHECK: SourceAdapter = ReignAdapter()

__all__ = [
    "REIGN_ADAPTER_FACTORY",
    "ReignAdapter",
    "create_reign_adapter",
    "register_reign",
]
