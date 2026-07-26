"""Execute content-first reader arms for a frozen AMLO document pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from leaders_db.conversational_evidence.document_reader_experiment import (
    DocumentReaderConfig,
    ReaderContentAudit,
    ReaderSummaryEnvelope,
    chunk_units,
    load_document_reader_config,
    render_reader_prompt,
)
from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import (
    ResearchModelProfile,
    load_research_model_profiles,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PROFILES = PROJECT_ROOT / "configs/research-models.yaml"


def _profile_slug(profile_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", profile_name.lower()).strip("-")


def main() -> None:
    """Run calibration or full reader-map production for one frozen experiment."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("arm", choices=("baseline", "candidate"))
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--candidate-profile")
    parser.add_argument("--factual-reviewer-profile")
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    config = load_document_reader_config(experiment_dir / "frozen/document_reader_experiment.json")
    profiles = load_research_model_profiles(MODEL_PROFILES).profiles
    manifest = _read_json(experiment_dir / "manifest.json")
    documents = manifest["acquired_documents"]
    selected_ids = (
        {item["requested_source_id"] for item in documents}
        if args.full
        else set(config.calibration_document_ids)
    )
    selected = [item for item in documents if item["requested_source_id"] in selected_ids]
    if args.arm == "baseline":
        profile_name = config.baseline_reader
        arm_dir = experiment_dir / "arm-a-sol"
    else:
        profile_name = args.candidate_profile or config.reader_ladder[0]
        if profile_name not in config.reader_ladder:
            raise ValueError("candidate profile must come from the configured fallback ladder")
        suffix = _profile_slug(profile_name)
        if args.factual_reviewer_profile:
            suffix += f"-reviewed-by-{_profile_slug(args.factual_reviewer_profile)}"
        arm_dir = experiment_dir / f"arm-b-{suffix}"
    arm_dir.mkdir(parents=True, exist_ok=True)
    content_auditor = profiles[config.content_auditor]
    reader = profiles[profile_name]
    factual_reviewer = (
        profiles[args.factual_reviewer_profile] if args.factual_reviewer_profile else None
    )
    brief_profile = profiles[config.reading_brief_model]

    results: list[dict[str, Any]] = []
    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    for document in selected:
        result = run_document(
            experiment_dir,
            arm_dir,
            document,
            config=config,
            reader=reader,
            factual_reviewer=factual_reviewer,
            brief_profile=brief_profile,
            content_auditor=content_auditor,
        )
        results.append(result)
        if args.arm == "candidate" and not args.full and not result["content_usable"]:
            break
    _write_json(
        arm_dir / ("full-run-summary.json" if args.full else "calibration-summary.json"),
        {
            "schema_version": "document_reader_arm_summary_v1",
            "profile": profile_name,
            "arm": args.arm,
            "full": args.full,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started_clock, 3),
            "documents": results,
        },
    )


