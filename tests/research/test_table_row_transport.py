from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import tiktoken

from leaders_db.research.corpus_reader_models import BoundEvidence, EvidenceCitation
from leaders_db.research.question_evidence_packet_models import (
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
)
from leaders_db.research.question_packet_prompts import load_question_packet_prompts
from leaders_db.research.question_packet_writer import (
    DiagnosticQuestionAnswer,
    build_question_writer_prompt,
)
from leaders_db.research.table_row_transport import (
    build_table_row_writer_transport_measurement,
)


def test_frozen_table_rows_reduce_question_writer_transport(tmp_path: Path) -> None:
    root = Path.cwd()
    quality_dir = tmp_path / "quality"
    shutil.copytree(
        root / "research/runs/netanyahu-2023-cost-opt-step11-table-row-quality-v1",
        quality_dir,
    )
    path = build_table_row_writer_transport_measurement(
        project_root=root,
        quality_run_dir=quality_dir,
        baseline_path=(
            root / "research/runs/netanyahu-2023-cost-opt-step07-span-v4/baseline-input.json"
        ),
        config_path=root / "configs/table-row-quality-comparison.yaml",
        profiles_path=root / "configs/research-models.yaml",
        output_dir=tmp_path / "transport",
    )
    measurement = json.loads(path.read_text())
    migrated = BoundEvidence.model_validate_json(
        (path.parent / "migrated-evidence.json").read_text()
    )

    assert measurement["model_calls"] == 0
    assert measurement["whole_unit_excerpt_preserved"] is True
    assert measurement["factual_gate"] == "pass"
    assert measurement["serialized_request_reduction_percent"] > 50
    assert measurement["compact_estimated_input_tokens"] < measurement[
        "legacy_estimated_input_tokens"
    ]
    schema_text = json.dumps(
        DiagnosticQuestionAnswer.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
    )
    encoding = tiktoken.get_encoding("o200k_base")
    assert measurement["legacy_estimated_input_tokens"] == len(
        encoding.encode((path.parent / "legacy-prompt.txt").read_text() + schema_text)
    )
    assert measurement["compact_estimated_input_tokens"] == len(
        encoding.encode((path.parent / "compact-prompt.txt").read_text() + schema_text)
    )
    assert len(migrated.citations) == measurement["citation_count"] == 38
    assert {60.1, 71.9, 65.7, 49.2} == set(measurement["corrected_values"])


def test_compact_writer_reconstructs_rows_and_rejects_source_drift(tmp_path: Path) -> None:
    root = Path.cwd()
    quality = json.loads(
        (root / "research/runs/netanyahu-2023-cost-opt-step11-table-row-quality-v1/"
        "table-row-quality-manifest.json").read_text()
    )
    baseline = BoundEvidence.model_validate_json(
        (
            root
            / "research/runs/netanyahu-2023-cost-opt-step07-span-v4/baseline-input.json"
        ).read_text()
    )
    citation = EvidenceCitation.model_validate({
        "span_id": quality["line_bindings"][0]["line_id"],
        "span": quality["line_bindings"][0]["span"],
        "exact_excerpt": quality["line_bindings"][0]["exact_text"],
        "excerpt_sha256": quality["line_bindings"][0]["span"]["text_sha256"],
    })
    evidence = baseline.model_copy(update={"citations": (citation,)})
    question_id = "5B.10"
    packet = QuestionEvidencePacket(
        question_id=question_id,
        question="Is employment broad, productive, and dignified?",
        priority_evidence=(evidence,),
        candidate_index=(CompactEvidenceCandidate(
            evidence_id=evidence.evidence_id,
            fact_summary=evidence.fact_summary,
            publisher=evidence.publisher,
            polarity=evidence.polarity,
            period_fit=evidence.period_fit,
            ruler_attribution=evidence.ruler_attribution,
            limitations=evidence.limitations,
            question_ids=evidence.question_ids,
        ),),
        direct_evidence_count=1,
        favorable_evidence_ids=(),
        adverse_evidence_ids=(),
        mixed_or_context_evidence_ids=(evidence.evidence_id,),
        coverage=QuestionCoverageChecklist(
            question_id=question_id,
            items=(EvidenceCoverageItem(
                evidence_id=evidence.evidence_id,
                requirement="must_address",
                carries_attribution=True,
                carries_period_fit=True,
                carries_limitations=True,
            ),),
            required_evidence_ids=(evidence.evidence_id,),
            reopenable_evidence_ids=(),
            favorable_available=False,
            adverse_available=False,
            mixed_or_context_available=True,
        ),
    )
    prompts, _ = load_question_packet_prompts(
        root / "configs/question-packet-prompts.yaml"
    )
    span = citation.span
    extraction = json.loads(
        (root / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/acquisition/"
        "extracted/SRC-afccda2f4a47b2bb.json").read_text()
    )
    exact = extraction["units"][span.unit - 1]["text"]

    compact = build_question_writer_prompt(
        packet,
        prompts,
        compact_table_citations=True,
        source_units={(evidence.source_id, span.unit): exact},
    )
    assert evidence.exact_excerpt not in compact
    with pytest.raises(ValueError, match="hash does not match"):
        build_question_writer_prompt(
            packet,
            prompts,
            compact_table_citations=True,
            source_units={(evidence.source_id, span.unit): "X" + exact[1:]},
        )
