"""Compact conversational projections and run comparative chapter judges."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from leaders_db.research.chapter_guides import load_chapter_guide
from leaders_db.research.chapter_judge_models import (
    ChapterJudgmentBatch,
    codex_chapter_judgment_json_schema,
)
from leaders_db.research.chapter_judge_prompt import build_chapter_judge_prompt
from leaders_db.research.chapter_projection import RulerChapterProjection

CHAPTERS = tuple(f"{number}B" for number in range(1, 9))
DISABLED = ("apps", "plugins", "multi_agent", "goals")
CODEX_INPUT_CHARACTER_LIMIT = 1_048_576


def prepare_compact_inputs(
    conversion_dir: Path, output_dir: Path, *, evidence_per_lens: int = 4
) -> dict[str, Any]:
    """Keep diverse, lens-specific evidence while preserving an omission ledger."""

    if evidence_per_lens < 1:
        raise ValueError("evidence_per_lens must be positive")
    conversion = _object(conversion_dir / "conversion-report.json")
    if not conversion["ready_for_judging"]:
        raise ValueError("conversion report is not ready for judging")
    target_year = int(conversion["year"])
    chapters = []
    for chapter_id in CHAPTERS:
        source_paths = sorted((conversion_dir / "projections" / chapter_id).glob("*.json"))
        written = []
        omitted = []
        for source_path in source_paths:
            source = RulerChapterProjection.model_validate(_object(source_path))
            compact, removed = _compact_projection(source, evidence_per_lens)
            path = output_dir / "projections" / chapter_id / source_path.name
            _write_json(path, compact.model_dump(mode="json"))
            written.append(str(path))
            omitted.append(
                {
                    "iso3": source.iso3,
                    "source_projection": str(source_path),
                    "source_evidence": len(source.evidence),
                    "retained_evidence": len(compact.evidence),
                    "omitted_evidence_ids": removed,
                }
            )
        tokens = sum(_tokens(_object(Path(path))) for path in written)
        guide, rubric = load_chapter_guide(chapter_id)
        overhead = 5_000 + (len(guide.encode("utf-8")) + 2) // 3
        manifest = {
            "schema_version": "conversational_compact_chapter_v1",
            "chapter_id": chapter_id,
            "target_year": target_year,
            "rubric_version": rubric,
            "projection_paths": written,
            "evidence_per_lens": evidence_per_lens,
            "projection_tokens": tokens,
            "prompt_overhead_tokens": overhead,
            "estimated_input_tokens": tokens + overhead,
            "estimated_input_characters": sum(
                len(json.dumps(_object(Path(path)), ensure_ascii=False)) for path in written
            )
            + len(guide)
            + 60_000,
            "omission_ledger": omitted,
        }
        path = output_dir / "chapters" / f"{chapter_id}.json"
        _write_json(path, manifest)
        chapters.append({**manifest, "path": str(path)})
    report = {
        "schema_version": "conversational_compaction_report_v1",
        "source_conversion": str(conversion_dir / "conversion-report.json"),
        "target_year": target_year,
        "evidence_per_lens": evidence_per_lens,
        "chapters": chapters,
    }
    _write_json(output_dir / "compaction-report.json", report)
    return report


def run_judges(
    compact_dir: Path,
    output_dir: Path,
    *,
    model: str = "gpt-5.4-mini",
    workers: int = 3,
    timeout_seconds: int = 1800,
    chapter_ids: tuple[str, ...] = CHAPTERS,
    run_key: str | None = None,
    instruction_path: Path | None = None,
) -> dict[str, Any]:
    """Run incomplete chapter jobs concurrently and preserve every artifact."""

    if workers < 1:
        raise ValueError("workers must be positive")
    if not chapter_ids or any(chapter not in CHAPTERS for chapter in chapter_ids):
        raise ValueError("chapter_ids must contain only chapters 1B through 8B")
    output_dir.mkdir(parents=True, exist_ok=True)
    supplemental_instructions = (
        instruction_path.read_text(encoding="utf-8") if instruction_path else ""
    )
    compaction = _object(compact_dir / "compaction-report.json")
    target_year = int(compaction["target_year"])
    effective_run_key = run_key or f"{target_year}-gpt54mini-judges-v1"
    pending = [
        chapter
        for chapter in chapter_ids
        if not (output_dir / chapter / "judgment.json").is_file()
    ]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_chapter,
                compact_dir,
                output_dir,
                chapter,
                model,
                timeout_seconds,
                effective_run_key,
                target_year,
                supplemental_instructions,
            ): chapter
            for chapter in pending
        }
        for future in as_completed(futures):
            chapter = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"chapter_id": chapter, "status": "failed", "error": str(exc)})
            _write_summary(
                output_dir,
                model=model,
                workers=workers,
                chapter_ids=chapter_ids,
                new_results=results,
            )
    return _write_summary(
        output_dir,
        model=model,
        workers=workers,
        chapter_ids=chapter_ids,
        new_results=results,
    )


def repair_saved_judgments(compact_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Revalidate saved successful candidates after deterministic normalizations."""

    repaired = []
    manifests = {
        path.stem: path for path in (compact_dir / "chapters").glob("*.json")
    }
    for chapter_id in CHAPTERS:
        manifest_path = manifests.get(chapter_id)
        pending_path = output_dir / chapter_id / "judgment.pending.json"
        if manifest_path is None or not pending_path.is_file():
            continue
        manifest = _object(manifest_path)
        projections = tuple(
            (Path(path), RulerChapterProjection.model_validate(_object(Path(path))))
            for path in manifest["projection_paths"]
        )
        work = output_dir / chapter_id
        candidate = _normalize_candidate(
            _object(work / "judgment.pending.json"), chapter_id, projections
        )
        batch = ChapterJudgmentBatch.model_validate(candidate)
        _validate_batch(
            batch,
            chapter_id=chapter_id,
            target_year=int(manifest["target_year"]),
            projections=projections,
        )
        _write_json(work / "judgment.json", batch.model_dump(mode="json"))
        repaired.append(chapter_id)
    return {"repaired_chapters": repaired, "llm_calls": 0}


