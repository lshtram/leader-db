"""Configuration and deterministic helpers for the long-document reader experiment."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA_PATH = Path(__file__).with_name("data") / "document_reader_experiment.json"

AccessState = Literal[
    "open_machine_readable",
    "open_browser_only",
    "metadata_only",
    "paywall_or_login",
    "bot_or_javascript_challenge",
    "robots_denied",
    "transient_failure",
    "unavailable",
]


class DocumentPackItem(BaseModel):
    """One frozen source and its reader routing metadata."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    document_type: str = Field(min_length=1)
    source_role: str = Field(min_length=1)


class ContentAcceptance(BaseModel):
    """Content-quality thresholds; serialization is deliberately excluded."""

    model_config = ConfigDict(extra="forbid")

    minimum_decisive_fact_recall: float = Field(ge=0, le=1)
    minimum_usable_locator_rate: float = Field(ge=0, le=1)
    fabricated_accepted_claims_allowed: int = Field(ge=0)
    format_errors_are_quality_failures: bool


class DocumentReaderConfig(BaseModel):
    """Versioned scientific and execution configuration for one reader experiment."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    chapter_id: str = Field(pattern=r"^[1-8]B$")
    reader_ladder: tuple[str, ...] = Field(min_length=1)
    baseline_reader: str = Field(min_length=1)
    reading_brief_model: str = Field(min_length=1)
    compiler: str = Field(min_length=1)
    normalizer: str = Field(min_length=1)
    content_auditor: str = Field(min_length=1)
    chunk_target_tokens: int = Field(gt=0)
    chunk_max_tokens: int = Field(gt=0)
    chunk_overlap_tokens: int = Field(ge=0)
    calibration_document_ids: tuple[str, ...] = Field(min_length=1)
    document_pack: tuple[DocumentPackItem, ...] = Field(min_length=1)
    fallbacks: dict[str, tuple[str, ...]]
    summary_target_tokens: dict[str, int]
    document_type_guidance: dict[str, str]
    reader_prompt: str = Field(min_length=1)
    normalizer_prompt: str = Field(min_length=1)
    compiler_prompt: str = Field(min_length=1)
    content_acceptance: ContentAcceptance

    @model_validator(mode="after")
    def _validate_cross_references(self) -> DocumentReaderConfig:
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("chunk target cannot exceed chunk maximum")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("chunk overlap must be smaller than the target")
        source_ids = [item.source_id for item in self.document_pack]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("document pack source IDs must be unique")
        if not set(self.calibration_document_ids).issubset(source_ids):
            raise ValueError("calibration documents must belong to the frozen pack")
        document_types = {item.document_type for item in self.document_pack}
        if document_types != set(self.summary_target_tokens):
            raise ValueError("every and only configured document types need token targets")
        if document_types != set(self.document_type_guidance):
            raise ValueError("every and only configured document types need guidance")
        if self.content_acceptance.format_errors_are_quality_failures:
            raise ValueError("reader content experiments cannot score formatting as quality")
        return self


class SourceMapClaim(BaseModel):
    """One atomic claim recovered from a document by a reader or normalizer."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    claim_kind: Literal[
        "observed_fact",
        "source_assertion",
        "interpretation",
        "allegation",
        "recommendation",
    ]
    locator: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    lens_ids: tuple[str, ...] = Field(min_length=1)
    period_fit: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    limitations: tuple[str, ...]
    contrary_or_corroboration_needed: tuple[str, ...]


class DocumentSourceMap(BaseModel):
    """Compact, traceable intermediate representation of one underlying document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["document_source_map_v1"]
    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_incentives_and_bias: tuple[str, ...]
    claims: tuple[SourceMapClaim, ...]
    unresolved_sections: tuple[str, ...]
    reopen_requests: tuple[str, ...]


class ReaderSummaryEnvelope(BaseModel):
    """Lossless JSON organization for format-variable reader content."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reader_summary_envelope_v1"]
    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    reader_model: str = Field(min_length=1)
    reader_output: str = Field(min_length=1)
    claimed_locator_numbers: tuple[int, ...]
    normalization_method: Literal["lossless_deterministic_envelope"]


class ReaderContentAudit(BaseModel):
    """High-quality audit of reader content after format-only normalization."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reader_content_audit_v1"]
    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    supported_claim_count: int = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)
    usable_locator_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    material_omission: bool
    material_omission_explanation: str
    content_usable: bool
    content_failure_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_counts(self) -> ReaderContentAudit:
        if self.supported_claim_count + self.unsupported_claim_count > self.claim_count:
            raise ValueError("audited claim counts cannot exceed total claims")
        if self.usable_locator_count > self.claim_count:
            raise ValueError("usable locators cannot exceed total claims")
        return self


class AccessAuditRecord(BaseModel):
    """One reproducible URL-access observation."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    requested_url: str = Field(min_length=1)
    final_url: str | None = None
    host: str = Field(min_length=1)
    state: AccessState
    http_status: int | None = None
    content_type: str | None = None
    bytes_sampled: int = Field(ge=0)
    robots_allowed: bool | None = None
    note: str = Field(min_length=1)


