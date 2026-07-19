"""Tests for deterministic judge scope exclusions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.conversational_evidence import scope_filter


def test_scope_filter_removes_evidence_and_preserves_ledger(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class FakeProjection:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
            self.iso3 = payload["iso3"]
            self.evidence = [type("Evidence", (), item)() for item in payload["evidence"]]

        @classmethod
        def model_validate(cls, payload: dict[str, Any]) -> FakeProjection:
            return cls(payload)

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return self.payload

    monkeypatch.setattr(scope_filter, "RulerChapterProjection", FakeProjection)
    source = tmp_path / "source"
    projection = {
        "schema_version": "ruler_chapter_projection_v1",
        "job_key": "dossier:test:2024:USA:1",
        "run_key": "test",
        "iso3": "USA",
        "ruler_id": "1",
        "ruler_year_id": 1,
        "ruler_name": "Example",
        "period_start_year": 2024,
        "period_end_year": 2024,
        "chapter_id": "1B",
        "methodology_ids": ["1B.1"],
        "evidence": [
            {"evidence_id": "E1", "claim": "keep", "url": "https://example.com/1"},
            {"evidence_id": "E2", "claim": "remove", "url": "https://example.com/2"},
        ],
        "mappings": [
            {"methodology_id": "1B.1", "evidence_id": "E1"},
            {"methodology_id": "1B.1", "evidence_id": "E2"},
        ],
        "coverage": [
            {"methodology_id": "1B.1", "status": "covered", "evidence_ids": ["E1", "E2"]}
        ],
        "local_prior_summary": "not_available",
        "estimated_input_tokens": 10,
    }
    projection_path = source / "projections/1B/USA-1.json"
    projection_path.parent.mkdir(parents=True)
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    (source / "chapters").mkdir()
    (source / "chapters/1B.json").write_text(
        json.dumps({"chapter_id": "1B", "projection_paths": [str(projection_path)]}),
        encoding="utf-8",
    )
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text(
        json.dumps({"exclusions": {"1B": {"USA": ["E2", "E9"]}}}), encoding="utf-8"
    )

    report = scope_filter.filter_scope(source, tmp_path / "output", exclusions)
    payload = json.loads((tmp_path / "output/projections/1B/USA-1.json").read_text())
    assert [item["evidence_id"] for item in payload["evidence"]] == ["E1"]
    assert report["chapters"][0]["ledger"][0]["requested_but_absent_ids"] == ["E9"]
