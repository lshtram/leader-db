"""Prompt construction for one ruler-period evidence worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_prior_package import summarize_local_priors_for_formatter


def build_dossier_prompt(
    job: dict[str, Any],
    *,
    project_root: Path,
    worker_output_dir: Path,
    local_priors: tuple[dict[str, Any], ...] = (),
    existing_candidate: dict[str, Any] | None = None,
    research_notebook: str | None = None,
) -> str:
    """Build a bounded prompt whose final response must be the dossier JSON."""

    question_ids = tuple(job["input"].get("question_ids", ()))
    if not question_ids:
        raise ValueError("dossier job has no selected question IDs")
    del project_root
    payload = {
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"].get("ruler_year_id"),
        "ruler_name": job["ruler_name"],
        "period_start_year": job["period_start_year"],
        "period_end_year": job["period_end_year"],
        "methodology_ids": question_ids,
        "provider_profile": job["provider_profile"],
        "provider": job["provider"],
        "model": job["model"],
        "worker_output_dir": str(worker_output_dir),
    }
    local_prior_package = summarize_local_priors_for_formatter(local_priors)
    return f"""Format the supplied completed research notebook. This is a no-search,
no-scoring serialization task. The parent has already performed research and supplied
the applicable guide material; do not read researcher or judge directives again.

Job input:
{json.dumps(payload, indent=2, sort_keys=True)}

Deduplicated local structured evidence (client matrix excluded):
{json.dumps(local_prior_package, indent=2, sort_keys=True)}

Permissive evidence-research notebook and handoff:
{research_notebook}

Existing candidate from a prior failed validation:
{json.dumps(existing_candidate, indent=2, sort_keys=True)}

Requirements:
- This is only a formatting and normalization pass.
  Interpret its prose, headings, tables, and JSON fragments flexibly. Preserve the
  researcher's claims, citations, caveats, main points, contrary evidence, and gaps;
  do not perform new research or discard material merely because its format varies.
  Formatting quality does not determine whether evidence existed. Preserve every
  materially distinct final claim, but consolidate repetitive context rows and
  equivalent source treatments when that makes the dossier clearer. If an item cannot
  be normalized safely, retain its caveat or gap instead of silently deleting it.
- The supplied notebook includes a `ruler_research_ledger_manifest_v1` accounting
  index. Use it to prevent evidence collapse. Every manifest entry marked
  `final_evidence` must appear in the dossier with the same canonical fact key and must
  remain mapped to every exact lens in `methodology_ids` and to at least one lens in
  every recorded `chapter_ids` chapter. Do not
  rewrite its key, merge it away, or substitute another source during formatting.
  Source upgrades and disposition changes belong in research before formatting.
  Manifest entries marked `rejected` must not be emitted as evidence.
- Treat the local structured priors above as the required local-first
  step. Do not rerun the local-evidence CLI when those payloads are present.
- Never use the client matrix as evidence.
- Do not search or add facts. The researcher has already completed direct internet
  research and reviewer-directed continuations in the notebook.
- Treat every `error_methodology_ids` entry as a blocking local-input failure, not
  missing evidence that internet material can silently replace. Preserve its compact
  disposition reason and instructions in the resulting gap or warning.
- Set each evidence `url` to either the exact HTTP(S) URL recorded by the researcher or
  `local-prior:<methodology-id>` for a claim taken directly from that question's
  hashed local-prior artifact. No other locator form is valid.
- Set `source_locator` to the precise PDF page/table/figure, HTML section plus
  paragraph, legal section, transcript timestamp, dataset row/field, or exact
  `local-prior:<methodology-id>` locator recorded by the researcher. Use
  `unknown_not_recorded` only for context or discovery material; an item with a missing
  or generic locator must not be emitted as `final_evidence`.
- Set `canonical_fact_key` to a stable value derived from the canonical URL, precise
  source locator, and normalized materially distinct claim. Reuse the same key and
  evidence object across chapter mappings; every emitted evidence object must have a
  unique canonical fact key.
