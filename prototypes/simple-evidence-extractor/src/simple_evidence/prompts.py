"""Compact worker prompts for the constrained evidence CLI."""

from __future__ import annotations

_CHAPTERS = """
1B nuclear and existential-risk responsibility; 2B international peace and lawful
security; 3B domestic safety, restraint, and protection; 4B political freedom and
authoritarian conduct; 5B economic wellbeing; 6B social wellbeing; 7B personal
integrity and honesty; 8B effectiveness and competence.
""".strip()


def extractor_prompt(
    source_id: str,
    start: int,
    end: int,
    *,
    pending: tuple[str, ...],
    reminder: bool,
) -> str:
    prefix = (
        "The prior worker did not inspect the assigned range. Do it now.\n\n"
        if reminder
        else ""
    )
    pending_text = (
        "\nUnresolved facts from an interrupted attempt: "
        + ", ".join(pending)
        + ". Show each, correct it if needed, then confirm it.\n"
        if pending
        else ""
    )
    return (
        prefix
        + "You identify materially distinct factual evidence about a political ruler. "
        "Reason naturally; your final prose is ignored. Evidence exists only when you "
        "write and confirm it through ./evidence.\n\n"
        f"Chapters: {_CHAPTERS}\n\n"
        f"Assigned range: {source_id} S{start:06d} S{end:06d}.\n"
        + pending_text
        + f"First run: ./evidence show {source_id} S{start:06d} S{end:06d}\n"
        "For each material fact run:\n"
        "./evidence add SOURCE START [END] --summary \"plain fact\"\n"
        "Never create test, placeholder, or schema-probing facts; the CLI is already "
        "tested and every add is a real registry proposal. Record at most 15 of the "
        "most material, ruler-relevant facts in this range; prefer concrete actions, "
        "mechanisms, quantities, outcomes, constraints, and well-supported contrary "
        "evidence over incidental biographical detail. Read the returned JSON. If the "
        "exact excerpt or summary is wrong, run ./evidence correct FACT_ID with "
        "corrected fields. When it is right, run ./evidence confirm FACT_ID. Keep "
        "promises, findings, forecasts, allegations, recommendations, and implemented "
        "outcomes distinct. Avoid duplicate facts. Do not record titles, signatures, "
        "or publication mechanics as separate facts unless they materially change the "
        "policy evidence or ruler assessment. Use USD instead of a dollar sign in "
        "shell summaries."
    )


def reviewer_prompt(fact_ids: tuple[str, ...], *, reminder: bool) -> str:
    prefix = "Complete every unresolved review now.\n\n" if reminder else ""
    return (
        prefix
        + "You are a fresh factual reviewer. Your prose is ignored. For every fact ID, "
        "run ./evidence show FACT_ID, compare the entire summary with the exact excerpt, "
        "and use ./evidence correct if the span or summary overstates the source. The "
        "stored excerpt alone must name every claimed actor; publisher metadata and "
        "neighboring text do not support attribution. If removing an unsupported "
        "actor, date, or qualification leaves a material supported fact, you MUST "
        "correct the summary and retain that supported fact; reject only when no "
        "material supported claim remains. Never accept unknown fact type, unknown "
        "period, or empty chapter IDs: correct them. Reject placeholders and "
        "administrative-only titles, signatures, or publication mechanics. Then run "
        "./evidence confirm FACT_ID. To reject, run ./evidence correct FACT_ID "
        '--type rejected --summary "reason", then confirm it.\n\nFact IDs:\n'
        + "\n".join(fact_ids)
    )


__all__ = ["extractor_prompt", "reviewer_prompt"]
