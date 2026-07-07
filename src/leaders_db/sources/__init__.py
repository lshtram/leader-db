"""Unified source-system contracts and seams.

This package is the clean future source interface. It is intentionally separate
from :mod:`leaders_db.ingest`, which remains available as the legacy Stage 2
subsystem during migration.

Importing :mod:`leaders_db.sources` must not import legacy ingest modules or
register legacy adapters. Optional compatibility lives behind explicit lazy
seams such as :mod:`leaders_db.sources.legacy`.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    CachePolicy,
    CoverageHint,
    EvidenceQuery,
    NormalizedObservation,
    OutputFormat,
    RawAsset,
    RawLocator,
    RawReadResult,
    ReadinessResult,
    SourceAdapter,
    SourceAttribution,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceIngestResult,
    SourceManifest,
    SourceWarning,
    TransformLocator,
    ValidationResult,
)
from .query import EvidenceRepository, InMemoryEvidenceRepository
from .validation import validate_observations


def __getattr__(name: str) -> Any:
    if name in {"InMemorySourceRegistry", "SourceRegistry", "build_default_source_registry"}:
        from .registry import (
            InMemorySourceRegistry,
            SourceRegistry,
            build_default_source_registry,
        )

        values = {
            "InMemorySourceRegistry": InMemorySourceRegistry,
            "SourceRegistry": SourceRegistry,
            "build_default_source_registry": build_default_source_registry,
        }
        return values[name]
    if name == "SourceIngestRunner":
        from .runner import SourceIngestRunner

        return SourceIngestRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)

__all__ = [
    "CachePolicy",
    "CoverageHint",
    "EvidenceQuery",
    "EvidenceRepository",
    "InMemoryEvidenceRepository",
    "InMemorySourceRegistry",
    "NormalizedObservation",
    "OutputFormat",
    "RawAsset",
    "RawLocator",
    "RawReadResult",
    "ReadinessResult",
    "SourceAdapter",
    "SourceAttribution",
    "SourceDescriptor",
    "SourceId",
    "SourceIngestRequest",
    "SourceIngestResult",
    "SourceIngestRunner",
    "SourceManifest",
    "SourceRegistry",
    "SourceWarning",
    "TransformLocator",
    "ValidationResult",
    "build_default_source_registry",
    "validate_observations",
]
