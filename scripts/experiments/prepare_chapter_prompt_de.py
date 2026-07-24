"""Prepare the ten-case refined-versus-hybrid chapter prompt gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ROOT = (
    PROJECT_ROOT
    / "research/conversational-evidence/chapter-prompt-ad-2022-v1"
)


def main() -> None:
    """Write hybrid prompts with references to the frozen D baseline."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_manifest = json.loads(
        (BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    manifest: dict[str, Any] = {
        "schema_version": "chapter_prompt_de_v1",
        "execution_model": None,
        "baseline_experiment": str(BASELINE_ROOT.relative_to(PROJECT_ROOT)),
        "baseline_variant": "D",
        "candidate_variant": "E",
        "cases": {},
        "controls": {
            "filesystem_tools": "disabled",
            "project_rules": "not_loaded",
            "web_research": "enabled",
            "fresh_candidate_session": True,
            "same_frozen_case_inputs": True,
            "baseline_reused_from_validated_gate": True,
        },
    }
    for case_id, case in baseline_manifest["cases"].items():
        baseline_dir = BASELINE_ROOT / case_id
        inputs = json.loads(
            (baseline_dir / "inputs.json").read_text(encoding="utf-8")
        )
        guide = (PROJECT_ROOT / inputs["guide_path"]).read_text(encoding="utf-8")
        prompt_e = build_hybrid_chapter_prompt(
            job=inputs["job"],
            chapter_id=str(case["chapter_id"]),
            guide=guide,
            resource_index=tuple(inputs["resource_index"]),
            reconnaissance_summary=json.dumps(
                inputs["reconnaissance_summary"],
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "prompt-e.txt").write_text(prompt_e, encoding="utf-8")
        (case_dir / "inputs.json").write_text(
            json.dumps(inputs, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest["cases"][case_id] = {
            "ruler_name": case["ruler_name"],
            "country_name": case["country_name"],
            "chapter_id": case["chapter_id"],
            "resource_count": len(inputs["resource_index"]),
            "prompt_d_characters": case["prompt_d_characters"],
            "prompt_e_characters": len(prompt_e),
            "baseline_output": str(
                (baseline_dir / "d/output.md").relative_to(PROJECT_ROOT)
            ),
            "baseline_events": str(
                (baseline_dir / "d/events.jsonl").relative_to(PROJECT_ROOT)
            ),
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_hybrid_chapter_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    resource_index: tuple[dict[str, Any], ...],
    reconnaissance_summary: str,
) -> str:
    """Return prompt E, retaining D's breadth with tighter evidence engineering."""

    subject = _chapter_subject(guide, chapter_id)
    research_guide = _researcher_guide(guide)
    identity = (
        f'{subject} under {job["ruler_name"]} in {job["country_name"]} '
        f'during {job["period_start_year"]}-{job["period_end_year"]}'
    )
    return f"""Research {identity}.

Prepare a complete, carefully sourced account for researchers who will assess this part
of the ruler's record. Research the subject without assigning a score.

Use the ten questions below as different angles on the same subject. They identify
material evidence; they are not separate ratings, quotas, or an arithmetic checklist.

{research_guide}

Earlier work found this information about authority, reporting conditions, statistics,
source concentration, and other possible distortions:

{reconnaissance_summary}

These previously found resources may be useful starting points:

{json.dumps(resource_index, separators=(",", ":"), sort_keys=True)}

First establish the ruler's formal and practical authority, inherited baseline,
external shocks and constraints, and the information environment. Then research the
material favorable, adverse, disputed, and exculpatory possibilities raised by all ten
questions.

Open an underlying source before accepting its claim. Prefer contemporaneous primary,
legal, administrative, audit, statistical, and direct reporting sources. Use later
material when it genuinely resolves a target-period fact, and label it as immediate
retrospective or later adjudicative evidence. Seek independent monitoring, scholarship,
reputable reporting, archives, relevant local-language material, and credible contrary
interpretations. Distinguish direct ruler acts, authority-based responsibility, shared
authority, implementation, outcomes, correction, allegations, procedural actions, and
final findings.

Continue while searching produces a materially new fact, a stronger underlying source,
credible contrary evidence, an important missing perspective, or a necessary
correction. Conclude when additional searching mostly repeats what is already known.
There is no source or record quota.

Use one evidence record for one materially distinct underlying fact. Before adding a
record, state what new fact it contributes beyond the existing records. Multiple
records may use one substantial source only when each has a different precise locator
and adds a genuinely different material fact; identify their shared source dependence.
Keep multi-source synthesis in the prose orientation rather than presenting it as one
atomic machine record.

Every contributing source needs its own stable URL and page, paragraph, table, heading,
case number, or similarly precise locator. Record the actual inspection state:

- `opened_underlying_source`: the cited content was opened and inspected;
- `partial_or_landing_page`: only part of the source or its official landing page was
  inspectable;
- `indexed_text_only`: the fact was visible only in indexed search text;
- `reused_opened_source`: a supplied source was reopened and verified;
- `uninspected_lead`: promising but not evidence;
- `blocked_source`: access failed, with the attempt recorded; or
- `rejected_source`: excluded, with the reason.

Only `opened_underlying_source` and `reused_opened_source` count as fully extracted.
Do not upgrade indexed text, a blocked PDF, a search snippet, or a citation in another
report to fully extracted evidence.

For every accepted record include:

- one precise factual claim and why it matters;
- source title, publisher, publication date, direct URL, and precise locator;
- contemporaneous, inherited, immediate-retrospective, or later-adjudicative period
  status;
- direct, authority-based, institutional, shared, limited, or unknown ruler
  attribution;
- allegation, procedural action, final finding, statistic, policy, implementation,
  outcome, or context evidentiary status;
- credible contrary or limiting evidence;
- source limitations and dependencies;
- exact question IDs supported; and
- separately identified independent corroboration.

Scan all ten questions before declaring saturation. An unanswered question gets an
honest source-landscape summary, not invented evidence or an automatic negative
inference.

Return:

1. a concise orientation covering authority, baseline, shocks, information conditions,
   and the central favorable/adverse balance;
2. a compact index with record ID, fact name, new contribution, and question IDs;
3. a ten-question disposition citing records or explaining the remaining gap;
4. separate corroboration, reused, uninspected, rejected, and blocked lists;
5. source-discovery and disposition counts;
6. remaining questions and whether more research is likely to add material information;
7. the machine records below.

Keep the human-readable sections compact. Do not repeat full citations, limitations, or
source descriptions outside the machine record.

For every accepted record, include one physical line outside code fences beginning
`SOURCE_CLAIM_JSON:`. The remainder is a valid JSON object containing `title`,
`publisher`, `publication_date`, `url`, `claim`, `locator`, `provisional_id`,
`canonical_fact_key`, `new_fact_contribution`, `inspection_state`, `evidence_status`,
`period_fit`, `disposition`, `chapter_ids`, `methodology_ids`, `source_type`,
`source_confidence`, `source_confidence_reason`, `final_evidence_use`,
`ruler_attribution`, `contrary_evidence`, `source_dependencies`, and `lenses`.

Use unique IDs beginning `WEB-{chapter_id}-`. Use `{chapter_id}` as the chapter label
and include every exact question ID supported by the record. Use one canonical key for
one underlying fact and preserve a supplied provisional ID when reusing an earlier
record. Validate every JSON line before returning it.
"""


def _chapter_subject(guide: str, chapter_id: str) -> str:
    first_line = next(
        (
            line.removeprefix("# ").strip()
            for line in guide.splitlines()
            if line.startswith("# ")
        ),
        f"Chapter {chapter_id}",
    )
    return first_line.replace(f"Chapter {chapter_id}", "").strip(" —-:")


def _researcher_guide(guide: str) -> str:
    start = guide.find("## Ten Evidence Lenses")
    if start < 0:
        return guide[:6_000].strip()
    rubric_markers = (
        "## Chapter-Level 1–10 Rubric",
        "## Holistic 1-10 Chapter Rubric",
        "## Holistic 1–10 Chapter Rubric",
    )
    ends = [
        index
        for marker in rubric_markers
        if (index := guide.find(marker, start)) >= 0
    ]
    end = min(ends) if ends else len(guide)
    return guide[start:end].strip()


if __name__ == "__main__":
    main()