def apply_projection_review(output_dir: Path, review_path: Path) -> dict[str, Any]:
    """Clear only unchanged scores explicitly approved by targeted review."""

    reviews = _object(review_path).get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("projection review must contain a reviews list")
    cleared = []
    for review in reviews:
        if not isinstance(review, dict) or review.get("decision") not in {
            "clear_unchanged",
            "clear_null_nonrecoverable",
        }:
            continue
        chapter_id = str(review["chapter_id"])
        iso3 = str(review["iso3"])
        path = output_dir / chapter_id / "judgment.json"
        batch = _object(path)
        evaluation = next(item for item in batch["evaluations"] if item["iso3"] == iso3)
        existing_score = evaluation["score_1_to_10"]
        if existing_score != review.get("existing_score"):
            raise ValueError(f"review score does not match {iso3}/{chapter_id}")
        if review.get("recommended_score") != existing_score:
            raise ValueError(f"unchanged review changes score for {iso3}/{chapter_id}")
        if review["decision"] == "clear_null_nonrecoverable" and existing_score is not None:
            raise ValueError(
                f"nonrecoverable-null review has a numeric score for {iso3}/{chapter_id}"
            )
        evaluation["manual_review_required"] = False
        evaluation["manual_review_reason_type"] = None
        evaluation["manual_review_reason"] = None
        ChapterJudgmentBatch.model_validate(batch)
        _write_json(path, batch)
        cleared.append(f"{iso3}/{chapter_id}")
    return {"cleared": cleared, "remaining": len(reviews) - len(cleared)}


def _compact_projection(
    source: RulerChapterProjection, limit: int
) -> tuple[RulerChapterProjection, list[str]]:
    evidence = {item.evidence_id: item for item in source.evidence}
    keep = _select_compact_evidence_ids(source, limit)
    payload = source.model_dump(mode="json")
    payload["evidence"] = [item for item in payload["evidence"] if item["evidence_id"] in keep]
    payload["mappings"] = [item for item in payload["mappings"] if item["evidence_id"] in keep]
    payload["contextual_discovery_only_evidence_ids"] = [
        value for value in payload["contextual_discovery_only_evidence_ids"] if value in keep
    ]
    for item in payload["coverage"]:
        item["evidence_ids"] = [value for value in item["evidence_ids"] if value in keep]
    payload["estimated_input_tokens"] = _tokens(
        {key: value for key, value in payload.items() if key != "estimated_input_tokens"}
    )
    compact = RulerChapterProjection.model_validate(payload)
    removed = sorted(set(evidence) - keep)
    return compact, removed


