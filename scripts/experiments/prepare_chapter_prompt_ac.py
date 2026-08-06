"""Prepare controlled current-versus-natural deep chapter prompts."""

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
    "putin-2b": {"job_id": 500, "chapter_id": "2B"},
    "tshisekedi-3b": {"job_id": 488, "chapter_id": "3B"},
    "biden-6b": {"job_id": 503, "chapter_id": "6B"},
}


def main() -> None:
    """Write A/C prompts with identical case-specific inputs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = load_research_workflow(PROJECT_ROOT / "configs/research-workflow.yaml")
    manifest: dict[str, Any] = {
        "schema_version": "chapter_prompt_ac_v1",
        "model": "gpt-5.6-sol",
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
        prompt_c = build_natural_chapter_prompt(
            job=job,
            chapter_id=chapter_id,
            guide=guide,
            resource_index=resource_index,
            reconnaissance_summary=reconnaissance_summary,
        )
        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "prompt-a.txt").write_text(prompt_a, encoding="utf-8")
        (case_dir / "prompt-c.txt").write_text(prompt_c, encoding="utf-8")
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
            "prompt_c_characters": len(prompt_c),
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
    for evidence_id in relevant_ids[:12]:
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


def build_natural_chapter_prompt(
    *,
    job: dict[str, Any],
    chapter_id: str,
    guide: str,
    resource_index: tuple[dict[str, Any], ...],
    reconnaissance_summary: str,
) -> str:
    """Return a self-contained, saturation-based chapter research prompt."""

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
important evidence; they are not separate ratings or evidence quotas.

{research_guide}

The earlier research found the following information about authority, reporting
conditions, statistics, source concentration, and other possible distortions:

{reconnaissance_summary}

These sources were found earlier and may be useful:

{json.dumps(resource_index, indent=2, sort_keys=True)}

Treat that list as a starting point. Open an underlying source before using it as
evidence, including a source found earlier. Search broadly for materially important
events, decisions, implementation, outcomes, favorable evidence, adverse evidence,
contrary interpretations, inherited conditions, external shocks, and limits on the
ruler's authority. Use primary and legal records, independent monitoring, scholarship,
reputable reporting, archives, and relevant local-language sources where available.

Continue while research is producing a materially new fact, a stronger underlying
source, credible contrary evidence, an important missing perspective, or a necessary
correction. Conclude when additional searching mostly repeats what is already known.
Preserve every credible source that could help later research.

Write one evidence record for each important underlying fact. Several reports repeating
one fact belong in the same record. One report may support several records when it
contains materially different findings.

Each developed record should contain:

- a short name for the underlying fact;
- one precise factual description and why it matters to the questions;
- the strongest source's title, publisher, date, direct link, and stable locator;
- whether it concerns the requested period, an inherited condition, or a later
  retrospective finding;
- how strongly it can be connected to the ruler or decisions within the ruler's
  authority;
- credible contrary or limiting evidence;
- reasons for caution about the source;
- the question IDs it helps answer; and
- other independent sources supporting the same fact.

Keep fully extracted evidence, opened corroboration, uninspected leads, and rejected
sources in separate sections. State why a rejected source was unsuitable. Keep later
retrospective evidence in a clearly marked subsection. Finish with a concise account of
the remaining unanswered questions and whether more research is likely to add material
information.

At the end, repeat each fully developed evidence record on one physical line beginning
`SOURCE_CLAIM_JSON:`. The remainder is a JSON object containing `title`, `publisher`,
`publication_date`, `url`, `claim`, `locator`, `provisional_id`,
`canonical_fact_key`, `disposition`, `chapter_ids`, `methodology_ids`, `source_type`,
`source_confidence`, `source_confidence_reason`, `final_evidence_use`, `period_fit`,
`ruler_attribution`, `contrary_evidence`, and `lenses`.

Use unique IDs beginning `WEB-{chapter_id}-`. Use `{chapter_id}` as the chapter label
and include the exact question IDs supported by each record. This appendix lets the
next researchers recover the evidence without changing the readable account.
"""


def _chapter_subject(guide: str, chapter_id: str) -> str:
    first_line = next(
        (line.removeprefix("# ").strip() for line in guide.splitlines() if line.startswith("# ")),
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
