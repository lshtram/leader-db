# Detailed Question-Prompt Baseline v1

This is the immutable comparison pointer for the detailed-only chapter-question and
research-prompt design immediately before the layered presentation was introduced.

- Commit: `143a0757d7a4d5ca2e819f243eb02af09d3e229b`
- Date frozen: 2026-07-25
- Restore or inspect any file with:
  `git show 143a0757d7a4d5ca2e819f243eb02af09d3e229b:<path>`

## Baseline file hashes

| File | SHA-256 |
|---|---|
| `docs/methodology/pipeline-agent-questions-and-prompts.md` | `c0418d006c54a759b084223e7ee0ae4321549eeed0fa58732f91051cdc9c18b9` |
| `docs/methodology/ranking-evaluation-criteria.md` | `2fcdeb8a13205829d400096f92922fdafa112315b46ec53db87729fd21da05d8` |
| `docs/methodology/chapter-guides/1b-nuclear-existential-risk.md` | `fea2c2895bb665a6f3d0b0c89d31e0e5ddd373597c797b506d65c563c0286da9` |
| `docs/methodology/chapter-guides/2b-international-peace.md` | `1fb6282231a5373b0fb7da97de2a74dfaeba0d2523f67090b8035a128415fd1c` |
| `docs/methodology/chapter-guides/3b-domestic-safety.md` | `d706abf2988b6f9c959c120eb8803d995cc35e3a3eeed73d07f68095a8e3b701` |
| `docs/methodology/chapter-guides/4b-political-freedom.md` | `a0b55789e62148ab2c1ca10a0c1c693b5841d175cea9dd147bd4d62c16666144` |
| `docs/methodology/chapter-guides/5b-economic-wellbeing.md` | `b399b55244cece4cd1e1ed18be30978f727578e8a29df622b637a43e157d7cae` |
| `docs/methodology/chapter-guides/6b-social-wellbeing.md` | `538fd664eddf7265666bb1e1c18fe1da57924234df9e455cf3eb16e65ef5a0f4` |
| `docs/methodology/chapter-guides/7b-integrity.md` | `36b4cb53befe90b405e5a29a166c1536ee141fa0b80e00a59ea278834e2b843a` |
| `docs/methodology/chapter-guides/8b-effectiveness.md` | `eb635d347e026204af68024ef85e2d0fb4d9815665670470bb8b5e98a73bc8dd` |
| `src/leaders_db/conversational_evidence/data/questions.json` | `de35dcd5d79827b9a877b3c867cb1fe35afbc4e2d95a3e49de0caf47f9618404` |
| `src/leaders_db/research/chapter_research_sequence.py` | `bd0b7e2767d4c189b89ffb73db6fd4116befc03b0fdbab8aca283ed1c04b926a` |
| `.agents/skills/ruler-evidence-researcher/SKILL.md` | `52574fea84d16ffdf757e8c972b9672ae1d49d1552a0fde663a4d14020217364` |

The Git commit contains the complete code, documentation, tests, prompts, question
catalogue, and role instructions needed to reproduce the baseline. Later comparison
runs must record their commit, prompt hashes, model/provider, inputs, outputs, token
usage, and evaluation method rather than relying on a mutable “current” label.
