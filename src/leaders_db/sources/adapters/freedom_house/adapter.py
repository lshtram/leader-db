"""Clean Freedom House FIW source adapter."""

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

from ._descriptor import build_freedom_house_descriptor
from ._raw_read import read_fiw_ratings_workbook
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_fiw_observations


class FreedomHouseAdapter:
    """Local-file-only FIW 2026 ratings/statuses adapter."""

    descriptor: SourceDescriptor = build_freedom_house_descriptor()

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
        return read_fiw_ratings_workbook(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_fiw_observations(request, raw)


def create_freedom_house_adapter() -> FreedomHouseAdapter:
    return FreedomHouseAdapter()


def register_freedom_house(registry: Any) -> FreedomHouseAdapter:
    adapter = create_freedom_house_adapter()
    registry.register(adapter)
    return adapter


FREEDOM_HOUSE_ADAPTER_FACTORY = create_freedom_house_adapter

_PROTOCOL_CHECK: SourceAdapter = FreedomHouseAdapter()

__all__ = [
    "FREEDOM_HOUSE_ADAPTER_FACTORY",
    "FreedomHouseAdapter",
    "create_freedom_house_adapter",
    "register_freedom_house",
]
