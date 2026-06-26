"""Clean SIPRI Yearbook Ch.7 source adapter."""

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

from ._descriptor import build_sipri_yearbook_ch7_descriptor
from ._raw_read import read_sipri_yearbook_ch7_pdf
from ._readiness import file_blocker, metadata_blocker, request_warnings, version_blocker
from ._transform import emit_sipri_yearbook_ch7_observations


class SipriYearbookCh7Adapter:
    """Local-file-only SIPRI Yearbook Chapter 7 PDF adapter."""

    descriptor: SourceDescriptor = build_sipri_yearbook_ch7_descriptor()

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
        return read_sipri_yearbook_ch7_pdf(request)

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        return emit_sipri_yearbook_ch7_observations(request, raw)


def create_sipri_yearbook_ch7_adapter() -> SipriYearbookCh7Adapter:
    return SipriYearbookCh7Adapter()


def register_sipri_yearbook_ch7(registry: Any) -> SipriYearbookCh7Adapter:
    adapter = create_sipri_yearbook_ch7_adapter()
    registry.register(adapter)
    return adapter


SIPRI_YEARBOOK_CH7_ADAPTER_FACTORY = create_sipri_yearbook_ch7_adapter

_PROTOCOL_CHECK: SourceAdapter = SipriYearbookCh7Adapter()

__all__ = [
    "SIPRI_YEARBOOK_CH7_ADAPTER_FACTORY",
    "SipriYearbookCh7Adapter",
    "create_sipri_yearbook_ch7_adapter",
    "register_sipri_yearbook_ch7",
]
