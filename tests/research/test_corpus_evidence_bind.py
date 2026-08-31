from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.corpus_evidence_bind import bind_batch_evidence
from leaders_db.research.corpus_reader_models import (
    BatchFactOutput,
    BatchVerification,
    BoundEvidence,
)
from leaders_db.research.corpus_reading_plan import CorpusReadingPlan
from leaders_db.research.corpus_verification import (
    apply_verification,
    build_verification_candidates,
    verification_prompt,
)


def test_binding_copies_exact_units_and_rejects_unaccounted_sources(tmp_path: Path) -> None:
    acquisition = tmp_path / "acquisition"
    (acquisition / "extracted").mkdir(parents=True)
    (acquisition / "extracted/SRC-1.json").write_text(
        json.dumps(
            {
                "source_id": "SRC-1",
                "raw_sha256": "abc",
                "units": [
                    {"unit": 1, "locator": "page 1", "text": "Exact first passage."},
                    {"unit": 2, "locator": "page 2", "text": "Exact second passage."},
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = CorpusReadingPlan.model_validate(
        {
            "ruler_name": "Fixture Ruler",
            "period_start_year": 2023,
            "period_end_year": 2023,
            "config": {},
            "documents": [
                {
                    "source_id": "SRC-1",
                    "url": "https://example.test/report",
                    "title": "Report",
                    "publisher": "Publisher",
                    "document_type": "report",
                    "chapter_ids": ["5B"],
                    "status": "queued",
                    "extracted_path": "extracted/SRC-1.json",
                    "raw_sha256": "abc",
                    "estimated_tokens": 10,
                }
            ],
            "batches": [
                {
                    "batch_id": "BATCH-0001",
                    "source_ids": ["SRC-1"],
                    "unit_ranges": {"SRC-1": [1, 2]},
                    "chapter_ids": ["5B"],
                    "estimated_tokens": 10,
                }
            ],
        }
    )
    output = BatchFactOutput.model_validate(
        {
            "facts": [
                {
                    "source_id": "SRC-1",
                    "start_unit": 1,
                    "end_unit": 2,
                    "fact_summary": "The report documents a material fact.",
                    "question_ids": ["5B.1", "5B.2"],
                    "polarity": "mixed",
                    "period_fit": "target year",
                    "ruler_attribution": "national policy responsibility",
                }
            ],
            "documents_with_no_material_fact": [],
        }
    )

    evidence = bind_batch_evidence(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        reader_output=output,
    )

    assert evidence[0].exact_excerpt == "Exact first passage.\n\nExact second passage."
    assert evidence[0].locator == "page 1 through page 2"
    assert evidence[0].question_ids == ("5B.1", "5B.2")

    contradictory = output.model_copy(
        update={"documents_with_no_material_fact": ("SRC-1",)}
    )
    with pytest.raises(ValueError, match="contradictory"):
        bind_batch_evidence(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            reader_output=contradictory,
        )


def test_binding_copies_only_selected_paragraph_spans(tmp_path: Path) -> None:
    acquisition = tmp_path / "acquisition"
    (acquisition / "extracted").mkdir(parents=True)
    (acquisition / "extracted/SRC-1.json").write_text(json.dumps({
        "source_id": "SRC-1",
        "raw_sha256": "abc",
        "units": [{
            "unit": 1,
            "locator": "page 1",
            "text": "Material first paragraph.\n\nUnrelated second paragraph.",
        }],
    }))
    plan = CorpusReadingPlan.model_validate({
        "ruler_name": "Fixture Ruler",
        "period_start_year": 2023,
        "period_end_year": 2023,
        "config": {},
        "documents": [{
            "source_id": "SRC-1",
            "url": "https://example.test/report",
            "title": "Report",
            "publisher": "Publisher",
            "document_type": "report",
            "chapter_ids": ["5B"],
            "status": "queued",
            "extracted_path": "extracted/SRC-1.json",
            "raw_sha256": "abc",
            "estimated_tokens": 10,
        }],
        "batches": [{
            "batch_id": "BATCH-0001",
            "source_ids": ["SRC-1"],
            "unit_ranges": {"SRC-1": [1, 1]},
            "chapter_ids": ["5B"],
            "estimated_tokens": 10,
        }],
    })
    output = BatchFactOutput.model_validate({
        "facts": [{
            "source_id": "SRC-1",
            "start_unit": 1,
            "end_unit": 1,
            "fact_summary": "The report documents a material fact.",
            "question_ids": ["5B.1"],
            "polarity": "mixed",
            "period_fit": "target year",
            "ruler_attribution": "national policy responsibility",
            "citation_span_ids": ["U1-P2", "U1-P1"],
        }],
        "documents_with_no_material_fact": [],
    })

    evidence = bind_batch_evidence(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        reader_output=output,
    )

    assert evidence[0].exact_excerpt == (
        "Material first paragraph.\n\nUnrelated second paragraph."
    )
    assert [item.exact_excerpt for item in evidence[0].citations] == [
        "Unrelated second paragraph.",
        "Material first paragraph.",
    ]
    assert evidence[0].citations[1].span.start_char == 0
    assert evidence[0].citations[1].span.end_char == 25
    verifier_input = verification_prompt(evidence)
    assert "Material first paragraph." in verifier_input
    assert "Unrelated second paragraph." in verifier_input
    assert '"exact_excerpt": "Material first paragraph."' in verifier_input
    assert "Material first paragraph.\\n\\nUnrelated second paragraph." not in verifier_input

    candidates = build_verification_candidates(
        acquisition_dir=acquisition,
        plan=plan,
        evidence=evidence,
    )
    candidate_prompt = verification_prompt(evidence, candidates)
    assert '"span_id": "U1-P1"' in candidate_prompt
    assert '"citations"' not in candidate_prompt
    assert "Material first paragraph.\\n\\nUnrelated second paragraph." not in candidate_prompt
    verification = BatchVerification.model_validate({
        "verdicts": [{
            "evidence_id": evidence[0].evidence_id,
            "status": "accepted",
            "citation_span_ids": ["U1-P1"],
        }],
    })
    narrowed = apply_verification(evidence, verification, candidates)
    assert [item.span_id for item in narrowed[0].citations] == ["U1-P1"]

    invalid = output.model_copy(
        update={"facts": (output.facts[0].model_copy(
            update={"citation_span_ids": ("U1-P3",)}
        ),)}
    )
    with pytest.raises(ValueError, match="unavailable paragraph span"):
        bind_batch_evidence(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            reader_output=invalid,
        )

    duplicate = output.model_copy(
        update={"facts": (output.facts[0].model_copy(
            update={"citation_span_ids": ("U1-P1", "U1-P1")}
        ),)}
    )
    with pytest.raises(ValueError, match="duplicate paragraph span"):
        bind_batch_evidence(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            reader_output=duplicate,
        )

    _assert_citation_tampering_is_rejected(evidence[0])


def _assert_citation_tampering_is_rejected(evidence: BoundEvidence) -> None:
    payload = evidence.model_dump(mode="json")
    payload["citations"][0]["span_id"] = "U9-P9"
    with pytest.raises(ValueError, match="span ID and unit"):
        BoundEvidence.model_validate(payload)
    payload = evidence.model_dump(mode="json")
    payload["citations"][0]["exact_excerpt"] = "Substituted text."
    with pytest.raises(ValueError, match="hashes must match"):
        BoundEvidence.model_validate(payload)
    payload = evidence.model_dump(mode="json")
    payload["citations"][0]["span"]["end_char"] = 999
    with pytest.raises(ValueError, match="offsets must match"):
        BoundEvidence.model_validate(payload)
    payload = evidence.model_dump(mode="json")
    payload["citations"].append(payload["citations"][0])
    with pytest.raises(ValueError, match="citations must be unique"):
        BoundEvidence.model_validate(payload)
    payload = evidence.model_dump(mode="json")
    payload["citations"][1]["span_id"] = "U1-P3"
    payload["citations"][1]["span"] = payload["citations"][0]["span"]
    payload["citations"][1]["exact_excerpt"] = payload["citations"][0]["exact_excerpt"]
    payload["citations"][1]["excerpt_sha256"] = payload["citations"][0][
        "excerpt_sha256"
    ]
    with pytest.raises(ValueError, match="citations must be unique"):
        BoundEvidence.model_validate(payload)
    payload = evidence.model_dump(mode="json")
    payload["start_unit"] = 2
    payload["end_unit"] = 2
    with pytest.raises(ValueError, match="outside its unit range"):
        BoundEvidence.model_validate(payload)


@pytest.mark.parametrize(
    "extraction",
    [
        {
            "source_id": "SRC-OTHER",
            "raw_sha256": "abc",
            "units": [{"unit": 1, "locator": "page 1", "text": "Text."}],
        },
        {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [{"unit": 1, "locator": "page 1", "text": 123}],
        },
        {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [
                {"unit": 1, "locator": "page 1", "text": "First."},
                {"unit": 1, "locator": "page 2", "text": "Second."},
            ],
        },
    ],
)
def test_binding_rejects_ambiguous_extraction_identity_and_units(
    tmp_path: Path, extraction: dict
) -> None:
    acquisition = tmp_path / "acquisition"
    (acquisition / "extracted").mkdir(parents=True)
    (acquisition / "extracted/SRC-1.json").write_text(json.dumps(extraction))
    plan = CorpusReadingPlan.model_validate({
        "ruler_name": "Fixture Ruler",
        "period_start_year": 2023,
        "period_end_year": 2023,
        "config": {},
        "documents": [{
            "source_id": "SRC-1", "url": "https://example.test", "title": "Report",
            "publisher": "Publisher", "document_type": "report", "chapter_ids": ["5B"],
            "status": "queued", "extracted_path": "extracted/SRC-1.json",
            "raw_sha256": "abc", "estimated_tokens": 1,
        }],
        "batches": [{
            "batch_id": "BATCH-0001", "source_ids": ["SRC-1"],
            "unit_ranges": {"SRC-1": [1, 1]}, "chapter_ids": ["5B"],
            "estimated_tokens": 1,
        }],
    })
    output = BatchFactOutput.model_validate({
        "facts": [{
            "source_id": "SRC-1", "start_unit": 1, "end_unit": 1,
            "fact_summary": "The report documents a material fact.",
            "question_ids": ["5B.1"], "polarity": "mixed",
            "period_fit": "target year", "ruler_attribution": "national responsibility",
            "citation_span_ids": ["U1-P1"],
        }],
        "documents_with_no_material_fact": [],
    })
    with pytest.raises(ValueError):
        bind_batch_evidence(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            reader_output=output,
        )


def test_verification_rejects_duplicate_verdict_ids() -> None:
    evidence = BoundEvidence(
        evidence_id="E-1",
        source_id="SRC-1",
        url="https://example.test",
        title="Source",
        publisher="Publisher",
        raw_sha256="a" * 64,
        fact_summary="One material factual account.",
        question_ids=("1B.1",),
        polarity="context",
        period_fit="2023",
        ruler_attribution="direct",
        limitations=(),
        start_unit=1,
        end_unit=1,
        locator="page 1",
        exact_excerpt="Exact text.",
        excerpt_sha256="b" * 64,
    )
    verification = BatchVerification.model_validate({
        "verdicts": [
            {"evidence_id": "E-1", "status": "accepted"},
            {"evidence_id": "E-1", "status": "rejected"},
        ],
    })
    with pytest.raises(ValueError, match="must be unique"):
        apply_verification((evidence,), verification)
