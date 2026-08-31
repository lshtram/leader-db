from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.research.citation_spans import (
    CitationSpan,
    paragraph_spans,
    resolve_citation_span,
)
from leaders_db.research.citation_table_rows import (
    TableLineSpan,
    measure_table_lines,
    resolve_table_line,
    table_line_spans,
)


def test_table_lines_round_trip_unicode_table_and_context() -> None:
    text = " Heading 😀 e\u0301. \r\n  60.1   71.9   Employment \r\n\r\nNote."
    spans = table_line_spans("SRC-1", 7, text)

    assert [
        resolve_table_line(
            text, span, expected_source_id="SRC-1", expected_unit=7
        )
        for span in spans
    ] == [
        "Heading 😀 e\u0301.",
        "60.1   71.9   Employment",
        "Note.",
    ]
    assert [span.kind for span in spans] == [
        "context_line",
        "table_row",
        "context_line",
    ]
    coverage = measure_table_lines("SRC-1", ((7, text),))
    assert (
        coverage.represented_nonblank_character_count
        == coverage.nonblank_character_count
    )
    assert coverage.unrepresented_whitespace_character_count > 0


def test_table_line_rejects_source_and_offset_tamper() -> None:
    text = "10.0 20.0 row"
    span = table_line_spans("SRC-1", 1, text)[0]

    with pytest.raises(ValueError, match="hash does not match"):
        resolve_table_line(
            "10.0 20.1 row",
            span,
            expected_source_id="SRC-1",
            expected_unit=1,
        )
    with pytest.raises(ValueError, match="identity does not match"):
        resolve_table_line(
            text, span, expected_source_id="SRC-OTHER", expected_unit=1
        )
    with pytest.raises(ValidationError, match="offsets must be ordered"):
        TableLineSpan.model_validate(
            span.model_dump() | {"start_char": span.end_char}
        )


def test_table_line_handles_empty_and_whitespace_units_explicitly() -> None:
    assert table_line_spans("SRC-1", 1, "") == ()
    assert table_line_spans("SRC-1", 1, " \t\r\n\u2003") == ()
    coverage = measure_table_lines("SRC-1", ((1, ""),))
    assert coverage.nonblank_character_count == 0
    assert coverage.selected_line_character_count == 0
    with pytest.raises(ValueError, match="unique, positive, and ordered"):
        measure_table_lines("SRC-1", ((1, "First"), (1, "Duplicate")))
    with pytest.raises(ValueError, match="unique, positive, and ordered"):
        measure_table_lines("SRC-1", ((2, "Later"), (1, "Earlier")))


def test_frozen_labour_table_has_small_exact_rows() -> None:
    artifact_path = Path(
        "research/runs/netanyahu-2023-cost-opt-step10-table-row-feasibility-v1/"
        "measurement.json"
    )
    artifact = json.loads(artifact_path.read_text())
    path = Path(artifact["extraction_path"])
    assert sha256(path.read_bytes()).hexdigest() == artifact["extraction_sha256"]
    predecessor = Path(artifact["predecessor_verified_evidence_path"])
    assert sha256(predecessor.read_bytes()).hexdigest() == artifact[
        "predecessor_verified_evidence_sha256"
    ]
    payload = json.loads(path.read_text())
    units = tuple(
        (number, payload["units"][number - 1]["text"])
        for number in range(artifact["unit_start"], artifact["unit_end"] + 1)
    )

    coverage = measure_table_lines(payload["source_id"], units)

    assert coverage.model_dump() == artifact["coverage"]
    assert coverage.table_row_count > 0
    assert coverage.context_line_count > 0
    assert coverage.largest_line_characters < 5_000
    assert coverage.lines_over_5000_characters == 0
    paragraphs = [
        resolve_citation_span(text, span)
        for unit, text in units
        for span in paragraph_spans(unit, text)
    ]
    assert {
        "span_count": len(paragraphs),
        "character_count": sum(len(item) for item in paragraphs),
        "largest_span_characters": max(len(item) for item in paragraphs),
    } == artifact["paragraph_baseline"]

    row_characters = 0
    selected_addresses = set()
    for item in artifact["known_fact_rows"]:
        span = TableLineSpan.model_validate(item["span"])
        text = payload["units"][span.unit - 1]["text"]
        row_characters += len(resolve_table_line(
            text,
            span,
            expected_source_id=artifact["source_id"],
            expected_unit=span.unit,
        ))
        selected_addresses.add((span.unit, span.line_number))
    assert row_characters == artifact["known_fact_measurement"]["data_row_characters"]

    context_in_selected_units = 0
    for unit in sorted({number for number, _line in selected_addresses}):
        text = payload["units"][unit - 1]["text"]
        context_in_selected_units += sum(
            len(resolve_table_line(
                text,
                span,
                expected_source_id=artifact["source_id"],
                expected_unit=unit,
            ))
            for span in table_line_spans(artifact["source_id"], unit, text)
            if span.kind == "context_line"
        )
    assert row_characters + context_in_selected_units == artifact[
        "known_fact_measurement"
    ]["data_rows_plus_all_context_lines_from_their_units"]

    paragraph_characters = 0
    for item in artifact["like_for_like_paragraph_spans"]:
        span = CitationSpan.model_validate(item)
        text = payload["units"][span.unit - 1]["text"]
        paragraph_characters += len(resolve_citation_span(text, span))
    assert paragraph_characters == artifact["known_fact_measurement"][
        "like_for_like_paragraph_characters"
    ]
    reduction = round(
        (1 - (row_characters + context_in_selected_units) / paragraph_characters)
        * 100,
        1,
    )
    assert reduction == artifact["known_fact_measurement"]["reduction_percent"]
