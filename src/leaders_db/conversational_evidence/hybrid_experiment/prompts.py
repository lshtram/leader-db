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
    claim_example = json.dumps(
        {
            "title": "...",
            "publisher": "...",
            "publication_date": "YYYY-MM-DD or best available",
            "url": "https://direct-source.example/...",
            "claim": "one precise material claim",
            "locator": "page, section, paragraph, table, or quoted phrase",
            "source_type": "primary/legal/IGO/NGO/scholarship/media/official/other",
            "source_confidence": "very_low|low|medium_low|medium|medium_high|high",
            "source_confidence_reason": "...",
            "final_evidence_use": "final_evidence|context|discovery_only",
            "period_fit": "...",
            "ruler_attribution": "...",
            "contrary_evidence": ["..."],
            "lenses": [f"{chapter_id}.1"],
        },
        separators=(",", ":"),
    )
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
Do not score.

Use these exact machine-readable lines in the relevant prose sections. Put each JSON
object on one physical line without a code fence.

For each reused item:
REUSE_JSON: {{"evidence_ids":["E0001"],"lenses":["{chapter_id}.1"]}}

For every newly accepted source-claim unit:
SOURCE_CLAIM_JSON: {claim_example}

One unit is one source plus one materially distinct claim and locator. Do not create
multiple units merely by paraphrasing the same passage. Every accepted new item must
have exactly one SOURCE_CLAIM_JSON line; narrative without that line is not accepted."""


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
    schema = """{
  "overall_decision":"pass|targeted_follow_up|manual_review",
  "chapters":[{
    "chapter_id":"1B",
    "decision":"pass|targeted_follow_up|credible_gap|manual_review",
    "remove_or_contextualize":[{"evidence_id":"E0001","reason":"..."}],
    "material_gaps":[{"gap":"...","lenses":["1B.1"],
      "best_source_or_query_direction":"...","why_it_matters":"..."}],
    "reason":"..."
  }]
}"""
    return f"""{prefix}Review the complete evidence package for {ruler}, {year}.
Do not browse, add evidence, rewrite claims, or score.

Return JSON only, using this exact shape and object types. Include Chapters 1B-8B in
order. `remove_or_contextualize` must contain objects with one exact evidence_id and
one reason; never put prose strings in that array. Use [] when there are none.
{schema}

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

Request follow-up only when one focused turn is likely to help. Return only the JSON
object in the exact shape above."""


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
directions or blockers. Store one source once and keep the answer concise.

Every newly accepted unit must also appear on one physical line, without a code fence,
using the exact SOURCE_CLAIM_JSON object required in the chapter prompts. Use exact
1B-8B lens IDs. Narrative without a valid SOURCE_CLAIM_JSON line is not accepted."""


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


def saturation_chapter(
    ruler: str,
    country: str,
    year: int,
    chapter_id: str,
    guide: str,
    priors: object,
    existing_index: str,
    *,
    wave: int,
    candidate_target: int,
    opened_target: int,
    accepted_min: int,
    accepted_max: int,
    domain_min: int,
) -> str:
    """Build one generic, measurable discovery wave for a chapter pilot."""

    claim_example = json.dumps(
        {
            "title": "...",
            "publisher": "...",
            "publication_date": "YYYY-MM-DD or best available",
            "url": "https://direct-source.example/...",
            "claim": "one precise material claim",
            "locator": "page, section, paragraph, table, or quoted phrase",
            "source_type": "primary/legal/IGO/NGO/scholarship/media/official/other",
            "source_confidence": "very_low|low|medium_low|medium|medium_high|high",
            "source_confidence_reason": "...",
            "final_evidence_use": "final_evidence|context|discovery_only",
            "period_fit": "...",
            "ruler_attribution": "...",
            "contrary_evidence": ["..."],
            "lenses": [f"{chapter_id}.1"],
        },
        separators=(",", ":"),
    )
    return f"""Research Chapter {chapter_id} for {ruler}, ruler of {country}, in
{year}. This is discovery wave {wave}. Do not score.

CHAPTER GUIDE
{guide}

LOCAL FACTS
{json.dumps(priors, ensure_ascii=False)}

ALREADY ACCEPTED EVIDENCE
{existing_index}

Search the chapter as a whole. In this wave, discover about {candidate_target}
plausible documents and open at least {opened_target} promising documents when they
are accessible. The overall chapter target is {accepted_min}-{accepted_max} genuinely
useful distinct URLs from at least {domain_min} domains. These are discovery targets,
not quotas: never retain weak, irrelevant, duplicate, or inaccessible material merely
to reach a number.

At least one third of the useful chapter evidence should come from independent sources
rather than the ruler's government or its agencies, when credible independent evidence
exists. Do not let many government implementation pages substitute for independent
outcome, criticism, distribution, or attribution evidence.

Use several query families: the ruler and major {year} events; each institution or
policy in the guide; primary/legal records; independent monitors and data; scholarship;
reputable reporting; archives; and useful local-language terms. Search favorable,
adverse, and contrary interpretations. Follow citations from strong documents. Open
the source itself before accepting it; search-result snippets are not evidence.

Remove duplicates before reporting. Treat syndicated copies, mirrors, press rewrites,
and several stories repeating the same event as one evidence family. Prefer the most
authoritative and information-rich member. Separate ruler conduct from inherited
conditions and general country context. Map only claims that the source actually
supports.

Return: (1) accepted new evidence; (2) a search ledger with counts for candidates
found, documents opened, duplicates, irrelevant/out-of-period items, inaccessible
items, and accepted distinct URLs; (3) material gaps and the next best query/source
directions. Do not repeat already accepted evidence and do not score.

When already accepted evidence genuinely supports this chapter, map it without
repeating the source. Emit one physical line with this exact shape:
REUSE_JSON: {{"evidence_ids":["E0001"],"lenses":["{chapter_id}.1"]}}

For every accepted source-claim unit, emit this exact prefix and one JSON object on one
physical line, without a code fence:
SOURCE_CLAIM_JSON: {claim_example}

One unit is one source plus one materially distinct claim and locator. Multiple claims
may share a URL only when they rely on different passages and add distinct evidence.
Narrative without a valid SOURCE_CLAIM_JSON line is not accepted."""


