#!/usr/bin/env python3
"""Build a static annual viewer from conversational dossiers and judgments."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_PATH = PROJECT_ROOT / "scripts" / "build_client_results_viewer.py"


def _shared() -> Any:
    spec = importlib.util.spec_from_file_location("client_viewer_builder", SHARED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared viewer builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_payload(batch_dir: Path) -> dict[str, Any]:
    """Join compact chapter projections to validated comparative judgments."""

    shared = _shared()
    conversion = _object(batch_dir / "judge-inputs-v1" / "conversion-report.json")
    target_year = int(conversion["year"])
    questions = shared._question_texts()
    projection_root = batch_dir / "judge-compact-v2" / "projections"
    judgment_paths = _judgment_paths(batch_dir, tuple(shared.CHAPTER_TITLES))
    judgments = {
        chapter: {
            item["iso3"]: item
            for item in _object(judgment_paths[chapter])["evaluations"]
        }
        for chapter in shared.CHAPTER_TITLES
    }
    rulers = []
    for ruler in conversion["rulers"]:
        iso3 = ruler["iso3"]
        dossier = _object(Path(ruler["dossier_path"]))
        chapters = []
        scores: dict[str, float | None] = {}
        for chapter_id in shared.CHAPTER_TITLES:
            projection_path = next((projection_root / chapter_id).glob(f"{iso3}-*.json"))
            projection = _object(projection_path)
            judgment = judgments[chapter_id][iso3]
            scores[chapter_id] = judgment["score_1_to_10"]
            chapters.append(shared._chapter_record(projection, chapter_id, judgment, questions))
        numeric = [value for value in scores.values() if value is not None]
        rulers.append(
            {
                "iso3": iso3,
                "country_name": dossier["country_name"],
                "ruler_name": dossier["ruler_name"],
                "ruler_year_id": dossier["ruler_year_id"],
                "source_run": f"{target_year} conversational evidence",
                "dossier_path": ruler["dossier_path"],
                "automated_scores": scores,
                "client_scores": {chapter: None for chapter in shared.CHAPTER_TITLES},
                "average_score": round(sum(numeric) / len(numeric), 3),
                "scored_chapters": len(numeric),
                "chapters": chapters,
            }
        )
    overall = [ruler["average_score"] for ruler in rulers]
    return {
        "schema_version": "leaders_db_annual_viewer_data_v1",
        "release_id": str(conversion["batch_id"]),
        "target_year": target_year,
        "chapter_titles": shared.CHAPTER_TITLES,
        "overall_average": round(sum(overall) / len(overall), 3),
        "overall_scored_cells": sum(ruler["scored_chapters"] for ruler in rulers),
        "rulers": rulers,
        "attributions_path": "docs/sources/attributions.md",
        "method_note": (
            "Each chapter score is a holistic comparative judgment on a 1–10 scale; "
            "the ruler average is descriptive and does not replace the chapter record."
        ),
        "methodology_update": (
            f"GPT-5.4 mini collected {target_year} evidence ruler by ruler. Separate no-search "
            "chapter judges compared all twenty rulers and documented every score, "
            "confidence assessment, plausible range, attribution limit, and anchor."
        ),
    }


def _judgment_paths(batch_dir: Path, chapters: tuple[str, ...]) -> dict[str, Path]:
    """Resolve release-selected chapter judgments while retaining the v2 default."""

    paths = {
        chapter: batch_dir / "judgments-v2" / chapter / "judgment.json"
        for chapter in chapters
    }
    manifest_path = batch_dir / "viewer-judgments.json"
    if not manifest_path.is_file():
        return paths
    manifest = _object(manifest_path)
    overrides = manifest.get("chapter_judgments", {})
    if not isinstance(overrides, dict):
        raise ValueError("viewer judgment manifest must contain chapter_judgments")
    for chapter, relative_path in overrides.items():
        if chapter not in paths or not isinstance(relative_path, str):
            raise ValueError(f"invalid viewer judgment override for {chapter}")
        candidate = (batch_dir / relative_path).resolve()
        if not candidate.is_relative_to(batch_dir.resolve()):
            raise ValueError(f"viewer judgment override escapes batch directory: {chapter}")
        paths[chapter] = candidate
    return paths


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = build_payload(args.batch_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output} ({len(payload['rulers'])} rulers)")


if __name__ == "__main__":
    main()
