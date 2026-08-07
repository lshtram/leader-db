"""Measured usage and pricing helpers for ruler HTML reports."""

from __future__ import annotations

import html
import json
from pathlib import Path


def usage_profile(run_dir: Path, dossier_usage_path: Path) -> tuple[dict, ...]:
    """Aggregate completed model-call usage by persisted pipeline phase."""

    phase_names = {
        "reading": "Corpus reading and exact-passage verification",
        "chapter-analysis": "Initial answers",
        "chapter-quality": "Initial independent review",
        "chapter-revisions": "Free-form targeted revisions",
        "chapter-revision-quality": "Reviews of free-form revisions",
        "chapter-coverage-repair": "Requirement-to-evidence repair",
        "chapter-compaction": "Evidence-preserving editorial compaction",
        "chapter-coverage-quality": "Final independent quality gates",
    }
    dossier = json.loads(dossier_usage_path.read_text(encoding="utf-8"))
    rows = [
        usage_row(
            "Evidence discovery and dossier review",
            [item["actual_usage"] for item in dossier["actions"]],
        )
    ]
    for folder, label in phase_names.items():
        usages = []
        for path in (run_dir / folder).rglob("events.jsonl"):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "turn.completed":
                    usages.append(event.get("usage", {}))
        if usages:
            rows.append(usage_row(label, usages))
    return tuple(rows)


def usage_row(label: str, usages: list[dict | None]) -> dict:
    """Aggregate a sequence of completed-call usage objects."""

    completed = [item for item in usages if isinstance(item, dict)]

    def total(key: str) -> int:
        return sum(int(item.get(key, 0) or 0) for item in completed)

    return {
        "phase": label,
        "calls": len(completed),
        "input": total("input_tokens"),
        "cached": total("cached_input_tokens"),
        "output": total("output_tokens"),
        "reasoning": total("reasoning_output_tokens"),
    }


def profile_html(phases: tuple[dict, ...], totals: dict, selection: dict) -> str:
    """Render measured usage using the pricing persisted with this run."""

    pricing = selection["pricing"]
    input_rate = float(pricing["input_usd_per_million"])
    output_rate = float(pricing["output_usd_per_million"])
    payg_equivalent = (
        totals["input"] * input_rate / 1_000_000
        + totals["output"] * output_rate / 1_000_000
    )
    rows = "".join(
        f'<tr><td>{html.escape(str(x["phase"]))}</td><td>{x["calls"]:,}</td>'
        f'<td>{x["input"]:,}</td><td>{x["cached"]:,}</td>'
        f'<td>{x["output"]:,}</td><td>{x["reasoning"]:,}</td></tr>'
        for x in phases
    )
    model_profile = html.escape(selection.get("model_profile", "model not recorded"))
    return (
        '<section id="profile"><h2>Measured model profile</h2>'
        f"<p>Persisted run model profile: {model_profile}. Actual billing is not "
        "exposed; counts below come from completed-call event records. At the persisted "
        f"${input_rate:.2f}/M input and ${output_rate:.2f}/M output standard rates, "
        "without a separate cached-input discount, the conservative PAYG-equivalent is "
        f"${payg_equivalent:,.2f}.</p>"
        "<table><thead><tr><th>Phase and work performed</th><th>Calls</th>"
        "<th>Input</th><th>Cached input</th><th>Output</th>"
        f'<th>Reasoning output</th></tr></thead><tbody>{rows}'
        f'<tr class="total"><td>Total</td><td>{totals["calls"]:,}</td>'
        f'<td>{totals["input"]:,}</td><td>{totals["cached"]:,}</td>'
        f'<td>{totals["output"]:,}</td><td>{totals["reasoning"]:,}</td>'
        "</tr></tbody></table></section>"
    )


__all__ = ["profile_html", "usage_profile", "usage_row"]