def _select_compact_evidence_ids(
    source: RulerChapterProjection, limit: int
) -> set[str]:
    """Prefer substantive evidence and add distinct records across broad lens mappings."""

    evidence = {item.evidence_id: item for item in source.evidence}
    mappings = {(item.methodology_id, item.evidence_id): item for item in source.mappings}
    keep: set[str] = set()
    for methodology_id in source.methodology_ids:
        candidates = [
            item.evidence_id for item in source.mappings if item.methodology_id == methodology_id
        ]
        selected: list[str] = []
        domains: set[str] = set()
        while len(selected) < limit and candidates:
            semantic_best = max(
                _semantic_evidence_rank(
                    mappings[(methodology_id, evidence_id)].relation,
                    evidence[evidence_id].final_evidence_use,
                )
                for evidence_id in candidates
            )
            tier = [
                evidence_id
                for evidence_id in candidates
                if _semantic_evidence_rank(
                    mappings[(methodology_id, evidence_id)].relation,
                    evidence[evidence_id].final_evidence_use,
                )
                == semantic_best
            ]
            unused = [evidence_id for evidence_id in tier if evidence_id not in keep]
            pool = unused or tier
            evidence_id = max(
                pool,
                key=lambda value: _quality_evidence_rank(evidence[value], domains),
            )
            selected.append(evidence_id)
            candidates.remove(evidence_id)
            domain = _source_domain(evidence[evidence_id].url)
            if domain:
                domains.add(domain)
        keep.update(selected)
    target = min(
        len(source.methodology_ids),
        sum(item.final_evidence_use == "final_evidence" for item in source.evidence),
    )
    chapter_domains = {_source_domain(evidence[evidence_id].url) for evidence_id in keep}
    candidates = [
        item.evidence_id
        for item in source.evidence
        if item.final_evidence_use == "final_evidence" and item.evidence_id not in keep
    ]
    while len(keep) < target and candidates:
        evidence_id = max(
            candidates,
            key=lambda value: _quality_evidence_rank(evidence[value], chapter_domains),
        )
        keep.add(evidence_id)
        candidates.remove(evidence_id)
        domain = _source_domain(evidence[evidence_id].url)
        if domain:
            chapter_domains.add(domain)
    return keep


def _semantic_evidence_rank(relation: str, final_use: str) -> tuple[int, int]:
    relation_rank = {"supports": 3, "contradicts": 3, "mitigates": 2, "context": 1}
    use_rank = {"final_evidence": 3, "context": 2, "discovery_only": 1}
    return relation_rank.get(relation, 0), use_rank.get(final_use, 0)


def _quality_evidence_rank(evidence: Any, used_domains: set[str]) -> tuple[int, int, str]:
    confidence_rank = {
        "high": 5,
        "medium_high": 4,
        "medium": 3,
        "medium_low": 2,
        "low": 1,
        "not_assessed": 0,
    }
    domain = _source_domain(evidence.url)
    return (
        int(bool(domain and domain not in used_domains)),
        confidence_rank.get(evidence.source_confidence, 0),
        evidence.evidence_id,
    )


