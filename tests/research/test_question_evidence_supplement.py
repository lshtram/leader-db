import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from leaders_db.research.question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
)
from leaders_db.research.question_evidence_supplement import (
    build_supplemented_question_package,
    load_trusted_supplemented_question_package,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_supplement_builds_and_trusted_reloads_with_context_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packets = tuple(
        QuestionEvidencePacket(
            question_id=f"7B.{number}",
            question=f"Question {number}",
            priority_evidence=(),
            candidate_index=(),
            direct_evidence_count=0,
            favorable_evidence_ids=(),
            adverse_evidence_ids=(),
            mixed_or_context_evidence_ids=(),
            coverage=QuestionCoverageChecklist(
                question_id=f"7B.{number}",
                items=(),
                required_evidence_ids=(),
                reopenable_evidence_ids=(),
                favorable_available=False,
                adverse_available=False,
                mixed_or_context_available=False,
            ),
        )
        for number in range(1, 11)
    )
    base = ChapterQuestionEvidencePackage(
        chapter_id="7B",
        source_package_sha256="1" * 64,
        selection_manifest_sha256="2" * 64,
        selected_analysis_sha256="3" * 64,
        question_catalogue_sha256="4" * 64,
        complete_ledger_evidence_count=0,
        complete_ledger_ids_sha256=_sha(b""),
        packets=packets,
        chapter_candidate_ids=(),
        complete_ledger_dispositions=(),
    )
    monkeypatch.setattr(
        "leaders_db.research.question_evidence_supplement."
        "load_trusted_chapter_question_evidence_package",
        lambda **_: base,
    )
    base_path = tmp_path / "base.json"
    base_path.write_text(base.model_dump_json())
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("Exact evidence excerpt")
    supplement_path = tmp_path / "supplement.json"
    review_path = tmp_path / "review.json"
    supplement = {
        "schema_version": "question_evidence_supplement_v1",
        "base_package_sha256": _sha(base_path.read_bytes()),
        "chapter_id": "7B",
        "question_id": "7B.3",
        "sources": [{
            "source_id": "SRC-1",
            "artifact_path": raw_path.name,
            "artifact_sha256": _sha(raw_path.read_bytes()),
            "extracted_artifact_path": raw_path.name,
            "extracted_artifact_sha256": _sha(raw_path.read_bytes()),
        }],
        "evidence": [{
            "evidence_id": "E-NEW",
            "source_id": "SRC-1",
            "url": "https://example.test/source",
            "title": "Source",
            "publisher": "Publisher",
            "raw_sha256": _sha(raw_path.read_bytes()),
            "fact_summary": "Mechanism context.",
            "question_ids": ["7B.3"],
            "polarity": "context",
            "period_fit": "Historical context only.",
            "ruler_attribution": "No direct ruler attribution.",
            "limitations": ["Receives no adverse weight."],
            "start_unit": 1,
            "end_unit": 1,
            "locator": "line 1",
            "exact_excerpt": "Exact evidence excerpt",
            "excerpt_sha256": _sha(b"Exact evidence excerpt"),
            "citations": [],
            "verification_status": "accepted",
            "verification_notes": ["Verified."],
        }],
        "independent_review_path": review_path.name,
        "independent_review_sha256": "0" * 64,
    }
    payload = {
        key: value
        for key, value in supplement.items()
        if not key.startswith("independent_review_")
    }
    payload_hash = _sha(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    review_path.write_text(json.dumps({
        "schema_version": "question_evidence_supplement_review_v1",
        "base_package_sha256": supplement["base_package_sha256"],
        "supplement_payload_sha256": payload_hash,
        "question_id": "7B.3",
        "reviewed_evidence_ids": ["E-NEW"],
        "review_gate": "pass",
        "limitations_confirmed": True,
    }))
    supplement["independent_review_sha256"] = _sha(review_path.read_bytes())
    supplement_path.write_text(json.dumps(supplement))
    output_path = tmp_path / "package.json"
    inputs = dict(
        project_root=tmp_path,
        base_package_path=base_path,
        judge_package_path=tmp_path / "unused-judge.json",
        selection_manifest_path=tmp_path / "unused-selection.json",
        supplement_path=supplement_path,
    )

    build_supplemented_question_package(**inputs, output_path=output_path)
    result = load_trusted_supplemented_question_package(
        **inputs, package_path=output_path
    )

    packet = next(item for item in result.packets if item.question_id == "7B.3")
    assert packet.adverse_evidence_ids == ()
    assert packet.mixed_or_context_evidence_ids == ("E-NEW",)
    assert result.complete_ledger_evidence_count == 1

    raw_path.write_text("tampered")
    with pytest.raises(ValueError, match="source artifact differs"):
        load_trusted_supplemented_question_package(**inputs, package_path=output_path)

    raw_path.write_text("Exact evidence excerpt")
    second = deepcopy(supplement["evidence"][0])
    second["evidence_id"] = "E-SECOND"
    second["raw_sha256"] = "9" * 64
    supplement["evidence"].append(second)
    payload = {
        key: value
        for key, value in supplement.items()
        if not key.startswith("independent_review_")
    }
    review = json.loads(review_path.read_text())
    review["supplement_payload_sha256"] = _sha(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    review["reviewed_evidence_ids"] = ["E-NEW", "E-SECOND"]
    review_path.write_text(json.dumps(review))
    supplement["independent_review_sha256"] = _sha(review_path.read_bytes())
    supplement_path.write_text(json.dumps(supplement))
    with pytest.raises(ValueError, match="raw hash differs"):
        build_supplemented_question_package(**inputs, output_path=output_path)
