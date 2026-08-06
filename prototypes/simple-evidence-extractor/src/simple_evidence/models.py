"""Small validated data contracts for the standalone extractor."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CHAPTER_IDS = frozenset(f"{number}B" for number in range(1, 9))
PERIOD_FITS = frozenset({"target", "pre_period", "post_period", "mixed", "unknown"})
FACT_TYPES = frozenset(
    {
        "observed_fact",
        "source_finding",
        "allegation",
        "recommendation",
        "forecast",
        "commitment",
        "context",
        "rejected",
        "unknown",
    }
)


def require_text(value: object, field_name: str) -> str:
    """Return a non-empty string or raise a field-specific error."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpec(StrictModel):
    """One allowlisted local source."""

    source_id: str
    title: str
    extracted_text_path: str
    original_file_path: str | None = None
    publisher: str = "unknown"
    publication_date: str = "unknown"
    source_role: str = "unknown"
    source_family: str = "unknown"

    @field_validator("source_id", "title", "extracted_text_path")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return require_text(value, info.field_name)


class SourceManifest(StrictModel):
    """Resolved ruler-period and source inventory."""

    ruler: str
    country_iso3: str
    target_period: str
    sources: tuple[SourceSpec, ...]

    @field_validator("ruler", "country_iso3", "target_period")
    @classmethod
    def validate_identity_text(cls, value: str, info: Any) -> str:
        return require_text(value, info.field_name)

    @model_validator(mode="after")
    def validate_sources(self) -> SourceManifest:
        if not self.sources:
            raise ValueError("sources must be non-empty")
        ids = [item.source_id for item in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be unique")
        return self


class Sentence(StrictModel):
    """Exact addressable source span."""

    sentence_id: int
    locator: str
    start_char: int
    end_char: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        result = self.model_dump()
        result["sentence_id"] = format_sentence_id(self.sentence_id)
        return result


class PreparedSource(StrictModel):
    """Hash-bound source with deterministic sentence addresses."""

    spec: SourceSpec
    extracted_sha256: str
    original_sha256: str | None
    locator_texts: tuple[tuple[str, str], ...]
    sentences: tuple[Sentence, ...]


class FactState(StrictModel):
    """Latest reconstructed state of one registry entity."""

    fact_id: str
    source_id: str
    start_sentence: int
    end_sentence: int
    summary: str
    excerpt: str
    locator: str
    start_char: int
    end_char: int
    source_sha256: str
    attempts: int = 1
    reviewer_attempts: int = 0
    fact_type: str = "unknown"
    period_fit: str = "unknown"
    chapters: list[str] = Field(default_factory=list)
    extractor_confirmed: bool = False
    reviewer_confirmed: bool = False
    disposition: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        value = self.model_dump()
        value["start_sentence"] = format_sentence_id(self.start_sentence)
        value["end_sentence"] = format_sentence_id(self.end_sentence)
        return value


class AccessScope(StrictModel):
    """Runner-owned authority granted to one model invocation."""

    role: Literal["extractor", "reviewer"]
    window_id: str
    source_id: str
    start_sentence: int
    end_sentence: int
    fact_ids: frozenset[str] = Field(default_factory=frozenset)


class BrokerRequest(StrictModel):
    """Untrusted request accepted by the registry broker."""

    capability: str
    arguments: list[str]


class BrokerResponse(StrictModel):
    """Validated response returned across the process boundary."""

    ok: bool
    entity: dict[str, Any] | None = None
    error: str | None = None


class ModelProfileConfig(StrictModel):
    name: str
    model: str


class WorkerConfig(StrictModel):
    """Small validated worker configuration."""

    window_sentences: int = Field(default=80, ge=1)
    overlap_sentences: int = Field(default=5, ge=0)
    timeout_seconds: int = Field(default=600, ge=1)
    runner_backend: Literal["docker", "host"] = "docker"
    docker_image: str = "leaders-db-superset:6.0.0"
    profiles: tuple[ModelProfileConfig, ...] = (
        ModelProfileConfig(name="minimax-m3", model="MiniMax-M3"),
        ModelProfileConfig(name="minimax-m27", model="MiniMax-M2.7"),
    )

    @model_validator(mode="after")
    def validate_window(self) -> WorkerConfig:
        if self.overlap_sentences >= self.window_sentences:
            raise ValueError("overlap_sentences must be less than window_sentences")
        if not self.profiles:
            raise ValueError("profiles must be non-empty")
        return self


class WindowMarker(StrictModel):
    schema_version: Literal["simple_evidence_window_v2"]
    binding: str
    registry_digest: str
    source_id: str
    original_sha256: str | None
    extracted_sha256: str
    start_sentence: int
    end_sentence: int
    fact_ids: tuple[str, ...]


def parse_sentence_id(value: str | int) -> int:
    """Parse `S000001` or a positive integer."""

    text = str(value).strip().upper()
    if text.startswith("S"):
        text = text[1:]
    if not text.isdigit() or int(text) < 1:
        raise ValueError(f"invalid sentence ID: {value}")
    return int(text)


def format_sentence_id(value: int) -> str:
    return f"S{value:06d}"


def validate_chapters(values: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(item.strip().upper() for item in values if item.strip()))
    invalid = sorted(set(cleaned) - CHAPTER_IDS)
    if invalid:
        raise ValueError(f"invalid chapter IDs: {invalid}")
    return cleaned