def _source_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _run_chapter(
    compact_dir: Path,
    output_dir: Path,
    chapter_id: str,
    model: str,
    timeout_seconds: int,
    run_key: str,
    target_year: int,
    supplemental_instructions: str,
) -> dict[str, Any]:
    work = output_dir / chapter_id
    work.mkdir(parents=True, exist_ok=True)
    manifest = _object(compact_dir / "chapters" / f"{chapter_id}.json")
    projections = tuple(
        (Path(path), RulerChapterProjection.model_validate(_object(Path(path))))
        for path in manifest["projection_paths"]
    )
    pending_path = work / "judgment.pending.json"
    profile_path = work / "profile.json"
    if pending_path.is_file() and profile_path.is_file():
        profile = _object(profile_path)
        if profile.get("return_code") == 0:
            candidate = _normalize_candidate(_object(pending_path), chapter_id, projections)
            batch = ChapterJudgmentBatch.model_validate(candidate)
            _validate_batch(
                batch,
                chapter_id=chapter_id,
                target_year=target_year,
                projections=projections,
            )
            _write_json(work / "judgment.json", batch.model_dump(mode="json"))
            return {"chapter_id": chapter_id, "status": "completed", **profile}
    guide, rubric = load_chapter_guide(chapter_id)
    job = {
        "job_key": f"chapter-judge:{run_key}:{target_year}:{chapter_id}",
        "run_key": run_key,
        "target_year": target_year,
        "input": {
            "chapter_id": chapter_id,
            "rubric_version": rubric,
            "unavailable_dossiers": [],
        },
    }
    prompt = build_chapter_judge_prompt(
        job,
        project_root=Path.cwd(),
        guide_text=guide,
        projections=projections,
        supplemental_instructions=supplemental_instructions,
    )
    if len(prompt) > CODEX_INPUT_CHARACTER_LIMIT:
        raise ValueError(
            "judge prompt exceeds Codex character limit: "
            f"{len(prompt)} > {CODEX_INPUT_CHARACTER_LIMIT}"
        )
    prompt_path = work / "prompt.txt"
    schema_path = work / "schema.json"
    events_path = work / "events.jsonl"
    prompt_path.write_text(prompt, encoding="utf-8")
    _write_json(schema_path, codex_chapter_judgment_json_schema())
    command = ["codex", "exec"]
    command.extend(item for feature in DISABLED for item in ("--disable", feature))
    command.extend(
        (
            "--model",
            model,
            "--ignore-rules",
            "-",
            "--json",
            "--color",
            "never",
            "--cd",
            str(Path.cwd()),
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(pending_path),
        )
    )
    started_at = datetime.now(UTC)
    started = time.monotonic()
    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    events_path.write_text(result.stdout, encoding="utf-8")
    usage = _usage(result.stdout)
    profile = {
        "chapter_id": chapter_id,
        "model": model,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "return_code": result.returncode,
        "usage": usage,
        "estimated_cost_usd": _cost(usage),
    }
    _write_json(work / "profile.json", profile)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"judge exited {result.returncode}")
    candidate = _normalize_candidate(_object(pending_path), chapter_id, projections)
    batch = ChapterJudgmentBatch.model_validate(candidate)
    _validate_batch(
        batch,
        chapter_id=chapter_id,
        target_year=target_year,
        projections=projections,
    )
    _write_json(work / "judgment.json", batch.model_dump(mode="json"))
    return {"chapter_id": chapter_id, "status": "completed", **profile}


def _normalize_candidate(
    candidate: dict[str, Any],
    chapter_id: str,
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
) -> dict[str, Any]:
    """Repair harmless lens-list overlap without changing judgment substance."""

    valid = {f"{chapter_id}.{number}" for number in range(1, 11)}
    evaluations = candidate.get("evaluations")
    if not isinstance(evaluations, list):
        return candidate
    known_by_key = {
        projection.job_key: {item.evidence_id for item in projection.evidence}
        for _, projection in projections
    }
    projection_by_key = {projection.job_key: projection for _, projection in projections}
    normalized_identity_keys: list[str] = []
    confidence_values = [
        float(item["confidence_score"])
        for item in evaluations
        if isinstance(item, dict) and isinstance(item.get("confidence_score"), (int, float))
    ]
    normalize_confidence = bool(
        confidence_values
        and all(0 <= value <= 1 for value in confidence_values)
        and any(0 < value < 1 for value in confidence_values)
    )
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        if normalize_confidence:
            evaluation["confidence_score"] = round(float(evaluation["confidence_score"]) * 100, 6)
        projection = _resolve_trusted_projection(evaluation, projection_by_key)
        if projection is not None and _restore_trusted_identity(evaluation, projection):
            normalized_identity_keys.append(projection.job_key)
        _normalize_scored_review_reason(evaluation)
        supported = _normalize_lens_values(evaluation.get("supported_lenses"), valid)
        missing = [
            value
            for value in _normalize_lens_values(
                evaluation.get("missing_or_weak_lenses"), valid
            )
            if value not in supported
        ]
        evaluation["supported_lenses"] = supported
        evaluation["missing_or_weak_lenses"] = missing
        known = known_by_key.get(str(evaluation.get("dossier_job_key")), set())
        dropped: list[str] = []
        for field in (
            "decisive_positive_evidence",
            "decisive_negative_evidence",
            "contrary_evidence",
        ):
            references = evaluation.get(field)
            if not isinstance(references, list):
                continue
            retained = []
            for reference in references:
                evidence_id = (
                    str(reference.get("evidence_id", "")) if isinstance(reference, dict) else ""
                )
                if evidence_id in known:
                    retained.append(reference)
                else:
                    dropped.append(evidence_id or "<missing>")
            evaluation[field] = retained
        if dropped:
            existing = str(evaluation.get("manual_review_reason") or "").strip()
            note = "Dropped out-of-projection evidence references: " + ", ".join(
                dict.fromkeys(dropped)
            )
            evaluation["manual_review_required"] = True
            evaluation["manual_review_reason_type"] = "projection_integrity"
            evaluation["manual_review_reason"] = f"{existing} {note}".strip()
    _append_identity_normalization_note(candidate, normalized_identity_keys)
    return candidate


