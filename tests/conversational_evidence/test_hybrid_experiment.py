from pathlib import Path

from leaders_db.conversational_evidence.hybrid_experiment.artifacts import (
    baseline_manifest,
    evidence_index,
    normalize_url,
    quality_summary,
)


def test_evidence_index_deduplicates_and_reuses_urls() -> None:
    notes = [
        ("1B", "1B.1 https://Example.com/a?utm_source=x"),
        ("2B", "2B.3 https://example.com/a"),
    ]

    records = evidence_index(notes)

    assert len(records) == 1
    assert records[0]["evidence_id"] == "E0001"
    assert records[0]["chapters"] == ["1B", "2B"]
    assert records[0]["mentioned_lenses"] == ["1B.1", "2B.3"]


def test_quality_summary_reports_mechanical_warnings() -> None:
    records = evidence_index([("3B", "3B.1 https://example.com/a")])

    summary = quality_summary(records)

    assert summary["chapters"]["3B"]["warnings"] == [
        "fewer_than_10_distinct_urls",
        "fewer_than_5_domains",
        "top_domain_above_35_percent",
        "not_all_lenses_mentioned_near_urls",
    ]


def test_baseline_manifest_hashes_production_files() -> None:
    root = Path(__file__).resolve().parents[2]

    value = baseline_manifest(root)

    assert value["git_head"]
    assert len(value["production_files"]) == 6
    assert normalize_url("https://EXAMPLE.com/a/?utm_campaign=x") == "https://example.com/a"
