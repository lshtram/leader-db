"""Regression tests for strict source disposition in corpus reading."""

import json
from pathlib import Path

import pytest

from leaders_db.research.corpus_reader_models import BatchFactOutput
from leaders_db.research.corpus_reader_normalize import (
    normalize_reader_output,
    reconcile_reader,
)
from leaders_db.research.corpus_reading_plan import ReadingBatch


def test_normalizer_does_not_invent_no_material_fact_disposition(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output.json"
    output.write_text(
        json.dumps(
            {
                "facts": [],
                "documents_with_no_material_fact": [],
                "batch_limitations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="reader omitted a disposition"):
        normalize_reader_output(output, {"SRC-1"})


def test_reconciliation_rejects_undispositioned_source() -> None:
    batch = ReadingBatch(
        batch_id="BATCH-0001",
        source_ids=("SRC-1",),
        unit_ranges={"SRC-1": (1, 2)},
        chapter_ids=("1B",),
        estimated_tokens=10,
    )
    reader = BatchFactOutput(facts=(), documents_with_no_material_fact=())

    with pytest.raises(ValueError, match="reader omitted a disposition"):
        reconcile_reader(reader, batch)
