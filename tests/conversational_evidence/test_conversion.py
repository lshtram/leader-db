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
            "year": 2022,
            "researcher": "gpt-5.4-mini",
            "cases": [
                {"iso3": "AAA", "country": "Alpha", "ruler": "Ready Ruler"},
                {"iso3": "BBB", "country": "Beta", "ruler": "Missing Ruler"},
            ],
        },
    )
    _catalog(catalog)
    for iso3, country, ruler in (("AAA", "Alpha", "Ready Ruler"), ("BBB", "Beta", "Missing Ruler")):
        _source(batch / "outputs" / f"{iso3.lower()}-2022", country, ruler)

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
    connection.execute("INSERT INTO ruler_years VALUES (12, 8, 2, 2022)")
    connection.commit()
    connection.close()
    convert_batch(manifest, batch, catalog, output)
    compact = prepare_compact_inputs(output, tmp_path / "compact", evidence_per_lens=1)
    assert compact["target_year"] == 2022
    assert len(compact["chapters"]) == 8
    assert all(item["evidence_per_lens"] == 1 for item in compact["chapters"])
    assert all(item["estimated_input_characters"] > 0 for item in compact["chapters"])


def test_conversion_preserves_hybrid_metadata_and_applies_chapter_review(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    batch = tmp_path / "batch"
    catalog = tmp_path / "catalog.sqlite"
    output = tmp_path / "converted"
    _write(
        manifest,
        {
            "batch_id": "hybrid-test",
            "year": 2022,
            "researcher": "gpt-5.4-mini",
            "cases": [{"iso3": "AAA", "country": "Alpha", "ruler": "Ready Ruler"}],
        },
    )
    _catalog(catalog)
    _hybrid_source(batch / "outputs" / "aaa-2022")
    _local_prior_package(batch / "outputs" / "aaa-2022" / "inputs" / "local-prior-package.json")

    report = convert_batch(manifest, batch, catalog, output)

    assert report["ready_for_judging"] is True
    dossier = json.loads(next((output / "dossiers").glob("*.json")).read_text())
    assert dossier["evidence"][0]["source_locator"] == "paragraph 4"
    assert dossier["evidence"][0]["canonical_fact_key"] == "fact-key"
    assert not [
        item
        for item in dossier["mappings"]
        if item["methodology_id"] == "1B.1" and item["evidence_id"] == "E0001"
    ]
    coverage = {item["methodology_id"]: item for item in dossier["coverage"]}
    assert coverage["1B.1"]["status"] == "covered"
    assert coverage["2B.1"]["status"] == "covered"
    priors = {item["methodology_id"]: item for item in dossier["local_priors"]}
    assert priors["2B.1"]["status"] == "evidence_found"
    assert "Conflict events: 27.0 (ucdp)" in priors["2B.1"]["summary"]
    assert not any(
        "Structured local priors were not collected" in item
        for item in report["rulers"][0]["warnings"]
    )
    compact = prepare_compact_inputs(output, tmp_path / "compact", evidence_per_lens=1)
    assert compact["chapters"][1]["omission_ledger"][0]["retained_evidence"] == 1


def _source(path: Path, country: str, ruler: str) -> None:
    path.mkdir(parents=True)
    question_ids = [f"{chapter}B.{lens}" for chapter in range(1, 9) for lens in range(1, 11)]
    _write(
        path / "evidence.json",
        {
            "ruler": ruler,
            "country": country,
            "year": 2022,
            "evidence": [
                {
                    "id": "E0001",
                    "title": "Title",
                    "publisher": "Publisher",
                    "date": "2022",
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
            "year": 2022,
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
            "year": 2022,
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


def _hybrid_source(path: Path) -> None:
    path.mkdir(parents=True)
    lenses = [f"{chapter}B.{lens}" for chapter in range(1, 9) for lens in range(1, 11)]
    _write(
        path / "dossier.json",
        {
            "identity": {"ruler": "Ready Ruler", "country": "Alpha", "year": 2022},
            "evidence": [
                {
                    "evidence_id": "E0001",
                    "claim": "A precise reviewed claim.",
                    "url": "https://example.test/item",
                    "title": "Title",
                    "publisher": "Publisher",
                    "publication_date": "2022-06-01",
                    "locator": "paragraph 4",
                    "canonical_fact_key": "fact-key",
                    "source_type": "official",
                    "source_confidence": "high",
                    "source_confidence_reason": "Direct record.",
                    "final_evidence_use": "final_evidence",
                    "period_fit": "Within 2022.",
                    "ruler_attribution": "Direct ruler action.",
                },
                *[
                    {
                        "evidence_id": f"E000{number}",
                        "claim": f"Discovery context {number}.",
                        "url": f"https://example.test/context-{number}",
                        "title": f"Context {number}",
                        "publisher": "Publisher",
                        "publication_date": "2022-06-01",
                        "locator": f"paragraph {number}",
                        "canonical_fact_key": f"context-key-{number}",
                        "source_type": "secondary",
                        "source_confidence": "low",
                        "source_confidence_reason": "Discovery context only.",
                        "final_evidence_use": "discovery_only",
                        "period_fit": "Within 2022.",
                        "ruler_attribution": "Indirect context.",
                    }
                    for number in (2, 3)
                ],
            ],
            "mappings": [
                {"evidence_id": evidence_id, "lenses": lenses}
                for evidence_id in ("E0001", "E0002", "E0003")
            ],
            "review": {
                "chapters": [
                    {
                        "chapter_id": f"{chapter}B",
                        "remove_or_contextualize": (
                            [{"evidence_id": "E0001", "reason": "Context only."}]
                            if chapter == 1
                            else []
                        ),
                        "material_gaps": [],
                    }
                    for chapter in range(1, 9)
                ]
            },
        },
    )
    _write(path / "session.json", {"ruler": "Ready Ruler", "country": "Alpha", "year": 2022})
    _write(
        path / "profile.json",
        {
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 2,
                "output_tokens": 3,
                "reasoning_output_tokens": 1,
            },
            "estimated_cost_usd": 0.1,
        },
    )


def _local_prior_package(path: Path) -> None:
    statuses = {
        f"{chapter}B.{lens}": "no_evidence_found"
        for chapter in range(1, 9)
        for lens in range(1, 11)
    }
    statuses["2B.1"] = "evidence_found"
    _write(
        path,
        {
            "methodology_statuses": statuses,
            "facts": [
                {
                    "label": "Conflict events",
                    "value": 27.0,
                    "source_slugs": ["ucdp"],
                    "candidate_methodology_ids": ["2B.1"],
                }
            ],
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
        INSERT INTO ruler_years VALUES (11, 7, 1, 2022);
    """)
    connection.commit()
    connection.close()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