- Preserve one evidence object per defensible source-claim unit identified in the
  notebook. A source-claim unit is one traceable source supporting one materially
  distinct claim. The same URL may therefore appear in multiple evidence objects;
  do not collapse a report's distinct events, findings, decisions, or outcomes into
  one omnibus record merely because they share a source. Deduplicate only genuinely
  duplicate claims, then indicate every chapter lens each retained unit informs.
  Conversely, never recreate the same source-locator-claim fact under separate
  chapter-specific evidence IDs. Preserve one global evidence object and map it to
  every genuinely relevant chapter lens.
  Never collapse a multi-finding report into one omnibus object merely to shorten the
  response. Evidence counts are depth diagnostics, not an alternative to preserving the
  manifest's exact accepted facts and chapter routing.
  Mapping and coverage wording are advisory handoff aids, not score-bearing decisions.
  Mapping is many-to-many. Add every directly relevant lens recorded or clearly
  indicated by the notebook; never select only one preferred lens for an evidence
  item that informs several questions. Coverage is a view over these mappings, not an
  independent reason to hide mapped evidence.
- Before responding, ensure every ID in `coverage` is declared in `evidence` and
  joined through `mappings`.
- Use simple stable evidence IDs when practical. The parent normalizes harmless ID,
  mapping, and coverage inconsistencies and records warnings rather than rejecting
  otherwise useful research.
- Every retained evidence item must appear in at least one `mappings` row so chapter
  judges can see it. Every mapping and coverage `evidence_id` must exactly equal one
  declared evidence ID; never concatenate, abbreviate, or combine evidence IDs.
  Reuse evidence across every genuinely relevant lens rather than leaving it invisible.
  Complete exact lens routing before coverage bookkeeping: every selected chapter must
  receive all evidence objects that the notebook explicitly links to that chapter. It is
  acceptable to use one representative lens mapping only when the notebook records a
  chapter but no exact lens. Never replace or omit an exact researcher-recorded lens
  mapping. Do not emit only one mapping per evidence object when the notebook links it
  to several chapters or lenses.
- Use `no_evidence_found` only when the researcher explicitly records searches for
  that lens and gives a specific reason no usable evidence was found. If the notebook
  lacks an explicit disposition, use `research_blocked`; never manufacture
  `no_evidence_found` because formatting produced no mapping.
- Collect meaningful contrary evidence and explicit gaps. Do not assign scores.
- Populate `evidence_environment` from cited notebook material. Answer all twelve
  environment questions: criticism opportunity; censorship/surveillance/intimidation;
  safe reporting channels; official-statistics reliability; languages/archives searched;
  source concentration; duplicate-event risk; complaint-volume interpretation;
  relevant denominators; inherited conditions/shocks/authority; chapter-specific biases;
  and supporting E-IDs. This assessment is mandatory and may not use uncited generalities.
- Remove any researcher-written score, score range, anchor, ranking recommendation,
  or advice to a judge about scoring/null handling; record it as a normalization
  warning rather than evidence.
- Use publication_date=unknown_not_exposed_by_source only when a reliable date
  cannot be established; never use null.
- Map general repression or protest-policing evidence as context unless the claim
  explains its specific incumbent-entrenchment mechanism.
- State source-type limitations and diversity in run_profile.source_mix_note.
- Populate local_priors with one schema-valid placeholder for every selected
  methodology ID using `methodology_statuses`; the parent replaces them with its
  complete hashed provenance before validation.
- Keep mapping `relevance`, coverage `reason`, and gap prose concise. Preserve every
  required ID and relationship, but do not repeat the underlying claim in bookkeeping
  fields. Output space belongs to distinct evidence, not duplicated prose.
- The final response must be only one JSON object matching the supplied output schema.
- Echo the exact job/run/identity/period/model fields from Job input.
- Record unknown usage fields as unknown_not_exposed_by_tool; never invent usage.
- If Existing candidate is not null, this is a repair-only retry: preserve its valid
  claims and citations, but compare it against the complete inlined notebook and
  restore any defensible source-claim units it collapsed or omitted. Correct
  schema/reference defects, perform the final consistency check, and do not repeat
  research or broad file reading outside the supplied materials. A
  `recovery_evidence_catalog`, when present inside the candidate, contains cited
  evidence objects preserved from other completed formatter attempts. It is not part
  of the output schema: use it only to restore manifest-required canonical keys that
  the selected candidate omitted, assigning collision-free evidence IDs and the exact
  manifest routing, then omit the catalog field from the final output.
"""
__all__ = ["build_dossier_prompt"]
