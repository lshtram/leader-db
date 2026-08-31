import json
from pathlib import Path

import pytest

from leaders_db.research.citation_spans import (
    measure_extraction_paragraphs,
    paragraph_spans,
    resolve_citation_span,
)

ROOT = Path.cwd()


def test_paragraph_spans_resolve_exact_source_substrings() -> None:
    text = "First paragraph.\nStill first.\n\n Second paragraph. \n\n\nThird."
    spans = paragraph_spans(7, text)

    assert [resolve_citation_span(text, span) for span in spans] == [
        "First paragraph.\nStill first.",
        "Second paragraph.",
        "Third.",
    ]
    assert all(span.unit == 7 for span in spans)


def test_citation_span_rejects_changed_source_text() -> None:
    text = "An immutable source paragraph."
    span = paragraph_spans(1, text)[0]

    with pytest.raises(ValueError, match="hash does not match"):
        resolve_citation_span("An immutablX source paragraph.", span)


def test_paragraph_spans_support_crlf_unicode_and_blank_inputs() -> None:
    text = "\r\nFirst 😀 e\u0301.\r\n \t\r\nSecond.\r\n\r\n"
    spans = paragraph_spans(2, text)

    assert [resolve_citation_span(text, span) for span in spans] == [
        "First 😀 e\u0301.",
        "Second.",
    ]
    assert spans[0].offset_unit == "unicode_code_point"
    assert spans[0].hash_encoding == "utf-8"
    assert paragraph_spans(1, "") == ()
    assert paragraph_spans(1, " \t\r\n\u2003") == ()


def test_measurement_rejects_malformed_extraction_rows(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    path = extracted / "source.json"
    path.write_text(
        json.dumps({"units": [{"unit": 1, "text": "Valid."}, {"unit": 1, "text": "Duplicate."}]})
    )

    with pytest.raises(ValueError, match="duplicate unit"):
        measure_extraction_paragraphs(extracted)

    path.write_text(json.dumps({"units": [{"unit": 1, "text": 42}]}))
    with pytest.raises(ValueError, match="must be a string"):
        measure_extraction_paragraphs(extracted)


def test_real_extraction_paragraph_measurement_is_internally_consistent() -> None:
    extracted = ROOT / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/acquisition/extracted"
    measurement = measure_extraction_paragraphs(extracted)

    assert measurement.document_count > 0
    assert measurement.paragraph_span_count >= measurement.unit_count
    assert measurement.paragraph_character_count <= measurement.unit_character_count
    assert measurement.paragraphs_over_5000_characters <= measurement.units_over_5000_characters
