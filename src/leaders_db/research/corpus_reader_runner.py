"""Execute resumable whole-context reading and fresh passage verification batches."""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from ._codex_worker_artifacts import read_codex_usage
from .codex_worker_command import build_codex_exec_command
from .corpus_evidence_bind import bind_batch_evidence
from .corpus_reader_models import (
    BatchFactOutput,
    BatchVerification,
    BoundEvidence,
)
from .corpus_reader_normalize import normalize_reader_output, reconcile_reader
from .corpus_reading_plan import CorpusReadingPlan, ReadingBatch
from .corpus_verification import (
    apply_verification as _apply_verification,
)
from .corpus_verification import (
    partition_verification as _partition_verification,
)
from .corpus_verification import (
    verification_prompt as _verification_prompt,
)
from .model_profiles import load_research_model_profiles


def run_corpus_reading(
    *,
    project_root: Path,
    acquisition_dir: Path,
    plan_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    parallel_batches: int = 3,
) -> Path:
    """Read, bind, and independently verify every queued reading batch."""

    plan = CorpusReadingPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if "document_reader" not in profile.roles:
        raise ValueError("selected profile does not permit document reading")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
        futures = {
            executor.submit(
                _run_batch,
                project_root=project_root,
                acquisition_dir=acquisition_dir,
                plan=plan,
                batch=batch,
                output_dir=output_dir,
                profile=profile,
            ): batch.batch_id
            for batch in plan.batches
        }
        for future in as_completed(futures):
            batch_id = futures[future]
            try:
                results[batch_id] = future.result()
            except Exception as exc:
                results[batch_id] = {
                    "batch_id": batch_id,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "evidence_count": 0,
                    "accepted_count": 0,
                }
    ordered = [results[batch.batch_id] for batch in plan.batches]
    path = output_dir / "reading-run-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "corpus_reading_run_v1",
                "profile": profile_name,
                "model": profile.model,
                "batches": ordered,
                "evidence_count": sum(item["evidence_count"] for item in ordered),
                "failed_batch_ids": [
                    item["batch_id"] for item in ordered if item.get("status") == "failed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _run_batch(
    *,
    project_root: Path,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    output_dir: Path,
    profile,
) -> dict[str, Any]:
    started = time.monotonic()
    batch_dir = output_dir / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = batch_dir / "verified-evidence.json"
    recovered = _recover_batch_evidence(
        acquisition_dir=acquisition_dir,
        plan=plan,
        batch=batch,
        batch_dir=batch_dir,
    )
    if recovered is not None:
        return _batch_result(
            batch,
            recovered,
            batch_dir,
            resumed=True,
            elapsed_seconds=time.monotonic() - started,
        )
    prompt = _reader_prompt(acquisition_dir, plan, batch)
    reader = _load_or_execute_json(
        project_root,
        profile,
        prompt,
        BatchFactOutput,
        batch_dir / "reader",
        expected_source_ids=set(batch.source_ids),
    )
    reader = reconcile_reader(reader, batch)
    bound = bind_batch_evidence(
        acquisition_dir=acquisition_dir,
        plan=plan,
        batch=batch,
        reader_output=reader,
    )
    (batch_dir / "bound-evidence.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in bound], indent=2) + "\n",
        encoding="utf-8",
    )
    if bound:
        verification = _load_or_execute_verification(
            project_root, profile, bound, batch_dir / "verification"
        )
        try:
            evidence = _apply_verification(bound, verification)
        except ValueError:
            verification_path = batch_dir / "verification/output.json"
            verification_path.rename(
                verification_path.with_suffix(".unreconciled.json")
            )
            verification = _load_or_execute_verification(
                project_root,
                profile,
                bound,
                batch_dir / "verification",
            )
            evidence = _apply_verification(bound, verification)
    else:
        evidence = ()
    evidence_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in evidence], indent=2) + "\n",
        encoding="utf-8",
    )
    return _batch_result(
        batch, evidence, batch_dir, resumed=False, elapsed_seconds=time.monotonic() - started
    )


def _recover_batch_evidence(
    *,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    batch_dir: Path,
) -> tuple[BoundEvidence, ...] | None:
    evidence_path = batch_dir / "verified-evidence.json"
    reader_path = batch_dir / "reader/output.json"
    if not evidence_path.is_file() or not reader_path.is_file():
        return None
    try:
        try:
            reader = BatchFactOutput.model_validate_json(
                reader_path.read_text(encoding="utf-8")
            )
        except ValueError:
            reader = normalize_reader_output(reader_path, set(batch.source_ids))
        reader = reconcile_reader(reader, batch)
        bound = bind_batch_evidence(
            acquisition_dir=acquisition_dir,
            plan=plan,
            batch=batch,
            reader_output=reader,
        )
        if bound:
            verification = BatchVerification.model_validate_json(
                (batch_dir / "verification/output.json").read_text(encoding="utf-8")
            )
            expected = _apply_verification(bound, verification)
        else:
            expected = ()
        stored = tuple(BoundEvidence.model_validate(item) for item in _read(evidence_path))
    except (OSError, ValueError):
        return None
    return stored if stored == expected else None