class TextChunk(BaseModel):
    """A deterministic source-text chunk with a stable locator envelope."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    start_unit: int = Field(ge=1)
    end_unit: int = Field(ge=1)
    estimated_tokens: int = Field(ge=0)
    text: str


def load_document_reader_config(path: Path = DATA_PATH) -> DocumentReaderConfig:
    """Load the single versioned document-reader experiment configuration."""

    return DocumentReaderConfig.model_validate_json(path.read_text(encoding="utf-8"))


def estimate_tokens(text: str) -> int:
    """Return a conservative tokenizer-free estimate for planning and chunking."""

    if not text:
        return 0
    return max((len(text) + 3) // 4, int(len(text.split()) * 1.5))


def chunk_units(
    units: Iterable[str],
    *,
    target_tokens: int,
    max_tokens: int,
) -> tuple[TextChunk, ...]:
    """Group page/section units without splitting their locator boundaries."""

    if target_tokens <= 0 or max_tokens < target_tokens:
        raise ValueError("invalid chunk token bounds")
    chunks: list[TextChunk] = []
    pending: list[str] = []
    pending_tokens = 0
    start_unit = 1
    for unit_number, unit in enumerate(units, start=1):
        unit_tokens = estimate_tokens(unit)
        if pending and pending_tokens + unit_tokens > target_tokens:
            chunks.append(_make_chunk(len(chunks) + 1, start_unit, unit_number - 1, pending))
            pending = []
            pending_tokens = 0
            start_unit = unit_number
        if unit_tokens > max_tokens:
            raise ValueError(f"unit {unit_number} exceeds chunk maximum; split at extraction")
        pending.append(unit)
        pending_tokens += unit_tokens
    if pending:
        chunks.append(
            _make_chunk(
                len(chunks) + 1,
                start_unit,
                start_unit + len(pending) - 1,
                pending,
            )
        )
    return tuple(chunks)


def render_reader_prompt(
    config: DocumentReaderConfig,
    item: DocumentPackItem,
    *,
    reading_brief: str,
) -> str:
    """Render the shared content prompt for either reader arm."""

    return "\n\n".join(
        (
            config.reader_prompt.format(
                summary_target_tokens=config.summary_target_tokens[item.document_type]
            ),
            f"Document type: {item.document_type}",
            f"Source role: {item.source_role}",
            f"Document-type guidance: {config.document_type_guidance[item.document_type]}",
            f"Reading brief:\n{reading_brief}",
        )
    )


def extract_json_object(value: str) -> dict[str, object] | None:
    """Recover a JSON object when present without treating failure as content failure."""

    candidates = [value.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = value.find("{")
    last = value.rfind("}")
    if first >= 0 and last > first:
        candidates.append(value[first : last + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def classify_access_response(
    *,
    source_id: str,
    requested_url: str,
    status_code: int | None,
    final_url: str | None,
    content_type: str | None,
    sampled_body: bytes,
    robots_allowed: bool | None,
    error: str | None = None,
) -> AccessAuditRecord:
    """Classify an HTTP observation without bypassing access restrictions."""

    host = urlparse(requested_url).netloc or "unknown"
    body = sampled_body.decode("utf-8", errors="ignore").casefold()
    if robots_allowed is False:
        state: AccessState = "robots_denied"
        note = "robots policy did not permit automated retrieval"
    elif error is not None:
        state = "transient_failure"
        note = error
    elif status_code in {401, 402, 403}:
        state = (
            "paywall_or_login"
            if any(marker in body for marker in ("subscribe", "suscríb", "login", "sign in"))
            else "bot_or_javascript_challenge"
        )
        note = f"restricted HTTP response {status_code}"
    elif status_code == 429 or (status_code is not None and status_code >= 500):
        state = "transient_failure"
        note = f"retryable HTTP response {status_code}"
    elif status_code is None or status_code >= 400:
        state = "unavailable"
        note = f"HTTP response {status_code}"
    elif (final_url and "error_404" in final_url.casefold()) or body.lstrip().startswith(
        "error 404"
    ):
        state = "unavailable"
        note = "successful transport resolved to an application-level 404 page"
    elif any(
        marker in body
        for marker in (
            "enable javascript",
            "verify you are human",
            "checking your browser",
            "captcha",
        )
    ):
        state = "bot_or_javascript_challenge"
        note = "challenge or JavaScript interstitial detected"
    elif any(marker in body for marker in ("subscribe to continue", "inicia sesión para")):
        state = "paywall_or_login"
        note = "paywall or login marker detected"
    elif content_type and (
        "application/pdf" in content_type.casefold()
        or "text/html" in content_type.casefold()
        or "text/plain" in content_type.casefold()
    ):
        state = "open_machine_readable"
        note = "readable response type sampled"
    else:
        state = "metadata_only"
        note = "response opened but no supported full-text type was established"
    return AccessAuditRecord(
        source_id=source_id,
        requested_url=requested_url,
        final_url=final_url,
        host=host,
        state=state,
        http_status=status_code,
        content_type=content_type,
        bytes_sampled=len(sampled_body),
        robots_allowed=robots_allowed,
        note=note,
    )


def sha256_bytes(value: bytes) -> str:
    """Hash immutable acquired or extracted source content."""

    return hashlib.sha256(value).hexdigest()


def _make_chunk(number: int, start: int, end: int, units: list[str]) -> TextChunk:
    text = "\n\n".join(units)
    return TextChunk(
        chunk_id=f"chunk-{number:04d}",
        start_unit=start,
        end_unit=end,
        estimated_tokens=estimate_tokens(text),
        text=text,
    )


__all__ = [
    "AccessAuditRecord",
    "ContentAcceptance",
    "DocumentPackItem",
    "DocumentReaderConfig",
    "DocumentSourceMap",
    "ReaderContentAudit",
    "ReaderSummaryEnvelope",
    "SourceMapClaim",
    "TextChunk",
    "chunk_units",
    "classify_access_response",
    "estimate_tokens",
    "extract_json_object",
    "load_document_reader_config",
    "render_reader_prompt",
    "sha256_bytes",
]
