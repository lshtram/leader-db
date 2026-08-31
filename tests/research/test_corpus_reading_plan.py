from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.corpus_extraction import (
    load_validated_extraction,
    render_reader_unit,
)
from leaders_db.research.corpus_reader_prompt import build_corpus_reader_prompt
from leaders_db.research.corpus_reading_plan import (
    CorpusReadingPlan,
    ReadingBatch,
    ReadingPlanConfig,
    build_corpus_reading_plan,
    build_transport_repair_plan,
)


def test_reading_plan_dispositions_all_urls_and_deduplicates_content(
    tmp_path: Path,
) -> None:
    catalogue = tmp_path / "catalogue.json"
    candidates = [
        {
            "url": f"https://example.test/{index}",
            "title": f"Source {index}",
            "publisher": "Publisher",
            "document_type": "report",
            "access_status": "unopened",
            "chapter_ids": ["5B", "6B"],
        }
        for index in range(3)
    ]
    catalogue.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    records = [
        _record(candidates[0]["url"], "SRC-0", "same", 10_000),
        _record(candidates[1]["url"], "SRC-1", "same", 10_000),
        _record(candidates[2]["url"], "SRC-2", None, 0, status="access_blocked"),
    ]
    acquisition = tmp_path / "acquisition.json"
    (tmp_path / "extracted").mkdir()
    for source_id in ("SRC-0", "SRC-1"):
        (tmp_path / f"extracted/{source_id}.json").write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "raw_sha256": "same",
                    "units": [
                        {"unit": 1, "locator": "page 1", "text": "evidence"}
                    ],
                }
            ),
            encoding="utf-8",
        )
    acquisition.write_text(
        json.dumps(
            {
                "schema_version": "catalog_acquisition_manifest_v1",
                "catalogue_path": str(catalogue),
                "catalogue_sha256": "hash",
                "config": {},
                "started_at_epoch": 1,
                "completed_at_epoch": 2,
                "records": records,
            }
        ),
        encoding="utf-8",
    )

    output = build_corpus_reading_plan(
        catalogue,
        acquisition,
        tmp_path / "plan.json",
        ruler_name="Example Ruler",
        period_start_year=2023,
        period_end_year=2023,
        config=ReadingPlanConfig(target_batch_tokens=20_000),
    )
    plan = json.loads(output.read_text(encoding="utf-8"))

    assert plan["ruler_name"] == "Example Ruler"
    assert plan["period_start_year"] == 2023
    assert plan["period_end_year"] == 2023
    assert [item["status"] for item in plan["documents"]] == [
        "queued",
        "content_duplicate",
        "not_acquired",
    ]
    assert plan["documents"][1]["duplicate_of"] == "SRC-0"
    assert plan["batches"][0]["source_ids"] == ["SRC-0"]
    assert plan["batches"][0]["unit_ranges"] == {"SRC-0": [1, 1]}


