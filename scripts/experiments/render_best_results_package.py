"""Render one human-review package from a completed chapter-research run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Render questions, search log, selected evidence, and classifications."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--version", default="v2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    run_dir = experiment_dir / args.version / "run-01"
    manifest = json.loads(
        (experiment_dir / "manifest.json").read_text(encoding="utf-8")
    )
    records = json.loads(
        (run_dir / "parsed-records.json").read_text(encoding="utf-8")
    )
    questions = _chapter_questions("5B")
    searches = _searches(run_dir / "events.jsonl")
    output = (run_dir / "output.md").read_text(encoding="utf-8")
    narrative = output.split("\nSOURCE_CLAIM_JSON:", maxsplit=1)[0].strip()
    usage = _usage(run_dir / "events.jsonl")

    lines = [
        "# Best Available AMLO 2022 Chapter 5B Evidence-Research Package",
        "",
        "Status: review package; selected evidence is provisional and unscored",
        "",
        "## Why this package was selected",
        "",
        "This package presents the fresh `gpt-5.4-mini` v2 run. Among the valid "
        "production-model runs, it produced the broadest source mix: 15 selected "
        "records, 15 unique URLs, and 14 publisher labels. Selection here means best "
        "available research artifact, not an approved final dossier.",
        "",
        "Known defects are preserved rather than repaired silently:",
        "",
        "- `methodology_ids` incorrectly contains prompt-version identifiers;",
        "- the exact question mappings are recoverable from each record's `lenses` field;",
        "- several locators are broad labels rather than precise pages, tables, sections, "
        "paragraphs, or record identifiers;",
        "- selected claims still require source-by-source reopening before score-bearing "
        "use; and",
        "- search-result snippets are not evidence; only opened underlying sources may "
        "support accepted claims.",
        "",
        "## Ruler and research scope",
        "",
        f"- Ruler: **{manifest['case']['ruler']}**",
        f"- Country: **{manifest['case']['country']}**",
        f"- Period: **{manifest['case']['period'][0]}**",
        f"- Chapter: **{manifest['case']['chapter_id']} — Economic Well-Being and "
        "Prosperity**",
        f"- Research model: **{manifest['execution']['model']}**",
        f"- Reasoning profile: **{manifest['execution']['reasoning']}**",
        "- Client and judge scores: **excluded**",
        "- Evidence quota: **none**",
        "",
        "## Research questions",
        "",
    ]
    for question in questions:
        lines.extend((f"### {question['id']}", "", question["text"], ""))

    lines.extend(
        (
            "## Search operations",
            "",
            f"The run recorded **{len(searches)}** web-search operations. The table "
            "preserves the requested query and any bundled candidate queries. It is a "
            "discovery log, not proof that every returned page was opened or accepted.",
            "",
            "| # | Requested search | Bundled candidate queries |",
            "|---:|---|---|",
        )
    )
    for number, search in enumerate(searches, start=1):
        lines.append(
            f"| {number} | {_cell(search['query'])} | "
            f"{_cell('<br>'.join(search['queries']))} |"
        )

    lines.extend(
        (
            "",
            "## Selected evidence summary",
            "",
            "| ID | Classification | Question lenses | Period | Source | Claim | Locator |",
            "|---|---|---|---|---|---|---|",
        )
    )
    for record in records:
        source = f"[{record['publisher']}: {record['title']}]({record['url']})"
        lines.append(
            f"| {_cell(record['provisional_id'])} | "
            f"{_cell(record['final_evidence_use'])} | "
            f"{_cell(', '.join(record['lenses']))} | "
            f"{_cell(record['period_fit'])} | {source} | "
            f"{_cell(record['claim'])} | {_cell(record['locator'])} |"
        )

    lines.extend(("", "## Detailed selected evidence records", ""))
    for record in records:
        lines.extend(_render_record(record))

    lines.extend(
        (
            "## Researcher's narrative handoff and source-state notes",
            "",
            "The following is the researcher's narrative before its machine records. It "
            "is preserved verbatim so reviewers can inspect its coverage matrix, source "
            "states, gaps, and qualifications.",
            "",
            narrative,
            "",
            "## Run usage",
            "",
            f"- Input tokens: {usage.get('input_tokens', 'not reported'):,}",
            f"- Cached input tokens: {usage.get('cached_input_tokens', 'not reported'):,}",
            f"- Output tokens: {usage.get('output_tokens', 'not reported'):,}",
            f"- Reasoning tokens: {usage.get('reasoning_output_tokens', 'not reported'):,}",
            "",
            "## Review checklist",
            "",
            "For each selected record, verify:",
            "",
            "- the URL opens the underlying source rather than a search result or summary;",
            "- the source directly supports the precise claim;",
            "- the locator is reproducible and sufficiently exact;",
            "- target-period and retrospective classifications are correct;",
            "- attribution does not convert country context into personal conduct;",
            "- contrary evidence and material limitations are complete;",
            "- records about one underlying event or dataset are dependency-clustered; and",
            "- the `lenses` mappings accurately identify the supported 5B questions.",
            "",
        )
    )
    args.output.write_text("\n".join(lines), encoding="utf-8")


def _chapter_questions(chapter_id: str) -> list[dict[str, str]]:
    payload = json.loads(
        (
            PROJECT_ROOT
            / "src/leaders_db/conversational_evidence/data/questions.json"
        ).read_text(encoding="utf-8")
    )
    chapter = next(item for item in payload["chapters"] if item["id"] == chapter_id)
    return chapter["questions"]


def _searches(path: Path) -> list[dict[str, Any]]:
    searches: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "web_search":
            continue
        if event.get("type") != "item.completed":
            continue
        action = item.get("action", {})
        queries = action.get("queries")
        if not isinstance(queries, list):
            query = action.get("query")
            queries = [query] if isinstance(query, str) and query else []
        searches.append({"query": str(item.get("query", "")), "queries": queries})
    return searches


def _usage(path: Path) -> dict[str, int]:
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        event = json.loads(line)
        if event.get("type") == "turn.completed":
            return event.get("usage", {})
    return {}


def _render_record(record: dict[str, Any]) -> list[str]:
    methodology = ", ".join(record.get("methodology_ids", []))
    lenses = ", ".join(record.get("lenses", []))
    return [
        f"### {record['provisional_id']} — {record['title']}",
        "",
        f"- Publisher: {record['publisher']}",
        f"- Publication date: {record['publication_date']}",
        f"- URL: {record['url']}",
        f"- Source type: `{record['source_type']}`",
        f"- Source confidence: `{record['source_confidence']}` — "
        f"{record['source_confidence_reason']}",
        f"- Evidence classification: `{record['final_evidence_use']}`",
        f"- Period fit: `{record['period_fit']}`",
        f"- Question lenses: {lenses}",
        f"- Raw `methodology_ids`: {methodology}",
        f"- Locator: {record['locator']}",
        f"- Underlying fact key: `{record['underlying_fact_key']}`",
        "",
        f"Claim: {record['claim']}",
        "",
        f"Ruler attribution: {record['ruler_attribution']}",
        "",
        f"Contrary or limiting evidence: {record['contrary_evidence']}",
        "",
    ]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>").strip()


if __name__ == "__main__":
    main()
