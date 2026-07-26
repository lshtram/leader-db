# Deep Chapter Researcher Quality Experiment

Status: frozen protocol; AMLO 2022 5B matched v1/v2 execution pending

The experiment tests whether `chapter_research_prompt_v2` improves deep chapter
research quality over frozen `chapter_research_prompt_v1`. It does not evaluate ruler
quality and must not receive client scores or judge scores.

## Success criterion

Record count is diagnostic and is never capped or targeted. A candidate advances only
when it has no material regression in source validity, locator precision, attribution,
atomicity, duplication control, or contrary-evidence treatment; matches or improves
blind overall quality; and adds defensible facts, deeper lens coverage, or materially
fewer unresolved gaps without padding or downstream repair.

Evaluate:

- unique material underlying facts and independent source families;
- depth by lens and importance of remaining gaps;
- source authority, independence, method, proximity, and temporal fit;
- underlying-source opening and page, section, paragraph, table, or record locators;
- direct conduct, formal responsibility, shared authority, and contextual attribution;
- favorable, adverse, disputed, contrary, and exculpatory evidence;
- contemporaneous and later-retrospective evidence;
- atomic claims, dependency clusters, and duplication;
- legislation, resources, personnel, implementation, rhetoric, and outcomes where
  relevant; and
- machine validity plus reviewer and formatter usability.

## Frozen AMLO gate

The first gate is Andrés Manuel López Obrador, Mexico, 2022, Chapter 5B. Preparation
freezes by SHA-256:

- the v1 and v2 prompt configurations and emitted prompts;
- the ruler identity, period, reconnaissance summary, resource index, selected lens
  IDs, `questions.json`, layered lens presentation, 5B guide, workflow configuration,
  researcher role skill, evaluator rubric, model, reasoning profile, and permissions;
- the repository commit and dirty-worktree digest.

The production-target researcher model is `gpt-5.4-mini`, using its configured default
reasoning profile unless a separately frozen experiment explicitly tests reasoning
effort. Prompt-quality conclusions require matched `gpt-5.4-mini` runs. Runs produced
with a larger model may diagnose workflow behavior but cannot promote or reject a
researcher prompt intended for the affordable production profile.

Run each prompt in a fresh ephemeral session with identical case inputs, web access,
no repository or filesystem access, no project rules, no plugins, no subagents, and no
cross-run memory. Preserve the complete prompt, output, JSONL event stream, searches,
opened URLs, terminal usage, stderr, and parsed source-claim records. Use historical
A/D artifacts only as secondary context after the fresh pair has been evaluated.

Audit every accepted or context machine record for schema validity, source support,
locator quality, period fit, attribution, source state, atomicity, dependency, and
duplication. Run two no-search blind evaluations: one presents v1 as X and v2 as Y;
the other reverses the order. Preserve both evaluator prompts, outputs, events, usage,
and the concealed label map.

## Optimization and expansion

Compare one prompt feature at a time against the current winner using a fresh matched
pair. Test no more than five prompt versions on AMLO before reassessing the design.
Keep the ten 5B lenses frozen initially. Change a lens only after repeated runs expose
the same missing or confusing dimension, and test that change independently from
prompt wording. Confirm the winner with two additional fresh runs.

Then compare the winner with v1 on:

| Case | Stress tested |
|---|---|
| Hasina 2022 4B | closed information environment and local-language evidence |
| Bolsonaro 2022 7B | personal nexus, allegations/findings, and duplication |
| Biden 2022 6B | abundant open-system administrative evidence |

Pass candidate outputs through the existing no-search reviewer and formatter. Measure
inferred mappings, dropped records, normalization, and repair work. After that gate,
repeat the established ten-case all-chapter matrix, including the three contrasting 2B
rulers, with matched fresh runs and order-reversed blind evaluation. Wider-cohort
research remains blocked until performance is consistent across chapters and evidence
environments.

## Long-document extension

After the prompt-only AMLO result is stable, test an optional low-cost reader for
lawfully accessible books, reports, audits, judgments, and datasets. Begin with an
access audit that distinguishes machine-readable full text from metadata, paywalls,
login or bot challenges, robots denial, and transient failure; never bypass an access
restriction. Preserve page or section boundaries and emit a compact, document-type-aware
source map of claims, locators, candidate lenses, limitations, source incentives, and
unresolved sections. Source maps are leads only: the main researcher must validate
consequential claims against the underlying document.

“Compact” does not mean an abstract, back-cover paragraph, table of contents, or
fixed-ratio condensation. The reader must preserve enough concrete episodes, actors,
actions, dates or periods, mechanisms, outcomes, material quantities, competing
accounts, and locators for a downstream judge to reason without routinely reopening
the original. A synthesis that merely states themes or conclusions fails even when
those conclusions are accurate. Discover the compression frontier empirically:
construct a complete question-aware evidence paper first, remove only demonstrated
redundancy in later attempts, and use a closed-book judge-utility comparison plus
claim/locator audit before promotion.

The first reader ladder is MiniMax M2.7 followed by GPT-5.6 Luna when M2.7 has a
material content failure. Invalid JSON, Markdown output, or another harmless
serialization defect does not fail a reader. A separate high-quality normalizer may
repair structure from the reader summary and supplied original extract, but may not
invent or strengthen substantive claims; evaluation audits content after normalization.
Both arms use the same high-quality dossier compiler so the test isolates compression
fidelity.

Compare the winning prompt alone against the same prompt plus source maps. Measure
compression, claim recall, locator accuracy, new defensible facts, repeated opening,
hallucination/error rate, normalization repair, access loss, and per-phase token cost.
Promote the reader only if it adds depth without weakening traceability. Official and
state-enterprise sources must be labelled by institutional role and incentives; a
decisive official claim requires independent corroboration or an explicit unresolved
verification warning.

## Artifact layout

Use `research/conversational-evidence/chapter-prompt-v1-v2-amlo-5b-2022-v1/`.
`manifest.json` is the immutable run contract and `checksums.sha256` covers every
frozen input. Each researcher and evaluator gets its own subdirectory containing
prompt, output, events, stderr, usage, and parsed records. Never overwrite a completed
run; start the next numbered experiment directory instead.
