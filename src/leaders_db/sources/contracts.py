"""Public contracts for the unified source subsystem.

The classes in this module define importable interfaces only. They do not read
raw data, transform observations, persist outputs, or register real sources.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | Mapping[str, "JsonValue"] | Sequence["JsonValue"]

SourceType: TypeAlias = Literal[
    "dataset",
    "api",
    "manual",
    "derived",
    "document",
    "knowledge_base",
    "validation_only",
]
CachePolicy: TypeAlias = Literal["offline_only", "prefer_cache", "refresh", "no_cache"]
OutputFormat: TypeAlias = Literal["parquet", "csv"]
ObservationValueType: TypeAlias = Literal[
    "numeric", "categorical", "text", "boolean", "json", "missing"
]
Severity: TypeAlias = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class SourceId:
    """Stable source identity used by registry, manifests, and data-lake paths."""

    slug: str


@dataclass(frozen=True)
class CoverageHint:
    """Declared coverage envelope for a source descriptor."""

    start_year: int | None = None
    end_year: int | None = None
    countries: tuple[str, ...] | None = None
    leaders: tuple[str, ...] | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SourceDescriptor:
    """Static metadata exposed by every source adapter."""

    source_id: SourceId
    display_name: str
    source_type: SourceType
    supported_observation_families: tuple[str, ...]
    default_version: str | None
    homepage_url: str | None
    attribution_key: str
    coverage_hint: CoverageHint
    requires_manual_approval: bool = False
    requires_network: bool = False


@dataclass(frozen=True)
class SourceIngestRequest:
    """Request-scoped source run contract.

    ``years=None`` means all available years in the source. ``dry_run=True`` is
    reserved for read/validate flows that must not mutate files or database rows.
    Network-capable adapters must interpret ``cache_policy`` before accessing
    the network.
    """

    source_id: SourceId
    years: tuple[int, ...] | None = None
    countries: tuple[str, ...] | None = None
    leaders: tuple[str, ...] | None = None
    raw_root: Path = Path("data/raw")
    processed_root: Path = Path("data/processed")
    metadata_root: Path = Path("data/metadata")
    db_url: str | None = None
    db_session: Any | None = None
    source_version: str | None = None
    run_id: str | None = None
    dry_run: bool = False
    overwrite: bool = False
    cache_policy: CachePolicy = "prefer_cache"
    output_formats: tuple[OutputFormat, ...] = ("parquet",)


@dataclass(frozen=True)
class SourceWarning:
    """Structured warning or error produced by source lifecycle steps."""

    code: str
    message: str
    severity: Severity = "warning"
    source_id: SourceId | None = None
    context: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class RawAsset:
    """Raw file, URL, cache response, or document asset referenced by a run."""

    asset_id: str
    source_id: SourceId
    version: str | None
    media_type: str | None
    path: Path | None = None
    url: str | None = None
    checksum_sha256: str | None = None
    retrieved_at: datetime | None = None
    immutable: bool = True


@dataclass(frozen=True)
class RawLocator:
    """Pointer from an observation to its source-native raw location."""

    asset_id: str
    path: str | None = None
    url: str | None = None
    sheet: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    page_number: int | None = None
    html_selector: str | None = None
    json_pointer: str | None = None
    api_endpoint: str | None = None
    api_params_hash: str | None = None


@dataclass(frozen=True)
class TransformLocator:
    """Pointer to source adapter/catalog logic that produced an observation."""

    adapter_version: str | None = None
    transform_name: str | None = None
    catalog_key: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class NormalizedObservation:
    """Canonical evidence unit emitted by source transforms."""

    source_id: SourceId
    observation_id: str
    observation_family: str
    indicator_code: str
    value: JsonValue
    value_type: ObservationValueType
    year: int | None
    country_code: str | None
    country_name: str | None
    leader_id: str | None
    leader_name: str | None
    unit: str | None
    scale: str | None
    source_version: str | None
    raw_locator: RawLocator
    transform_locator: TransformLocator
    quality_flags: tuple[str, ...] = ()
    warnings: tuple[SourceWarning, ...] = ()
    extension: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessResult:
    """Pre-flight result returned before raw parsing begins."""

    ready: bool
    warnings: tuple[SourceWarning, ...] = ()
    errors: tuple[SourceWarning, ...] = ()


@dataclass(frozen=True)
class RawReadResult:
    """Raw read payload boundary.

    ``payload`` is intentionally opaque to shared infrastructure until adapter
    implementations define source-specific parser contracts.
    """

    source_id: SourceId
    assets: tuple[RawAsset, ...] = ()
    payload: Any | None = None
    warnings: tuple[SourceWarning, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    """Shared validation result for normalized observations."""

    valid: bool
    warnings: tuple[SourceWarning, ...] = ()
    errors: tuple[SourceWarning, ...] = ()


@dataclass(frozen=True)
class SourceAttribution:
    """Machine-readable normative attribution entry."""

    attribution_key: str
    source_id: SourceId
    text: str
    citation_url: str | None = None
    license_name: str | None = None


@dataclass(frozen=True)
class SourceManifest:
    """Immutable source-run manifest contract."""

    source_id: SourceId
    run_id: str
    request: SourceIngestRequest
    source_version: str | None
    raw_assets: tuple[RawAsset, ...]
    output_assets: tuple[RawAsset, ...] = ()
    observation_count: int = 0
    coverage: Mapping[str, JsonValue] = field(default_factory=dict)
    warnings: tuple[SourceWarning, ...] = ()
    attribution: SourceAttribution | None = None
    adapter_version: str | None = None
    content_hash: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SourceIngestResult:
    """End-of-run result returned by the future shared runner."""

    source_id: SourceId
    request: SourceIngestRequest
    readiness: ReadinessResult
    validation: ValidationResult
    manifest: SourceManifest | None = None
    observations: tuple[NormalizedObservation, ...] = ()
    warnings: tuple[SourceWarning, ...] = ()


@dataclass(frozen=True)
class EvidenceQuery:
    """Query contract for downstream evidence consumers."""

    source_ids: tuple[SourceId, ...] | None = None
    observation_families: tuple[str, ...] | None = None
    indicator_codes: tuple[str, ...] | None = None
    years: tuple[int, ...] | None = None
    countries: tuple[str, ...] | None = None
    leaders: tuple[str, ...] | None = None
    include_raw_locators: bool = True
    include_attribution: bool = True
    include_warnings: bool = True
    include_quality_flags: bool = True
    include_manifests: bool = False


@runtime_checkable
class SourceAdapter(Protocol):
    """Thin adapter protocol implemented by future source adapters."""

    descriptor: SourceDescriptor

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        """Validate request/raw/source readiness without parsing payloads."""
        ...

    def read_raw(self, request: SourceIngestRequest) -> RawReadResult:
        """Read immutable raw assets or cache-permitted API payloads."""
        ...

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        """Convert raw payload into normalized observations."""
        ...
