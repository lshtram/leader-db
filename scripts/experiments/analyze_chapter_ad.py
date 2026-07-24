"""Summarize the ten-case chapter prompt A/D experiment."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

URL_PATTERN = re.compile(r'https?://[^\s)\]"<>]+')


def main() -> None:
    """Write per-cell metrics and a compact aggregate summary."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    manifest = json.loads(
        (experiment_dir / "manifest.json").read_text(encoding="utf-8")
    )
    evaluations = {
        "forward": _evaluation_scores(
            experiment_dir / "evaluator-forward.output.md",
            manifest,
            {"X": "a", "Y": "d"},
        ),
        "reverse": _evaluation_scores(
            experiment_dir / "evaluator-reverse.output.md",
            manifest,
            {"X": "d", "Y": "a"},
        ),
    }
    rows = [
        _cell_metrics(
            experiment_dir=experiment_dir,
            case_id=case_id,
            case=case,
            variant=variant,
            evaluations=evaluations,
        )
        for case_id, case in manifest["cases"].items()
        for variant in ("a", "d")
    ]
    _write_csv(experiment_dir / "metrics.csv", rows)
    summary = _summary(rows)
    (experiment_dir / "metrics-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evaluation_scores(
    path: Path,
    manifest: dict[str, Any],
    label_to_variant: dict[str, str],
) -> dict[tuple[str, str], float]:
    text = path.read_text(encoding="utf-8")
    scores: dict[tuple[str, str], float] = {}
    for case_id, case in manifest["cases"].items():
        heading = re.search(
            rf"^## \d+\. {re.escape(case['ruler_name'])} .*$",
            text,
            re.MULTILINE,
        )
        if heading is None:
            raise ValueError(f"missing evaluator section for {case_id} in {path}")
        next_heading = re.search(r"^## \d+\. ", text[heading.end() :], re.MULTILINE)
        section_end = (
            heading.end() + next_heading.start()
            if next_heading is not None
            else len(text)
        )
        section = text[heading.end() : section_end]
        for label, variant in label_to_variant.items():
            row = re.search(
                rf"^\| {label} \|.*?\| \*\*([0-9.]+)\*\* \|$",
                section,
                re.MULTILINE,
            )
            if row is None:
                raise ValueError(
                    f"missing evaluator score {label} for {case_id} in {path}"
                )
            scores[(case_id, variant)] = float(row.group(1))
    return scores


def _cell_metrics(
    *,
    experiment_dir: Path,
    case_id: str,
    case: dict[str, Any],
    variant: str,
    evaluations: dict[str, dict[tuple[str, str], float]],
) -> dict[str, Any]:
    cell_dir = experiment_dir / case_id / variant
    events = [
        json.loads(line)
        for line in (cell_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    completed = [
        event for event in events if event.get("type") == "turn.completed"
    ]
    if len(completed) != 1:
        raise ValueError(
            f"{case_id}/{variant} has {len(completed)} completed-turn events"
        )
    usage = completed[0]["usage"]
    output = (cell_dir / "output.md").read_text(encoding="utf-8")
    records = [
        line.split(":", 1)[1].strip()
        for line in output.splitlines()
        if line.startswith("SOURCE_CLAIM_JSON:")
    ]
    valid_records = 0
    for record in records:
        try:
            json.loads(record)
        except json.JSONDecodeError:
            continue
        valid_records += 1
    chapter_id = str(case["chapter_id"])
    question_ids_present = sum(
        bool(re.search(rf"\b{re.escape(chapter_id)}\.{number}\b", output))
        for number in range(1, 11)
    )
    forward_score = evaluations["forward"][(case_id, variant)]
    reverse_score = evaluations["reverse"][(case_id, variant)]
    return {
        "case_id": case_id,
        "ruler_name": case["ruler_name"],
        "chapter_id": chapter_id,
        "variant": variant.upper(),
        "prompt_characters": case[f"prompt_{variant}_characters"],
        "prior_resources": case["resource_count"],
        "input_tokens": usage["input_tokens"],
        "cached_input_tokens": usage["cached_input_tokens"],
        "noncached_input_tokens": (
            usage["input_tokens"] - usage["cached_input_tokens"]
        ),
        "output_tokens": usage["output_tokens"],
        "web_search_events": sum(
            event.get("item", {}).get("type") == "web_search" for event in events
        ),
        "output_characters": len(output),
        "source_claim_records": len(records),
        "valid_source_claim_records": valid_records,
        "distinct_urls": len(set(URL_PATTERN.findall(output))),
        "question_ids_present": question_ids_present,
        "forward_evaluator_score": forward_score,
        "reverse_evaluator_score": reverse_score,
        "mean_evaluator_score": round((forward_score + reverse_score) / 2, 2),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"schema_version": "chapter_prompt_ad_metrics_v1"}
    variants: dict[str, dict[str, Any]] = {}
    for variant in ("A", "D"):
        selected = [row for row in rows if row["variant"] == variant]
        variants[variant] = {
            "cells": len(selected),
            "input_tokens": sum(row["input_tokens"] for row in selected),
            "cached_input_tokens": sum(
                row["cached_input_tokens"] for row in selected
            ),
            "noncached_input_tokens": sum(
                row["noncached_input_tokens"] for row in selected
            ),
            "output_tokens": sum(row["output_tokens"] for row in selected),
            "web_search_events": sum(
                row["web_search_events"] for row in selected
            ),
            "output_characters": sum(
                row["output_characters"] for row in selected
            ),
            "source_claim_records": sum(
                row["source_claim_records"] for row in selected
            ),
            "valid_source_claim_records": sum(
                row["valid_source_claim_records"] for row in selected
            ),
            "mean_forward_evaluator_score": round(
                sum(row["forward_evaluator_score"] for row in selected)
                / len(selected),
                3,
            ),
            "mean_reverse_evaluator_score": round(
                sum(row["reverse_evaluator_score"] for row in selected)
                / len(selected),
                3,
            ),
            "mean_combined_evaluator_score": round(
                sum(row["mean_evaluator_score"] for row in selected) / len(selected),
                3,
            ),
        }
    summary["variants"] = variants
    summary["mean_score_difference_d_minus_a"] = round(
        variants["D"]["mean_combined_evaluator_score"]
        - variants["A"]["mean_combined_evaluator_score"],
        3,
    )
    return summary


if __name__ == "__main__":
    main()
