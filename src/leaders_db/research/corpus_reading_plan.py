"""Deterministic document deduplication and bounded whole-context reading batches."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import tiktoken
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog_acquisition import CatalogAcquisitionManifest
from .corpus_extraction import load_validated_extraction, render_reader_unit
from .source_candidate_catalog import read_source_candidate_catalog


class ReadingPlanConfig(BaseModel):
    """Context controls that shape calls without dropping eligible documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_batch_tokens: int = Field(default=220_000, ge=20_000, le=300_000)
    maximum_batch_tokens: int = Field(default=280_000, ge=30_000, le=340_000)
    maximum_batch_characters: int = Field(
        default=800_000, ge=100_000, le=900_000
    )
    maximum_documents_per_batch: int = Field(default=12, ge=1, le=30)


class ReadingDocument(BaseModel):
    """One acquired document's deterministic reading disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    url: str
    title: str
    publisher: str
    document_type: str
    chapter_ids: tuple[str, ...]
    status: Literal["queued", "content_duplicate", "not_acquired", "empty_extraction"]
    duplicate_of: str | None = None
    extracted_path: str | None = None
    raw_sha256: str | None = None
    estimated_tokens: int = Field(default=0, ge=0)


class ReadingBatch(BaseModel):
    """One context-bounded group of complete extracted documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str
    source_ids: tuple[str, ...]
    unit_ranges: dict[str, tuple[int, int]]
    chapter_ids: tuple[str, ...]
    estimated_tokens: int = Field(ge=0)


