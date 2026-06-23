"""Evidence query interfaces for downstream consumers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .contracts import (
    EvidenceQuery,
    NormalizedObservation,
    SourceAttribution,
    SourceId,
    SourceManifest,
)


@runtime_checkable
class EvidenceRepository(Protocol):
    """Read-only source-evidence query boundary."""

    def query_observations(self, query: EvidenceQuery) -> Sequence[NormalizedObservation]:
        """Return observations matching ``query`` without rerunning ingestion."""
        ...

    def get_manifest(self, source_id: SourceId, run_id: str | None = None) -> SourceManifest:
        """Return a source manifest by source and optional run id."""
        ...

    def get_attributions(self, source_ids: Sequence[SourceId]) -> Sequence[SourceAttribution]:
        """Return normative attribution records for ``source_ids``."""
        ...