def _restore_trusted_identity(
    evaluation: dict[str, Any], projection: RulerChapterProjection
) -> bool:
    """Restore immutable identity fields when the exact dossier key is already trusted."""

    immutable = {
        "dossier_job_key": projection.job_key,
        "iso3": projection.iso3,
        "ruler_id": projection.ruler_id,
        "ruler_year_id": projection.ruler_year_id,
        "ruler_name": projection.ruler_name,
        "period_start_year": projection.period_start_year,
        "period_end_year": projection.period_end_year,
        "chapter_id": projection.chapter_id,
    }
    changed = any(evaluation.get(field) != value for field, value in immutable.items())
    evaluation.update(immutable)
    return changed


def _resolve_trusted_projection(
    evaluation: dict[str, Any],
    projection_by_key: dict[str, RulerChapterProjection],
) -> RulerChapterProjection | None:
    """Resolve stale keys only through one exact immutable ruler-period identity."""

    keyed = projection_by_key.get(str(evaluation.get("dossier_job_key")))
    if keyed is not None:
        return keyed
    identity_fields = (
        "iso3",
        "ruler_id",
        "ruler_year_id",
        "ruler_name",
        "period_start_year",
        "period_end_year",
        "chapter_id",
    )
    matches = [
        projection
        for projection in projection_by_key.values()
        if all(evaluation.get(field) == getattr(projection, field) for field in identity_fields)
    ]
    return matches[0] if len(matches) == 1 else None


def _normalize_scored_review_reason(evaluation: dict[str, Any]) -> None:
    """Replace a null-only review label without dropping the requested review."""

    if (
        evaluation.get("score_1_to_10") is not None
        and evaluation.get("manual_review_reason_type") == "recoverable_null"
    ):
        evaluation["manual_review_reason_type"] = "projection_integrity"


def _append_identity_normalization_note(
    candidate: dict[str, Any], normalized_identity_keys: list[str]
) -> None:
    """Expose deterministic identity recovery in the persisted batch notes."""

    if not normalized_identity_keys:
        return
    notes = candidate.setdefault("batch_notes", [])
    if isinstance(notes, list):
        notes.append(
            "Deterministically restored immutable identity fields from trusted "
            "projections for: " + ", ".join(dict.fromkeys(normalized_identity_keys))
        )


