from leaders_db.research.codex_worker import _embedded_ledger_manifest
from leaders_db.research.ledger_manifest_dedup import collapse_recovered_url_duplicates


def test_recovered_url_duplicate_merges_routing_into_complete_owner() -> None:
    owner = {
        "canonical_fact_key": "fact",
        "url": "https://example.test/report",
        "claim": "Supported fact.",
        "locator": "p. 4",
        "chapter_ids": ["1B"],
        "methodology_ids": ["1B.1"],
    }
    recovered = {
        "canonical_fact_key": "recovered:https://example.test/report|WEB-1B-03",
        "chapter_ids": ["1B"],
        "methodology_ids": ["1B.2", "1B.3"],
    }

    normalized, count = collapse_recovered_url_duplicates(
        {"schema_version": "ruler_research_ledger_manifest_v1", "entries": [owner, recovered]}
    )

    assert count == 1
    assert normalized["entries"] == [owner]
    assert owner["methodology_ids"] == ["1B.1", "1B.2", "1B.3"]


def test_complete_distinct_records_on_same_url_are_preserved() -> None:
    records = [
        {
            "canonical_fact_key": key,
            "url": "https://example.test/report",
            "claim": claim,
            "locator": locator,
        }
        for key, claim, locator in (("a", "First.", "p. 1"), ("b", "Second.", "p. 2"))
    ]

    normalized, count = collapse_recovered_url_duplicates({"entries": records})

    assert count == 0
    assert normalized["entries"] == records


def test_embedded_manifest_collapses_recovery_duplicate_before_accounting() -> None:
    notebook = """--- RESEARCH LEDGER MANIFEST ---
{"schema_version":"ruler_research_ledger_manifest_v1","entries":[
 {"provisional_id":"E1","canonical_fact_key":"fact","disposition":"final_evidence",
  "url":"https://example.test/report","claim":"Fact.","locator":"p. 1",
  "chapter_ids":["1B"],"methodology_ids":["1B.1"]},
 {"provisional_id":"E2","canonical_fact_key":"recovered:https://example.test/report|E2",
  "disposition":"final_evidence","chapter_ids":["1B"],"methodology_ids":["1B.2"]}
]}
"""

    manifest = _embedded_ledger_manifest(notebook)

    assert manifest is not None
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["methodology_ids"] == ["1B.1", "1B.2"]
