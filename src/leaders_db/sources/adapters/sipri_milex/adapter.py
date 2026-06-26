"""Clean SIPRI Milex source adapter."""

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

from ._descriptor import build_sipri_milex_descriptor
from ._raw_read import read_sipri_milex_xlsx
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_sipri_milex_observations


class SipriMilexAdapter:
    """Local-file-only SIPRI Military Expenditure Database adapter."""

    descriptor: SourceDescriptor = build_sipri_milex_descriptor()

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
        return read_sipri_milex_xlsx(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_sipri_milex_observations(request, raw)


def create_sipri_milex_adapter() -> SipriMilexAdapter:
    return SipriMilexAdapter()


def register_sipri_milex(registry: Any) -> SipriMilexAdapter:
    adapter = create_sipri_milex_adapter()
    registry.register(adapter)
    return adapter


SIPRI_MILEX_ADAPTER_FACTORY = create_sipri_milex_adapter

_PROTOCOL_CHECK: SourceAdapter = SipriMilexAdapter()

__all__ = [
    "SIPRI_MILEX_ADAPTER_FACTORY",
    "SipriMilexAdapter",
    "create_sipri_milex_adapter",
    "register_sipri_milex",
]