def _reader_prompt(
    acquisition_dir: Path, plan: CorpusReadingPlan, batch: ReadingBatch
) -> str:
    documents = {item.source_id: item for item in plan.documents}
    sections = []
    for source_id in batch.source_ids:
        document = documents[source_id]
        extraction = _read(acquisition_dir / str(document.extracted_path))
        start, end = batch.unit_ranges[source_id]
        units = "\n\n".join(
            f"[{source_id} UNIT {item['unit']} | {item['locator']}]\n{item['text']}"
            for item in extraction["units"]
            if start <= int(item["unit"]) <= end
        )
        sections.append(
            f"SOURCE {source_id}\nTITLE: {document.title}\nURL: {document.url}\n{units}"
        )
    questions = _read(
        Path(__file__).parents[1] / "conversational_evidence/data/questions.json"
    )
    return (
        "Read the complete supplied documents once. Identify materially distinct, "
        "concrete facts relevant to the supplied 1B-8B questions for "
        f"{plan.ruler_name} during {plan.period_start_year}-{plan.period_end_year}. "
        "Preserve adverse, favorable, mixed, exculpatory, and "
        "qualifying facts. Each record must describe one event, policy, quantitative "
        "result, or institutional finding; emit separate records for independent facts "
        "even when they occur in the same source. Do not write document essays and do "
        "not score. Cite one to three contiguous labeled units for each fact. State each "
        "fact once. Map a question ID only when that concrete fact materially helps "
        "answer the exact lens; thematic association is insufficient. Account for every "
        "source either with at least one fact "
        "or in documents_with_no_material_fact. Return only the schema JSON.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        + "\n\n--- DOCUMENT ---\n\n".join(sections)
    )


def _load_or_execute_verification(
    project_root: Path,
    profile,
    evidence: tuple[BoundEvidence, ...],
    output_dir: Path,
) -> BatchVerification:
    output_path = output_dir / "output.json"
    if output_path.is_file():
        return BatchVerification.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
    groups = _partition_verification(evidence)
    if len(groups) == 1:
        return _load_or_execute_json(
            project_root,
            profile,
            _verification_prompt(evidence),
            BatchVerification,
            output_dir,
        )
    verdicts = []
    for number, group in enumerate(groups, start=1):
        result = _load_or_execute_json(
            project_root,
            profile,
            _verification_prompt(group),
            BatchVerification,
            output_dir / f"part-{number:03d}",
        )
        verdicts.extend(result.verdicts)
    combined = BatchVerification(verdicts=tuple(verdicts))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(combined.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return combined


def execute_json_model(
    project_root: Path,
    profile,
    prompt: str,
    model: type[BaseModel],
    output_dir: Path,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "prompt.txt"
    schema_path = output_dir / "schema.json"
    output_path = output_dir / "output.json"
    events_path = output_dir / "events.jsonl"
    stderr_path = output_dir / "stderr.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    schema = model.model_json_schema()
    make_strict_response_schema(schema)
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    command = build_codex_exec_command(
        profile=profile,
        project_root=project_root,
        schema_path=schema_path,
        final_message_path=output_path,
        writable_dir=output_dir,
        isolated_web_research=True,
    )
    with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        subprocess.run(
            command, input=prompt, text=True, stdout=events, stderr=stderr, check=True
        )
    return model.model_validate_json(output_path.read_text(encoding="utf-8"))


def _load_or_execute_json(
    project_root: Path,
    profile,
    prompt: str,
    model: type[BaseModel],
    output_dir: Path,
    expected_source_ids: set[str] | None = None,
):
    output_path = output_dir / "output.json"
    if output_path.is_file():
        try:
            return model.model_validate_json(output_path.read_text(encoding="utf-8"))
        except ValueError:
            if model is BatchFactOutput and expected_source_ids is not None:
                return normalize_reader_output(output_path, expected_source_ids)
            output_path.rename(output_path.with_suffix(".invalid.json"))
    try:
        return execute_json_model(project_root, profile, prompt, model, output_dir)
    except ValueError:
        if model is BatchFactOutput and expected_source_ids is not None:
            return normalize_reader_output(output_path, expected_source_ids)
        raise


def _batch_result(
    batch: ReadingBatch,
    evidence: list[BoundEvidence] | tuple[BoundEvidence, ...],
    batch_dir: Path,
    *,
    resumed: bool,
    elapsed_seconds: float,
) -> dict[str, Any]:
    usage = []
    for path in sorted(batch_dir.glob("*/events.jsonl")):
        item = read_codex_usage(path)
        usage.append(item.model_dump(mode="json") if item is not None else None)
    return {
        "batch_id": batch.batch_id,
        "source_ids": batch.source_ids,
        "estimated_source_tokens": batch.estimated_tokens,
        "evidence_count": len(evidence),
        "accepted_count": sum(item.verification_status != "rejected" for item in evidence),
        "resumed": resumed,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "usage": usage,
    }


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["execute_json_model", "run_corpus_reading"]
