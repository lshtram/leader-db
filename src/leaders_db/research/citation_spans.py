"""Deterministic paragraph spans within immutable extracted source units."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CitationSpan(BaseModel):
    """One exact substring address within an extracted source unit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["citation_span_v1"] = "citation_span_v1"
    offset_unit: Literal["unicode_code_point"] = "unicode_code_point"
    hash_encoding: Literal["utf-8"] = "utf-8"
    unit: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_offsets(self) -> CitationSpan:
        if self.end_char <= self.start_char:
            raise ValueError("citation span offsets must be ordered")
        return self


class CitationSpanMeasurement(BaseModel):
    """Size measurements for one immutable extraction collection."""

    model_config = ConfigDict(extra="forbid")

    document_count: int = Field(ge=1)
    unit_count: int = Field(ge=1)
    unit_character_count: int = Field(ge=1)
    paragraph_span_count: int = Field(ge=1)
    paragraph_character_count: int = Field(ge=1)
    units_over_5000_characters: int = Field(ge=0)
    paragraphs_over_5000_characters: int = Field(ge=0)


def paragraph_spans(unit: int, text: str) -> tuple[CitationSpan, ...]:
    """Address nonblank paragraphs without normalizing or rewriting source text."""

    spans = []
    separators = tuple(
        re.finditer(r"(?:\r\n|\n)[^\S\r\n]*(?:(?:\r\n|\n))+", text)
    )
    boundaries = [0, *(match.end() for match in separators)]
    ends = [*(match.start() for match in separators), len(text)]
    for raw_start, raw_end in zip(boundaries, ends, strict=True):
        segment = text[raw_start:raw_end]
        if not segment.strip():
            continue
        leading = len(segment) - len(segment.lstrip())
        trailing = len(segment.rstrip())
        start = raw_start + leading
        end = raw_start + trailing
        exact = text[start:end]
        spans.append(
            CitationSpan(
                unit=unit,
                start_char=start,
                end_char=end,
                text_sha256=sha256(exact.encode()).hexdigest(),
            )
        )
    return tuple(spans)


def resolve_citation_span(text: str, span: CitationSpan) -> str:
    """Resolve one address and reject any offset or source-text mismatch."""

    if span.end_char > len(text):
        raise ValueError("citation span exceeds its source unit")
    exact = text[span.start_char : span.end_char]
    if sha256(exact.encode()).hexdigest() != span.text_sha256:
        raise ValueError("citation span hash does not match its source unit")
    return exact


def measure_extraction_paragraphs(extracted_dir: Path) -> CitationSpanMeasurement:
    """Measure paragraph granularity across frozen extraction JSON files."""

    paths = sorted(extracted_dir.glob("*.json"))
    unit_lengths = []
    paragraph_lengths = []
    for path in paths:
        payload = json.loads(path.read_text())
        seen_units = set()
        for row in payload["units"]:
            unit = row.get("unit")
            text = row.get("text")
            if type(unit) is not int or unit < 1 or unit in seen_units:
                raise ValueError("extraction contains invalid or duplicate unit IDs")
            if not isinstance(text, str):
                raise ValueError("extraction unit text must be a string")
            seen_units.add(unit)
            unit_lengths.append(len(text))
            paragraph_lengths.extend(
                len(resolve_citation_span(text, span))
                for span in paragraph_spans(unit, text)
            )
    if not unit_lengths or not paragraph_lengths:
        raise ValueError("extraction collection contains no measurable source text")
    return CitationSpanMeasurement(
        document_count=len(paths),
        unit_count=len(unit_lengths),
        unit_character_count=sum(unit_lengths),
        paragraph_span_count=len(paragraph_lengths),
        paragraph_character_count=sum(paragraph_lengths),
        units_over_5000_characters=sum(length > 5_000 for length in unit_lengths),
        paragraphs_over_5000_characters=sum(
            length > 5_000 for length in paragraph_lengths
        ),
    )


__all__ = [
    "CitationSpan",
    "CitationSpanMeasurement",
    "measure_extraction_paragraphs",
    "paragraph_spans",
    "resolve_citation_span",
]
