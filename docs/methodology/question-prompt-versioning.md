# Question And Prompt Versioning

Every evidence-research experiment must remain reproducible and reversible. A prompt
presentation may improve readability while reducing research quality, so no version is
promoted solely because it looks clearer.

## Version lineage

| Version | State | Immutable reference | Description |
|---|---|---|---|
| `detailed_questions_v1` | Frozen comparison baseline | Commit `143a0757d7a4d5ca2e819f243eb02af09d3e229b`; hashes in `docs/archive/methodology/question-prompts-detailed-v1/readme.md` | Ten detailed questions per chapter without a short title, simple question, or priority-category layer |
| `layered_lenses_v1` | Active candidate | The commit containing this document and `question_lens_presentation.json` | Short title, simple question, unchanged detailed question, and non-exclusive priority evidence categories |
| `chapter_research_prompt_v1` | Frozen prompt baseline | Tag `question-prompts-layered-v1`; commit `8d40df0` | Prose-led deep chapter research instructions |
| `chapter_research_prompt_v2` | Active prompt candidate | `chapter_research_prompt.json` | Seven-step research workplan with the same local/web and machine-record contracts |

The v2 static template is 4,518 characters and 568 words, compared with 6,711
characters and 859 words in v1. The shorter structure is a design improvement, not yet
proof of better evidence. It requires controlled comparison on preserved cases before
promotion beyond the candidate path.

## Required run record

Every comparison or score-bearing research run records:

- exact Git commit and dirty-worktree status;
- lens-presentation version and hashes of the question catalogue, presentation
  catalogue, chapter guide, executable prompt source, workflow config, and role skill;
- ruler, country, period, selected chapter and lens IDs;
- provider, model, reasoning profile and tool permissions;
- complete emitted prompt, output, tool events and accepted/rejected evidence ledger;
- input, cached-input, output and reasoning tokens where reported;
- source counts, independent source families, mappings, gaps and reviewer findings;
- formatter and judge versions when those stages are included;
- evaluator method, order randomization and blind labels for comparative tests.

## Promotion and rollback

Compare versions on the same frozen ruler/chapter matrix with the same local
orientation and resource index. Evaluate evidence quality, lens coverage, contrary
evidence, attribution, source diversity, duplication, token use and downstream
judgeability. Do not overwrite prior artifacts.

The active progressive quality experiment is defined in
[`deep-chapter-researcher-quality-experiment.md`](deep-chapter-researcher-quality-experiment.md).
It begins with a fresh matched AMLO 2022 Chapter 5B v1/v2 pair, permits at most five
prompt versions on that case before reassessment, confirms a provisional winner with
two additional fresh runs, then expands to contrasting information environments and
the established ten-case matrix. Raw record count, runtime, and token use are
diagnostics rather than promotion targets.

A presentation can be promoted only when it is at least as good as the frozen baseline
on material evidence quality and does not create a systematic blind spot. If it
underperforms, restore the prior implementation from its immutable commit or run the
old and new versions side by side while the cause is investigated.