def _normalize_lens_values(values: object, valid: set[str]) -> list[str]:
    """Recover a leading methodology ID from otherwise useful free-form lens text."""

    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        match = re.match(r"^(\d+B\.\d{1,2})(?:\b|\s|[:\-—])", text, re.IGNORECASE)
        candidate = match.group(1).upper() if match else text.upper()
        if candidate in valid and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _validate_batch(
    batch: ChapterJudgmentBatch,
    *,
    chapter_id: str,
    target_year: int,
    projections: tuple[tuple[Path, RulerChapterProjection], ...],
) -> None:
    if batch.chapter_id != chapter_id or batch.target_year != target_year:
        raise ValueError("judge returned the wrong chapter or year")
    by_key = {item.job_key: item for _, item in projections}
    evaluations = {item.dossier_job_key: item for item in batch.evaluations}
    if set(evaluations) != set(by_key):
        raise ValueError("judge did not return exactly one evaluation per ruler")
    for job_key, evaluation in evaluations.items():
        projection = by_key[job_key]
        if (
            evaluation.iso3 != projection.iso3
            or evaluation.ruler_year_id != projection.ruler_year_id
        ):
            raise ValueError(f"judge identity mismatch for {job_key}")
        if evaluation.chapter_id != chapter_id or len(evaluation.chapter_rationale) < 250:
            raise ValueError(f"judge rationale is incomplete for {job_key}")
        known = {item.evidence_id for item in projection.evidence}
        references = (
            *evaluation.decisive_positive_evidence,
            *evaluation.decisive_negative_evidence,
            *evaluation.contrary_evidence,
        )
        if any(item.evidence_id not in known for item in references):
            raise ValueError(f"judge cited unknown evidence for {job_key}")


def _write_summary(
    output_dir: Path,
    *,
    model: str,
    workers: int,
    chapter_ids: tuple[str, ...],
    new_results: list[dict[str, Any]],
) -> dict[str, Any]:
    chapters = []
    for chapter_id in chapter_ids:
        profile_path = output_dir / chapter_id / "profile.json"
        completed = (output_dir / chapter_id / "judgment.json").is_file()
        profile = _object(profile_path) if profile_path.is_file() else {}
        chapters.append(
            {
                "chapter_id": chapter_id,
                "status": "completed" if completed else "pending_or_failed",
                **profile,
            }
        )
    usage_keys = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    summary = {
        "model": model,
        "workers": workers,
        "completed": sum(item["status"] == "completed" for item in chapters),
        "total": len(chapter_ids),
        "usage": {
            key: sum(int(item.get("usage", {}).get(key, 0)) for item in chapters)
            for key in usage_keys
        },
        "estimated_cost_usd": round(
            sum(float(item.get("estimated_cost_usd", 0)) for item in chapters), 6
        ),
        "chapters": chapters,
        "latest_results": new_results,
    }
    _write_json(output_dir / "run-summary.json", summary)
    return summary


def _usage(events: str) -> dict[str, int]:
    usage: dict[str, int] = {}
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            value = event.get("usage")
            if isinstance(value, dict):
                usage = {key: int(number) for key, number in value.items()}
    return usage


def _cost(usage: dict[str, int]) -> float:
    input_tokens = usage.get("input_tokens", 0)
    cached = usage.get("cached_input_tokens", 0)
    output = usage.get("output_tokens", 0)
    return round((input_tokens - cached) * 0.75e-6 + cached * 0.075e-6 + output * 4.5e-6, 6)


def _tokens(value: object) -> int:
    return max(
        1, (len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) + 2) // 3
    )


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(pending, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("conversion_dir", type=Path)
    prepare.add_argument("output_dir", type=Path)
    prepare.add_argument("--evidence-per-lens", type=int, default=4)
    run = subparsers.add_parser("run")
    run.add_argument("compact_dir", type=Path)
    run.add_argument("output_dir", type=Path)
    run.add_argument("--model", default="gpt-5.4-mini")
    run.add_argument("--workers", type=int, default=3)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--chapters", nargs="+", choices=CHAPTERS, default=list(CHAPTERS))
    run.add_argument("--run-key")
    run.add_argument("--instructions", type=Path)
    repair = subparsers.add_parser("repair")
    repair.add_argument("compact_dir", type=Path)
    repair.add_argument("output_dir", type=Path)
    apply_review = subparsers.add_parser("apply-review")
    apply_review.add_argument("output_dir", type=Path)
    apply_review.add_argument("review", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_compact_inputs(
            args.conversion_dir,
            args.output_dir,
            evidence_per_lens=args.evidence_per_lens,
        )
    elif args.command == "run":
        result = run_judges(
            args.compact_dir,
            args.output_dir,
            model=args.model,
            workers=args.workers,
            timeout_seconds=args.timeout,
            chapter_ids=tuple(args.chapters),
            run_key=args.run_key,
            instruction_path=args.instructions,
        )
    elif args.command == "repair":
        result = repair_saved_judgments(args.compact_dir, args.output_dir)
    else:
        result = apply_projection_review(args.output_dir, args.review)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
