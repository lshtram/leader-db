"""Render the full M3/M3 AMLO document-reader run as a reviewable dossier."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    arm_dir = run_dir / "arm-b-minimax-m3-long-context-reviewed-by-minimax-m3-long-context"
    summary = _read_json(arm_dir / "full-run-summary.json")
    summary["_arm_dir"] = str(arm_dir)
    manifest = _read_json(run_dir / "manifest.json")
    profiles = _usage_profile(run_dir, arm_dir)
    lines = _header(summary, manifest, profiles)
    lines.extend(_manual_review())
    lines.extend(_document_table(summary, manifest))
    lines.extend(_appendices(arm_dir, manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _header(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    profiles: dict[str, dict[str, int]],
) -> list[str]:
    documents = manifest["acquired_documents"]
    audits = [audit for document in summary["documents"] for audit in document["audits"]]
    source_tokens = sum(item["estimated_source_tokens"] for item in documents)
    artifact_times = [
        path.stat().st_mtime
        for path in (
            Path(summary["_arm_dir"]).rglob("reader-events.jsonl") if "_arm_dir" in summary else ()
        )
    ]
    artifact_times.extend(
        path.stat().st_mtime
        for path in (
            Path(summary["_arm_dir"]).rglob("content-audit.json") if "_arm_dir" in summary else ()
        )
    )
    artifact_span = max(artifact_times) - min(artifact_times)
    return [
        "# AMLO 2022 Chapter 5B — full M3/M3 evidence-reader dossier",
        "",
        "This is an evidence dossier, not a score. It preserves the complete output "
        "of a fresh MiniMax M3 reader followed by a separate fresh MiniMax M3 "
        "factual-verification pass for every frozen document chunk.",
        "",
        "## Run profile",
        "",
        f"- Documents: {len(documents)}",
        f"- Extracted source tokens: {source_tokens:,}",
        f"- Chunks: {sum(item['chunk_count'] for item in summary['documents'])}",
        f"- Start: {summary['started_at']}",
        f"- Completion: {summary['completed_at']}",
        f"- Measured elapsed time: {summary['elapsed_seconds']:,.3f} seconds "
        f"({summary['elapsed_seconds'] / 60:.2f} minutes) for the resumed full phase",
        f"- First-reader-artifact to last-audit-artifact span: "
        f"{artifact_span:,.3f} seconds ({artifact_span / 60:.2f} minutes)",
        f"- Claims counted by the content auditor: {sum(item['claim_count'] for item in audits):,}",
        f"- Supported: {sum(item['supported_claim_count'] for item in audits):,}",
        f"- Unsupported or materially misstated: "
        f"{sum(item['unsupported_claim_count'] for item in audits):,}",
        f"- Usable claim locators: {sum(item['usable_locator_count'] for item in audits):,}",
        "",
        "### Exact provider-reported token usage",
        "",
        "| Role | Calls | Input | Cached input | Output | Reasoning output |",
        "|---|---:|---:|---:|---:|---:|",
        *[
            f"| {role} | {usage['calls']:,} | {usage['input_tokens']:,} | "
            f"{usage['cached_input_tokens']:,} | {usage['output_tokens']:,} | "
            f"{usage['reasoning_output_tokens']:,} |"
            for role, usage in profiles.items()
        ],
        "",
        "M3 reader and verifier usage is the proposed low-cost production path. "
        "GPT-5.4-mini produced document-specific reading briefs. GPT-5.6 Sol was "
        "used here only as an experimental content auditor and is not required to "
        "read every production document. The resumed full phase reused the already "
        "completed GOV-003 calibration checkpoint; the artifact span includes that "
        "earlier M3/M3 document and is the better end-to-end timing measure for all "
        "25 chunks.",
        "",
    ]


def _manual_review() -> list[str]:
    rows = [
        (
            "GOV-017",
            "Written-contract share",
            "Incorrect",
            "16,301,660 / 39,775,332 is about 41.0%, not 42.0% (unit 9).",
        ),
        (
            "IMP-001",
            "Local input shortage",
            "Overstated",
            "The detailed passage says “posibles desabastos”; it supports possible, "
            "not unqualified observed, shortages (unit 3).",
        ),
        (
            "LAW-005",
            "Agreement was routine",
            "Unsupported",
            "The extract establishes a 10–16 December 2022 instrument, but not "
            "recurrence or routine status (units 1–2).",
        ),
        (
            "MAC-010",
            "Authorities cited fiscal discipline",
            "Misattributed",
            "Fiscal discipline appears in staff discussion; the cited authorities’ "
            "paragraph does not make that point.",
        ),
        (
            "MAC-010",
            "Excise fall caused by price smoothing",
            "Overstated",
            "The source reports a budget cost, but the cited paragraph does not "
            "explicitly attribute the table-row change to smoothing.",
        ),
        (
            "MAC-010",
            "Figures use identical peer groups",
            "Incorrect",
            "Figures 6, 7, and 11 use differently described comparison groups.",
        ),
        (
            "MAC-010",
            "Phillips-curve samples",
            "Incorrect",
            "The table gives both 2003Q1–2019Q4 and 2003Q1–2020Q4 specifications "
            "for both headline and core inflation (unit 82).",
        ),
        (
            "MAC-015",
            "Bank association runs payment system",
            "Overstated",
            "The source says it sets rules and operational standards, not that it "
            "operates the system (unit 111).",
        ),
        (
            "MAC-015",
            "Digital identity merely announced",
            "Incorrect qualification",
            "The source says government created the identity document in 2020; "
            "future operability qualifies the registry (unit 114).",
        ),
        (
            "BOOK-013",
            "Trump metal tariffs locator",
            "Bad locator",
            "The claim is in block 63, not blocks 58–59.",
        ),
        (
            "BOOK-013",
            "Older-adult pension locator",
            "Bad locator",
            "The MXN 1,500 commitment is in block 62, not block 64.",
        ),
        (
            "PREZ-005",
            "Talos block returned to Pemex",
            "Material misstatement",
            "AMLO said Pemex received operation of a shared reservoir after "
            "consultations; he did not say Talos’s block was returned (unit 36).",
        ),
    ]
    sample_rows = [
        ("GOV-003", "MXN 6.595tn revenue; MXN 422bn above program", "block 4"),
        ("GOV-017", "Contract-status totals and denominators", "unit 9/table"),
        (
            "MAC-010",
            "Moderate sovereign-stress risk and debt-sustainability qualification",
            "p. 60, Annex III Figure 1",
        ),
        ("MAC-015", "0.4%-of-GDP health response", "pp. 25–26"),
        ("LAW-005", "Fuel-specific percentages and pesos/litre", "units 1–2"),
        ("LAW-017", "20 July 2022 USMCA consultation request", "block 3"),
        ("LAW-019", "CRE institutional acts and stated objectives", "source map"),
        ("IMP-005", "MXN 9.5bn described as unresolved, not adjudicated loss", "extract"),
        ("RES-001", "260 federal institutions; 2018–2022 contracts", "blocks 2, 4"),
        ("IMP-001", "Possible local input shortages", "unit 3"),
        ("RES-006", "Definitions and 2023 projection qualifications", "pp. 2, 5"),
        ("RES-005", "Publisher claims separated from observed fiscal facts", "extract"),
        ("RES-019", "More than 1.5m contracts, 2013–2020", "extract"),
        ("BOOK-013", "Guardia Nacional pledge and gradual military withdrawal", "block 63"),
        ("PREZ-005", "Shared-reservoir account and 150k-barrel capacity claim", "unit 36"),
        ("NEWS-010", "MXN 1.282bn AIFA transfers attributed to statements", "block 1"),
    ]
    return [
        "## Manual fact-check",
        "",
        "I reopened every claim that the content auditor flagged as unsupported or "
        "materially misstated and checked it against the frozen underlying extract. "
        "I also reopened at least one representative accepted claim from every "
        "document. This is a targeted manual check, not a second exhaustive audit of "
        "all 870 claims.",
        "",
        "### All twelve flagged claims",
        "",
        "| Source | Claim | Manual disposition | Correction |",
        "|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows],
        "",
        "### Cross-source accepted-claim checks",
        "",
        "| Source | Reopened item | Locator |",
        "|---|---|---|",
        *[f"| {a} | {b} | {c} |" for a, b, c in sample_rows],
        "",
        "The manual check confirms that the twelve automated flags are substantive "
        "and should be excluded or corrected. It did not identify an additional "
        "unsupported claim in the representative cross-source sample. General-"
        "knowledge or external-source validation remains a separate later stage.",
        "",
    ]


def _document_table(summary: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    by_id = {item["requested_source_id"]: item for item in manifest["acquired_documents"]}
    lines = [
        "## Document-level results",
        "",
        "| Source | Type | Source tokens | Chunks | Claims | Supported | Unsupported | "
        "Usable locators | Gate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in summary["documents"]:
        audits = item["audits"]
        source = by_id[item["source_id"]]
        lines.append(
            f"| {item['source_id']} | {source['document_type']} | "
            f"{source['estimated_source_tokens']:,} | {item['chunk_count']} | "
            f"{sum(a['claim_count'] for a in audits)} | "
            f"{sum(a['supported_claim_count'] for a in audits)} | "
            f"{sum(a['unsupported_claim_count'] for a in audits)} | "
            f"{sum(a['usable_locator_count'] for a in audits)} | "
            f"{'pass' if item['content_usable'] else 'review'} |"
        )
    lines.extend(
        [
            "",
            "A `review` gate can reflect unsupported claims, low locator-rate "
            "accounting, or decisive omitted material. It does not mean the whole "
            "document map is unusable; see the chunk audits below.",
            "",
        ]
    )
    return lines


def _appendices(arm_dir: Path, manifest: dict[str, Any]) -> list[str]:
    lines = [
        "## Complete verified M3 source maps",
        "",
        "The following appendices reproduce every post-verification M3 source map. "
        "They intentionally preserve prose organization rather than forcing a strict "
        "claim JSON schema.",
        "",
    ]
    order = [item["requested_source_id"] for item in manifest["acquired_documents"]]
    maps_root = arm_dir / "maps"
    for source_id in order:
        lines.extend([f"### {source_id}", ""])
        for chunk_dir in sorted((maps_root / source_id).glob("chunk-*")):
            lines.extend([f"#### {chunk_dir.name}", ""])
            output = (chunk_dir / "factual-review-output.md").read_text(encoding="utf-8")
            lines.extend([output.rstrip(), "", "##### Content audit", "", "```json"])
            audit = _read_json(chunk_dir / "content-audit.json")
            lines.extend([json.dumps(audit, indent=2, ensure_ascii=False), "```", ""])
    return lines


def _usage_profile(run_dir: Path, arm_dir: Path) -> dict[str, dict[str, int]]:
    groups = {
        "M3 reader": list(arm_dir.rglob("reader-events.jsonl")),
        "M3 verifier": list(arm_dir.rglob("factual-review-events.jsonl")),
        "Sol content auditor": list(arm_dir.rglob("audit-events.jsonl")),
        "GPT-5.4-mini reading briefs": list(
            (run_dir / "frozen/reading-briefs").glob("*.events.jsonl")
        ),
    }
    result: dict[str, dict[str, int]] = {}
    for name, paths in groups.items():
        usage = defaultdict(int)
        for path in paths:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "turn.completed":
                    continue
                usage["calls"] += 1
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "reasoning_output_tokens",
                ):
                    usage[key] += event.get("usage", {}).get(key, 0) or 0
        result[name] = dict(usage)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
