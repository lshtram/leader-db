"""Isolated exact-line prototype for table-shaped citation granularity."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TableLineSpan(BaseModel):
    """One exact nonblank physical line in an immutable extracted unit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["table_line_span_v1"] = "table_line_span_v1"
    offset_unit: Literal["unicode_code_point"] = "unicode_code_point"
    hash_encoding: Literal["utf-8"] = "utf-8"
    source_id: str = Field(min_length=1)
    unit: int = Field(ge=1)
    line_number: int = Field(ge=1)
    kind: Literal["table_row", "context_line"]
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_offsets(self) -> TableLineSpan:
        if self.end_char <= self.start_char:
            raise ValueError("table line offsets must be ordered")
        return self


class TableLineCoverage(BaseModel):
    """Coverage and size measurement for one collection of extracted units."""

    model_config = ConfigDict(extra="forbid")

    unit_count: int = Field(ge=1)
    source_character_count: int = Field(ge=0)
    nonblank_character_count: int = Field(ge=0)
    represented_nonblank_character_count: int = Field(ge=0)
    selected_line_character_count: int = Field(ge=0)
    unrepresented_whitespace_character_count: int = Field(ge=0)
    table_row_count: int = Field(ge=0)
    context_line_count: int = Field(ge=0)
    largest_line_characters: int = Field(ge=0)
    lines_over_5000_characters: int = Field(ge=0)


_NUMBER = re.compile(r"(?<![\w.])(?:\d[\d,.]*|\.\.)(?![\w.])")


def table_line_spans(source_id: str, unit: int, text: str) -> tuple[TableLineSpan, ...]:
    """Address all nonblank lines; flag numeric candidate rows heuristically."""

    if not source_id.strip():
        raise ValueError("table line source ID must be nonblank")
    if unit < 1:
        raise ValueError("table line unit must be positive")
    if not isinstance(text, str):
        raise TypeError("table line source text must be a string")
    spans = []
    cursor = 0
    for line_number, physical_line in enumerate(text.splitlines(keepends=True), start=1):
        content = physical_line.rstrip("\r\n")
        leading = len(content) - len(content.lstrip())
        trailing = len(content.rstrip())
        if trailing > leading:
            start = cursor + leading
            end = cursor + trailing
            exact = text[start:end]
            spans.append(TableLineSpan(
                source_id=source_id,
                unit=unit,
                line_number=line_number,
                kind="table_row" if len(_NUMBER.findall(exact)) >= 2 else "context_line",
                start_char=start,
                end_char=end,
                text_sha256=sha256(exact.encode()).hexdigest(),
            ))
        cursor += len(physical_line)
    return tuple(spans)


def resolve_table_line(
    text: str,
    span: TableLineSpan,
    *,
    expected_source_id: str,
    expected_unit: int,
) -> str:
    """Resolve an exact line address and reject source or offset drift."""

    if span.source_id != expected_source_id or span.unit != expected_unit:
        raise ValueError("table line source or unit identity does not match")
    if span.end_char > len(text):
        raise ValueError("table line span exceeds its source unit")
    exact = text[span.start_char : span.end_char]
    if len(exact) != span.end_char - span.start_char:
        raise ValueError("table line span length differs from its offsets")
    if sha256(exact.encode()).hexdigest() != span.text_sha256:
        raise ValueError("table line hash does not match its source unit")
    return exact


def measure_table_lines(
    source_id: str, units: tuple[tuple[int, str], ...]
) -> TableLineCoverage:
    """Measure lossless nonblank-line coverage for selected immutable units."""

    if not units:
        raise ValueError("table line measurement requires at least one unit")
    represented = []
    represented_nonblank = 0
    source_characters = 0
    nonblank_characters = 0
    table_rows = 0
    context_lines = 0
    previous_unit = 0
    for unit, text in units:
        if type(unit) is not int or unit <= previous_unit:
            raise ValueError(
                "table line measurement units must be unique, positive, and ordered"
            )
        previous_unit = unit
        spans = table_line_spans(source_id, unit, text)
        exact = [
            resolve_table_line(
                text,
                span,
                expected_source_id=source_id,
                expected_unit=unit,
            )
            for span in spans
        ]
        represented.extend(len(item) for item in exact)
        represented_nonblank += sum(
            not character.isspace() for item in exact for character in item
        )
        source_characters += len(text)
        nonblank_characters += sum(not character.isspace() for character in text)
        table_rows += sum(span.kind == "table_row" for span in spans)
        context_lines += sum(span.kind == "context_line" for span in spans)
    if represented_nonblank != nonblank_characters:
        raise ValueError("table line spans do not cover every nonblank source character")
    selected_characters = sum(represented)
    return TableLineCoverage(
        unit_count=len(units),
        source_character_count=source_characters,
        nonblank_character_count=nonblank_characters,
        represented_nonblank_character_count=represented_nonblank,
        selected_line_character_count=selected_characters,
        unrepresented_whitespace_character_count=(
            source_characters - selected_characters
        ),
        table_row_count=table_rows,
        context_line_count=context_lines,
        largest_line_characters=max(represented, default=0),
        lines_over_5000_characters=sum(length > 5_000 for length in represented),
    )


__all__ = [
    "TableLineCoverage",
    "TableLineSpan",
    "measure_table_lines",
    "resolve_table_line",
    "table_line_spans",
]
