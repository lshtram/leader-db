"""Tolerant normalization of whole-context reader content."""

from __future__ import annotations

import json
from pathlib import Path

from .corpus_reader_models import BatchFactOutput, FactIntent
from .corpus_reading_plan import ReadingBatch


def normalize_reader_output(
    output_path: Path, expected_source_ids: set[str]
) -> BatchFactOutput:
    """Preserve individually valid facts from an imperfect reader envelope."""

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    valid_facts = []
    warnings = list(payload.get("batch_limitations", []))
    for index, item in enumerate(payload.get("facts", [])):
        try:
            fact = FactIntent.model_validate(item)
        except ValueError as exc:
            warnings.append(f"reader fact row {index} omitted during normalization: {exc}")
            continue
        if fact.source_id not in expected_source_ids:
            warnings.append(f"reader fact row {index} cited a source outside the batch")
            continue
        valid_facts.append(fact)
    fact_sources = {item.source_id for item in valid_facts}
    no_fact = {
        str(item)
        for item in payload.get("documents_with_no_material_fact", [])
        if str(item) in expected_source_ids and str(item) not in fact_sources
    }
    missing = expected_source_ids - fact_sources - no_fact
    if missing:
        raise ValueError(_reopen_warning(missing))
    normalized = BatchFactOutput(
        facts=tuple(valid_facts),
        documents_with_no_material_fact=tuple(sorted(no_fact)),
        batch_limitations=tuple(warnings),
    )
    (output_path.parent / "normalization.json").write_text(
        normalized.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return normalized


def reconcile_reader(reader: BatchFactOutput, batch: ReadingBatch) -> BatchFactOutput:
    """Remove only facts outside the immutable batch source/unit envelope."""

    expected = set(batch.source_ids)
    warnings = list(reader.batch_limitations)
    facts = []
    for fact in reader.facts:
        unit_range = batch.unit_ranges.get(fact.source_id)
        if (
            fact.source_id not in expected
            or unit_range is None
            or fact.start_unit < unit_range[0]
            or fact.end_unit > unit_range[1]
        ):
            warnings.append(
                f"fact omitted because its source or unit range was outside {batch.batch_id}: "
                f"{fact.source_id} {fact.start_unit}-{fact.end_unit}"
            )
            continue
        facts.append(fact)
    fact_sources = {item.source_id for item in facts}
    no_fact = (set(reader.documents_with_no_material_fact) & expected) - fact_sources
    missing = expected - fact_sources - no_fact
    if missing:
        raise ValueError(_reopen_warning(missing))
    return BatchFactOutput(
        facts=tuple(facts),
        documents_with_no_material_fact=tuple(sorted(no_fact)),
        batch_limitations=tuple(warnings),
    )


def _reopen_warning(source_ids: set[str]) -> str:
    return (
        "sources requiring targeted reopen because the reader omitted a disposition: "
        + ", ".join(sorted(source_ids))
    )


__all__ = ["normalize_reader_output", "reconcile_reader"]
