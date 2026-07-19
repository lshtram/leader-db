from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from leaders_db.conversational_evidence.conversion import convert_batch
from leaders_db.conversational_evidence.judging import prepare_compact_inputs


def test_conversion_writes_valid_partial_projections_and_blocks_missing_identity(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    batch = tmp_path / "batch"
    catalog = tmp_path / "catalog.sqlite"
    output = tmp_path / "converted"
    _write(
        manifest,
        {
            "batch_id": "test-batch",
            "year": 2024,
            "researcher": "gpt-5.4-mini",
            "cases": [
                {"iso3": "AAA", "country": "Alpha", "ruler": "Ready Ruler"},
                {"iso3": "BBB", "country": "Beta", "ruler": "Missing Ruler"},
            ],
        },
    )
    _catalog(catalog)
    for iso3, country, ruler in (("AAA", "Alpha", "Ready Ruler"), ("BBB", "Beta", "Missing Ruler")):
        _source(batch / "outputs" / f"{iso3.lower()}-2024", country, ruler)

    report = convert_batch(manifest, batch, catalog, output)

    assert report["llm_calls"] == 0
    assert report["ready_rulers"] == 1
    assert report["blocked_rulers"] == 1
    assert report["ready_for_judging"] is False
    assert len(list((output / "projections").glob("*/*.json"))) == 8
    chapter = json.loads((output / "chapters" / "4B.json").read_text())
    assert chapter["missing_iso3"] == ["BBB"]
    assert chapter["ready_for_judging"] is False
    assert chapter["context_estimate"]["projection_count"] == 1
    assert chapter["context_estimate"]["estimated_input_tokens"] > 0
    projection = json.loads(next((output / "projections" / "4B").glob("*.json")).read_text())
    assert projection["chapter_id"] == "4B"
    assert len(projection["methodology_ids"]) == 10
    assert projection["evidence"][0]["source_confidence"] == "not_assessed"

    connection = sqlite3.connect(catalog)
    connection.execute("INSERT INTO leaders VALUES (8, 'Missing Ruler')")
    connection.execute("INSERT INTO ruler_years VALUES (12, 8, 2, 2024)")
    connection.commit()
    connection.close()
    convert_batch(manifest, batch, catalog, output)
    compact = prepare_compact_inputs(output, tmp_path / "compact", evidence_per_lens=1)
    assert len(compact["chapters"]) == 8
    assert all(item["evidence_per_lens"] == 1 for item in compact["chapters"])
    assert all(item["estimated_input_characters"] > 0 for item in compact["chapters"])


def _source(path: Path, country: str, ruler: str) -> None:
    path.mkdir(parents=True)
    question_ids = [f"{chapter}B.{lens}" for chapter in range(1, 9) for lens in range(1, 11)]
    _write(
        path / "evidence.json",
        {
            "ruler": ruler,
            "country": country,
            "year": 2024,
            "evidence": [
                {
                    "id": "E0001",
                    "title": "Title",
                    "publisher": "Publisher",
                    "date": "2024",
                    "url": "https://example.test/item",
                    "summary": "Compact cited claim.",
                }
            ],
        },
    )
    _write(
        path / "mappings.json",
        {
            "ruler": ruler,
            "country": country,
            "year": 2024,
            "questions": {
                item: {
                    "evidence_ids": ["E0001"],
                    "search_note": "Search completed with cited evidence.",
                }
                for item in question_ids
            },
        },
    )
    _write(
        path / "session.json",
        {
            "ruler": ruler,
            "country": country,
            "year": 2024,
            "completed": ["study", *question_ids],
            "pending": None,
        },
    )
    usage = {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "output_tokens": 3,
        "reasoning_output_tokens": 1,
    }
    _write(
        path / "profile.json",
        {
            "research": {"usage": usage},
            "formatter": {"usage": usage},
            "estimated_researcher_cost_usd": 0.1,
        },
    )


def _catalog(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE countries (id INTEGER PRIMARY KEY, iso3 TEXT);
        CREATE TABLE leaders (id INTEGER PRIMARY KEY, full_name TEXT);
        CREATE TABLE ruler_years (
            id INTEGER PRIMARY KEY,
            leader_id INTEGER,
            country_id INTEGER,
            year INTEGER
        );
        INSERT INTO countries VALUES (1, 'AAA'), (2, 'BBB');
        INSERT INTO leaders VALUES (7, 'Ready Ruler');
        INSERT INTO ruler_years VALUES (11, 7, 1, 2024);
    """)
    connection.commit()
    connection.close()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
