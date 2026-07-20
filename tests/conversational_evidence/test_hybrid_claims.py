import json
from pathlib import Path

import pytest

from leaders_db.conversational_evidence.hybrid_experiment.claims import (
    build_ledger,
    dossier,
    ledger_quality,
    parse_chapter_note,
)


def _claim(*, url: str, claim: str, lenses: list[str]) -> str:
    value = {
        "title": "Primary record",
        "publisher": "Example institution",
        "publication_date": "2022-06-01",
        "url": url,
        "claim": claim,
        "locator": "section 2, paragraph 4",
        "source_type": "primary/legal",
        "source_confidence": "high",
        "source_confidence_reason": "Direct institutional record.",
        "final_evidence_use": "final_evidence",
        "period_fit": "Directly records a 2022 action.",
        "ruler_attribution": "The ruler signed the measure.",
        "contrary_evidence": ["The institution described a security rationale."],
        "lenses": lenses,
    }
    return "SOURCE_CLAIM_JSON: " + json.dumps(value)


def test_parse_chapter_note_requires_exact_chapter_lenses() -> None:
    note = _claim(url="https://example.org/a", claim="A material act.", lenses=["2B.1"])

    with pytest.raises(ValueError, match="cross-chapter"):
        parse_chapter_note(note, "1B")


def test_build_ledger_preserves_distinct_claims_and_reuse(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    chapters.joinpath("1B.md").write_text(
        _claim(
            url="https://EXAMPLE.org/report?utm_source=test",
            claim="First material claim.",
            lenses=["1B.1", "1B.2"],
        ),
        encoding="utf-8",
    )
    chapters.joinpath("2B.md").write_text(
        "\n".join(
            (
                'REUSE_JSON: {"evidence_ids":["E0001"],"lenses":["2B.3"]}',
                _claim(
                    url="https://example.org/report",
                    claim="Second materially distinct claim.",
                    lenses=["2B.4"],
                ),
            )
        ),
        encoding="utf-8",
    )

    records = build_ledger(tmp_path)

    assert len(records) == 2
    assert records[0].evidence_id == "E0001"
    assert records[0].chapters == ("1B", "2B")
    assert records[0].lenses == ("1B.1", "1B.2", "2B.3")
    assert records[0].canonical_url == "https://example.org/report"
    assert records[1].evidence_id == "E0002"


def test_quality_and_dossier_are_derived_without_generation(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    chapters.joinpath("1B.md").write_text(
        _claim(url="https://example.org/a", claim="A material act.", lenses=["1B.1"]),
        encoding="utf-8",
    )
    records = build_ledger(tmp_path)

    quality = ledger_quality(records)
    value = dossier(
        ruler="Leader",
        country="Country",
        iso3="AAA",
        year=2022,
        records=records,
        review={"overall_decision": "pass"},
        notes={"1B": "saved"},
    )

    assert quality["accepted_claims"] == 1
    assert quality["distinct_urls"] == 1
    assert value["schema_version"] == "hybrid_experiment_dossier_v2"
    assert value["evidence"][0]["evidence_id"] == "E0001"
    assert value["evidence"][0]["review_disposition"]["status"] == "accepted"
    assert value["formatting"]["method"] == "deterministic_validated_parser"


def test_dossier_rejects_unknown_reviewer_evidence_id(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    chapters.joinpath("1B.md").write_text(
        _claim(url="https://example.org/a", claim="A material act.", lenses=["1B.1"]),
        encoding="utf-8",
    )
    records = build_ledger(tmp_path)

    with pytest.raises(ValueError, match="unknown evidence ID"):
        dossier(
            ruler="Leader",
            country="Country",
            iso3="AAA",
            year=2022,
            records=records,
            review={
                "chapters": [
                    {
                        "chapter_id": "1B",
                        "remove_or_contextualize": [
                            {"evidence_id": "E9999", "reason": "Not relevant."}
                        ],
                    }
                ]
            },
            notes={},
        )