def saturation_curation(
    ruler: str,
    year: int,
    chapter_id: str,
    evidence: object,
) -> str:
    evidence_ids = [str(record["evidence_id"]) for record in evidence]
    return f"""Curate the collected Chapter {chapter_id} evidence for {ruler}, {year}.
Do not browse, add facts, rewrite claims, or score.

Return JSON only:
{{"chapter_id":"{chapter_id}","records":[{{"evidence_id":"E0001",
"disposition":"retain|context|drop","source_family":"concise institutional or wire
family","duplicate_of":null,"reason":"..."}}],"summary":{{"retained":0,
"context":0,"dropped":0,"remaining_concerns":["..."]}}}}

Include every supplied evidence ID exactly once. Retain the strongest, most direct,
information-rich evidence. Use context only for a genuinely useful limitation,
interpretation, or secondary corroboration. Drop:
- mirrors, syndications, or rewrites of the same underlying wire story;
- several reports repeating the same event or mechanism without a material new fact;
- incident subdivisions when a strong synthesis already establishes the pattern;
- weak, indirect, out-of-period, or poorly attributed claims;
- official self-description when it merely repeats another official source.

Prefer synthesis plus at most two illustrative incidents per mechanism. Treat a wire
service and all republishers as one source family. Treat agencies of one government as
distinct publishers but one institutional family for independence analysis. Preserve
meaningful favorable, adverse, and contrary evidence. A normal high-quality result is
about 20-35 retained or contextual URLs across at least 10 useful source families, but
quality overrides the count. No source family should exceed 25 percent of the retained
or contextual records when credible alternatives or a synthesis exist. Set duplicate_of
to the retained evidence ID for direct duplicates, otherwise null. Make the numeric
summary match the records.

Before returning, check mechanically that:
- `records` contains exactly {len(evidence_ids)} objects;
- its evidence IDs are exactly the supplied IDs below, with no omission or duplicate;
- every `duplicate_of` is either null or an ID retained in this same result;
- every source family is an institutional or underlying wire family, not a page title;
- the three summary counts equal the dispositions.

SUPPLIED EVIDENCE IDS
{json.dumps(evidence_ids)}

EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}"""


def saturation_top_up(
    ruler: str,
    year: int,
    chapter_id: str,
    guide: str,
    index: str,
    curation: object,
    *,
    wave: int,
) -> str:
    claim_example = json.dumps(
        {
            "title": "...",
            "publisher": "...",
            "publication_date": "YYYY-MM-DD or best available",
            "url": "https://direct-source.example/...",
            "claim": "one precise material claim",
            "locator": "page, section, paragraph, table, or quoted phrase",
            "source_type": "primary/legal/IGO/NGO/scholarship/media/official/other",
            "source_confidence": "very_low|low|medium_low|medium|medium_high|high",
            "source_confidence_reason": "...",
            "final_evidence_use": "final_evidence|context|discovery_only",
            "period_fit": "...",
            "ruler_attribution": "...",
            "contrary_evidence": ["..."],
            "lenses": [f"{chapter_id}.1"],
        },
        separators=(",", ":"),
    )
    return f"""Run targeted saturation wave {wave} for Chapter {chapter_id} on
{ruler}, {year}, in the same ruler research thread. Do not score.

CHAPTER GUIDE
{guide}

CURRENT GLOBAL EVIDENCE INDEX
{index}

CURATION RESULTS AND REMAINING CONCERNS
{json.dumps(curation, ensure_ascii=False)}

The prior pass was curated below the required breadth, independence, or coverage. Find
materially new evidence; do not replace dropped duplicates with more versions of the
same story. Search specifically for missing mechanisms, lenses, contrary findings,
direct ruler attribution, primary or legal records, synthesis sources, scholarship,
and independent or local-language families absent from the retained set.

Discover roughly 30-45 new candidates and open at least 15-20 promising documents.
Normally retain only 6-12 genuinely additive source-claim units. Prefer a new mechanism
or source family over another incident proving an established pattern. Open the source
itself; snippets are not evidence. Record candidate, opened, duplicate, irrelevant,
inaccessible, and accepted counts. Explain any credible scarcity or access blocker.

For every accepted unit emit exactly one physical line, without a code fence:
SOURCE_CLAIM_JSON: {claim_example}

Map only exact {chapter_id} lenses. Narrative without a valid SOURCE_CLAIM_JSON line
is not accepted."""


def repair_chapter_contract(ruler: str, year: int, chapter_id: str, error: str) -> str:
    """Request a bounded serialization repair in the persistent research thread."""

    return f"""Repair your immediately preceding Chapter {chapter_id} answer for
{ruler}, {year}. Do not browse, search, or add facts. The parent rejected it with:
{error}

Use only sources and claims you already opened in that answer. Return a short corrected
answer containing the required `SOURCE_CLAIM_JSON:` and/or `REUSE_JSON:` physical
lines with exact {chapter_id} lens IDs. Include every genuinely accepted source-claim
unit once, but omit the long narrative and search diary. Do not score."""


__all__ = [
    "chapter",
    "follow_up",
    "formatter",
    "reconnaissance",
    "repair_chapter_contract",
    "review",
    "saturation_chapter",
    "saturation_curation",
    "saturation_top_up",
]