def run_document(
    experiment_dir: Path,
    arm_dir: Path,
    document: dict[str, Any],
    *,
    config: DocumentReaderConfig,
    reader: ResearchModelProfile,
    factual_reviewer: ResearchModelProfile | None,
    brief_profile: ResearchModelProfile,
    content_auditor: ResearchModelProfile,
) -> dict[str, Any]:
    """Produce and content-audit normalized source maps for one document."""

    source_id = str(document["requested_source_id"])
    work_dir = arm_dir / "maps" / source_id
    work_dir.mkdir(parents=True, exist_ok=True)
    extraction = _read_json(experiment_dir / str(document["extracted_path"]))
    brief_path = experiment_dir / "frozen/reading-briefs" / f"{source_id}.md"
    if not brief_path.exists():
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_prompt = render_brief_prompt(document, config)
        brief_path.with_suffix(".prompt.txt").write_text(brief_prompt, encoding="utf-8")
        execute_prompt(
            brief_profile,
            brief_prompt,
            output_path=brief_path,
            events_path=brief_path.with_suffix(".events.jsonl"),
            stderr_path=brief_path.with_suffix(".stderr.txt"),
            writable_dir=brief_path.parent,
        )
    reading_brief = brief_path.read_text(encoding="utf-8")
    units = [f"{item['locator']}\n{item['text']}" for item in extraction["units"]]
    chunks = chunk_units(
        units,
        target_tokens=config.chunk_target_tokens,
        max_tokens=config.chunk_max_tokens,
    )
    item = next(value for value in config.document_pack if value.source_id == source_id)
    map_paths: list[str] = []
    audits: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_dir = work_dir / chunk.chunk_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        prompt = "\n\n".join(
            (
                render_reader_prompt(config, item, reading_brief=reading_brief),
                f"Source ID: {source_id}",
                f"Title: {document['title']}",
                f"URL: {document['final_url']}",
                f"Source SHA-256: {document['raw_sha256']}",
                f"Chunk locator envelope: units {chunk.start_unit}-{chunk.end_unit}",
                "DOCUMENT EXTRACT:\n" + chunk.text,
            )
        )
        (chunk_dir / "reader-prompt.txt").write_text(prompt, encoding="utf-8")
        raw_path = chunk_dir / "reader-output.md"
        if not raw_path.exists():
            execute_prompt(
                reader,
                prompt,
                output_path=raw_path,
                events_path=chunk_dir / "reader-events.jsonl",
                stderr_path=chunk_dir / "reader-stderr.txt",
                writable_dir=chunk_dir,
            )
        normalized_path = chunk_dir / "source-map.json"
        reader_output = raw_path.read_text(encoding="utf-8")
        final_reader_output = reader_output
        if factual_reviewer is not None:
            review_output_path = chunk_dir / "factual-review-output.md"
            review_prompt = render_factual_review_prompt(reader_output, chunk.text)
            (chunk_dir / "factual-review-prompt.txt").write_text(review_prompt, encoding="utf-8")
            if not review_output_path.exists():
                execute_prompt(
                    factual_reviewer,
                    review_prompt,
                    output_path=review_output_path,
                    events_path=chunk_dir / "factual-review-events.jsonl",
                    stderr_path=chunk_dir / "factual-review-stderr.txt",
                    writable_dir=chunk_dir,
                )
            final_reader_output = review_output_path.read_text(encoding="utf-8")
        envelope = ReaderSummaryEnvelope(
            schema_version="reader_summary_envelope_v1",
            source_id=source_id,
            source_sha256=str(document["raw_sha256"]),
            title=str(document["title"]),
            url=str(document["final_url"]),
            document_type=item.document_type,
            source_role=item.source_role,
            reader_model=reader.model,
            reader_output=final_reader_output,
            claimed_locator_numbers=tuple(
                sorted(
                    {
                        int(value)
                        for value in re.findall(
                            r"(?:page|block|unit|página|bloque)\s+([0-9]+)",
                            reader_output,
                            flags=re.IGNORECASE,
                        )
                    }
                )
            ),
            normalization_method="lossless_deterministic_envelope",
        )
        normalized_path.write_text(
            envelope.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        audit_path = chunk_dir / "content-audit.json"
        audit_prompt = render_content_audit_prompt(envelope, chunk.text)
        (chunk_dir / "audit-prompt.txt").write_text(audit_prompt, encoding="utf-8")
        if not audit_path.exists():
            execute_prompt(
                content_auditor,
                audit_prompt,
                output_path=audit_path,
                events_path=chunk_dir / "audit-events.jsonl",
                stderr_path=chunk_dir / "audit-stderr.txt",
                writable_dir=chunk_dir,
                schema_model=ReaderContentAudit,
            )
        audit = ReaderContentAudit.model_validate_json(audit_path.read_text(encoding="utf-8"))
        map_paths.append(str(normalized_path.relative_to(experiment_dir)))
        audits.append(audit.model_dump(mode="json"))
    return {
        "source_id": source_id,
        "reader_model": reader.model,
        "factual_reviewer_model": (
            factual_reviewer.model if factual_reviewer is not None else None
        ),
        "chunk_count": len(chunks),
        "map_paths": map_paths,
        "audits": audits,
        "content_usable": all(
            audit_meets_acceptance(
                ReaderContentAudit.model_validate(item),
                config=config,
            )
            for item in audits
        ),
        "format_failures_scored": False,
    }


def audit_meets_acceptance(
    audit: ReaderContentAudit,
    *,
    config: DocumentReaderConfig,
) -> bool:
    """Apply the frozen content gate without considering output organization."""

    locator_rate = audit.usable_locator_count / audit.claim_count if audit.claim_count else 0.0
    acceptance = config.content_acceptance
    return (
        audit.content_usable
        and audit.unsupported_claim_count <= acceptance.fabricated_accepted_claims_allowed
        and locator_rate >= acceptance.minimum_usable_locator_rate
    )


def render_brief_prompt(
    document: dict[str, Any],
    config: DocumentReaderConfig,
) -> str:
    """Ask the production researcher for document-specific reading priorities."""

    questions = _read_json(
        PROJECT_ROOT / "src/leaders_db/conversational_evidence/data/questions.json"
    )
    selected = next(
        chapter["questions"]
        for chapter in questions["chapters"]
        if chapter["id"] == config.chapter_id
    )
    return (
        "Prepare a concise reading brief for a document reader. Do not research, "
        "summarize the unseen document, score the ruler, or invent claims. Identify "
        "which supplied Chapter 5B questions are most likely relevant, facts and "
        "qualifications to extract, official-claim verification needs, likely opposing "
        "perspectives, and document-type-specific traps.\n\n"
        f"Document: {document['title']}\n"
        f"Document type: {document['document_type']}\n"
        f"Source role: {document['source_role']}\n"
        f"Questions:\n{json.dumps(selected, ensure_ascii=False)}"
    )


def render_content_audit_prompt(source_map: ReaderSummaryEnvelope, extract: str) -> str:
    """Render a content-only audit that expressly ignores serialization quality."""

    return (
        "Audit the normalized source map against the original extract. Ignore prose "
        "style and all formatting problems in the original reader output. Count only "
        "affirmative evidence claims in claim_count; do not count an explicitly "
        "labelled limitation, absence-of-evidence warning, or reopen request as an "
        "accepted claim requiring an affirmative locator. Do not count source-identity "
        "metadata such as title, catalog ID, or manifest URL; provenance metadata is "
        "verified separately against the frozen manifest. Count a locator as usable "
        "when it identifies the supporting unit, block, page, section, article, table, "
        "or record precisely enough to reopen it. Identify material omitted facts and "
        "qualifications separately. An omission makes content_usable false only when "
        "it removes or distorts evidence decisive to the chapter questions; otherwise "
        "record material_omission=true and explain it without failing usability. A "
        "formatting repair is never a content failure. Return the required JSON only.\n\n"
        f"READER SUMMARY:\n{source_map.reader_output}\n\n"
        f"ORIGINAL EXTRACT:\n{extract}"
    )


def render_factual_review_prompt(reader_output: str, extract: str) -> str:
    """Ask an independent low-cost pass to correct content against the source."""

    return (
        "Act only as a factual verifier of the draft source map against the original "
        "extract. Return the corrected draft in readable Markdown. You may delete an "
        "unsupported claim or minimally replace its exact unit, time span, comparator, "
        "qualification, causal wording, legal status, attribution, or locator with the "
        "wording supported by the cited passage. Do not add claims, calculate implied "
        "values or differences, reconcile figures, infer accounting scope, speculate, "
        "or synthesize new conclusions. Do not generally expand the draft. You may "
        "restore an omitted fact only when it is decisive to a supplied chapter lens, "
        "and then only under `VERIFIED ADDITIONS` with (1) the exact supporting source "
        "passage, (2) a minimal faithful paraphrase, and (3) its precise locator. If an "
        "omission cannot meet all three conditions, list it only under `REOPEN REQUESTS`. "
        "Every retained or restored affirmative claim must have a precise locator into "
        "the supplied extract. Do not score and do not trust the first reader without "
        "checking the original. For legal instruments specifically: do not convert a "
        "signing date into a publication or effective date; do not infer beneficiaries "
        "or incidence from covered products; do not infer a recurring legal requirement "
        "from one period-specific instrument; and do not infer a shock-response purpose "
        "unless the text states it. Formatting is secondary to factual fidelity.\n\n"
        f"DRAFT SOURCE MAP:\n{reader_output}\n\n"
        f"ORIGINAL EXTRACT:\n{extract}"
    )


def execute_prompt(
    profile: ResearchModelProfile,
    prompt: str,
    *,
    output_path: Path,
    events_path: Path,
    stderr_path: Path,
    writable_dir: Path,
    schema_model: type[BaseModel] | None = None,
) -> None:
    """Execute one isolated model turn and persist complete provider artifacts."""

    schema_path: Path | None = None
    if schema_model is not None:
        schema_path = writable_dir / f"{output_path.stem}.schema.json"
        _write_json(schema_path, schema_model.model_json_schema())
    command = build_codex_exec_command(
        profile=profile,
        project_root=PROJECT_ROOT,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=writable_dir,
        isolated_web_research=True,
    )
    with (
        events_path.open("w", encoding="utf-8") as events,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=events,
            stderr=stderr,
            check=True,
        )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
