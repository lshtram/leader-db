"""Manifest loading and deterministic sentence addressing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .models import PreparedSource, Sentence, SourceManifest, SourceSpec

_SENTENCE_END = re.compile(r"(?<=[.!?])(?:[\"'»”)]*)\s+(?=[A-ZÁÉÍÓÚÜÑ0-9¿¡])")


def load_manifest(path: Path) -> SourceManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return SourceManifest.model_validate(payload)


def load_sources(manifest_path: Path) -> dict[str, PreparedSource]:
    manifest = load_manifest(manifest_path)
    return {
        spec.source_id: prepare_source(spec, manifest_path.parent)
        for spec in manifest.sources
    }


def prepare_source(spec: SourceSpec, manifest_root: Path) -> PreparedSource:
    extracted_path = _resolve_input(manifest_root, spec.extracted_text_path)
    raw_bytes = extracted_path.read_bytes()
    units = _read_units(extracted_path, raw_bytes)
    sentences: list[Sentence] = []
    for locator, text in units:
        sentences.extend(_unit_sentences(locator, text, len(sentences)))
    if not sentences:
        raise ValueError(f"{spec.source_id} contains no text")
    original_sha = None
    if spec.original_file_path:
        original_path = _resolve_input(manifest_root, spec.original_file_path)
        original_sha = _sha256(original_path.read_bytes())
    return PreparedSource(
        spec=spec,
        extracted_sha256=_sha256(raw_bytes),
        original_sha256=original_sha,
        locator_texts=units,
        sentences=tuple(sentences),
    )


def select_sentences(
    source: PreparedSource,
    start: int,
    end: int | None = None,
) -> tuple[Sentence, ...]:
    resolved_end = start if end is None else end
    if start < 1 or resolved_end < start or resolved_end > len(source.sentences):
        raise ValueError(
            f"sentence range must be within S000001-S{len(source.sentences):06d}"
        )
    return source.sentences[start - 1 : resolved_end]


def resolve_span(
    source: PreparedSource,
    start: int,
    end: int | None = None,
) -> tuple[str, str, int, int]:
    selected = select_sentences(source, start, end)
    locators = {item.locator for item in selected}
    if len(locators) != 1:
        raise ValueError("one fact cannot cross locator boundaries")
    locator = selected[0].locator
    source_text = dict(source.locator_texts)[locator]
    excerpt = source_text[selected[0].start_char : selected[-1].end_char]
    return locator, excerpt, selected[0].start_char, selected[-1].end_char


def source_summary(source: PreparedSource, start: int, end: int) -> dict[str, Any]:
    selected = select_sentences(source, start, end)
    return {
        "source_id": source.spec.source_id,
        "title": source.spec.title,
        "publisher": source.spec.publisher,
        "source_role": source.spec.source_role,
        "extracted_sha256": source.extracted_sha256,
        "sentences": [item.to_dict() for item in selected],
    }


def _read_units(path: Path, raw_bytes: bytes) -> tuple[tuple[str, str], ...]:
    if path.suffix.lower() == ".json":
        payload = json.loads(raw_bytes)
        if not isinstance(payload, dict) or not isinstance(payload.get("units"), list):
            raise ValueError(f"{path} must contain an object with a units list")
        units = []
        for number, item in enumerate(payload["units"], start=1):
            if not isinstance(item, dict):
                raise ValueError("source units must be objects")
            locator = str(item.get("locator") or f"unit {number}")
            text = str(item.get("text") or "")
            if text.strip():
                units.append((locator, text))
        return tuple(units)
    return ((path.name, raw_bytes.decode("utf-8")),)


def _unit_sentences(locator: str, text: str, prior_count: int) -> list[Sentence]:
    pieces: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n|\Z)", text):
        line = match.group(0)
        line_start = match.start()
        cursor = 0
        for part in _SENTENCE_END.split(line):
            stripped = part.strip()
            if not stripped:
                continue
            relative = line.find(stripped, cursor)
            start = line_start + relative
            end = start + len(stripped)
            pieces.append((start, end, stripped))
            cursor = relative + len(stripped)
    return [
        Sentence(
            sentence_id=prior_count + offset,
            locator=locator,
            start_char=start,
            end_char=end,
            text=value,
        )
        for offset, (start, end, value) in enumerate(pieces, start=1)
    ]


def _resolve_input(root: Path, value: str) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_file():
        raise ValueError(f"input file does not exist: {resolved}")
    return resolved


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
