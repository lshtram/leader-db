"""Shared identity and unit validation for frozen corpus extractions."""

from __future__ import annotations

import json
from pathlib import Path

from .citation_spans import paragraph_spans, resolve_citation_span


def load_validated_extraction(
    path: Path, *, expected_source_id: str, expected_raw_sha256: str
) -> tuple[dict[str, object], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("document extraction must be an object")
    if payload.get("source_id") != expected_source_id:
        raise ValueError("document extraction source identity mismatch")
    if payload.get("raw_sha256") != expected_raw_sha256:
        raise ValueError("document extraction content hash mismatch")
    rows = payload.get("units")
    if not isinstance(rows, list) or not rows:
        raise ValueError("document extraction units must be a nonempty list")
    validated = []
    for expected_unit, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError("document extraction unit must be an object")
        unit, text, locator = row.get("unit"), row.get("text"), row.get("locator")
        if type(unit) is not int or unit != expected_unit:
            raise ValueError("document extraction units must be ordered and contiguous")
        if (
            not isinstance(text, str)
            or not isinstance(locator, str)
        ):
            raise ValueError("document extraction unit text and locator must be strings")
        validated.append(row)
    return tuple(validated)


def render_reader_unit(source_id: str, unit: dict[str, object]) -> str:
    """Render the whole-unit representation used in fact-discovery prompts."""

    number, text, locator = unit["unit"], unit["text"], unit["locator"]
    if type(number) is not int or not isinstance(text, str) or not isinstance(locator, str):
        raise ValueError("validated extraction unit has an invalid runtime shape")
    return f"[SOURCE={source_id} UNIT={number} LOCATOR={locator}]\n{text}"


def render_paragraph_spans(source_id: str, unit: dict[str, object]) -> str:
    """Render stable paragraph labels for citation selection during verification."""

    number, text, locator = unit["unit"], unit["text"], unit["locator"]
    if type(number) is not int or not isinstance(text, str) or not isinstance(locator, str):
        raise ValueError("validated extraction unit has an invalid runtime shape")
    return "\n\n".join(
        f"[SOURCE={source_id} SPAN_ID=U{number}-P{index} LOCATOR={locator}]\n"
        f"{resolve_citation_span(text, span)}"
        for index, span in enumerate(paragraph_spans(number, text), start=1)
    )


__all__ = ["load_validated_extraction", "render_paragraph_spans", "render_reader_unit"]