class CorpusReadingPlan(BaseModel):
    """Complete, reconciled reading plan for an acquisition manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["corpus_reading_plan_v1"] = "corpus_reading_plan_v1"
    ruler_name: str = Field(min_length=1)
    period_start_year: int = Field(ge=1900, le=2100)
    period_end_year: int = Field(ge=1900, le=2100)
    config: ReadingPlanConfig
    documents: tuple[ReadingDocument, ...]
    batches: tuple[ReadingBatch, ...]

    @model_validator(mode="after")
    def validate_identities(self) -> CorpusReadingPlan:
        document_ids = [item.source_id for item in self.documents]
        batch_ids = [item.batch_id for item in self.batches]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("reading plan document source IDs must be unique")
        if len(batch_ids) != len(set(batch_ids)):
            raise ValueError("reading plan batch IDs must be unique")
        known = set(document_ids)
        for batch in self.batches:
            if len(batch.source_ids) != len(set(batch.source_ids)):
                raise ValueError("reading batch source IDs must be unique")
            if set(batch.source_ids) != set(batch.unit_ranges):
                raise ValueError("reading batch sources and unit ranges must match")
            if not set(batch.source_ids).issubset(known):
                raise ValueError("reading batch references an unknown source")
        return self


def build_corpus_reading_plan(
    catalogue_path: Path,
    acquisition_manifest_path: Path,
    output_path: Path,
    *,
    ruler_name: str,
    period_start_year: int,
    period_end_year: int,
    config: ReadingPlanConfig,
) -> Path:
    """Deduplicate acquired content and queue every representative exactly once."""

    catalogue = read_source_candidate_catalog(catalogue_path)
    manifest = CatalogAcquisitionManifest.model_validate_json(
        acquisition_manifest_path.read_text(encoding="utf-8")
    )
    candidates = {item.url: item for item in catalogue.candidates}
    records = {item.requested_url: item for item in manifest.records}
    if set(candidates) != set(records):
        raise ValueError("acquisition manifest and source catalogue URL sets differ")
    documents: list[ReadingDocument] = []
    representative_by_hash: dict[str, str] = {}
    for url, candidate in candidates.items():
        record = records[url]
        status: Literal["queued", "content_duplicate", "not_acquired", "empty_extraction"]
        duplicate_of = None
        if record.status != "acquired":
            status = "not_acquired"
        elif not record.estimated_tokens or not record.extracted_path:
            status = "empty_extraction"
        elif record.raw_sha256 in representative_by_hash:
            status = "content_duplicate"
            duplicate_of = representative_by_hash[record.raw_sha256]
        else:
            status = "queued"
            if record.raw_sha256:
                representative_by_hash[record.raw_sha256] = record.source_id
        documents.append(
            ReadingDocument(
                source_id=record.source_id,
                url=url,
                title=candidate.title,
                publisher=candidate.publisher,
                document_type=candidate.document_type,
                chapter_ids=candidate.chapter_ids,
                status=status,
                duplicate_of=duplicate_of,
                extracted_path=record.extracted_path,
                raw_sha256=record.raw_sha256,
                estimated_tokens=record.estimated_tokens,
            )
        )
    queued = sorted(
        (item for item in documents if item.status == "queued"),
        key=lambda item: (_priority(item), item.source_id),
    )
    batches = _pack_batches(queued, config, acquisition_manifest_path.parent)
    if period_end_year < period_start_year:
        raise ValueError("period end year must not precede period start year")
    plan = CorpusReadingPlan(
        ruler_name=ruler_name,
        period_start_year=period_start_year,
        period_end_year=period_end_year,
        config=config,
        documents=tuple(documents),
        batches=batches,
    )
    _write_json(output_path, plan.model_dump(mode="json"))
    return output_path


def build_transport_repair_plan(
    plan_path: Path,
    acquisition_dir: Path,
    output_path: Path,
    *,
    batch_ids: tuple[str, ...],
    maximum_document_characters: int,
) -> Path:
    """Split only transport-oversized batches without renumbering completed work."""

    plan = CorpusReadingPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    selected = [item for item in plan.batches if item.batch_id in set(batch_ids)]
    if {item.batch_id for item in selected} != set(batch_ids):
        raise ValueError("transport repair references unknown batch IDs")
    documents = {item.source_id: item for item in plan.documents}
    repairs: list[ReadingBatch] = []
    for batch in selected:
        number = 0
        for source_id in batch.source_ids:
            document = documents[source_id]
            units = load_validated_extraction(
                acquisition_dir / str(document.extracted_path),
                expected_source_id=document.source_id,
                expected_raw_sha256=str(document.raw_sha256),
            )
            lower, upper = batch.unit_ranges[source_id]
            current_start = lower
            characters = 0
            tokens = 0
            for unit in units:
                unit_number = int(unit["unit"])
                if not lower <= unit_number <= upper:
                    continue
                rendering = render_reader_unit(source_id, unit)
                unit_characters = len(rendering) + 2
                unit_tokens = len(tiktoken.get_encoding("o200k_base").encode(rendering))
                if unit_characters > maximum_document_characters:
                    raise ValueError("one extraction unit exceeds repair character budget")
                if unit_tokens > plan.config.maximum_batch_tokens:
                    raise ValueError("one extraction unit exceeds repair token budget")
                if characters and (
                    characters + unit_characters > maximum_document_characters
                    or tokens + unit_tokens > plan.config.maximum_batch_tokens
                ):
                    number += 1
                    repairs.append(
                        _repair_batch(
                            batch,
                            document,
                            number,
                            current_start,
                            unit_number - 1,
                            tokens,
                        )
                    )
                    current_start, characters, tokens = unit_number, 0, 0
                characters += unit_characters
                tokens += unit_tokens
            if characters:
                number += 1
                repairs.append(
                        _repair_batch(batch, document, number, current_start, upper, tokens)
                )
    repair_plan = CorpusReadingPlan(
        ruler_name=plan.ruler_name,
        period_start_year=plan.period_start_year,
        period_end_year=plan.period_end_year,
        config=plan.config,
        documents=plan.documents,
        batches=tuple(repairs),
    )
    _write_json(output_path, repair_plan.model_dump(mode="json"))
    return output_path


def _repair_batch(
    parent: ReadingBatch,
    document: ReadingDocument,
    number: int,
    start: int,
    end: int,
    tokens: int,
) -> ReadingBatch:
    return ReadingBatch(
        batch_id=f"{parent.batch_id}-R{number:02d}",
        source_ids=(document.source_id,),
        unit_ranges={document.source_id: (start, end)},
        chapter_ids=parent.chapter_ids,
        estimated_tokens=tokens,
    )


def _priority(document: ReadingDocument) -> tuple[int, int, int]:
    kind = document.document_type.casefold()
    source_rank = 0 if any(word in kind for word in ("book", "academic", "report")) else 1
    return source_rank, -len(document.chapter_ids), document.estimated_tokens


def _pack_batches(
    documents: list[ReadingDocument],
    config: ReadingPlanConfig,
    acquisition_dir: Path,
) -> tuple[ReadingBatch, ...]:
    batches: list[ReadingBatch] = []
    slices = [
        item
        for document in documents
        for item in _document_slices(document, acquisition_dir, config)
    ]
    current: list[tuple[ReadingDocument, int, int, int, int]] = []
    tokens = 0
    characters = 0
    for item in slices:
        _, _, _, slice_tokens, slice_characters = item
        would_exceed = (
            current
            and (
                tokens + slice_tokens > config.target_batch_tokens
                or characters + slice_characters > config.maximum_batch_characters
                or len(current) >= config.maximum_documents_per_batch
            )
        )
        if would_exceed:
            batches.append(_batch(len(batches) + 1, current))
            current, tokens, characters = [], 0, 0
        current.append(item)
        tokens += slice_tokens
        characters += slice_characters
    if current:
        batches.append(_batch(len(batches) + 1, current))
    return tuple(batches)


def _document_slices(
    document: ReadingDocument,
    acquisition_dir: Path,
    config: ReadingPlanConfig,
) -> list[tuple[ReadingDocument, int, int, int, int]]:
    units = load_validated_extraction(
        acquisition_dir / str(document.extracted_path),
        expected_source_id=document.source_id,
        expected_raw_sha256=str(document.raw_sha256),
    )
    slices = []
    start = 1
    tokens = 0
    characters = 0
    for unit in units:
        rendering = render_reader_unit(document.source_id, unit)
        unit_tokens = len(tiktoken.get_encoding("o200k_base").encode(rendering))
        unit_characters = len(rendering) + 2
        if unit_tokens > config.maximum_batch_tokens:
            raise ValueError("one extraction unit exceeds reader token budget")
        if unit_characters > config.maximum_batch_characters:
            raise ValueError("one extraction unit exceeds reader character budget")
        if tokens and (
            tokens + unit_tokens > config.maximum_batch_tokens
            or characters + unit_characters > config.maximum_batch_characters
        ):
            slices.append(
                (document, start, int(unit["unit"]) - 1, tokens, characters)
            )
            start, tokens, characters = int(unit["unit"]), 0, 0
        tokens += unit_tokens
        characters += unit_characters
    if units:
        slices.append(
            (document, start, int(units[-1]["unit"]), tokens, characters)
        )
    return slices


def _batch(
    number: int, documents: list[tuple[ReadingDocument, int, int, int, int]]
) -> ReadingBatch:
    chapters = sorted(
        {chapter for item, _, _, _, _ in documents for chapter in item.chapter_ids}
    )
    return ReadingBatch(
        batch_id=f"BATCH-{number:04d}",
        source_ids=tuple(item.source_id for item, _, _, _, _ in documents),
        unit_ranges={
            item.source_id: (start, end) for item, start, end, _, _ in documents
        },
        chapter_ids=tuple(chapters),
        estimated_tokens=sum(tokens for _, _, _, tokens, _ in documents),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    with temporary.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


__all__ = [
    "CorpusReadingPlan",
    "ReadingPlanConfig",
    "build_corpus_reading_plan",
    "build_transport_repair_plan",
]
