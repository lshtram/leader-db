from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.corpus_evidence_bind import bind_batch_evidence
from leaders_db.research.corpus_reader_models import BatchFactOutput
from leaders_db.research.corpus_reading_plan import CorpusReadingPlan


def test_binding_copies_exact_units_and_rejects_unaccounted_sources(tmp_path: Path) -> None:
    acquisition = tmp_path / "acquisition"
    (acquisition / "extracted").mkdir(parents=True)
    (acquisition / "extracted/SRC-1.json").write_text(
        json.dumps(
            {
                "units": [
                    {"unit": 1, "locator": "page 1", "text": "Exact first passage."},
                    {"unit": 2, "locator": "page 2", "text": "Exact second passage."},
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = CorpusReadingPlan.model_validate(
        {
            "config": {},
            "documents": [
                {
                    "source_id": "SRC-1",
                    "url": "https://example.test/report",
                    "title": "Report",
                    "publisher": "Publisher",
                    "document_type": "report",
                    "chapter_ids": ["5B"],
                    "status": "queued",
                    "extracted_path": "extracted/SRC-1.json",
                    "raw_sha256": "abc",
                    "estimated_tokens": 10,
                }
            ],
            "batches": [
                {
                    "batch_id": "BATCH-0001",
                    "source_ids": ["SRC-1"],
                    "unit_ranges": {"SRC-1": [1, 2]},
                    "chapter_ids": ["5B"],
                    "estimated_tokens": 10,
                }
            ],
        }
    )
    output = BatchFactOutput.model_validate(
        {
            "facts": [
                {
                    "source_id": "SRC-1",
                    "start_unit": 1,
                    "end_unit": 2,
                    "fact_summary": "The report documents a material fact.",
                    "question_ids": ["5B.1", "5B.2"],
                    "polarity": "mixed",
                    "period_fit": "target year",
                    "ruler_attribution": "national policy responsibility",
                }
            ],
            "documents_with_no_material_fact": [],
        }
    )

    evidence = bind_batch_evidence(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        reader_output=output,
    )

    assert evidence[0].exact_excerpt == "Exact first passage.\n\nExact second passage."
    assert evidence[0].locator == "page 1 through page 2"
    assert evidence[0].question_ids == ("5B.1", "5B.2")

    contradictory = output.model_copy(
        update={"documents_with_no_material_fact": ("SRC-1",)}
    )
    with pytest.raises(ValueError, match="contradictory"):
        bind_batch_evidence(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            reader_output=contradictory,
        )
