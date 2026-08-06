from __future__ import annotations

import json
from pathlib import Path

from leaders_db.research.corpus_judge_package import build_corpus_judge_package


def test_judge_package_stores_evidence_once_and_maps_it_to_several_questions(
    tmp_path: Path,
) -> None:
    batch = tmp_path / "reading/BATCH-0001"
    batch.mkdir(parents=True)
    evidence = {
        "evidence_id": "BATCH-0001-E001",
        "source_id": "SRC-1",
        "url": "https://example.test/report",
        "title": "Report",
        "publisher": "Publisher",
        "raw_sha256": "a" * 64,
        "fact_summary": "The policy changed implementation in 2023.",
        "question_ids": ["5B.1", "8B.6"],
        "polarity": "mixed",
        "period_fit": "target year",
        "ruler_attribution": "national policy",
        "limitations": [],
        "start_unit": 1,
        "end_unit": 1,
        "locator": "page 1",
        "exact_excerpt": "Exact source text.",
        "excerpt_sha256": "b" * 64,
        "verification_status": "accepted",
        "verification_notes": [],
    }
    (batch / "verified-evidence.json").write_text(
        json.dumps([evidence]), encoding="utf-8"
    )

    output = build_corpus_judge_package(
        tmp_path / "reading", tmp_path / "judge-package.json"
    )
    package = json.loads(output.read_text(encoding="utf-8"))
    questions = {item["methodology_id"]: item for item in package["questions"]}

    assert len(package["evidence"]) == 1
    assert questions["5B.1"]["evidence_ids"] == ["BATCH-0001-E001"]
    assert questions["8B.6"]["evidence_ids"] == ["BATCH-0001-E001"]


def test_judge_package_combines_main_and_repair_reading_dirs(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main/BATCH-0001"
    repair = tmp_path / "repair/BATCH-0002-R01"
    main.mkdir(parents=True)
    repair.mkdir(parents=True)
    evidence = {
        "source_id": "SRC-1",
        "url": "https://example.test/report",
        "title": "Report",
        "publisher": "Publisher",
        "raw_sha256": "a" * 64,
        "fact_summary": "A material fact.",
        "question_ids": ["1B.1"],
        "polarity": "mixed",
        "period_fit": "target year",
        "ruler_attribution": "national policy",
        "limitations": [],
        "start_unit": 1,
        "end_unit": 1,
        "locator": "page 1",
        "exact_excerpt": "Exact source text.",
        "excerpt_sha256": "b" * 64,
        "verification_status": "accepted",
        "verification_notes": [],
    }
    for directory, evidence_id in ((main, "E-1"), (repair, "E-2")):
        payload = {**evidence, "evidence_id": evidence_id}
        (directory / "verified-evidence.json").write_text(
            json.dumps([payload]), encoding="utf-8"
        )

    output = build_corpus_judge_package(
        tmp_path / "main",
        tmp_path / "package.json",
        additional_reading_dirs=(tmp_path / "repair",),
    )
    package = json.loads(output.read_text(encoding="utf-8"))

    assert {item["evidence_id"] for item in package["evidence"]} == {"E-1", "E-2"}
