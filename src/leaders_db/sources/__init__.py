"""Unified source-system contracts and seams.

This package is the clean future source interface. It is intentionally separate
from :mod:`leaders_db.ingest`, which remains available as the legacy Stage 2
subsystem during migration.

Importing :mod:`leaders_db.sources` must not import legacy ingest modules or
register legacy adapters. Optional compatibility lives behind explicit lazy
seams such as :mod:`leaders_db.sources.legacy`.
"""

from __future__ import annotations

from .contracts import (
    CachePolicy,
    CoverageHint,
    EvidenceQuery,
    NormalizedObservation,
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
from .registry import InMemorySourceRegistry, SourceRegistry, build_default_source_registry
from .runner import SourceIngestRunner
from .validation import validate_observations

__all__ = [
    "CachePolicy",
    "CoverageHint",
    "EvidenceQuery",
    "EvidenceRepository",
    "InMemoryEvidenceRepository",
    "InMemorySourceRegistry",
    "NormalizedObservation",
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
