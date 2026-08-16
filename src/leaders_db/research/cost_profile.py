"""Canonical, deterministic model-call profiling for ruler research runs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .cost_profile_events import (
    TOKEN_KEYS,
    cache_distribution,
    event_rows,
    group_totals,
    output_distribution,
    totals,
)
from .cost_profile_models import StageRules

_TOKEN_KEYS = TOKEN_KEYS


def build_cost_profile(run_root: Path, output_dir: Path, rules_path: Path) -> Path:
    """Profile trusted completed calls and write JSON, CSV, and Markdown artifacts."""

    root = run_root.resolve(strict=True)
    rules = _load_rules(rules_path)
    rows = event_rows(root, rules)
    metrics = _scientific_metrics(root)
    snapshot = _selected_scientific_snapshot(root)
    manifest = {
        "schema_version": "research_cost_profile_v1",
        "implementation_version": "step01_v1",
        "source_root": str(root),
        "stage_rules": {
            "schema_version": rules.schema_version,
            "sha256": sha256(rules_path.read_bytes()).hexdigest(),
        },
        "source_artifacts": _source_artifacts(root),
        "totals": totals(rows),
        "by_stage": group_totals(rows, "stage"),
        "by_chapter": group_totals(rows, "chapter_id"),
        "by_selection_status": group_totals(rows, "selection_status"),
        "cache_distribution": cache_distribution(rows),
        "output_distribution": output_distribution(rows),
        "largest_calls": sorted(
            rows, key=lambda row: (-row["input_tokens"], row["event_path"])
        )[:20],
        "scientific_metrics": metrics,
        "selected_scientific_snapshot": snapshot,
        "gate_results": _gate_results(snapshot, rows),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "profile-manifest.json"
    json_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_ledger(output_dir / "call-ledger.csv", rows)
    (output_dir / "profile-report.md").write_text(
        _profile_markdown(manifest), encoding="utf-8"
    )
    return json_path


def compare_cost_profiles(
    baseline_path: Path, candidate_path: Path, output_path: Path
) -> Path:
    """Compare profiles built with the same schema and stage definitions."""

    baseline = _read_profile(baseline_path)
    candidate = _read_profile(candidate_path)
    if baseline["stage_rules"] != candidate["stage_rules"]:
        raise ValueError("profiles use different stage-classification rules")
    keys = ("calls", *_TOKEN_KEYS)
    comparison = {
        "schema_version": "research_cost_comparison_v1",
        "baseline_profile": str(baseline_path.resolve()),
        "candidate_profile": str(candidate_path.resolve()),
        "delta": {
            key: candidate["totals"][key] - baseline["totals"][key] for key in keys
        },
        "baseline": baseline["totals"],
        "candidate": candidate["totals"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_comparison_markdown(comparison), encoding="utf-8")
    output_path.with_suffix(".json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_path


def _load_rules(path: Path) -> StageRules:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return StageRules.model_validate(payload)


def _source_artifacts(root: Path) -> list[dict[str, Any]]:
    names = (
        "approved-ruler-package.json",
        "corpus-judge-package.json",
        "selected-chapter-manifest.json",
        "reading/reading-run-manifest.json",
    )
    artifacts = [
        {"path": name, "sha256": sha256((root / name).read_bytes()).hexdigest()}
        for name in names
        if (root / name).is_file()
    ]
    selection = _optional_json(root / "selected-chapter-manifest.json") or {}
    for chapter in selection.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        for key, value in chapter.items():
            path = root / value if key.endswith("_path") and isinstance(value, str) else None
            if path is not None and path.is_file():
                artifacts.append(
                    {
                        "path": value,
                        "sha256": sha256(path.read_bytes()).hexdigest(),
                    }
                )
    return sorted(artifacts, key=lambda item: item["path"])


def _gate_results(
    snapshot: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    complete_selection = (
        snapshot["chapter_count"] == 8
        and snapshot["answer_count"] == 80
        and all(
            chapter.get("safe_for_judge_use") is True
            for chapter in snapshot["chapters"]
        )
    )
    return {
        "functional_gate": "pass" if rows and complete_selection else "inconclusive",
        "quality_gate": "pass" if complete_selection else "inconclusive",
        "quality_proof": (
            "Read-only profiling bound all eight selected safe-for-judge chapters, "
            "exactly eighty answers, selected reviews, and source artifact hashes."
            if complete_selection
            else "The input does not contain a complete approved eight-chapter selection."
        ),
        "cost_gate": "not_applicable_profiling_step",
    }


def _selected_scientific_snapshot(root: Path) -> dict[str, Any]:
    selection = _optional_json(root / "selected-chapter-manifest.json") or {}
    chapters = []
    for item in selection.get("chapters", []):
        if not isinstance(item, dict) or not isinstance(item.get("analysis_path"), str):
            continue
        analysis_path = root / item["analysis_path"]
        analysis = _optional_json(analysis_path) or {}
        answers = analysis.get("answers", [])
        answer_rows = []
        for answer in answers if isinstance(answers, list) else []:
            if not isinstance(answer, dict):
                continue
            supporting = answer.get("supporting_evidence_ids", [])
            contrary = answer.get("contrary_or_qualifying_evidence_ids", [])
            answer_rows.append(
                {
                    "question_id": answer.get("question_id"),
                    "answer_characters": len(str(answer.get("answer", ""))),
                    "supporting_citation_count": (
                        len(supporting) if isinstance(supporting, list) else 0
                    ),
                    "contrary_citation_count": (
                        len(contrary) if isinstance(contrary, list) else 0
                    ),
                }
            )
        review_path_value = item.get("review_path")
        review = (
            _optional_json(root / review_path_value)
            if isinstance(review_path_value, str)
            else None
        )
        chapters.append(
            {
                "chapter_id": item.get("chapter_id"),
                "analysis_path": item["analysis_path"],
                "analysis_sha256": sha256(analysis_path.read_bytes()).hexdigest(),
                "answers": answer_rows,
                "review_path": review_path_value,
                "review_sha256": item.get("review_sha256"),
                "review_finding_count": _review_finding_count(review),
                "safe_for_judge_use": (review or {}).get("safe_for_judge_use"),
            }
        )
    return {
        "chapter_count": len(chapters),
        "answer_count": sum(len(item["answers"]) for item in chapters),
        "chapters": chapters,
    }


def _review_finding_count(review: dict[str, Any] | None) -> int:
    if review is None:
        return 0
    count = 0
    for key in ("systemic_problems", "concrete_corrections_required"):
        value = review.get(key)
        count += len(value) if isinstance(value, list) else 0
    for lens in review.get("lens_quality", []):
        if not isinstance(lens, dict):
            continue
        for key in ("material_errors", "material_omissions"):
            value = lens.get(key)
            count += len(value) if isinstance(value, list) else 0
    return count


def _scientific_metrics(root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    acquisition = _optional_json(root / "acquisition" / "acquisition-manifest.json")
    if acquisition:
        dispositions = acquisition.get(
            "records", acquisition.get("dispositions", acquisition.get("sources", []))
        )
        if isinstance(dispositions, list):
            counts["source_count"] = len(dispositions)
            counts["extracted_characters"] = sum(
                int(item.get("extracted_characters", 0) or 0)
                for item in dispositions
                if isinstance(item, dict)
            )
            counts["estimated_source_tokens"] = sum(
                int(item.get("estimated_tokens", 0) or 0)
                for item in dispositions
                if isinstance(item, dict)
            )
    for path in sorted((root / "reading").glob("*/verified-evidence.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else raw.get("evidence", raw.get("records", []))
        if isinstance(records, list):
            counts["evidence_count"] += len(records)
            counts["evidence_question_links"] += sum(
                len(item.get("methodology_ids", item.get("question_ids", [])))
                for item in records
                if isinstance(item, dict)
            )
    judge = _optional_json(root / "corpus-judge-package.json")
    if judge:
        evidence = judge.get("evidence", [])
        questions = judge.get("questions", [])
        counts["judge_evidence_count"] = len(evidence) if isinstance(evidence, list) else 0
        if isinstance(questions, list):
            counts["question_count"] = len(questions)
            counts["mapping_count"] = sum(
                len(item.get("evidence_ids", []))
                for item in questions
                if isinstance(item, dict)
            )
    return dict(sorted(counts.items()))


def _optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else [
        "event_path", "call_index", "artifact_type", "stage", "chapter_id",
        "selection_status", "call_status", *_TOKEN_KEYS,
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _profile_markdown(profile: dict[str, Any]) -> str:
    totals = profile["totals"]
    lines = [
        "# Research cost profile",
        "",
        "| Stage | Calls | Input | Cached | Output |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage, row in profile["by_stage"].items():
        lines.append(
            f"| {stage} | {row['calls']} | {row['input_tokens']} | "
            f"{row['cached_input_tokens']} | {row['output_tokens']} |"
        )
    lines.extend(
        [
            "",
            f"Total completed calls: {totals['calls']}. "
            f"Cache rate: {totals['cache_rate']:.1%}.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "research_cost_profile_v1":
        raise ValueError(f"unsupported cost profile: {path}")
    return payload


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Research cost comparison",
        "",
        "| Measure | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key, delta in comparison["delta"].items():
        lines.append(
            f"| {key} | {comparison['baseline'][key]} | "
            f"{comparison['candidate'][key]} | {delta:+} |"
        )
    return "\n".join((*lines, ""))


__all__ = ["build_cost_profile", "compare_cost_profiles"]
