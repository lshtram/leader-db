"""Short prompt builders for the v2 controlled flow."""

from __future__ import annotations

import json


def reconnaissance(ruler: str, country: str, year: int, priors: object) -> str:
    return f"""Research {ruler}, ruler of {country}, during {year}. Do not score.

Start with the local facts below. They exclude the client matrix, which must not be used
as evidence. Do not search again for facts already supplied locally.

LOCAL FACTS
{json.dumps(priors, ensure_ascii=False)}

Confirm the ruler's office, authority, and constraints; identify major events and
inherited conditions; and identify strong primary, independent, local-language,
favorable, and critical source families for Chapters 1B-8B. Keep only the most useful
cross-chapter sources, normally no more than 12. For each retained source give title,
publisher, date, direct URL, precise fact, period fit, ruler attribution, limitations,
and contrary points. Finish with a compact event map and chapter source plan. Do not
score or create 80 separate lens answers."""


def chapter(
    ruler: str,
    year: int,
    chapter_id: str,
    guide: str,
    priors: object,
    existing_index: str,
) -> str:
    return f"""Now research Chapter {chapter_id} for {ruler} during {year}. Continue in
the same thread and do not score.

CHAPTER GUIDE
{guide}

RELEVANT LOCAL FACTS
{json.dumps(priors, ensure_ascii=False)}

EXISTING REUSABLE EVIDENCE
{existing_index}

Research the chapter as a whole. Reuse existing evidence when it genuinely applies.
Search broadly enough to consider roughly 25-40 distinct documents. Open promising
documents and retain only the best non-duplicative evidence, normally 10-18 distinct
URLs. Prefer primary material plus strong independent monitoring, scholarship,
reputable reporting, and useful local-language evidence. Include meaningful favorable
or contrary evidence. Separate ruler conduct from inherited or country context and
explain attribution. Do not pad weak lenses or repeat one event through many publishers.

Return these sections: Reused evidence (IDs and exact lenses); New evidence (for each:
title, publisher, date, direct URL, precise claim and locator or short excerpt, source
type and credibility, temporal fit, ruler attribution and limits, contrary points, and
exact {chapter_id} lenses); Search and rejection summary (documents considered and
duplicate/irrelevant/weak/blocked/out-of-period removals); Remaining gaps (specific,
material, and whether more search would help). Do not repeat reused evidence in full.
Do not score."""


def review(
    ruler: str,
    year: int,
    guides: str,
    warnings: object,
    package: object,
    *, final: bool = False,
) -> str:
    prefix = (
        "This is the final review after the single allowed follow-up. Do not request "
        "more research.\n\n"
        if final
        else ""
    )
    return f"""{prefix}Review the complete evidence package for {ruler}, {year}.
Do not browse, add evidence, rewrite claims, or score.

For every chapter decide whether the package can fairly present conduct, outcomes,
contrary evidence, attribution, favorable and adverse interpretations, and uncertainty.
Flag cross-chapter contamination, duplicated events or publisher families, country
context presented as ruler conduct, unsupported allegations, wrong-period evidence,
weak discriminating lenses, and personal claims without personal connection.

GUIDES
{guides}

PARENT QUALITY SUMMARY
{json.dumps(warnings, ensure_ascii=False)}

EVIDENCE PACKAGE
{json.dumps(package, ensure_ascii=False)}

Return JSON only with overall_decision (pass, targeted_follow_up, or manual_review) and
eight chapters. Each chapter needs chapter_id, decision, remove_or_contextualize,
material_gaps, and reason. A material gap needs gap, lenses, best_source_or_query_direction,
and why_it_matters. Request follow-up only when one focused turn is likely to help."""


def follow_up(ruler: str, year: int, index: str, gaps: object) -> str:
    return f"""Address only the material evidence gaps below for {ruler}, {year} in the
same research thread. This is the only follow-up round. Do not score.

CURRENT EVIDENCE INDEX
{index}

REVIEWER GAPS
{json.dumps(gaps, ensure_ascii=False)}

For each gap say resolved, partly resolved, or not recoverable. For every new retained
source give title, publisher, date, direct URL, precise claim and locator, temporal fit,
attribution and limits, contrary points, and exact chapter lenses. Briefly record failed
directions or blockers. Store one source once and keep the answer concise."""


def formatter(ruler: str, year: int, package: object) -> str:
    return f"""Convert this reviewed research package for {ruler}, {year} into concise
JSON. Do not browse, add facts, infer mappings, or score. Preserve URLs, evidence IDs,
chapter and lens mappings, temporal and attribution limits, contrary points, review
decisions, and explicit gaps.

Return JSON only with: schema_version='hybrid_experiment_dossier_v1', ruler, year,
evidence (the supplied evidence index without invented fields), chapter_notes (one
object per chapter with chapter_id and note), review, and limitations.

PACKAGE
{json.dumps(package, ensure_ascii=False)}"""


__all__ = ["chapter", "follow_up", "formatter", "reconnaissance", "review"]
