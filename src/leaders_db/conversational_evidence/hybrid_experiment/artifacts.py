"""Deterministic artifact helpers for the hybrid experiment."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from leaders_db.conversational_evidence.deep_artifacts import canonical_url, urls

CHAPTERS = tuple(f"{number}B" for number in range(1, 9))
_LENS = re.compile(r"\b([1-8]B\.(?:10|[1-9]))\b", re.IGNORECASE)


def write_json(path: Path, value: object) -> None:
    """Atomically write one JSON artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(pending, path)


def baseline_manifest(project_root: Path) -> dict[str, object]:
    """Fingerprint the production flow without changing it."""

    relative_paths = (
        "src/leaders_db/conversational_evidence/collector.py",
        "src/leaders_db/conversational_evidence/data/prompts.json",
        "src/leaders_db/conversational_evidence/data/questions.json",
        "src/leaders_db/conversational_evidence/data/result.schema.json",
        "src/leaders_db/conversational_evidence/luna.py",
        "src/leaders_db/conversational_evidence/researcher.py",
    )
    return {
        "schema_version": "hybrid-experiment-baseline-v1",
        "git_head": _git(project_root, "rev-parse", "HEAD"),
        "git_status": _git(project_root, "status", "--short"),
        "production_files": {
            name: hashlib.sha256((project_root / name).read_bytes()).hexdigest()
            for name in relative_paths
        },
    }


def evidence_index(notes: list[tuple[str, str]]) -> list[dict[str, object]]:
    """Assign stable IDs to distinct URLs in first-seen order."""

    records: dict[str, dict[str, object]] = {}
    for chapter_id, note in notes:
        note_lenses = sorted({item.upper() for item in _LENS.findall(note)})
        for value in sorted(urls(note)):
            record = records.get(value)
            if record is None:
                record = {
                    "evidence_id": f"E{len(records) + 1:04d}",
                    "url": value,
                    "domain": urlparse(value).netloc.lower(),
                    "chapters": [],
                    "mentioned_lenses": [],
                }
                records[value] = record
            if chapter_id not in record["chapters"]:
                record["chapters"].append(chapter_id)
            record["mentioned_lenses"] = sorted(
                set(record["mentioned_lenses"]) | set(note_lenses)
            )
    return list(records.values())


def quality_summary(records: list[dict[str, object]]) -> dict[str, object]:
    """Report mechanical warnings without rejecting research judgments."""

    chapters: dict[str, object] = {}
    for chapter_id in CHAPTERS:
        selected = [item for item in records if chapter_id in item["chapters"]]
        domains = Counter(str(item["domain"]) for item in selected)
        lenses = sorted(
            {
                lens
                for item in selected
                for lens in item["mentioned_lenses"]
                if lens.startswith(chapter_id)
            }
        )
        warnings = []
        if len(selected) < 10:
            warnings.append("fewer_than_10_distinct_urls")
        if len(domains) < 5:
            warnings.append("fewer_than_5_domains")
        if selected and domains.most_common(1)[0][1] / len(selected) > 0.35:
            warnings.append("top_domain_above_35_percent")
        if len(lenses) < 10:
            warnings.append("not_all_lenses_mentioned_near_urls")
        chapters[chapter_id] = {
            "distinct_urls": len(selected),
            "domains": len(domains),
            "top_domains": domains.most_common(5),
            "mentioned_lenses": lenses,
            "warnings": warnings,
        }
    return {"distinct_urls": len(records), "chapters": chapters}


def compact_index(records: list[dict[str, object]], limit: int = 180) -> str:
    """Return a compact reusable source index for the next model turn."""

    rows = [
        f"{item['evidence_id']} | {item['domain']} | {item['url']} | "
        f"{','.join(item['chapters'])}"
        for item in records[-limit:]
    ]
    return "\n".join(rows) or "No web evidence retained yet."


def normalize_url(value: str) -> str:
    """Public wrapper used by focused tests."""

    return canonical_url(value)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


__all__ = [
    "CHAPTERS", "baseline_manifest", "compact_index", "evidence_index",
    "normalize_url", "quality_summary", "write_json",
]
