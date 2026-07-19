"""Build judge projections with audited inadmissible evidence removed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from leaders_db.research.chapter_projection import RulerChapterProjection


def filter_scope(
    compact_dir: Path, output_dir: Path, exclusions_path: Path
) -> dict[str, Any]:
    """Remove explicitly audited IDs and persist a complete exclusion ledger."""

    exclusions = _object(exclusions_path).get("exclusions")
    if not isinstance(exclusions, dict) or not exclusions:
        raise ValueError("scope exclusions must contain a non-empty exclusions object")
    reports = []
    for chapter_id, by_iso3 in exclusions.items():
        if not isinstance(by_iso3, dict):
            raise ValueError(f"scope exclusions for {chapter_id} must be an object")
        manifest = _object(compact_dir / "chapters" / f"{chapter_id}.json")
        paths = []
        removed = []
        for source_value in manifest["projection_paths"]:
            source_path = Path(source_value)
            projection = RulerChapterProjection.model_validate(_object(source_path))
            blocked = set(by_iso3.get(projection.iso3, []))
            known = {item.evidence_id for item in projection.evidence}
            unknown = sorted(blocked - known)
            blocked &= known
            payload = projection.model_dump(mode="json")
            payload["evidence"] = [
                item for item in payload["evidence"] if item["evidence_id"] not in blocked
            ]
            payload["mappings"] = [
                item for item in payload["mappings"] if item["evidence_id"] not in blocked
            ]
            for item in payload["coverage"]:
                item["evidence_ids"] = [
                    value for value in item["evidence_ids"] if value not in blocked
                ]
            filtered = RulerChapterProjection.model_validate(payload)
            target = output_dir / "projections" / chapter_id / source_path.name
            _write_json(target, filtered.model_dump(mode="json"))
            paths.append(str(target))
            removed.append(
                {
                    "iso3": projection.iso3,
                    "removed_evidence_ids": sorted(blocked),
                    "requested_but_absent_ids": unknown,
                }
            )
        target_manifest = {**manifest, "projection_paths": paths, "scope_exclusions": removed}
        _write_json(output_dir / "chapters" / f"{chapter_id}.json", target_manifest)
        reports.append({"chapter_id": chapter_id, "projections": len(paths), "ledger": removed})
    report = {
        "schema_version": "conversational_scope_filter_v1",
        "source_compact_dir": str(compact_dir),
        "source_exclusions": str(exclusions_path),
        "chapters": reports,
    }
    _write_json(output_dir / "scope-filter-report.json", report)
    return report


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
    parser.add_argument("compact_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("exclusions", type=Path)
    args = parser.parse_args()
    print(json.dumps(filter_scope(args.compact_dir, args.output_dir, args.exclusions), indent=2))


if __name__ == "__main__":
    main()
