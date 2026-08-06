from __future__ import annotations

import json
from pathlib import Path

from leaders_db.research.corpus_reader_runner import _reader_prompt
from leaders_db.research.corpus_reading_plan import (
    CorpusReadingPlan,
    ReadingBatch,
    ReadingPlanConfig,
    build_corpus_reading_plan,
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
                {"units": [{"unit": 1, "locator": "page 1", "text": "evidence"}]}
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
                {"units": [{"unit": 1, "locator": "page 1", "text": "evidence"}]}
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
            {"units": [{"unit": 1, "locator": "page 1", "text": "evidence"}]}
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

    prompt = _reader_prompt(acquisition_dir, plan, batch)

    assert "Example Ruler during 2022-2023" in prompt
    assert "Andrés Manuel López Obrador" not in prompt


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
