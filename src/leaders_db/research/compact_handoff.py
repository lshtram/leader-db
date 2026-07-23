"""Deterministic compact handoff from research producers to LLM consumers."""

from __future__ import annotations

import json
from pathlib import Path

_ACCOUNTING_MARKERS = (
    "Research accounting:",
    "Research accounting",
    "Evidence accounting:",
    "Source accounting:",
)


def build_compact_research_handoff(
    *,
    attempt_dir: Path,
    fallback_notebook: str,
) -> str:
    """Return the ledger plus chapter conclusions without replaying raw notebooks."""

    manifest_path = attempt_dir / "research-ledger-manifest.json"
    if not manifest_path.is_file():
        return fallback_notebook
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback_notebook
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "ruler_research_ledger_manifest_v1"
        or not isinstance(manifest.get("entries"), list)
        or not manifest["entries"]
    ):
        return fallback_notebook

    sections = [
        "Compact research handoff. The parent preserves the complete raw notebook "
        "separately; this consumer receives the authoritative evidence ledger and "
        "chapter accounting conclusions.\n",
        "--- RESEARCH LEDGER MANIFEST ---\n"
        + json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
    ]
    for path in sorted(attempt_dir.glob("research-chapter-*.md")):
        text = path.read_text(encoding="utf-8")
        starts = [text.rfind(marker) for marker in _ACCOUNTING_MARKERS]
        starts = [offset for offset in starts if offset >= 0]
        conclusion = text[max(starts) :] if starts else text[-5_000:]
        sections.append(f"CHAPTER_CONCLUSION {path.stem}:\n{conclusion.strip()}")
    return "\n\n".join(sections)


__all__ = ["build_compact_research_handoff"]
