"""Prepare frozen prompts for reconnaissance language experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from leaders_db.research.dossier_notebook_prompt import (
    build_research_notebook_prompt,
)
from leaders_db.research.local_prior_package import build_local_research_briefing
from leaders_db.research.research_workflow import load_research_workflow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTION_IDS = tuple(
    f"{chapter}B.{question}"
    for chapter in range(1, 9)
    for question in range(1, 11)
)
CASES = {
    "putin": {
        "iso3": "RUS",
        "country_name": "Russian Federation",
        "ruler_name": "Vladimir Putin",
        "period_start_year": 2022,
        "period_end_year": 2022,
        "local_priors_path": PROJECT_ROOT
        / "research/conversational-evidence/bias-smoke/2022-top20-v1/"
        "dossiers/jobs/500/trusted/003-f3502dca-764/local-priors.json",
    },
    "tshisekedi": {
        "iso3": "COD",
        "country_name": "Democratic Republic of the Congo",
        "ruler_name": "Félix Tshisekedi",
        "period_start_year": 2022,
        "period_end_year": 2022,
        "local_priors_path": PROJECT_ROOT
        / "research/conversational-evidence/bias-smoke/2022-top20-v1/"
        "dossiers/jobs/488/trusted/009-52317913-795/local-priors.json",
    },
}


def main() -> None:
    """Write identical-input A and B prompts and a machine-readable manifest."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "recon_prompt_ab_v1",
        "cases": {},
        "controlled_variables": {
            "target_year": 2022,
            "question_ids": list(QUESTION_IDS),
            "model": "gpt-5.6-sol",
            "execution_surface": "codex",
            "filesystem_tools": "disabled",
            "project_rules": "not_loaded",
            "web_research": "enabled",
        },
    }
    for case_id, case in CASES.items():
        case_dir = output_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        local_priors = tuple(
            json.loads(Path(case["local_priors_path"]).read_text(encoding="utf-8"))
        )
        briefing = build_local_research_briefing(local_priors)
        job = {
            **{key: value for key, value in case.items() if key != "local_priors_path"},
            "input": {"question_ids": list(QUESTION_IDS)},
        }
        prompt_a = build_research_notebook_prompt(
            job,
            project_root=PROJECT_ROOT,
            worker_output_dir=case_dir / "a",
            local_priors=local_priors,
            workflow=load_research_workflow(
                PROJECT_ROOT / "configs/research-workflow.yaml"
            ),
        )
        prompt_b = build_natural_prompt(case, briefing)
        prompt_c = build_hybrid_prompt(case, briefing)
        (case_dir / "prompt-a.txt").write_text(prompt_a, encoding="utf-8")
        (case_dir / "prompt-b.txt").write_text(prompt_b, encoding="utf-8")
        (case_dir / "prompt-c.txt").write_text(prompt_c, encoding="utf-8")
        (case_dir / "briefing.json").write_text(
            json.dumps(briefing, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        manifest["cases"][case_id] = {
            "identity": {
                key: value for key, value in case.items() if key != "local_priors_path"
            },
            "local_priors_path": str(case["local_priors_path"].relative_to(PROJECT_ROOT)),
            "local_prior_count": len(local_priors),
            "prompt_a": str((case_dir / "prompt-a.txt").relative_to(output_dir)),
            "prompt_b": str((case_dir / "prompt-b.txt").relative_to(output_dir)),
            "prompt_c": str((case_dir / "prompt-c.txt").relative_to(output_dir)),
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_natural_prompt(case: dict[str, Any], briefing: dict[str, Any]) -> str:
    """Return the natural-language experimental prompt."""

    identity = (
        f'{case["ruler_name"]}, who governed {case["country_name"]}, '
        f'focusing on {case["period_start_year"]}'
    )
    return f"""Research {identity}.

We are preparing an evidence-based assessment of this ruler. Give the researchers who
continue this work a reliable starting point.

Begin by confirming who held power, the ruler's official position and actual influence,
and important limits on that influence. These may include courts, parliament, coalition
partners, the military, regional governments, foreign powers, or other institutions.

Then identify the most important events, decisions, policies, controversies, successes,
and failures from this period. Give attention to war and diplomacy; major military and
security risks; domestic violence, policing, repression, and public safety; elections,
political competition, media freedom, protest, and civil liberties; economic policy and
living standards; health, education, welfare, and essential services; honesty,
corruption, conflicts of interest, nepotism, and accountability; and the ruler's main
goals and how successfully the government carried them out.

Explain how easy or difficult it was to obtain reliable information. Consider
censorship, intimidation, weak statistics, propaganda, political polarization, unequal
international attention, and restrictions affecting journalists, victims, opposition
groups, officials, courts, and investigators.

Search until you have a clear understanding of the ruler, the major events of the
period, and the important questions that need deeper investigation. Preserve every
credible and potentially useful source you find.

For the most important evidence, provide:

- a short factual description and why it matters;
- the source's title, publisher, date, and direct link;
- the page, section, table, paragraph, or short passage that supports the description;
- whether it concerns 2022, an inherited condition, or a later retrospective finding;
- how strongly it can be connected to the ruler or to decisions within the ruler's
  authority;
- credible evidence that complicates or contradicts it; and
- reasons to be cautious about the source.

Other useful sources can be recorded more briefly with their title, publisher, date,
direct link, and a sentence explaining their likely value. Continue while searches
produce materially new information, stronger sources, meaningful contrary evidence, or
important perspectives. Conclude when additional searching mostly repeats what you
already found.

Prefer original documents, official records, courts, international organizations,
independent investigations, academic research, and high-quality reporting. Use a
mixture of source types and perspectives. Open and examine the underlying source before
relying on it.

Organize the result as:

1. a short overview of the ruler and the period;
2. the most important evidence;
3. other useful sources;
4. the information environment and limitations of the available evidence;
5. important questions for deeper research; and
6. sources opened and sources used.

Here is the factual background already available from statistical and institutional
datasets:

{json.dumps(briefing, separators=(",", ":"), sort_keys=True, default=str)}
"""


def build_hybrid_prompt(case: dict[str, Any], briefing: dict[str, Any]) -> str:
    """Return the natural prompt with compact, reusable evidence packaging."""

    identity = (
        f'{case["ruler_name"]}, who governed {case["country_name"]}, '
        f'focusing on {case["period_start_year"]}'
    )
    return f"""Research {identity}.

We are preparing an evidence-based assessment of this ruler. Give the researchers who
continue this work a reliable, well-organized starting point.

Begin by confirming who held power, the ruler's official position and actual influence,
and important limits on that influence. These may include courts, parliament, coalition
partners, the military, regional governments, foreign powers, or other institutions.

Then identify the most important events, decisions, policies, controversies, successes,
and failures from this period. Cover war and diplomacy; major military and security
risks; domestic violence, policing, repression, and public safety; elections, political
competition, media freedom, protest, and civil liberties; economic policy and living
standards; health, education, welfare, and essential services; honesty, corruption,
conflicts of interest, nepotism, and accountability; and the ruler's main goals and how
successfully the government carried them out.

Explain how easy or difficult it was to obtain reliable information. Consider
censorship, intimidation, weak statistics, propaganda, political polarization, unequal
international attention, and restrictions affecting journalists, victims, opposition
groups, officials, courts, and investigators.

Search until additional work mostly repeats facts already found instead of adding
material information, a stronger underlying source, credible contrary evidence, or an
important missing perspective. Preserve every credible source that could be useful to
the researchers who continue this work.

Open and examine the underlying source before treating it as evidence. Prefer original
documents, official records, courts, international organizations, independent
investigations, academic research, and high-quality reporting. Use a mixture of source
types and perspectives.

Write a separate evidence record for each important underlying fact. A report containing
several materially different findings may support several records. Several articles
repeating the same underlying fact belong in one record.

Each evidence record should contain:

- a short name for the underlying fact;
- one precise factual description and why it matters;
- the strongest source's title, publisher, date, and direct link;
- a stable page, section, table, paragraph, or short passage that supports it;
- whether it concerns 2022, an inherited condition, or a later retrospective finding;
- how strongly it can be connected to the ruler or to decisions within the ruler's
  authority;
- credible evidence that complicates or contradicts it;
- reasons to be cautious about the source; and
- other sources that independently support the same fact.

Keep later retrospective evidence in a clearly marked subsection. Keep these three
source categories separate:

1. evidence opened and fully extracted into a record;
2. sources opened and useful mainly for corroboration; and
3. promising leads that still need to be opened or examined.

Organize the result as:

1. a short overview of the ruler and the period;
2. compact evidence records, with one underlying fact per record;
3. the information environment and limitations of the evidence;
4. a concise list of important questions for deeper research;
5. corroborating sources; and
6. promising leads still needing inspection.

Make the overview and final research plan concise. Put factual detail in the evidence
records, state repeated facts once, and make clear which sources were actually opened.

Here is the factual background already available from statistical and institutional
datasets:

{json.dumps(briefing, separators=(",", ":"), sort_keys=True, default=str)}
"""


if __name__ == "__main__":
    main()
