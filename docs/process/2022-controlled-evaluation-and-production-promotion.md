# 2022 Controlled Evaluation and Production Promotion Gates

## Current readiness

The repository is ready to begin the controlled full 20-ruler evaluation defined in
`configs/evaluations/2022-bias-local-v3-controlled.yaml`. It is not ready to promote
the resulting scores to production. Controlled evaluation asks whether the method works
at cohort scale; production promotion additionally requires stable, reviewed, reproducible,
publishable results.

## Gate A — safeguards required before the controlled run

- [x] Compact prompts do not replay the complete local package or raw accumulated notebook.
- [x] Reviewer handoff includes a bounded parent-owned local-data disposition audit.
- [x] Every LLM action exposes prompt size and provider input/cached/output/reasoning tokens.
- [x] Formatter recovery retains the richest valid completed output and cannot prefer fake bias IDs.
- [x] AMLO's greater-than-one-point 2B movement was audited and corrected.
- [x] AMLO's four material-attribution flags were individually dispositioned.
- [x] Cohort, baseline artifacts, model profiles, workflow, batch order, and stop gates are frozen.
- [x] Client scores are prohibited from research and judgment prompts.
- [x] The earlier Putin singleton, Biden/Tshisekedi contrast, five-ruler
  constrained/high-data pilot, and prior full-cohort gate are preserved and hash-bound
  as prerequisites in the controlled configuration.

## Gate B — controlled full-evaluation completion

- [ ] All 20 reviewed/locked ruler identities complete the selected 2022 period.
- [ ] All 20 dossiers validate with 80 coverage rows and 80 local-prior provenance rows.
- [ ] Every dossier carries a cited evidence-environment assessment.
- [ ] All eight common-meter chapter batches complete 20 evaluations or explicit justified nulls.
- [ ] Every judgment carries cited bias reasoning and the two mandatory safeguards.
- [ ] Every evidence, mapping, coverage, local-prior, decisive, contrary, and bias reference resolves.
- [ ] Local evidence survives package → researcher briefing → dossier → chapter projection
  → judge without silent loss, conversion into web citations, or directional ruler attribution.
- [ ] Every `structured_prior_summary` matches the hashed package and no stage falsely
  states that available local evidence was unavailable.
- [ ] Failed and retried calls remain in cumulative usage, runtime, and cost profiles.
- [ ] Four five-ruler batch checkpoints pass before automatic continuation.

## Gate C — methodological and comparative audit

- [ ] Score/order auditor reviews all 160 cells and relative ordering.
- [ ] Every movement greater than one point has an evidence-, attribution-, baseline-, or
  rubric-based explanation and explicit auditor disposition.
- [ ] Median unchanged-evidence rerun drift is at most 0.5.
- [ ] No unchanged score moves more than one point without explicit approval.
- [ ] Open-system complaint visibility and closed-system silence primarily affect confidence
  and ranges, not automatic score direction.
- [ ] Duplicate or syndicated coverage remains one underlying source-claim event.
- [ ] Event location is never treated as aggressor, perpetrator, or ruler responsibility.
- [ ] Military expenditure is not mechanically interpreted as aggression or poor peace performance.
- [ ] Peer comparisons use no post-ruler or post-target information and disclose peer sensitivity.
- [ ] Missing evidence never becomes favorable evidence or a fabricated midpoint.
- [ ] Client values never enter research, evidence review, formatting, judgment, or confidence.

## Gate D — chapter-specific validity

- [ ] 1B has meaningful capability, treaty, safeguards, testing, doctrine, and exposure coverage;
  non-exposure is context rather than automatic positive scoring.
- [ ] 2B separates international conduct from domestic policing, conflict location from
  responsibility, defensive participation from aggression, and peace effort from peace outcome.
- [ ] 3B separates criminal/subnational violence, allegations, state policy, command responsibility,
  remedy, and inherited insecurity.
- [ ] 4B separates inherited democratic baseline from ruler conduct and preserves contestability,
  institutional constraint, media, opposition, surveillance, and trajectory evidence.
- [ ] 5B separates nominal, real, PPP, and constant-price concepts and includes distribution,
  labor, resilience, debt, investment, baseline, lag, and shocks.
- [ ] 6B separates spending, access, coverage, quality, outcomes, inequality, and shared
  implementation authority.
- [ ] 7B never converts national corruption or associate conduct into ruler integrity without
  a personal nexus.
- [ ] 8B freezes a broad ruler program before outcomes, separates inherited capacity and luck,
  and requires attributable implementation for scores above 5.

## Gate E — evidence and source maturity

- [ ] Source-readiness registry accurately distinguishes identified, vetted, raw, adapted,
  normalized, persisted, matched, mapped, routed, and validated states.
- [ ] Every enabled source has valid provenance, license/terms review, metadata, version,
  coverage, and normative attribution text.
- [ ] Units, revisions, proxy years, missingness, uncertainty intervals, and series breaks survive
  into local packages and derived signals.
- [ ] Correlated composites and repeated underlying sources are not counted as independent.
- [ ] Evidence breadth and source-family diversity are at least comparable to the preserved
  lean-v4 baseline, with qualitative inspection rather than count-only acceptance.
- [ ] At least four contrasting complete rulers—Russia, United States, DRC, and Germany—receive
  manual dossier-to-judgment reading.
- [ ] A side-by-side old/new comparison manifest records, for every ruler and chapter,
  local records, web evidence, mappings, scores, confidence, plausible ranges, nulls,
  source-family diversity, and review status.

## Gate F — operational and cost maturity

- [ ] Every run has an immutable manifest with code/config/model/rubric/artifact hashes.
- [ ] Jobs are resumable, lease-fenced, idempotent, and cannot publish stale attempts.
- [ ] Context-size and output-size limits pass for all rulers and chapters.
- [ ] Token, runtime, and equivalent-cost profiles are acceptable at 20-ruler scale.
- [ ] Research-context amplification is understood well enough to set operational budgets;
  hidden billing remains explicitly unknown.
- [ ] Full automated test suite, Ruff, schema validation, deterministic bias tests, and
  metamorphic tests are green. The existing Wikidata cache-fixture failures must be resolved
  or formally shown to be an environment-only test defect before promotion.
- [ ] No debug artifacts, secrets, stale fixtures, orphan outputs, or unreviewed code remain.

## Gate G — release and publication

- [ ] All release-blocking manual-review items are resolved or explicitly excluded.
- [ ] Accepted artifacts are selected by a release manifest; rejected/retried artifacts remain
  recoverable.
- [ ] Old and new 2022 releases remain permanently available side by side.
- [ ] Viewer and exports are rebuilt from the selected immutable artifacts.
- [ ] Every public output carries the exact normative source-attribution block.
- [ ] Methodology, architecture, requirements, source registry, attributions, workplan, and
  release notes match the implemented system.
- [ ] Final human approval is recorded after reviewing score movements, ordering, nulls,
  confidence, evidence quality, bias treatment, runtime, and cost.

Only after Gates B–G pass may the controlled result replace the current main 2022 flow.
