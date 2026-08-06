"""Deterministic indexes and exact span resolution for frozen extractions."""

from __future__ import annotations

from collections.abc import Iterable

from .citation_models import CitationSelection, LocatorIndex, SourceSegment
from .ingest import FrozenExtraction


class CitationIndexError(ValueError):
    """A requested source, locator, or span is invalid."""


class FrozenCitationIndex:
    """Read-only exact-text index over hash-bound frozen sources."""

    def __init__(
        self,
        extractions: Iterable[FrozenExtraction],
        *,
        segment_characters: int,
    ) -> None:
        self._extractions = {item.source_id: item for item in extractions}
        self._segment_characters = segment_characters

    def locator_index(self, source_id: str, locator: str) -> LocatorIndex:
        extraction = self._source(source_id)
        unit = next(
            (item for item in extraction.units if item.locator == locator),
            None,
        )
        if unit is None:
            raise CitationIndexError(
                f"unknown locator {locator!r} for source {source_id}"
            )
        return LocatorIndex(
            source_id=source_id,
            source_sha256=extraction.raw_sha256,
            locator=locator,
            segments=_segment_text(unit.text, self._segment_characters),
        )

    def resolve(self, selection: CitationSelection) -> tuple[str, int, int]:
        index = self.locator_index(selection.source_id, selection.locator)
        if selection.source_sha256 != index.source_sha256:
            raise CitationIndexError(
                f"source hash changed for {selection.source_id}; refresh the index"
            )
        by_id = {item.segment_id: item for item in index.segments}
        try:
            start = by_id[selection.start_segment_id]
            end = by_id[selection.end_segment_id]
        except KeyError as error:
            raise CitationIndexError(
                f"unknown segment {error.args[0]!r} for {selection.locator}"
            ) from error
        if start.start_char > end.start_char:
            raise CitationIndexError("citation segments must be in source order")
        source_text = self._unit_text(selection.source_id, selection.locator)
        excerpt = source_text[start.start_char : end.end_char]
        if not excerpt:
            raise CitationIndexError("citation selection resolved to empty text")
        return excerpt, start.start_char, end.end_char

    def _source(self, source_id: str) -> FrozenExtraction:
        try:
            return self._extractions[source_id]
        except KeyError as error:
            raise CitationIndexError(f"unknown source {source_id}") from error

    def _unit_text(self, source_id: str, locator: str) -> str:
        extraction = self._source(source_id)
        return next(item.text for item in extraction.units if item.locator == locator)


def _segment_text(text: str, maximum_characters: int) -> tuple[SourceSegment, ...]:
    segments: list[SourceSegment] = []
    start = 0
    while start < len(text):
        target = min(len(text), start + maximum_characters)
        end = _preferred_boundary(text, start, target)
        segments.append(
            SourceSegment(
                segment_id=f"S{len(segments) + 1:05d}",
                start_char=start,
                end_char=end,
                text=text[start:end],
            )
        )
        start = end
    return tuple(segments)


def _preferred_boundary(text: str, start: int, target: int) -> int:
    if target == len(text):
        return target
    minimum = start + max(1, (target - start) // 2)
    for delimiter in ("\n", ". ", "; ", ", ", " "):
        boundary = text.rfind(delimiter, minimum, target)
        if boundary >= minimum:
            return boundary + len(delimiter)
    return target


__all__ = ["CitationIndexError", "FrozenCitationIndex"]
