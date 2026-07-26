"""Find a question-aware M3 semantic-compression frontier without ratio targets."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from leaders_db.conversational_evidence.document_reader_experiment import (
    extract_json_object,
)
from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import (
    ResearchModelProfile,
    load_research_model_profiles,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PROFILES = PROJECT_ROOT / "configs/research-models.yaml"
DEFAULT_DOCUMENTS = ("BOOK-013", "MAC-010", "IMP-001")


class CompressionReview(BaseModel):
    """Content-based review of one compressed document synthesis."""

    schema_version: str = "m3_compression_review_v2"
    source_id: str
    attempt: int = Field(ge=0)
    acceptable_for_handoff: bool
    serious_loss: bool
    concrete_fact_payload_sufficient: bool
    judge_can_reason_without_routine_reopening: bool
    abstract_or_back_cover_failure: bool
    factual_error_count: int = Field(ge=0)
    factual_errors: list[str]
    lost_decisive_takeaways: list[str]
    changed_emphasis_or_attribution: list[str]
    traceability_problems: list[str]
    material_episodes_or_details_lost: list[str]
    routine_reopening_reasons: list[str]
    valuable_redundancy_remaining: list[str]
    further_compression_appears_safe: bool
    assessment: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--source-id", action="append", dest="source_ids")
    parser.add_argument(
        "--all-sources",
        action="store_true",
        help="Process every acquired document in manifest order.",
    )
    parser.add_argument("--refresh-reviews", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = load_research_model_profiles(MODEL_PROFILES).profiles["minimax-m3-long-context"]
    manifest = _read_json(run_dir / "manifest.json")
    documents = {item["requested_source_id"]: item for item in manifest["acquired_documents"]}
    if args.all_sources and args.source_ids:
        parser.error("--all-sources cannot be combined with --source-id")
    source_ids = (
        tuple(documents)
        if args.all_sources
        else tuple(args.source_ids or DEFAULT_DOCUMENTS)
    )
    questions = _chapter_questions(run_dir)
    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    results = []
    for source_id in source_ids:
        results.append(
            run_document(
                run_dir,
                output_dir,
                documents[source_id],
                questions=questions,
                attempts=args.attempts,
                profile=profile,
                refresh_reviews=args.refresh_reviews,
            )
        )
    _write_json(
        output_dir / "frontier-summary.json",
        {
            "schema_version": "m3_compression_frontier_v2",
            "source_ids": source_ids,
            "attempts_requested": args.attempts,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started_clock, 3),
            "documents": results,
        },
    )


def run_document(
    run_dir: Path,
    output_dir: Path,
    document: dict[str, Any],
    *,
    questions: list[dict[str, Any]],
    attempts: int,
    profile: ResearchModelProfile,
    refresh_reviews: bool,
) -> dict[str, Any]:
    source_id = document["requested_source_id"]
    extraction = _read_json(run_dir / document["extracted_path"])
    original = _render_original(extraction)
    document_dir = output_dir / source_id
    document_dir.mkdir(parents=True, exist_ok=True)
    previous: str | None = None
    attempt_results = []
    for attempt in range(attempts):
        attempt_dir = document_dir / f"attempt-{attempt:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        summary_path = attempt_dir / "summary.md"
        prompt = _render_summary_prompt(
            document,
            original,
            questions,
            previous=previous,
            attempt=attempt,
        )
        (attempt_dir / "summary-prompt.txt").write_text(prompt, encoding="utf-8")
        if not summary_path.exists():
            _execute(
                profile,
                prompt,
                output_path=summary_path,
                events_path=attempt_dir / "summary-events.jsonl",
                stderr_path=attempt_dir / "summary-stderr.txt",
                writable_dir=attempt_dir,
            )
        summary = summary_path.read_text(encoding="utf-8")
        review_path = attempt_dir / "review.json"
        review_prompt = _render_review_prompt(
            source_id,
            original,
            summary,
            questions,
            attempt=attempt,
        )
        (attempt_dir / "review-prompt.txt").write_text(review_prompt, encoding="utf-8")
        if refresh_reviews or not review_path.exists():
            _execute(
                profile,
                review_prompt,
                output_path=review_path,
                events_path=attempt_dir / "review-events.jsonl",
                stderr_path=attempt_dir / "review-stderr.txt",
                writable_dir=attempt_dir,
                schema_model=CompressionReview,
            )
        review = _normalize_review(
            _read_json(review_path),
            source_id=source_id,
            attempt=attempt,
        )
        normalized_review_path = attempt_dir / "review-normalized.json"
        _write_json(normalized_review_path, review.model_dump(mode="json"))
        attempt_results.append(
            {
                "attempt": attempt,
                "summary_path": str(summary_path.relative_to(output_dir)),
                "review_path": str(review_path.relative_to(output_dir)),
                "normalized_review_path": str(normalized_review_path.relative_to(output_dir)),
                "source_characters": len(original),
                "summary_characters": len(summary),
                "observed_character_ratio": round(len(original) / len(summary), 3),
                "review": review.model_dump(mode="json"),
            }
        )
        previous = summary
        if attempt >= 2 and (review.serious_loss or not review.further_compression_appears_safe):
            break
    acceptable = [item for item in attempt_results if item["review"]["acceptable_for_handoff"]]
    selected = max(
        acceptable,
        key=lambda item: item["observed_character_ratio"],
        default=None,
    )
    return {
        "source_id": source_id,
        "document_type": document["document_type"],
        "estimated_source_tokens": document["estimated_source_tokens"],
        "attempts": attempt_results,
        "selected_attempt": selected["attempt"] if selected else None,
        "selected_observed_character_ratio": (
            selected["observed_character_ratio"] if selected else None
        ),
    }


def _normalize_review(  # noqa: PLR0911, PLR0915
    value: dict[str, Any],
    *,
    source_id: str,
    attempt: int,
) -> CompressionReview:
    """Normalize alternate M3 organizations without treating format as quality."""

    try:
        return CompressionReview.model_validate(value)
    except ValueError:
        # V1 normalization branches are retained so old experimental artifacts remain
        # readable. They are deliberately ineligible under the stricter V2 handoff
        # contract because V1 did not test factual payload or downstream judge utility.
        v2_defaults = {
            "concrete_fact_payload_sufficient": False,
            "judge_can_reason_without_routine_reopening": False,
            "abstract_or_back_cover_failure": True,
            "material_episodes_or_details_lost": [
                "Not assessed by the V2 decision-useful factual-payload rubric."
            ],
            "routine_reopening_reasons": [
                "Not assessed by the V2 closed-book judge-utility test."
            ],
        }
        if "important_episodes_or_facts_lost_that_prevent_ordinary_reasoning" in value:
            lost = [
                str(item)
                for item in value.get(
                    "important_episodes_or_facts_lost_that_prevent_ordinary_reasoning",
                    [],
                )
            ]
            abstract_failure = bool(value.get("abstract_or_back_cover_failure", False))
            payload_sufficient = bool(value.get("concrete_fact_payload_sufficient", False))
            judge_ready = bool(
                value.get("judge_can_reason_without_routine_reopening", False)
            )
            acceptable = bool(
                value.get("acceptable_for_handoff", False)
                and payload_sufficient
                and judge_ready
                and not abstract_failure
            )
            return CompressionReview(
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=acceptable,
                serious_loss=not acceptable,
                concrete_fact_payload_sufficient=payload_sufficient,
                judge_can_reason_without_routine_reopening=judge_ready,
                abstract_or_back_cover_failure=abstract_failure,
                factual_error_count=0,
                factual_errors=[],
                lost_decisive_takeaways=lost,
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                material_episodes_or_details_lost=lost,
                routine_reopening_reasons=(
                    [str(value.get("summary", ""))] if not judge_ready else []
                ),
                valuable_redundancy_remaining=[],
                further_compression_appears_safe=False,
                assessment=str(value.get("summary", "")),
            )
        if "overall" in value and isinstance(value["overall"], dict):
            overall = value["overall"]
            findings = value.get("cross_cutting_findings", {})
            material_errors = [str(item) for item in findings.get("material_errors", [])]
            serious_loss = bool(overall.get("serious_loss", False))
            judgment = value.get("compression_judgment", {})
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=(
                    overall.get("label") == "retain" and not material_errors and not serious_loss
                ),
                serious_loss=serious_loss,
                factual_error_count=len(material_errors),
                factual_errors=material_errors,
                lost_decisive_takeaways=[],
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                valuable_redundancy_remaining=(
                    [str(judgment.get("reason", ""))] if overall.get("can_compress_further") else []
                ),
                further_compression_appears_safe=bool(overall.get("can_compress_further", False)),
                assessment=str(judgment.get("reason", "")),
            )
        if "findings" in value and "required_corrections" in value:
            findings = list(value.get("findings", []))
            factual_errors = [
                str(item.get("assessment", ""))
                for item in findings
                if item.get("type") in {"material_factual_error", "unsupported_or_overstated_claim"}
            ]
            lost = [
                str(item.get("assessment", ""))
                for item in findings
                if item.get("type") in {"serious_omission", "important_omission"}
            ]
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=value.get("verdict") != "fail",
                serious_loss=bool(value.get("serious_loss", False)),
                factual_error_count=len(factual_errors),
                factual_errors=factual_errors,
                lost_decisive_takeaways=lost,
                changed_emphasis_or_attribution=[],
                traceability_problems=[
                    str(item.get("assessment", ""))
                    for item in findings
                    if item.get("type") == "reopenability_issue"
                ],
                valuable_redundancy_remaining=[
                    str(item.get("assessment", ""))
                    for item in findings
                    if item.get("type") == "compression_assessment"
                ],
                further_compression_appears_safe=bool(
                    value.get("further_compressible_without_serious_loss", False)
                ),
                assessment="; ".join(str(item) for item in value.get("required_corrections", [])),
            )
        if "document_level" in value:
            document_level = value.get("document_level", {})
            compression = value.get("compressibility", {})
            acceptable = document_level.get("verdict") == "faithful"
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=acceptable,
                serious_loss=not acceptable,
                factual_error_count=0,
                factual_errors=[],
                lost_decisive_takeaways=[],
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                valuable_redundancy_remaining=(
                    [str(compression.get("rationale", ""))]
                    if compression.get("can_compress_further")
                    else []
                ),
                further_compression_appears_safe=bool(
                    compression.get("can_compress_further", False)
                ),
                assessment=str(document_level.get("notes", "")),
            )
        if "factual_fidelity_checks" in value:
            checks = list(value.get("factual_fidelity_checks", []))
            factual_errors = [
                str(item.get("claim_synthesis", ""))
                for item in checks
                if not str(item.get("verdict", "")).lower().startswith("accurate")
            ]
            loss = value.get("omission_or_loss_assessment", {})
            serious_findings = [str(item) for item in loss.get("serious_loss_findings", [])]
            compression = value.get("compressibility_assessment", {})
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=not factual_errors and not serious_findings,
                serious_loss=bool(serious_findings),
                factual_error_count=len(factual_errors),
                factual_errors=factual_errors,
                lost_decisive_takeaways=serious_findings,
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                valuable_redundancy_remaining=(
                    [str(compression.get("rationale", ""))]
                    if compression.get("can_be_compressed")
                    else []
                ),
                further_compression_appears_safe=bool(compression.get("can_be_compressed", False)),
                assessment=str(value.get("overall_judgment", "")),
            )
        if "document_id" in value:
            issues = [str(item) for item in value.get("included_claim_issues", [])]
            omissions = [str(item) for item in value.get("omissions_material_to_understanding", [])]
            serious_loss = bool(value.get("serious_loss", False) or omissions)
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=(
                    value.get("overall_assessment") == "pass" and not issues and not serious_loss
                ),
                serious_loss=serious_loss,
                factual_error_count=len(issues),
                factual_errors=issues,
                lost_decisive_takeaways=omissions,
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                valuable_redundancy_remaining=(
                    [str(value.get("compression_judgment", ""))]
                    if value.get("can_compress_further")
                    else []
                ),
                further_compression_appears_safe=bool(value.get("can_compress_further", False)),
                assessment=str(value.get("notes", value.get("compression_judgment", ""))),
            )
        if "factual_fidelity_issues" in value:
            issues = [str(item) for item in value.get("factual_fidelity_issues", [])]
            serious_loss = bool(value.get("serious_loss", False))
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=not issues and not serious_loss,
                serious_loss=serious_loss,
                factual_error_count=len(issues),
                factual_errors=issues,
                lost_decisive_takeaways=[],
                changed_emphasis_or_attribution=[],
                traceability_problems=[],
                valuable_redundancy_remaining=(
                    [str(value.get("compression_notes", ""))]
                    if value.get("compression_possible")
                    else []
                ),
                further_compression_appears_safe=bool(value.get("compression_possible", False)),
                assessment=str(
                    value.get(
                        "reopenability_assessment",
                        value.get("factual_fidelity_notes", ""),
                    )
                ),
            )
        if "serious_loss_check" in value:
            factual_checks = list(value.get("factual_checks", []))
            factual_errors = [
                str(item.get("note") or item.get("claim"))
                for item in factual_checks
                if item.get("fidelity") != "accurate"
            ]
            loss_check = value.get("serious_loss_check", {})
            lost = [
                key for key, present in loss_check.items() if key != "notes" and present is False
            ]
            compression = value.get("compression_assessment", {})
            serious_loss = bool(lost)
            return CompressionReview(
                **v2_defaults,
                source_id=source_id,
                attempt=attempt,
                acceptable_for_handoff=not factual_errors and not serious_loss,
                serious_loss=serious_loss,
                factual_error_count=len(factual_errors),
                factual_errors=factual_errors,
                lost_decisive_takeaways=lost,
                changed_emphasis_or_attribution=[],
                traceability_problems=[
                    str(item.get("note") or item.get("claim"))
                    for item in factual_checks
                    if item.get("reopenable") is False and item.get("fidelity") != "accurate"
                ],
                valuable_redundancy_remaining=(
                    [str(compression.get("notes", ""))]
                    if compression.get("can_be_compressed_further")
                    else []
                ),
                further_compression_appears_safe=bool(
                    compression.get("can_be_compressed_further", False)
                ),
                assessment=str(value.get("summary", loss_check.get("notes", ""))),
            )
        factual = value.get("factual_fidelity", {})
        coverage = value.get("coverage", {})
        reopenability = value.get("reopenability", {})
        compression = value.get("compression", {})
        factual = factual if isinstance(factual, dict) else {}
        coverage = coverage if isinstance(coverage, dict) else {}
        reopenability = reopenability if isinstance(reopenability, dict) else {}
        compression = compression if isinstance(compression, dict) else {}
        factual_findings = list(factual.get("findings", []))
        coverage_findings = list(coverage.get("findings", []))
        reopen_findings = list(reopenability.get("findings", []))
        serious_loss = bool(value.get("serious_loss", False))
        acceptable = (
            value.get("verdict") == "pass"
            and factual.get("status", "pass") == "pass"
            and coverage.get("status", "pass") == "pass"
            and reopenability.get("status", "pass") == "pass"
            and not serious_loss
        )
        return CompressionReview(
            **v2_defaults,
            source_id=source_id,
            attempt=attempt,
            acceptable_for_handoff=acceptable,
            serious_loss=serious_loss,
            factual_error_count=(len(factual_findings) if factual.get("status") != "pass" else 0),
            factual_errors=(factual_findings if factual.get("status") != "pass" else []),
            lost_decisive_takeaways=(coverage_findings if coverage.get("status") != "pass" else []),
            changed_emphasis_or_attribution=[],
            traceability_problems=(
                reopen_findings if reopenability.get("status") != "pass" else []
            ),
            valuable_redundancy_remaining=(
                [str(compression.get("assessment", ""))]
                if compression.get("can_compress_further_without_serious_loss")
                else []
            ),
            further_compression_appears_safe=bool(
                compression.get("can_compress_further_without_serious_loss", False)
            ),
            assessment=str(
                value.get(
                    "overall_assessment",
                    compression.get("assessment", ""),
                )
            ),
        )


def _render_summary_prompt(
    document: dict[str, Any],
    original: str,
    questions: list[dict[str, Any]],
    *,
    previous: str | None,
    attempt: int,
) -> str:
    common = (
        "Produce a substantive document-level evidence paper for AMLO, Mexico, 2022, "
        "Chapter 5B. Do not score. This is not an abstract, executive summary, back-cover "
        "paragraph, table of contents, or list of themes. The downstream judge needs the "
        "facts themselves, not reassurance that relevant facts exist in the source. "
        "Preserve enough concrete episodes, actors, actions, dates or periods, causal "
        "sequences, outcomes, quantitative details, institutional mechanisms, competing "
        "accounts, and author interpretations for the judge to reason from this paper "
        "without routinely reopening the original. Ground every material conclusion in "
        "specific factual accounts and give precise locators for consequential claims. "
        "Explain what happened and why it matters to the supplied questions; do not merely "
        "name a topic. Preserve material contrary and exculpatory evidence, qualifications, "
        "source perspective, and target-period limits. Distinguish observed fact, official "
        "or subject assertion, allegation, and interpretation. Select intelligently rather "
        "than inventorying every sentence, but do not trade away factual texture for a "
        "shorter output. Formatting is secondary to content. There is no compression-ratio "
        "or token target; compression is acceptable only after decision-useful detail is "
        "secure. State each material fact or account once and attach every applicable "
        "question ID to that single account. Do not restate evidence in a later "
        "question-by-question section, reproduce the question wording, or pad missing "
        "lenses with repeated no-evidence paragraphs. End with only a compact mapping of "
        "question IDs to the already-written findings and one gap note. Keep the paper "
        "proportionate to useful source content: a short record with a few relevant facts "
        "should yield a short, nearly lossless note, never an expanded essay; a long, dense "
        "source may require a substantial evidence paper."
    )
    if previous is None:
        task = (
            "Create the first complete, decision-useful evidence paper directly from the "
            "source. Err on the side of retaining substantive factual accounts. A later "
            "attempt may test whether genuine redundancy can be removed."
        )
    else:
        task = (
            "Attempt to remove only genuine redundancy from the previous evidence paper. "
            "Do not collapse detailed accounts into thematic conclusions. Retain it "
            "unchanged where shortening would make a judge reopen the source to learn what "
            "actually happened. Return a complete replacement paper, not editing "
            "instructions or a change log."
        )
    return (
        f"{common}\n\n{task}\nAttempt: {attempt}\n"
        f"Document: {document['title']}\n"
        f"Document type: {document['document_type']}\n"
        f"Source role: {document['source_role']}\n"
        f"Questions:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        f"PREVIOUS SYNTHESIS:\n{previous or 'NONE'}\n\n"
        f"ORIGINAL DOCUMENT WITH LOCATORS:\n{original}"
    )


def _render_review_prompt(
    source_id: str,
    original: str,
    summary: str,
    questions: list[dict[str, Any]],
    *,
    attempt: int,
) -> str:
    return (
        "Act as a fresh independent evidence and downstream-judge-utility reviewer. "
        "Compare the evidence paper with the complete original for the supplied questions. "
        "The paper must contain the facts themselves: concrete episodes, actors, actions, "
        "dates or periods, mechanisms, outcomes, material figures, competing accounts, and "
        "precise locators. It is not enough to preserve high-level themes or conclusions. "
        "Fail any paper that resembles an abstract, back-cover summary, or table of contents; "
        "that says what topics exist without adequately explaining what happened; or that "
        "would force the judge to reopen the original for ordinary reasoning about claims that "
        "this source can actually support. Do not fail the paper because the original source "
        "itself lacks target-year evidence; identify that as a source limitation. The test is "
        "whether the paper faithfully carries forward the source's useful question-relevant "
        "content. Do not demand unrelated biographical detail merely because it appears in the "
        "original. Personal, electoral, health, family, campaign, or party-history details count "
        "only when you explain a material connection to a supplied Chapter 5B question. "
        "List important episodes or factual details whose loss prevents such reasoning. "
        "Check every included consequential claim for factual fidelity, attribution, and "
        "locator quality. Omission is acceptable only when it is genuinely duplicative or "
        "immaterial to the questions, not merely because the headline conclusion survives. "
        "Also fail needless expansion: repeated question text, evidence retold under "
        "multiple lenses, or analytical prose longer than needed to carry the source's "
        "question-relevant factual payload. Proportionality is content-based, not a fixed "
        "token or ratio target. "
        "Set acceptable_for_handoff true only when concrete_fact_payload_sufficient and "
        "judge_can_reason_without_routine_reopening are both true and "
        "abstract_or_back_cover_failure is false. Judge further compression cautiously and "
        "without a target ratio. Return the required JSON only.\n\n"
        f"Source ID: {source_id}\nAttempt: {attempt}\n"
        f"Questions:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        f"SYNTHESIS:\n{summary}\n\nORIGINAL:\n{original}"
    )


def _render_original(extraction: dict[str, Any]) -> str:
    return "\n\n".join(
        f"<<< UNIT {item['unit']} | {item.get('locator', '')} >>>\n{item['text']}"
        for item in extraction["units"]
    )


def _chapter_questions(run_dir: Path) -> list[dict[str, Any]]:
    questions = _read_json(run_dir / "frozen/questions.json")
    if isinstance(questions, list):
        return questions
    if "questions" in questions:
        return questions["questions"]
    for chapter in questions["chapters"]:
        if chapter["id"] == "5B":
            return chapter["questions"]
    raise ValueError("Chapter 5B questions not found")


def _execute(
    profile: ResearchModelProfile,
    prompt: str,
    *,
    output_path: Path,
    events_path: Path,
    stderr_path: Path,
    writable_dir: Path,
    schema_model: type[BaseModel] | None = None,
) -> None:
    schema_path = None
    if schema_model is not None:
        schema_path = writable_dir / f"{output_path.stem}.schema.json"
        schema_path.write_text(
            json.dumps(schema_model.model_json_schema(), indent=2) + "\n",
            encoding="utf-8",
        )
    command = build_codex_exec_command(
        profile=profile,
        project_root=PROJECT_ROOT,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=writable_dir,
        isolated_web_research=True,
    )
    with events_path.open("w", encoding="utf-8") as stdout_file:
        with stderr_path.open("w", encoding="utf-8") as stderr_file:
            subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=stdout_file,
                stderr=stderr_file,
                cwd=PROJECT_ROOT,
                check=True,
            )


def _read_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        extracted = extract_json_object(text)
        return extracted if isinstance(extracted, dict) else json.loads(extracted)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