def test_reading_plan_queues_every_unique_acquired_document(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalogue.json"
    candidates = [
        {
            "url": f"https://example.test/{index}",
            "title": f"Source {index}",
            "publisher": "Publisher",
            "document_type": "report",
            "access_status": "unopened",
            "chapter_ids": ["1B"],
        }
        for index in range(40)
    ]
    catalogue.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "extracted").mkdir()
    records = []
    for index, candidate in enumerate(candidates):
        source_id = f"SRC-{index}"
        (tmp_path / f"extracted/{source_id}.json").write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "raw_sha256": f"hash-{index}",
                    "units": [
                        {"unit": 1, "locator": "page 1", "text": "evidence"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        records.append(_record(candidate["url"], source_id, f"hash-{index}", 10_000))
    acquisition = tmp_path / "acquisition.json"
    acquisition.write_text(
        json.dumps(
            {
                "schema_version": "catalog_acquisition_manifest_v1",
                "catalogue_path": str(catalogue),
                "catalogue_sha256": "hash",
                "config": {},
                "started_at_epoch": 1,
                "completed_at_epoch": 2,
                "records": records,
            }
        ),
        encoding="utf-8",
    )

    output = build_corpus_reading_plan(
        catalogue,
        acquisition,
        tmp_path / "plan.json",
        ruler_name="Example Ruler",
        period_start_year=2023,
        period_end_year=2023,
        config=ReadingPlanConfig(
            target_batch_tokens=20_000,
            maximum_documents_per_batch=12,
        ),
    )
    plan = json.loads(output.read_text(encoding="utf-8"))

    assert sum(len(batch["source_ids"]) for batch in plan["batches"]) == 40
    assert {item["status"] for item in plan["documents"]} == {"queued"}


def test_reader_prompt_uses_persisted_ruler_period(tmp_path: Path) -> None:
    acquisition_dir = tmp_path / "acquisition"
    (acquisition_dir / "extracted").mkdir(parents=True)
    (acquisition_dir / "extracted/SRC-1.json").write_text(
        json.dumps(
            {
                "source_id": "SRC-1",
                "raw_sha256": "hash",
                "units": [{"unit": 1, "locator": "page 1", "text": "evidence"}],
            }
        ),
        encoding="utf-8",
    )
    plan = CorpusReadingPlan.model_validate(
        {
            "ruler_name": "Example Ruler",
            "period_start_year": 2022,
            "period_end_year": 2023,
            "config": {},
            "documents": [
                {
                    "source_id": "SRC-1",
                    "url": "https://example.test/1",
                    "title": "Source",
                    "publisher": "Publisher",
                    "document_type": "report",
                    "chapter_ids": ["1B"],
                    "status": "queued",
                    "extracted_path": "extracted/SRC-1.json",
                    "raw_sha256": "hash",
                    "estimated_tokens": 10,
                }
            ],
            "batches": [],
        }
    )
    batch = ReadingBatch(
        batch_id="BATCH-001",
        source_ids=("SRC-1",),
        unit_ranges={"SRC-1": (1, 1)},
        chapter_ids=("1B",),
        estimated_tokens=10,
    )

    prompt = build_corpus_reader_prompt(
        acquisition_dir=acquisition_dir,
        plan=plan,
        batch=batch,
        prompts_path=Path("configs/corpus-reader-prompts.yaml"),
        questions_path=Path(
            "src/leaders_db/conversational_evidence/data/questions.json"
        ),
    ).prompt

    assert "Example Ruler during 2022-2023" in prompt
    assert "Andrés Manuel López Obrador" not in prompt


def test_reading_plan_splits_on_rendered_character_budget(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalogue.json"
    candidate = {
        "url": "https://example.test/large",
        "title": "Large Source",
        "publisher": "Publisher",
        "document_type": "report",
        "access_status": "unopened",
        "chapter_ids": ["1B"],
    }
    catalogue.write_text(json.dumps({
        "schema_version": "ruler_source_candidate_catalog_v1",
        "candidates": [candidate],
    }))
    (tmp_path / "extracted").mkdir()
    (tmp_path / "extracted/SRC-1.json").write_text(json.dumps({
        "source_id": "SRC-1",
        "raw_sha256": "hash",
        "units": [
            {"unit": 1, "locator": "page 1", "text": "a" * 60_000},
            {"unit": 2, "locator": "page 2", "text": "b" * 60_000},
        ],
    }))
    acquisition = tmp_path / "acquisition.json"
    acquisition.write_text(json.dumps({
        "schema_version": "catalog_acquisition_manifest_v1",
        "catalogue_path": str(catalogue),
        "catalogue_sha256": "hash",
        "config": {},
        "started_at_epoch": 1,
        "completed_at_epoch": 2,
        "records": [_record(candidate["url"], "SRC-1", "hash", 30_000)],
    }))

    output = build_corpus_reading_plan(
        catalogue,
        acquisition,
        tmp_path / "plan.json",
        ruler_name="Example Ruler",
        period_start_year=2023,
        period_end_year=2023,
        config=ReadingPlanConfig(maximum_batch_characters=100_000),
    )
    plan = CorpusReadingPlan.model_validate_json(output.read_text())

    assert [batch.unit_ranges["SRC-1"] for batch in plan.batches] == [(1, 1), (2, 2)]
    units = load_validated_extraction(
        tmp_path / "extracted/SRC-1.json",
        expected_source_id="SRC-1",
        expected_raw_sha256="hash",
    )
    for batch in plan.batches:
        start, end = batch.unit_ranges["SRC-1"]
        content_characters = sum(
            len(render_reader_unit("SRC-1", unit)) + 2
            for unit in units
            if start <= int(unit["unit"]) <= end
        )
        assert content_characters <= plan.config.maximum_batch_characters

    combined = plan.model_copy(update={
        "config": plan.config.model_copy(update={"maximum_batch_characters": 200_000}),
        "batches": (plan.batches[0].model_copy(update={
            "unit_ranges": {"SRC-1": (1, 2)},
            "estimated_tokens": 30_000,
        }),),
    })
    combined_path = tmp_path / "combined-plan.json"
    combined_path.write_text(combined.model_dump_json())
    repaired_path = build_transport_repair_plan(
        combined_path,
        tmp_path,
        tmp_path / "repair-plan.json",
        batch_ids=(combined.batches[0].batch_id,),
        maximum_document_characters=70_000,
    )
    repaired = CorpusReadingPlan.model_validate_json(repaired_path.read_text())
    assert [batch.unit_ranges["SRC-1"] for batch in repaired.batches] == [
        (1, 1),
        (2, 2),
    ]

    extraction_path = tmp_path / "extracted/SRC-1.json"
    oversized = json.loads(extraction_path.read_text())
    oversized["units"] = [
        {"unit": 1, "locator": "page 1", "text": "x" * 110_000}
    ]
    extraction_path.write_text(json.dumps(oversized))
    with pytest.raises(ValueError, match="exceeds reader character budget"):
        build_corpus_reading_plan(
            catalogue,
            acquisition,
            tmp_path / "oversized-plan.json",
            ruler_name="Example Ruler",
            period_start_year=2023,
            period_end_year=2023,
            config=ReadingPlanConfig(maximum_batch_characters=100_000),
        )


def test_reading_plan_rejects_identity_collisions() -> None:
    payload = {
        "ruler_name": "Example Ruler",
        "period_start_year": 2023,
        "period_end_year": 2023,
        "config": {},
        "documents": [
            {
                "source_id": "SRC-1", "url": "https://example.test/1",
                "title": "One", "publisher": "Publisher", "document_type": "report",
                "chapter_ids": ["1B"], "status": "queued",
                "extracted_path": "extracted/SRC-1.json", "raw_sha256": "hash",
            },
            {
                "source_id": "SRC-1", "url": "https://example.test/2",
                "title": "Two", "publisher": "Publisher", "document_type": "report",
                "chapter_ids": ["1B"], "status": "queued",
                "extracted_path": "extracted/SRC-2.json", "raw_sha256": "other",
            },
        ],
        "batches": [],
    }
    with pytest.raises(ValueError, match="source IDs must be unique"):
        CorpusReadingPlan.model_validate(payload)


def _record(
    url: str,
    source_id: str,
    digest: str | None,
    tokens: int,
    *,
    status: str = "acquired",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "requested_url": url,
        "final_url": url,
        "status": status,
        "http_status": 200,
        "content_type": "text/html",
        "elapsed_seconds": 1,
        "raw_bytes": 100,
        "raw_sha256": digest,
        "extracted_characters": tokens * 4,
        "estimated_tokens": tokens,
        "unit_count": 1,
        "raw_path": f"raw/{source_id}.html" if status == "acquired" else None,
        "extracted_path": (
            f"extracted/{source_id}.json" if status == "acquired" else None
        ),
    }
