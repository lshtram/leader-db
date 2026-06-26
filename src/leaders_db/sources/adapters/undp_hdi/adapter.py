"""Clean UNDP HDI source adapter."""

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

from ._descriptor import build_undp_hdi_descriptor
from ._raw_read import read_undp_hdi_csv_raw
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_undp_hdi_observations


class UndpHdiAdapter:
    """Local-file-only UNDP HDI country-year adapter."""

    descriptor: SourceDescriptor = build_undp_hdi_descriptor()

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        for blocker in (metadata_blocker(request), file_blocker(request), version_blocker(request)):
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
        return read_undp_hdi_csv_raw(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_undp_hdi_observations(request, raw)


def create_undp_hdi_adapter() -> UndpHdiAdapter:
    return UndpHdiAdapter()


def register_undp_hdi(registry: Any) -> UndpHdiAdapter:
    adapter = create_undp_hdi_adapter()
    registry.register(adapter)
    return adapter


UNDP_HDI_ADAPTER_FACTORY = create_undp_hdi_adapter

_PROTOCOL_CHECK: SourceAdapter = UndpHdiAdapter()

__all__ = [
    "UNDP_HDI_ADAPTER_FACTORY",
    "UndpHdiAdapter",
    "create_undp_hdi_adapter",
    "register_undp_hdi",
]
