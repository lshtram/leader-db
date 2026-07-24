"""Prepare the ten-case current-versus-refined chapter prompt gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from leaders_db.research.chapter_research_sequence import (
    build_chapter_research_prompt,
)
from leaders_db.research.research_workflow import load_research_workflow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOP20_ROOT = (
    PROJECT_ROOT
    / "research/conversational-evidence/bias-smoke/2022-top20-v1/dossiers/jobs"
)
CASES = {
    "xi-1b": {"job_id": 487, "chapter_id": "1B"},
    "putin-2b": {"job_id": 500, "chapter_id": "2B"},
    "scholz-2b": {"job_id": 489, "chapter_id": "2B"},
    "tshisekedi-2b": {"job_id": 488, "chapter_id": "2B"},
    "sisi-3b": {"job_id": 490, "chapter_id": "3B"},
    "hasina-4b": {"job_id": 485, "chapter_id": "4B"},
    "amlo-5b": {"job_id": 496, "chapter_id": "5B"},
    "biden-6b": {"job_id": 503, "chapter_id": "6B"},
    "bolsonaro-7b": {"job_id": 486, "chapter_id": "7B"},
    "nguyen-8b": {"job_id": 504, "chapter_id": "8B"},
}


def main() -> None:
    """Write paired current and refined prompts with frozen inputs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = load_research_workflow(PROJECT_ROOT / "configs/research-workflow.yaml")
    manifest: dict[str, Any] = {
        "schema_version": "chapter_prompt_ad_v1",
        "execution_model": None,
        "cases": {},
        "controls": {
            "filesystem_tools": "disabled",
            "project_rules": "not_loaded",
            "web_research": "enabled",
            "fresh_session": True,
            "same_case_inputs_within_pair": True,
        },
    }
    for case_id, case in CASES.items():
        dossier_path = _latest_dossier(int(case["job_id"]))
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
        chapter_id = str(case["chapter_id"])
        guide_path = next(
            (PROJECT_ROOT / "docs/methodology/chapter-guides").glob(
                f"{chapter_id.lower()}-*.md"
            )
        )
        guide = guide_path.read_text(encoding="utf-8")
        resource_index = _resource_index(dossier, chapter_id)
        reconnaissance_summary = json.dumps(
            dossier["evidence_environment"],
            separators=(",", ":"),
            sort_keys=True,
        )
        job = {
            "ruler_name": dossier["ruler_name"],
            "country_name": dossier["country_name"],
            "period_start_year": dossier["period_start_year"],
            "period_end_year": dossier["period_end_year"],
            "input": {
                "question_ids": [
                    f"{chapter_id}.{question}" for question in range(1, 11)
                ]
            },
        }
        prompt_a = build_chapter_research_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide,
            workflow=workflow,
            resource_index=resource_index,
            reconnaissance_summary=reconnaissance_summary,
        )
        prompt_d = build_refined_chapter_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide,
            resource_index=resource_index,
            reconnaissance_summary=reconnaissance_summary,
        )
        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "prompt-a.txt").write_text(prompt_a, encoding="utf-8")
        (case_dir / "prompt-d.txt").write_text(prompt_d, encoding="utf-8")
        (case_dir / "inputs.json").write_text(
            json.dumps(
                {
                    "job": job,
                    "resource_index": resource_index,
                    "reconnaissance_summary": dossier["evidence_environment"],
                    "guide_path": str(guide_path.relative_to(PROJECT_ROOT)),
                    "source_dossier": str(dossier_path.relative_to(PROJECT_ROOT)),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["cases"][case_id] = {
            "ruler_name": dossier["ruler_name"],
            "country_name": dossier["country_name"],
            "chapter_id": chapter_id,
            "resource_count": len(resource_index),
            "prompt_a_characters": len(prompt_a),
            "prompt_d_characters": len(prompt_d),
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _latest_dossier(job_id: int) -> Path:
    candidates = sorted(
        (TOP20_ROOT / str(job_id) / "attempts").glob("*/dossier.json"),
        key=lambda path: path.parent.name,
    )
    if not candidates:
        raise FileNotFoundError(f"no dossier found for job {job_id}")
    return candidates[-1]


def _resource_index(
    dossier: dict[str, Any], chapter_id: str
) -> tuple[dict[str, Any], ...]:
    evidence_by_id = {
        str(item["evidence_id"]): item for item in dossier.get("evidence", [])
    }
    relevant_ids: list[str] = []
    for mapping in dossier.get("mappings", []):
        if not str(mapping.get("methodology_id", "")).startswith(f"{chapter_id}."):
            continue
        evidence_id = str(mapping.get("evidence_id", ""))
        if evidence_id and evidence_id not in relevant_ids:
            relevant_ids.append(evidence_id)
    resources = []
    for evidence_id in relevant_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        resources.append(
            {
                "provisional_id": evidence_id,
                "url": evidence.get("url"),
                "claim": evidence.get("claim"),
                "locator": evidence.get("source_locator"),
                "disposition": evidence.get("final_evidence_use"),
            }
        )
    return tuple(resources)


def build_refined_chapter_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    resource_index: tuple[dict[str, Any], ...],
    reconnaissance_summary: str,
) -> str:
    """Return the refined natural prompt with A-style evidence engineering."""

    subject = _chapter_subject(guide, chapter_id)
    research_guide = _researcher_guide(guide)
    identity = (
        f'{subject} under {job["ruler_name"]} in {job["country_name"]} '
        f'during {job["period_start_year"]}-{job["period_end_year"]}'
    )
    return f"""Research {identity}.

We are preparing an evidence-based assessment of this part of the ruler's record. Give
the researchers who continue this work a complete, carefully sourced account. Research
the subject without assigning a score.

Use the ten questions below as different angles on the same subject. They help identify
important evidence; they are not separate ratings, search quotas, or an arithmetic
checklist.

{research_guide}

The earlier research found the following information about authority, reporting
conditions, statistics, source concentration, and other possible distortions:

{reconnaissance_summary}

These sources were found earlier and may be useful:

{json.dumps(resource_index, separators=(",", ":"), sort_keys=True)}

Start by forming a working account of:

- what the ruler formally and practically controlled;
- the inherited baseline at the beginning of the period;
- external shocks and constraints;
- the important favorable, adverse, and disputed possibilities raised by all ten
  questions.

Treat the source list as a starting point. Open an underlying source before using it as
evidence, including a source found earlier. Search across primary and legal records,
independent monitoring, scholarship, reputable reporting, archives, relevant
local-language material, and credible favorable, adverse, and contrary interpretations.
Look for direct ruler statements, decisions, implementation, outcomes, correction or
remedy, and evidence that challenges an initially plausible conclusion.

Continue while research is producing a materially new fact, a stronger underlying
source, credible contrary evidence, an important missing perspective, or a necessary
correction. Conclude when additional searching mostly repeats what is already known.
Preserve every credible source that could help later research.

Write one evidence record for one material underlying fact. Split facts when they have
different sources, dates, periods, attribution levels, or evidentiary status. Combine
articles only when they repeat the same underlying fact. Every source contributing to a
record needs its own stable URL and locator. State when apparently independent reports
depend on the same investigation, dataset, wire story, official claim, or event.

Each developed record contains:

- a short name and one precise factual claim;
- why the fact matters to the chapter questions;
- source title, publisher, date, direct URL, and stable locator;
- target-period, inherited, or later-retrospective status;
- direct, authority-based, institutional, shared, limited, or unknown ruler attribution;
- credible contrary or limiting evidence;
- source limitations and dependencies;
- exact question IDs supported; and
- separately identified independent corroboration.

Keep these source states separate:

1. fully extracted evidence;
2. opened corroboration;
3. reused evidence from the supplied list;
4. promising sources still needing inspection;
5. rejected sources, with the reason;
6. access-blocked sources, with what was attempted.

Scan all ten questions before declaring the research saturated. An unanswered question
gets an honest source-landscape summary, not invented evidence or an automatic negative
inference.

Return:

1. a concise authority, baseline, shock, and information-environment orientation;
2. a compact evidence index listing each record ID, fact name, and why it matters;
3. a disposition for all ten questions, citing record IDs or explaining the remaining
   gap;
4. separate corroboration, reused-source, uninspected-lead, rejected, and blocked lists;
5. counts of sources discovered, opened, accepted, reused, rejected, and blocked;
6. remaining questions and whether more research is likely to add material information;
7. the machine records described below.

The compact index should not repeat full source descriptions. Put the complete evidence
record only in its machine line.

For every fully developed record, include one physical line outside code fences
beginning `SOURCE_CLAIM_JSON:`. The remainder is a JSON object containing `title`,
`publisher`, `publication_date`, `url`, `claim`, `locator`, `provisional_id`,
`canonical_fact_key`, `disposition`, `chapter_ids`, `methodology_ids`, `source_type`,
`source_confidence`, `source_confidence_reason`, `final_evidence_use`, `period_fit`,
`ruler_attribution`, `contrary_evidence`, and `lenses`.

Use unique IDs beginning `WEB-{chapter_id}-`. Use `{chapter_id}` as the chapter label
and include every exact question ID supported by the record. Use one canonical key for
one underlying fact and preserve the supplied provisional ID when reusing an earlier
record. This append-only payload lets the next researchers recover and deduplicate the
evidence.
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
