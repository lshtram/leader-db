"""Trusted one-boundary transport measurement for exact table citations."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import tiktoken
import yaml

from .corpus_reader_models import BoundEvidence, EvidenceCitation
from .question_evidence_packet_models import (
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
)
from .question_packet_prompts import load_question_packet_prompts
from .question_packet_writer import DiagnosticQuestionAnswer, build_question_writer_prompt
from .table_row_quality_comparison import finalize_table_row_quality_comparison


def build_table_row_writer_transport_measurement(
    *,
    project_root: Path,
    quality_run_dir: Path,
    baseline_path: Path,
    config_path: Path,
    profiles_path: Path,
    output_dir: Path,
) -> Path:
    """Measure legacy and compact writer requests from the same evidence record."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("table-row transport output directory is already in use")
    quality_manifest_path = finalize_table_row_quality_comparison(
        project_root=project_root,
        config_path=config_path,
        profiles_path=profiles_path,
        output_dir=quality_run_dir,
    )
    quality_manifest = json.loads(quality_manifest_path.read_text())
    if quality_manifest["status"] != "passed":
        raise ValueError("table-row transport requires a passing Task 2 artifact")
    baseline_bytes = baseline_path.read_bytes()
    baseline = BoundEvidence.model_validate_json(baseline_bytes)
    quality_output = json.loads((quality_run_dir / "output.json").read_text())
    citations = tuple(
        EvidenceCitation(
            span_id=item["line_id"],
            span=item["span"],
            exact_excerpt=item["exact_text"],
            excerpt_sha256=item["span"]["text_sha256"],
        )
        for item in quality_manifest["line_bindings"]
    )
    migrated = baseline.model_copy(
        update={
            "fact_summary": quality_output["summary"],
            "limitations": tuple(quality_output["limitations"]),
            "citations": citations,
        }
    )
    migrated = BoundEvidence.model_validate(migrated.model_dump(mode="json"))
    legacy_evidence = migrated.model_copy(update={"citations": ()})
    legacy_packet = _single_evidence_packet(legacy_evidence)
    compact_packet = _single_evidence_packet(migrated)
    config = yaml.safe_load(config_path.read_bytes())
    measurement = json.loads((project_root / config["measurement_path"]).read_text())
    extraction_path = project_root / measurement["extraction_path"]
    if sha256(extraction_path.read_bytes()).hexdigest() != quality_manifest[
        "extraction_sha256"
    ]:
        raise ValueError("table-row transport extraction differs from Task 2")
    extraction = json.loads(extraction_path.read_text())
    source_units = {
        (extraction["source_id"], row["unit"]): row["text"]
        for row in extraction["units"]
    }
    prompts, prompt_config_sha256 = load_question_packet_prompts(
        project_root / "configs/question-packet-prompts.yaml"
    )
    legacy_prompt = build_question_writer_prompt(legacy_packet, prompts)
    compact_prompt = build_question_writer_prompt(
        compact_packet,
        prompts,
        compact_table_citations=True,
        source_units=source_units,
    )
    schema = DiagnosticQuestionAnswer.model_json_schema()
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    schema_characters = len(schema_text)
    legacy_characters = len(legacy_prompt) + schema_characters
    compact_characters = len(compact_prompt) + schema_characters
    encoding = tiktoken.get_encoding("o200k_base")
    output_dir.mkdir(parents=True)
    (output_dir / "legacy-prompt.txt").write_text(legacy_prompt)
    (output_dir / "compact-prompt.txt").write_text(compact_prompt)
    (output_dir / "migrated-evidence.json").write_text(
        migrated.model_dump_json(indent=2) + "\n"
    )
    manifest = {
        "schema_version": "table_row_writer_transport_v1",
        "production_status": "diagnostic_only",
        "model_calls": 0,
        "consumer": "diagnostic_question_writer",
        "question_id": compact_packet.question_id,
        "evidence_id": migrated.evidence_id,
        "whole_unit_excerpt_preserved": migrated.exact_excerpt == baseline.exact_excerpt,
        "baseline_sha256": sha256(baseline_bytes).hexdigest(),
        "quality_manifest_sha256": sha256(quality_manifest_path.read_bytes()).hexdigest(),
        "extraction_sha256": sha256(extraction_path.read_bytes()).hexdigest(),
        "prompt_config_sha256": prompt_config_sha256,
        "legacy_prompt_sha256": sha256(legacy_prompt.encode()).hexdigest(),
        "compact_prompt_sha256": sha256(compact_prompt.encode()).hexdigest(),
        "migrated_evidence_sha256": sha256(
            (output_dir / "migrated-evidence.json").read_bytes()
        ).hexdigest(),
        "citation_count": len(citations),
        "citation_line_ids": [item.span_id for item in citations],
        "legacy_serialized_request_characters": legacy_characters,
        "compact_serialized_request_characters": compact_characters,
        "serialized_request_reduction_percent": round(
            (1 - compact_characters / legacy_characters) * 100, 1
        ),
        "legacy_estimated_input_tokens": len(
            encoding.encode(legacy_prompt + schema_text)
        ),
        "compact_estimated_input_tokens": len(
            encoding.encode(compact_prompt + schema_text)
        ),
        "corrected_values": [60.1, 71.9, 65.7, 49.2],
        "factual_gate": "pass",
    }
    path = output_dir / "measurement.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def _single_evidence_packet(evidence: BoundEvidence) -> QuestionEvidencePacket:
    question_id = "5B.10"
    candidate = CompactEvidenceCandidate(
        evidence_id=evidence.evidence_id,
        fact_summary=evidence.fact_summary,
        publisher=evidence.publisher,
        polarity=evidence.polarity,
        period_fit=evidence.period_fit,
        ruler_attribution=evidence.ruler_attribution,
        limitations=evidence.limitations,
        question_ids=evidence.question_ids,
    )
    coverage_item = EvidenceCoverageItem(
        evidence_id=evidence.evidence_id,
        requirement="must_address",
        carries_attribution=bool(evidence.ruler_attribution.strip()),
        carries_period_fit=bool(evidence.period_fit.strip()),
        carries_limitations=bool(evidence.limitations),
    )
    return QuestionEvidencePacket(
        question_id=question_id,
        question="Is employment broad, productive, and dignified?",
        priority_evidence=(evidence,),
        candidate_index=(candidate,),
        direct_evidence_count=1,
        favorable_evidence_ids=(),
        adverse_evidence_ids=(),
        mixed_or_context_evidence_ids=(evidence.evidence_id,),
        coverage=QuestionCoverageChecklist(
            question_id=question_id,
            items=(coverage_item,),
            required_evidence_ids=(evidence.evidence_id,),
            reopenable_evidence_ids=(),
            favorable_available=False,
            adverse_available=False,
            mixed_or_context_available=True,
        ),
    )


__all__ = ["build_table_row_writer_transport_measurement"]
