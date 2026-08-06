import json
from pathlib import Path

import pytest

from leaders_db.conversational_evidence.hybrid_experiment.claims import (
    build_ledger,
    chapter_parse_errors,
    dossier,
    ledger_quality,
    parse_chapter_note,
    parse_reuse,
)
from leaders_db.conversational_evidence.hybrid_experiment.runner import (
    _recover_completed_chapter_turn,
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


def test_parse_chapter_note_accepts_markdown_list_marker() -> None:
    note = "- " + _claim(
        url="https://example.org/a", claim="A material act.", lenses=["1B.1"]
    )

    records = parse_chapter_note(note, "1B")

    assert len(records) == 1
    assert str(records[0].url) == "https://example.org/a"


def test_parse_chapter_note_accepts_inline_code_wrapper() -> None:
    note = "- `" + _claim(
        url="https://example.org/a", claim="A material act.", lenses=["6B.1"]
    ) + "`"

    records = parse_chapter_note(note, "6B")

    assert len(records) == 1


def test_parse_chapter_note_accepts_claim_after_introductory_prose() -> None:
    note = "A concise finding. " + _claim(
        url="https://example.org/a", claim="A material act.", lenses=["6B.1"]
    )

    records = parse_chapter_note(note, "6B")

    assert len(records) == 1


def test_parse_chapter_note_rejects_only_malformed_record() -> None:
    valid = _claim(
        url="https://example.org/a", claim="A material act.", lenses=["2B.1"]
    )
    malformed = 'SOURCE_CLAIM_JSON: {"title":"missing fields"}'
    note = valid + "\n" + malformed

    records = parse_chapter_note(note, "2B")
    errors = chapter_parse_errors(note)

    assert len(records) == 1
    assert len(errors) == 1
    assert errors[0]["line_number"] == 2
    assert len(str(errors[0]["record_sha256"])) == 64


def test_parse_reuse_rejects_only_malformed_record() -> None:
    note = "\n".join(
        (
            'REUSE_JSON: {"evidence_ids":["E0001"],"lenses":["2B.1"]}',
            "REUSE_JSON: n/a",
        )
    )

    records = parse_reuse(note, "2B")
    errors = chapter_parse_errors(note)

    assert len(records) == 1
    assert records[0].evidence_ids == ("E0001",)
    assert len(errors) == 1
    assert errors[0]["line_number"] == 2


def test_parse_chapter_note_accepts_reuse_without_new_claims() -> None:
    note = 'REUSE_JSON: {"evidence_ids":["E0001"],"lenses":["4B.1"]}'

    claims = parse_chapter_note(note, "4B")
    reused = parse_reuse(note, "4B")

    assert claims == ()
    assert len(reused) == 1


def test_parse_chapter_note_rejects_note_without_claims_or_reuse() -> None:
    with pytest.raises(ValueError, match="no SOURCE_CLAIM_JSON: or REUSE_JSON:"):
        parse_chapter_note("No structured evidence records were emitted.", "4B")


def test_recover_completed_chapter_turn(tmp_path: Path) -> None:
    work = tmp_path / ".researcher"
    work.mkdir()
    note = "- " + _claim(
        url="https://example.org/a", claim="A material act.", lenses=["5B.1"]
    )
    work.joinpath("turn-006.md").write_text(note, encoding="utf-8")
    work.joinpath("turn-006.profile.json").write_text(
        json.dumps({"return_code": 0}), encoding="utf-8"
    )
    chapter_path = tmp_path / "chapters" / "5B.md"

    recovered = _recover_completed_chapter_turn(tmp_path, chapter_path, "5B", 6)

    assert recovered is True
    assert chapter_path.read_text(encoding="utf-8") == note + "\n"


def test_recover_completed_chapter_turn_after_prior_retry(tmp_path: Path) -> None:
    work = tmp_path / ".researcher"
    work.mkdir()
    invalid = "The prior attempt did not emit a structured record."
    work.joinpath("turn-006.md").write_text(invalid, encoding="utf-8")
    work.joinpath("turn-006.profile.json").write_text(
        json.dumps({"return_code": 0}), encoding="utf-8"
    )
    valid = "Finding. " + _claim(
        url="https://example.org/a", claim="A material act.", lenses=["5B.1"]
    )
    work.joinpath("turn-007.md").write_text(valid, encoding="utf-8")
    work.joinpath("turn-007.profile.json").write_text(
        json.dumps({"return_code": 0}), encoding="utf-8"
    )
    chapter_path = tmp_path / "chapters" / "5B.md"

    recovered = _recover_completed_chapter_turn(tmp_path, chapter_path, "5B", 6)

    assert recovered is True
    assert chapter_path.read_text(encoding="utf-8") == valid + "\n"


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


def test_build_ledger_does_not_renumber_existing_claims_when_follow_up_is_prepended(
    tmp_path: Path,
) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    chapters.joinpath("1B.md").write_text(
        _claim(url="https://example.org/base", claim="Base claim.", lenses=["1B.1"]),
        encoding="utf-8",
    )
    old_follow_up = _claim(
        url="https://example.org/old-follow-up",
        claim="Existing follow-up.",
        lenses=["1B.2"],
    )
    (tmp_path / "follow-up.md").write_text(old_follow_up, encoding="utf-8")
    original = build_ledger(tmp_path)
    (tmp_path / "evidence-ledger.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in original]),
        encoding="utf-8",
    )
    new_follow_up = _claim(
        url="https://example.org/new-follow-up",
        claim="New follow-up.",
        lenses=["1B.3"],
    )
    (tmp_path / "follow-up.md").write_text(
        f"{new_follow_up}\n{old_follow_up}", encoding="utf-8"
    )

    updated = build_ledger(tmp_path)
    by_url = {str(item.url): item.evidence_id for item in updated}

    assert by_url["https://example.org/base"] == "E0001"
    assert by_url["https://example.org/old-follow-up"] == "E0002"
    assert by_url["https://example.org/new-follow-up"] == "E0003"


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
